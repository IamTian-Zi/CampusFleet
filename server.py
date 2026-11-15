"""CampusFleet HTTP API, static obstacle inflation and legacy single-agent A*."""
import heapq
import ipaddress
import json
import math
import mimetypes
import os
import socket
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from planner import neighbours, road_directions, solve, collides
from pedestrians import generate as generate_pedestrians
from indoor import plan as plan_indoor
from terrain import TerrainGraph
import storage

ROOT = Path(__file__).resolve().parent
MAP = json.loads((ROOT / 'campus_map.json').read_text(encoding='utf-8'))
BLOCKED = {'building', 'stairs', 'water', 'green', 'obstacle'}
NATIVE_DIR = ROOT / 'cpp' / 'python'
if str(NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(NATIVE_DIR))
try:
    from campusfleet_native import (Agent as CppAgent, Bridge as CppBridge,
                                    Direction as CppDirection, GridMap as CppGridMap,
                                    Method as CppMethod, Node as CppNode, Options as CppOptions,
                                    Point as CppPoint, DStarLite as CppDStarLite,
                                    find_static_path as cpp_find_static_path,
                                    inflate_obstacles as cpp_inflate_obstacles, solve as cpp_solve)
    CPP_IMPORT_ERROR = None
except (ImportError, OSError) as error:
    CPP_IMPORT_ERROR = error
    CppAgent = CppBridge = CppDirection = CppGridMap = CppMethod = CppNode = CppOptions = CppPoint = CppDStarLite = None
    cpp_find_static_path = cpp_inflate_obstacles = cpp_solve = None
PLANNER_BACKEND = os.environ.get('CAMPUSFLEET_PLANNER_BACKEND', 'cpp' if cpp_solve else 'python').lower()
if PLANNER_BACKEND not in ('cpp', 'python'):
    raise RuntimeError('CAMPUSFLEET_PLANNER_BACKEND must be cpp or python')
if PLANNER_BACKEND == 'cpp' and cpp_solve is None:
    raise RuntimeError(f'C++ planner requested but module could not load: {CPP_IMPORT_ERROR}')
TASKS = {}
TASK_LOCK = threading.Lock()
TASK_ITEMS = {'教材', '文件', '包裹'}
TASK_STEP_SECONDS = .14
DSTAR_SESSIONS = {}
DSTAR_LOCK = threading.Lock()
storage.init_db()
for _stored in storage.load_orders():
    if _stored.get('_started_at_wall') and _stored['status'] == '已模拟支付':
        _stored['_started_at'] = time.monotonic() - max(0, time.time() - _stored['_started_at_wall'])
    TASKS[_stored['id']] = _stored


