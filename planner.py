"""Directed eight-neighbour paths and bounded multi-agent space-time search."""
import heapq
import itertools
import math
import time
from collections import deque

MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1),
         (1, 1), (1, -1), (-1, 1), (-1, -1))


class SearchLimit(Exception):
    pass


class Budget:
    def __init__(self, seconds):
        self.deadline = time.monotonic() + seconds
        self.explored = 0

    def check(self):
        if time.monotonic() > self.deadline or self.explored >= 500000:
            raise SearchLimit


def road_directions(data):
    return {tuple(cell): tuple(lane['direction'])
            for lane in data.get('lanes', []) if lane.get('direction')
            for cell in lane['cells']}


def neighbours(point, width, height, blocked, directions):
    if hasattr(directions, 'neighbours'):
        yield from directions.neighbours(point)
        return
    x, y = point
    for dx, dy in MOVES:
        target = (x + dx, y + dy)
        if not (0 <= target[0] < width and 0 <= target[1] < height):
            continue
        if target in blocked:
            continue
        if dx and dy and ((x + dx, y) in blocked or (x, y + dy) in blocked):
            continue
        # Apply the rule to both ends, including entering and leaving a lane.
        if any(direction and dx * direction[0] + dy * direction[1] <= 0
               for direction in (directions.get(point), directions.get(target))):
            continue
        yield target


def minimum_distance(a, b, c, d):
    """Minimum centre distance during two simultaneous linear moves."""
    rx, ry = a[0] - c[0], a[1] - c[1]
    vx, vy = b[0] - a[0] - d[0] + c[0], b[1] - a[1] - d[1] + c[1]
    speed = vx * vx + vy * vy
    fraction = max(0, min(1, -(rx * vx + ry * vy) / speed)) if speed else 0
    return math.hypot(rx + fraction * vx, ry + fraction * vy)


def collides(a, b, c, d, clearance, vertical_clearance=1.2):
    lower, upper = 0.0, 1.0
    if len(a) == 3:
        height = a[2] - c[2]
        change = b[2] - a[2] - d[2] + c[2]
        if abs(change) < 1e-12:
            if abs(height) >= vertical_clearance:
                return False
        else:
            crossings = sorted(((-vertical_clearance - height) / change,
                                (vertical_clearance - height) / change))
            lower, upper = max(lower, crossings[0]), min(upper, crossings[1])
            if lower >= upper:
                return False
    def interpolate(source, target, fraction):
        return tuple(source[k] + (target[k] - source[k]) * fraction for k in range(2))
    distance = minimum_distance(interpolate(a, b, lower), interpolate(a, b, upper),
                                interpolate(c, d, lower), interpolate(c, d, upper))
    # Coincidence is forbidden even for zero-radius demonstration robots.
    return distance < 1e-8 or distance < clearance - 1e-8


def position(path, tick):
    return path[min(tick, len(path) - 1)]


def first_conflict(paths, clearance, budget=None, vertical_clearance=1.2):
    for tick in range(max(map(len, paths))):
        if budget:
            budget.check()
        for i, j in itertools.combinations(range(len(paths)), 2):
            a, b = position(paths[i], tick), position(paths[i], tick + 1)
            c, d = position(paths[j], tick), position(paths[j], tick + 1)
            if collides(a, b, c, d, clearance, vertical_clearance):
                return i, j, tick, a, b, c, d
    return None


def reverse_distances(goal, width, height, blocked, directions, budget):
    if hasattr(directions, 'reverse_distances'):
        return directions.reverse_distances(goal, budget)
    distances = {goal: 0}
    queue = deque([goal])
    while queue:
        budget.check()
        target = queue.popleft()
        for dx, dy in MOVES:
            source = (target[0] + dx, target[1] + dy)
            if source in distances or source in blocked:
                continue
            if not (0 <= source[0] < width and 0 <= source[1] < height):
                continue
            diagonal_blocked = dx and dy and ((source[0], target[1]) in blocked or (target[0], source[1]) in blocked)
            legal_direction = all(not direction or -dx * direction[0] - dy * direction[1] > 0
                                  for direction in (directions.get(source), directions.get(target)))
            if not diagonal_blocked and legal_direction:
                distances[source] = distances[target] + 1
                queue.append(source)
    return distances