def share_ipv4():
    """Choose the host IPv4 used by the LAN route; allow an explicit Wi-Fi override."""
    configured = os.environ.get('CAMPUSFLEET_SHARE_IP', '').strip()
    if configured:
        try:
            address = ipaddress.IPv4Address(configured)
        except ipaddress.AddressValueError as error:
            raise ValueError('CAMPUSFLEET_SHARE_IP 必须是有效的 IPv4 地址') from error
        if address.is_loopback or address.is_link_local or address.is_unspecified:
            raise ValueError('CAMPUSFLEET_SHARE_IP 必须是可供其他设备访问的地址')
        return str(address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            # UDP connect only chooses an interface; it sends no packet.
            probe.connect(('192.0.2.1', 80))
            address = ipaddress.IPv4Address(probe.getsockname()[0])
            if not (address.is_loopback or address.is_link_local or address.is_unspecified):
                return str(address)
        except OSError:
            pass
    try:
        candidates = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        candidates = []
    for candidate in candidates:
        address = ipaddress.IPv4Address(candidate[4][0])
        if not (address.is_loopback or address.is_link_local or address.is_unspecified):
            return str(address)
    return None


def native_map(blocked, directions=None, radius=0, robot_height=1, margin=0,
               max_slope=20, deck_blocked=(), layered=False):
    native = CppGridMap()
    native.width, native.height = MAP['width'], MAP['height']
    native.resolution_m = MAP['resolution_m']
    native.blocked = [int((x, y) in blocked)
                      for y in range(MAP['height']) for x in range(MAP['width'])]
    direction_map = directions if directions is not None else road_directions(MAP)
    native.directions = [CppDirection(*direction_map.get((x, y), (0, 0)))
                         for y in range(MAP['height']) for x in range(MAP['width'])]
    native.deck_blocked = [int((x, y) in deck_blocked)
                           for y in range(MAP['height']) for x in range(MAP['width'])] if deck_blocked else []
    native.layered = layered
    native.radius, native.robot_height = radius, robot_height
    native.margin, native.max_slope_deg = margin, max_slope
    if layered:
        bridge = MAP['bridge']
        native.bridge = CppBridge()
        for key in ('start', 'end', 'plateau_start', 'plateau_end', 'y_min', 'y_max', 'height', 'thickness'):
            setattr(native.bridge, key, bridge[key])
    return native


def inflated_map(cells, radius, resolution=1):
    height, width = len(cells), len(cells[0])
    if PLANNER_BACKEND == 'cpp':
        native = CppGridMap()
        native.width, native.height = width, height
        native.resolution_m = resolution
        native.blocked = [int(cells[y][x] in BLOCKED) for y in range(height) for x in range(width)]
        expanded = cpp_inflate_obstacles(native, radius)
        return {(index % width, index // width) for index, value in enumerate(expanded) if value}
    reach = math.ceil(radius / resolution) + 1
    blocked = {(x, y) for y in range(height) for x in range(width) if cells[y][x] in BLOCKED}
    result = set(blocked)
    # Preserve stage one's conservative whole-cell clearance semantics.
    offsets = [(dx, dy) for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1)
               if (dx or dy) and math.hypot(max(abs(dx) - 1, 0) * resolution,
                                           max(abs(dy) - 1, 0) * resolution) < radius - 1e-9]
    for x, y in blocked:
        for dx, dy in offsets:
            target = (x + dx, y + dy)
            if 0 <= target[0] < width and 0 <= target[1] < height:
                result.add(target)
    if radius > 0:
        for y in range(height):
            for x in range(width):
                if min(x, y, width - 1 - x, height - 1 - y) * resolution < radius - 1e-9:
                    result.add((x, y))
    return result


def find_path(cells, start, goal, blocked=None, directions=None):
    height, width = len(cells), len(cells[0])
    if blocked is None:
        blocked = inflated_map(cells, 0)
    if start in blocked or goal in blocked:
        return [], 0
    if PLANNER_BACKEND == 'cpp':
        native = native_map(blocked, directions)
        result = cpp_find_static_path(native, CppNode(*start), CppNode(*goal))
        path = [(int(point.x), int(point.y)) for point in result.path]
        return path, result.explored

    def heuristic(point):
        dx, dy = abs(point[0] - goal[0]), abs(point[1] - goal[1])
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)

    queue = [(heuristic(start), 0, start)]
    costs, previous, explored = {start: 0}, {}, 0
    while queue:
        _, cost, point = heapq.heappop(queue)
        if cost > costs[point] + 1e-9:
            continue
        explored += 1
        if point == goal:
            path = [point]
            while point in previous:
                point = previous[point]
                path.append(point)
            return path[::-1], explored
        for target in neighbours(point, width, height, blocked, directions or {}):
            new_cost = cost + math.dist(point, target)
            if new_cost < costs.get(target, math.inf) - 1e-9:
                costs[target], previous[target] = new_cost, point
                heapq.heappush(queue, (new_cost + heuristic(target), new_cost, target))
    return [], explored


def parse_request(data):
    if not isinstance(data, dict):
        raise ValueError('请求必须是对象')
    width, height = MAP['width'], MAP['height']

    def point(value):
        if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value):
            raise ValueError('坐标必须是两个整数')
        x, y = value
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError('坐标超出地图')
        return x, y

    radius, margin = data.get('radius', .3), data.get('margin', .2)
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 3
           for v in (radius, margin)):
        raise ValueError('半径和余量必须在 0 到 3 米之间')
    obstacles = data.get('obstacles', [])
    if not isinstance(obstacles, list) or len(obstacles) > width * height:
        raise ValueError('障碍物格式无效')
    cells = [row[:] for row in MAP['cells']]
    # Duplicates represent the same temporary obstacle and are harmless.
    for x, y in {point(item) for item in obstacles}:
        if cells[y][x] in BLOCKED:
            raise ValueError('无法覆盖原有障碍')
        cells[y][x] = 'obstacle'
    blocked = inflated_map(cells, radius + margin, MAP['resolution_m'])
    original = {(x, y) for y in range(height) for x in range(width) if cells[y][x] in BLOCKED}
    return cells, blocked, sorted(blocked - original), radius, margin, point