def space_time_path(start, goal, width, height, blocked, directions,
                    constraints, horizon, distances, budget, reservations=(), clearance=0,
                    allow_slowdown=False, vertical_clearance=1.2, corridor=None,
                    pedestrians=(), pedestrian_clearance=None):
    if start not in distances:
        return []
    latest = max((entry[0] for entry in constraints), default=-1)
    reserved_until = max((len(path) - 1 for path in tuple(reservations) + tuple(pedestrians)), default=0)

    def allowed(a, b, tick):
        if (tick, a, b) in constraints:
            return False
        return (all(not collides(a, b, position(path, tick), position(path, tick + 1), clearance, vertical_clearance)
                    for path in reservations)
                and all(not collides(a, b, position(path, tick), position(path, tick + 1),
                                     pedestrian_clearance, vertical_clearance) for path in pedestrians))

    queue = [(distances[start], 0, 0.0, 0, 0, start)]
    costs = {(start, 0): (0, 0.0)}
    previous = {}
    serial = itertools.count(1)
    while queue:
        budget.check()
        _, waits, length, _, tick, point = heapq.heappop(queue)
        if (waits, length) != costs[(point, tick)]:
            continue
        budget.explored += 1
        if point == goal and all(allowed(goal, goal, future)
                                 for future in range(tick, max(latest + 1, reserved_until + 1))):
            segments = []
            state = (point, tick)
            while state in previous:
                state, samples = previous[state]
                segments.append(samples)
            return [start] + [sample for samples in reversed(segments) for sample in samples]
        if tick >= horizon:
            continue
        for target in itertools.chain(neighbours(point, width, height, blocked, directions), [point]):
            if target not in distances or (corridor is not None and target not in corridor):
                continue
            durations = (1, 2) if allow_slowdown and target != point else (1,)
            for duration in durations:
                arrival = tick + duration
                if arrival + distances[target] > horizon:
                    continue
                # Half speed occupies the edge for two ticks. Fractional samples
                # retain the true position, rather than disguising slowing as waiting.
                samples = [point] + [tuple(a + (b - a) * step / duration for a, b in zip(point, target))
                                     for step in range(1, duration)] + [target]
                if not all(allowed(a, b, tick + step)
                           for step, (a, b) in enumerate(zip(samples, samples[1:]))):
                    continue
                new_length = length + math.dist(point, target)
                new_waits = waits + int(point == target)
                state = (target, arrival)
                new_cost = (new_waits, new_length)
                if new_cost < costs.get(state, (math.inf, math.inf)):
                    costs[state] = new_cost
                    previous[state] = ((point, tick), samples[1:])
                    heapq.heappush(queue, (arrival + distances[target], new_waits,
                                           new_length, next(serial), arrival, target))
    return []