def fleet_result(data, blocked, radius, margin, point):
    use_terrain = data.get('use_terrain', False)
    height, max_slope = data.get('height', 1.0), data.get('max_slope', 20)
    if type(use_terrain) is not bool:
        raise ValueError('立体路面参数必须为布尔值')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in (height, max_slope)) or not .1 <= height <= 4 or not 0 <= max_slope <= 45:
        raise ValueError('车身高度必须为 0.1 到 4 米，最大坡度为 0 到 45 度')
    deck_blocked = set()
    if use_terrain and data.get('obstacles'):
        temporary_cells = [['road'] * MAP['width'] for _ in range(MAP['height'])]
        for x,y in data['obstacles']:
            temporary_cells[y][x] = 'obstacle'
        deck_blocked = inflated_map(temporary_cells,radius+margin,MAP['resolution_m'])
    graph = TerrainGraph(MAP, blocked, road_directions(MAP), radius, height, margin, max_slope, deck_blocked) if use_terrain else None

    def endpoint(value):
        if not use_terrain:
            return point(value)
        if not isinstance(value, list) or len(value) not in (2, 3):
            raise ValueError('立体坐标必须为 [x,y] 或 [x,y,z]')
        x, y = point(value[:2])
        z = value[2] if len(value) == 3 else 0
        if type(z) not in (int, float) or not math.isfinite(z) or z < 0 or z > MAP['bridge']['height']:
            raise ValueError('路面高度无效')
        return x, y, z

    agents = data.get('agents')
    if not isinstance(agents, list) or not 1 <= len(agents) <= 10:
        raise ValueError('机器人数量必须为 1 到 10')
    cleaned = []
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            raise ValueError('机器人格式无效')
        cleaned.append({'id': str(index + 1), 'start': endpoint(agent.get('start')),
                        'goal': endpoint(agent.get('goal'))})
    method = data.get('method', 'cbs')
    allow_slowdown = data.get('allow_slowdown', False)
    if type(allow_slowdown) is not bool:
        raise ValueError('允许减速参数必须为布尔值')
    horizon, seconds = data.get('max_steps', 400), data.get('time_limit_s', 8)
    if method not in ('cbs', 'priority'):
        raise ValueError('未知规划方法')
    if type(horizon) is not int or not 1 <= horizon <= 800:
        raise ValueError('时间步上限必须为 1 到 800 的整数')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 20:
        raise ValueError('计算时限必须为 1 到 20 秒')
    pedestrian_count = data.get('pedestrian_count', 0)
    pedestrian_seed = data.get('pedestrian_seed', 1)
    if type(pedestrian_count) is not int or not 0 <= pedestrian_count <= 15:
        raise ValueError('行人数量必须为 0 到 15 的整数')
    if type(pedestrian_seed) is not int or not 0 <= pedestrian_seed <= 2147483647:
        raise ValueError('随机种子必须为非负整数')
    clearance = (2 * radius + margin) / MAP['resolution_m']
    for index, agent in enumerate(cleaned):
        for other in cleaned[index + 1:]:
            for endpoint in ('start', 'goal'):
                a, b = agent[endpoint], other[endpoint]
                if collides(a, a, b, b, clearance, height + margin):
                    raise ValueError('机器人起点之间或终点之间距离不足；到达后终点会持续占用')
    if any((not graph.valid(agent[key])) if graph else (agent[key] in blocked) for agent in cleaned for key in ('start', 'goal')):
        return {'found': False, 'reason': '起终点无法通行，请检查障碍、安全距离、路面高度、桥下净高或最大坡度。', 'explored': 0}
    pedestrian_clearance = (radius + .25 + margin) / MAP['resolution_m']
    walking_blocked = blocked | ({(x, y) for y in range(MAP['height']) for x in range(MAP['width'])
                                   if not graph.valid((x, y, 0))} if graph else set())
    pedestrian_paths = generate_pedestrians(
        pedestrian_count, pedestrian_seed, horizon, MAP['width'], MAP['height'],
        walking_blocked, road_directions(MAP),
        [agent[key] for agent in cleaned for key in ('start', 'goal')],
        max(.5 + margin, pedestrian_clearance)) if pedestrian_count else []
    if graph:
        pedestrian_paths = [[(x, y, 0) for x, y in path] for path in pedestrian_paths]
    if PLANNER_BACKEND == 'cpp':
        native = native_map(blocked, road_directions(MAP), radius, height, margin,
                            max_slope, deck_blocked, use_terrain)
        native_agents = [CppAgent(agent['id'],
                                  CppNode(agent['start'][0], agent['start'][1], len(agent['start']) == 3 and agent['start'][2] > 1e-8),
                                  CppNode(agent['goal'][0], agent['goal'][1], len(agent['goal']) == 3 and agent['goal'][2] > 1e-8))
                         for agent in cleaned]
        native_options = CppOptions()
        native_options.method = CppMethod.CBS if method == 'cbs' else CppMethod.PRIORITY
        native_options.horizon = horizon
        native_options.time_limit_s = seconds
        native_options.robot_clearance = clearance
        native_options.pedestrian_clearance = pedestrian_clearance
        native_options.vertical_clearance = height + margin
        native_options.allow_slowdown = allow_slowdown
        native_pedestrians = [[CppPoint(point[0], point[1], point[2] if len(point) == 3 else 0)
                               for point in path] for path in pedestrian_paths]
        native_result = cpp_solve(native, native_agents, native_options, native_pedestrians)
        used_method = 'priority' if native_result.used_method == CppMethod.PRIORITY else 'cbs'
        result = {
            'found': native_result.found,
            'reason': native_result.reason,
            'agents': [{'id': agent.id,
                        'path': [[point.x, point.y, point.z] if use_terrain else [point.x, point.y]
                                 for point in agent.path],
                        'arrival_step': agent.arrival_step,
                        'wait_steps': agent.wait_steps,
                        'slow_steps': agent.slow_steps,
                        'speed_profile_mps': list(agent.speed_profile_mps),
                        'distance_m': agent.distance_m}
                       for agent in native_result.agents],
            'sum_arrival_steps': native_result.sum_arrival_steps,
            'makespan_steps': native_result.makespan_steps,
            'conflicts': 0,
            'used_method': used_method,
            'warning': native_result.warning,
            'explored': native_result.explored,
            'cbs_nodes': native_result.cbs_nodes,
            'planning_ms': native_result.planning_ms,
        }
    else:
        result = solve(cleaned, MAP['width'], MAP['height'], blocked, graph or road_directions(MAP),
                       clearance, method, horizon, seconds, allow_slowdown, height + margin,
                       pedestrian_paths, pedestrian_clearance)
        for agent in result.get('agents', []):
            agent['distance_m'] = round(agent['distance_m'] * MAP['resolution_m'], 2)
    result.update({'method': method, 'allow_slowdown': allow_slowdown,
                   'planner_backend': PLANNER_BACKEND,
                   'tick_seconds': math.sqrt(2) * MAP['resolution_m'],
                   'pedestrians': [{'id': str(index + 1), 'path': path}
                                   for index, path in enumerate(pedestrian_paths)]})
    return result


def create_task(data):
    if not isinstance(data, dict):
        raise ValueError('任务请求必须是对象')
    building = data.get('building')
    item = data.get('item')
    room = data.get('room')
    if item not in TASK_ITEMS or room not in ('A', 'B'):
        raise ValueError('请选择配送物品和目标房间')
    shapes = [shape for shape in MAP['shapes'] if shape['kind'] == 'building']
    shape = next((shape for shape in shapes if shape['label'] == building), None)
    if shape is None:
        raise ValueError('未知建筑')
    crowd = data.get('crowd', 4)
    seed = data.get('seed', 1)
    pedestrians = data.get('pedestrian_count', 4)
    can_climb = data.get('can_climb', True)
    if type(pedestrians) is not int or not 0 <= pedestrians <= 15:
        raise ValueError('室外行人数量必须为 0 到 15 的整数')
    user_id = data.get('user_id') or 'GUEST-' + uuid.uuid4().hex[:8].upper()
    if not isinstance(user_id, str) or not 1 <= len(user_id) <= 64 or not all(
            char.isalnum() or char in '-_' for char in user_id):
        raise ValueError('用户编号格式无效')
    x_values = [point[0] for point in shape['points']]
    y_values = [point[1] for point in shape['points']]
    center = (min(x_values) + max(x_values)) / 2
    blocked = inflated_map(MAP['cells'], .5, MAP['resolution_m'])
    entrance_candidates = [(x, y) for y in range(max(y_values) + 1, min(MAP['height'], max(y_values) + 9))
                           for x in range(max(0, min(x_values) - 4), min(MAP['width'], max(x_values) + 5))
                           if (x, y) not in blocked]
    entrance_candidates.sort(key=lambda point: (point[1] - max(y_values), abs(point[0] - center)))
    start = tuple(MAP['default_start'])
    entrance = next((candidate for candidate in entrance_candidates
                     if find_path(MAP['cells'], start, candidate, blocked, road_directions(MAP))[0]), None)
    if entrance is None:
        raise ValueError('建筑入口无法从室外配送起点到达')
    request = {'agents': [{'start': list(start), 'goal': list(entrance)}],
               'method': 'priority', 'allow_slowdown': True,
               'max_steps': min(800, MAP['width'] + MAP['height'] + 100),
               'pedestrian_count': pedestrians, 'pedestrian_seed': seed}
    _, route_blocked, _, radius, margin, point = parse_request(request)
    outdoor = fleet_result(request, route_blocked, radius, margin, point)
    if not outdoor['found']:
        raise ValueError(outdoor['reason'])
    outdoor_agent = outdoor['agents'][0]
    door_steps = 4
    transition_step = outdoor_agent['arrival_step'] + door_steps
    indoor = plan_indoor(building, crowd, can_climb, [s['label'] for s in shapes],
                         seed, (0,) if room == 'A' else (1,), transition_step)
    indoor_agent = dict(indoor['robots'][0])
    indoor_agent['id'] = 1
    price = round(2 + outdoor_agent['distance_m'] * .03 + 2 * 1.5, 2)
    task_id = uuid.uuid4().hex
    task = {'id': task_id, 'robot_id': 'R-' + task_id[:6].upper(),
            'status': '待模拟支付', 'building': building,
            'user_id': user_id, 'created_at': time.time(), 'route_revision': 0,
            'item': item, 'room': room, 'price': price, 'currency': '模拟元',
            'entrance': entrance, 'start': start, 'door_steps': door_steps,
            'transition_step': transition_step,
            'arrival_step': transition_step + indoor_agent['arrival_step'],
            'outdoor': outdoor_agent, 'indoor': indoor_agent,
            'elevator': indoor['elevator'], 'pedestrians': outdoor['pedestrians'],
            'crowd': crowd, 'can_climb': can_climb, 'seed': seed,
            'pedestrian_count': pedestrians}
    with TASK_LOCK:
        TASKS[task['id']] = task
        storage.save_order(task)
    return task