def solve(agents, width, height, blocked, directions, clearance,
          method='cbs', horizon=400, seconds=8, allow_slowdown=False, vertical_clearance=1.2,
          pedestrians=(), pedestrian_clearance=None):
    begun = time.monotonic()
    budget = Budget(seconds)
    cbs_nodes = 0
    incumbent = None
    fallback = False
    try:
        heuristics = {}
        for agent in agents:
            goal = tuple(agent['goal'])
            if goal not in heuristics:
                heuristics[goal] = reverse_distances(goal, width, height, blocked, directions, budget)

        cache = {}

        def near_original_route(path):
            corridor = set(path)
            for point in path:
                frontier = {point}
                for _ in range(3):
                    frontier = {target for source in frontier
                                for target in neighbours(source, width, height, blocked, directions)}
                    corridor.update(frontier)
            return corridor

        original_routes = {}
        if pedestrians:
            for index, agent in enumerate(agents):
                route = space_time_path(tuple(agent['start']), tuple(agent['goal']), width, height,
                                        blocked, directions, frozenset(), horizon,
                                        heuristics[tuple(agent['goal'])], budget)
                original_routes[index] = near_original_route(route) if route else None

        def plan(index, constraints, reservations=()):
            agent = agents[index]
            key = (index, frozenset(constraints))
            if not reservations and key in cache:
                return cache[key]
            for corridor in ((original_routes[index], None) if pedestrians else (None,)):
                path = space_time_path(tuple(agent['start']), tuple(agent['goal']), width, height,
                                       blocked, directions, constraints, horizon,
                                       heuristics[tuple(agent['goal'])], budget,
                                       reservations, clearance, allow_slowdown,
                                       vertical_clearance, corridor, pedestrians,
                                       pedestrian_clearance)
                if path:
                    break
            if not reservations:
                cache[key] = path
            return path

        paths = []
        for index in range(len(agents)):
            path = plan(index, frozenset(), paths if method == 'priority' else ())
            if not path:
                return {'found': False, 'reason': '当前策略及时间步范围内未找到方案，请调整端点、规划顺序或时间上限。',
                        'explored': budget.explored, 'cbs_nodes': cbs_nodes}
            paths.append(path)
        if method == 'cbs':
            # Keep a verified feasible schedule available while CBS improves it.
            # This is especially useful when extra speed choices enlarge the tree.
            candidate = []
            for index in range(len(agents)):
                path = plan(index, frozenset(), candidate)
                if not path:
                    break
                candidate.append(path)
            if len(candidate) == len(agents) and first_conflict(candidate, clearance, budget, vertical_clearance) is None:
                incumbent = candidate
            counter = itertools.count()
            constraints = tuple(frozenset() for _ in agents)
            def score(trajectories):
                return (sum(len(path) - 1 for path in trajectories),
                        sum(a == b for path in trajectories for a, b in zip(path, path[1:])),
                        sum(math.dist(a, b) for path in trajectories for a, b in zip(path, path[1:])))

            queue = [(score(paths), next(counter), constraints, paths)]
            seen = {constraints}
            while queue:
                budget.check()
                if cbs_nodes >= 1000:
                    raise SearchLimit
                _, _, constraints, paths = heapq.heappop(queue)
                cbs_nodes += 1
                conflict = first_conflict(paths, clearance, budget, vertical_clearance)
                if conflict is None:
                    break
                i, j, tick, a, b, c, d = conflict
                for index, source, target in ((i, a, b), (j, c, d)):
                    child = list(constraints)
                    child[index] = child[index] | {(tick, source, target)}
                    child = tuple(child)
                    if child in seen:
                        continue
                    seen.add(child)
                    path = plan(index, child[index])
                    if path:
                        updated = list(paths)
                        updated[index] = path
                        heapq.heappush(queue, (score(updated), next(counter), child, updated))
            else:
                return {'found': False, 'reason': '当前时间步范围内未找到联合方案。',
                        'explored': budget.explored, 'cbs_nodes': cbs_nodes}
        # Independently verify the complete set of returned, goal-padded trajectories.
        if first_conflict(paths, clearance, budget, vertical_clearance):
            raise RuntimeError('轨迹安全检查未通过')
        if pedestrians and any(first_conflict([path, pedestrian],
                                                    pedestrian_clearance or clearance,
                                                    budget, vertical_clearance)
                               for path in paths for pedestrian in pedestrians):
            raise RuntimeError('行人避让检查未通过')
    except SearchLimit:
        if incumbent is None:
            return {'found': False, 'reason': '已达到规划计算上限，本次未找到方案。可减少机器人、增大计算时限或调整端点。',
                    'explored': budget.explored, 'cbs_nodes': cbs_nodes,
                    'planning_ms': round((time.monotonic() - begun) * 1000, 1)}
        paths = incumbent
        fallback = True
    results = []
    for agent, path in zip(agents, paths):
        step_distances = [math.dist(a, b) for a, b in zip(path, path[1:])]
        results.append({'id': agent['id'], 'path': path, 'arrival_step': len(path) - 1,
                        'wait_steps': sum(a == b for a, b in zip(path, path[1:])),
                        'slow_steps': sum(0 < max(abs(b[0] - a[0]), abs(b[1] - a[1])) < 1
                                          for a, b in zip(path, path[1:])),
                        'speed_profile_mps': [distance / math.sqrt(2) for distance in step_distances],
                        'distance_m': round(sum(step_distances), 2)})
    return {'found': True, 'agents': results, 'sum_arrival_steps': sum(len(p) - 1 for p in paths),
            'makespan_steps': max(len(p) - 1 for p in paths), 'conflicts': 0,
            'used_method': 'priority' if fallback else method,
            'warning': 'CBS 已达到计算上限，返回已验证的优先级可行方案，未证明最优。' if fallback else '',
            'explored': budget.explored, 'cbs_nodes': cbs_nodes,
            'planning_ms': round((time.monotonic() - begun) * 1000, 1)}