def replan_task(task_id):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            raise ValueError('任务不存在或服务已重启')
        if task['status'] != '待模拟支付':
            raise ValueError('只能在确认模拟付款前重新规划')
        current = dict(task)
    old_path = current['outdoor']['path']
    candidates = [old_path[int((len(old_path) - 1) * fraction)]
                  for fraction in (.5, .35, .65)]
    planned = None
    for point in candidates:
        if len(point) < 2 or not all(type(value) in (int, float) and float(value).is_integer()
                                     for value in point[:2]):
            continue
        cell = [int(value) for value in point[:2]]
        if tuple(cell) in (tuple(current['start']), tuple(current['entrance'])):
            continue
        request = {'agents': [{'start': list(current['start']), 'goal': list(current['entrance'])}],
                   'method': 'priority', 'allow_slowdown': True,
                   'pedestrian_count': current['pedestrian_count'], 'pedestrian_seed': current['seed'],
                   'obstacles': [cell]}
        _, blocked, _, radius, margin, read_point = parse_request(request)
        result = fleet_result(request, blocked, radius, margin, read_point)
        if result['found'] and result['agents'][0]['path'] != old_path:
            planned = result
            break
    if planned is None:
        raise ValueError('当前道路条件下没有可行的其他路线')
    outdoor = planned['agents'][0]
    transition_step = outdoor['arrival_step'] + current['door_steps']
    buildings = [shape['label'] for shape in MAP['shapes'] if shape['kind'] == 'building']
    indoor = plan_indoor(current['building'], current['crowd'], current['can_climb'],
                         buildings, current['seed'], (0,) if current['room'] == 'A' else (1,),
                         transition_step)
    indoor_agent = dict(indoor['robots'][0])
    indoor_agent['id'] = 1
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None or task['status'] != '待模拟支付' or task['route_revision'] != current['route_revision']:
            raise ValueError('订单状态已变化，请刷新后重试')
        task.update(outdoor=outdoor, indoor=indoor_agent, elevator=indoor['elevator'],
                    pedestrians=planned['pedestrians'], transition_step=transition_step,
                    arrival_step=transition_step + indoor_agent['arrival_step'],
                    price=round(2 + outdoor['distance_m'] * .03 + 2 * 1.5, 2),
                    route_revision=task['route_revision'] + 1)
        storage.save_order(task)
        return public_task(task)


def advance_task(task):
    started_at = task.get('_started_at')
    if task['status'] == '已模拟支付' and started_at is not None:
        elapsed_steps = int((time.monotonic() - started_at) / TASK_STEP_SECONDS)
        if elapsed_steps >= task['arrival_step']:
            task['status'] = '已送达'
            storage.save_order(task)


def task_progress(task):
    advance_task(task)
    started_at = task.get('_started_at')
    tick = (task['arrival_step'] if task['status'] == '已送达' else
            min(task['arrival_step'], int((time.monotonic() - started_at) / TASK_STEP_SECONDS))
            if started_at is not None else 0)
    if tick <= task['outdoor']['arrival_step']:
        phase = '校园道路'
        point = task['outdoor']['path'][min(tick, len(task['outdoor']['path']) - 1)]
        position = {'x': point[0], 'y': point[1]}
    elif tick < task['transition_step']:
        phase = '进入建筑'
        position = {'x': task['entrance'][0], 'y': task['entrance'][1]}
    else:
        phase = '建筑室内'
        indoor_tick = tick - task['transition_step']
        point = task['indoor']['path'][min(indoor_tick, len(task['indoor']['path']) - 1)]
        position = {'x': point[0], 'y': point[1], 'floor': point[2]}
    return {'id': task['id'], 'robot_id': task['robot_id'], 'status': task['status'],
            'route_revision': task.get('route_revision', 0),
            'tick': tick, 'total_steps': task['arrival_step'],
            'percent': round(100 * tick / task['arrival_step'], 1),
            'phase': phase, 'position': position,
            'remaining_seconds': round((task['arrival_step'] - tick) * TASK_STEP_SECONDS, 1)}


def public_task(task):
    advance_task(task)
    return {key: value for key, value in task.items() if not key.startswith('_')}


def get_task(task_id):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            raise ValueError('任务不存在或服务已重启')
        return public_task(task)


def pay_task(task_id):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            raise ValueError('任务不存在或服务已重启')
        if task['status'] == '待模拟支付':
            task['status'] = '已模拟支付'
            task['_started_at'] = time.monotonic()
            task['_started_at_wall'] = time.time()
            storage.save_order(task)
        return public_task(task)


def complete_task(task_id):
    with TASK_LOCK:
        task = TASKS.get(task_id)
        if task is None:
            raise ValueError('任务不存在或服务已重启')
        if task['status'] == '待模拟支付':
            raise ValueError('请先完成模拟支付')
        task['status'] = '已送达'
        storage.save_order(task)
        return public_task(task)


def dstar_snapshot(session):
    started = time.perf_counter()
    result = session['planner'].plan()
    path = [[int(p.x), int(p.y), round(p.z, 3)] if p.z else [int(p.x), int(p.y)]
            for p in result.path]
    return {'session_id': session['id'], 'found': result.found, 'path': path,
            'start': list(session['start']), 'goal': list(session['goal']),
            'temporary_obstacles': [list(p) for p in sorted(session['obstacles'])],
            'explored': result.explored, 'planning_ms': round((time.perf_counter() - started) * 1000, 2),
            'method': 'dstar_lite', 'planner_backend': 'cpp'}


def start_dstar_session(data):
    if CppDStarLite is None:
        raise ValueError('D* Lite 需要先重新编译 C++ Python 扩展')
    if not isinstance(data, dict): raise ValueError('请求必须是对象')
    _, blocked, _, radius, margin, point = parse_request(data)
    start, goal = point(data.get('start')), point(data.get('goal'))
    if start in blocked or goal in blocked: raise ValueError('起点或终点不可通行')
    native = native_map(blocked, road_directions(MAP), radius, 1, margin, 20,
                        layered=bool(data.get('use_terrain', False)))
    session = {'id': uuid.uuid4().hex, 'planner': CppDStarLite(native, CppNode(*start), CppNode(*goal)),
               'start': start, 'goal': goal, 'obstacles': set(tuple(p) for p in data.get('obstacles', [])),
               'blocked': blocked, 'radius': radius, 'margin': margin, 'lock': threading.Lock()}
    snapshot = dstar_snapshot(session)
    with DSTAR_LOCK:
        DSTAR_SESSIONS[session['id']] = session
    return snapshot


def update_dstar_session(session_id, data):
    with DSTAR_LOCK:
        session = DSTAR_SESSIONS.get(session_id)
    if session is None: raise ValueError('D* Lite 会话不存在，请重新创建')
    if not isinstance(data, dict): raise ValueError('请求必须是对象')
    changes = data.get('changes', [])
    if not isinstance(changes, list) or len(changes) > 30: raise ValueError('每次最多更新 30 个道路格')
    with session['lock']:
        obstacles = set(session['obstacles'])
        for change in changes:
            if not isinstance(change, dict) or type(change.get('blocked')) is not bool:
                raise ValueError('道路更新需包含 x、y 和 blocked 布尔值')
            x, y = change.get('x'), change.get('y')
            if type(x) is not int or type(y) is not int or not (0 <= x < MAP['width'] and 0 <= y < MAP['height']):
                raise ValueError('道路更新坐标无效')
            if MAP['cells'][y][x] in BLOCKED: raise ValueError('只能修改原有可通行道路')
            if change['blocked']: obstacles.add((x, y))
            else: obstacles.discard((x, y))
        _, blocked, _, _, _, point = parse_request({'obstacles': [list(p) for p in obstacles],
            'radius': session['radius'], 'margin': session['margin']})
        start = point(data.get('start', list(session['start'])))
        if start in blocked: raise ValueError('机器人当前位置被封闭')
        for x, y in session['blocked'] - blocked: session['planner'].set_blocked(x, y, False)
        for x, y in blocked - session['blocked']: session['planner'].set_blocked(x, y, True)
        session['planner'].move_start(CppNode(*start))
        session.update(start=start, obstacles=obstacles, blocked=blocked)
        return dstar_snapshot(session)


class Handler(BaseHTTPRequestHandler):
    def auth_token(self):
        value = self.headers.get('Authorization', '')
        return value[7:] if value.startswith('Bearer ') else ''

    def current_user(self):
        return storage.user_for_token(self.auth_token())

    def require_user(self):
        user = self.current_user()
        if user is None:
            self.send_json(401, {'error': '请先登录'})
        return user

    def owns(self, task_id, user):
        with TASK_LOCK:
            task = TASKS.get(task_id)
            return (task is not None and task['user_id'] == user['id']
                    and (not user.get('checkout_order_id') or task_id == user['checkout_order_id']))

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/auth/me':
            user = self.require_user()
            return self.send_json(200, user) if user else None
        if path == '/api/share-url':
            try:
                address = share_ipv4()
            except ValueError as error:
                return self.send_json(400, {'error': str(error)})
            bound_host = self.server.server_address[0]
            return self.send_json(200, {
                'base_url': f'http://{address}:{self.server.server_port}' if address else None,
                'lan_enabled': bound_host == '0.0.0.0' or bound_host == address,
            })
        if path == '/api/map':
            return self.send_json(200, MAP)
        if path in ('/api/tasks', '/api/operator/tasks'):
            if path == '/api/operator/tasks':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    return self.send_json(403, {'error': '调度记录仅供本机查看'})
                user = None
            else:
                user = self.require_user()
                if not user: return
            with TASK_LOCK:
                for task in TASKS.values():
                    advance_task(task)
                tasks = [{'id': task['id'], 'building': task['building'], 'item': task['item'],
                          'room': task['room'], 'price': task['price'], 'status': task['status']}
                         for task in TASKS.values() if user is None or
                         (task['user_id'] == user['id'] and
                          (not user.get('checkout_order_id') or task['id'] == user['checkout_order_id']))]
            return self.send_json(200, tasks)
        if path.startswith('/api/tasks/') and path.endswith('/progress'):
            user = self.require_user()
            if not user: return
            task_id = path[len('/api/tasks/'):-len('/progress')]
            if not self.owns(task_id, user):
                return self.send_json(404, {'error': '订单不存在'})
            with TASK_LOCK:
                task = TASKS.get(task_id)
                progress = task_progress(task) if task is not None else None
            return self.send_json(200, progress) if progress is not None else self.send_json(404, {'error': '任务不存在或服务已重启'})
        if path.startswith('/api/tasks/'):
            user = self.require_user()
            if not user: return
            if not self.owns(path[len('/api/tasks/'):], user):
                return self.send_json(404, {'error': '订单不存在'})
            try:
                return self.send_json(200, get_task(path[len('/api/tasks/'):]))
            except ValueError as error:
                return self.send_json(404, {'error': str(error)})
        files = {'/': 'index.html', '/client': 'client.html', '/checkout': 'client.html',
                 '/dstar': 'dstar.html', '/dstar.js': 'dstar.js',
                 '/style.css': 'style.css', '/app.js': 'app.js',
                 '/scene3d.js': 'scene3d.js', '/indoor-scene.js': 'indoor-scene.js',
                 '/indoor.js': 'indoor.js', '/tasks.js': 'tasks.js',
                 '/operator.js': 'operator.js', '/qr.js': 'qr.js',
                 '/qr.LICENSE.md': 'qr.LICENSE.md'}
        if path not in files:
            return self.send_json(404, {'error': '不存在的页面'})
        file = ROOT / 'static' / files[path]
        body = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(file.name)[0] + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/dstar/sessions' or (path.startswith('/api/dstar/sessions/') and path.endswith('/update')):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 200000: raise ValueError('请求大小无效')
                data = json.loads(self.rfile.read(size))
                if path == '/api/dstar/sessions': return self.send_json(200, start_dstar_session(data))
                session_id = path[len('/api/dstar/sessions/'):-len('/update')]
                return self.send_json(200, update_dstar_session(session_id, data))
            except (ValueError, TypeError, KeyError, RuntimeError) as error:
                return self.send_json(400, {'error': str(error)})
        if path in ('/api/auth/register', '/api/auth/login', '/api/auth/logout'):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096: raise ValueError('请求大小无效')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict): raise ValueError('请求必须是对象')
                if path == '/api/auth/register':
                    storage.register(data.get('username'), data.get('password'))
                    return self.send_json(200, storage.login(data['username'], data['password']))
                if path == '/api/auth/login':
                    return self.send_json(200, storage.login(data.get('username'), data.get('password')))
                storage.logout(self.auth_token())
                return self.send_json(200, {'ok': True})
            except (ValueError, TypeError, KeyError) as error:
                return self.send_json(400, {'error': str(error)})
        payment_id = path[len('/api/tasks/'):-len('/pay')] if path.startswith('/api/tasks/') and path.endswith('/pay') else None
        replan_id = path[len('/api/tasks/'):-len('/replan')] if path.startswith('/api/tasks/') and path.endswith('/replan') else None
        completion_id = path[len('/api/tasks/'):-len('/complete')] if path.startswith('/api/tasks/') and path.endswith('/complete') else None
        if path not in ('/api/path', '/api/fleet', '/api/indoor', '/api/tasks') and payment_id is None and replan_id is None and completion_id is None and not path.endswith('/checkout-ticket'):
            return self.send_json(404, {'error': '不存在的接口'})
        ticket_order_id = (path[len('/api/tasks/'):-len('/checkout-ticket')]
                           if path.startswith('/api/tasks/') and path.endswith('/checkout-ticket') else None)
        if path == '/api/tasks' or payment_id or replan_id or completion_id or ticket_order_id:
            user = self.require_user()
            if not user: return
            task_id = payment_id or replan_id or completion_id
            if user.get('checkout_order_id') and (path == '/api/tasks' or ticket_order_id):
                return self.send_json(403, {'error': '此付款链接只能用于查看和支付指定订单'})
            if task_id and not self.owns(task_id, user):
                return self.send_json(404, {'error': '订单不存在'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 200000:
                raise ValueError('请求大小无效')
            data = json.loads(self.rfile.read(size))
            if ticket_order_id is not None:
                if not isinstance(data, dict): raise ValueError('请求必须是对象')
                with TASK_LOCK:
                    task = TASKS.get(ticket_order_id)
                    if task is None or task['user_id'] != user['id'] or task['status'] != '待模拟支付':
                        raise ValueError('只有本人待付款订单可以生成付款链接')
                ticket = storage.create_checkout_ticket(user['id'], ticket_order_id)
                return self.send_json(200, {'ticket': ticket, 'expires_in': 1800})
            if payment_id is not None:
                if not isinstance(data, dict):
                    raise ValueError('模拟支付请求必须是对象')
                return self.send_json(200, pay_task(payment_id))
            if replan_id is not None:
                if not isinstance(data, dict):
                    raise ValueError('重新规划请求必须是对象')
                return self.send_json(200, replan_task(replan_id))
            if completion_id is not None:
                if not isinstance(data, dict):
                    raise ValueError('送达请求必须是对象')
                return self.send_json(200, complete_task(completion_id))
            if path == '/api/tasks':
                if not isinstance(data, dict): raise ValueError('请求必须是对象')
                data['user_id'] = user['id']
                return self.send_json(200, create_task(data))
            if path == '/api/indoor':
                if not isinstance(data, dict):
                    raise ValueError('请求必须是对象')
                buildings = [shape['label'] for shape in MAP['shapes'] if shape['kind'] == 'building']
                result = plan_indoor(data.get('building'), data.get('crowd', 4),
                                     data.get('can_climb', True), buildings,
                                     data.get('seed', 1))
                return self.send_json(200, result)
            cells, blocked, expanded, radius, margin, point = parse_request(data)
            if path == '/api/fleet':
                result = fleet_result(data, blocked, radius, margin, point)
            else:
                start, goal = point(data.get('start')), point(data.get('goal'))
                if start in blocked or goal in blocked:
                    result = {'found': False, 'reason': '起点或终点位于障碍物或膨胀区域，请更换位置或调整参数。',
                              'path': [], 'explored': 0}
                else:
                    route, explored = find_path(cells, start, goal, blocked, road_directions(MAP))
                    distance = sum(math.dist(a, b) for a, b in zip(route, route[1:])) * MAP['resolution_m']
                    result = {'found': bool(route), 'path': route, 'steps': max(0, len(route) - 1),
                              'distance_m': round(distance, 2), 'explored': explored,
                              'reason': '' if route else '无法到达终点：请检查障碍或调整位置。'}
            result.setdefault('planner_backend', PLANNER_BACKEND)
            result['inflated'] = expanded
            self.send_json(200, result)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self.send_json(400, {'error': str(error)})


if __name__ == '__main__':
    host = os.environ.get('CAMPUSFLEET_HOST', '127.0.0.1')
    port = int(os.environ.get('CAMPUSFLEET_PORT', '8000'))
    http = ThreadingHTTPServer((host, port), Handler)
    display_host = '127.0.0.1' if host == '0.0.0.0' else host
    print(f'CampusFleet 已启动：http://{display_host}:{port}（监听 {host}）', flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器已停止。')
    finally:
        http.server_close()
