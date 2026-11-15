"""Three-floor indoor demonstration shared by every campus building."""

from math import dist
import random

CAPACITY = 8
TRAVEL = 3
FLOORS = 3
GOALS = ((6, 4, 3), (24, 4, 3))
STARTS = ((14, 13, 1), (16, 13, 1))


def car_at(tick):
    phase = tick % 27
    if phase <= 5:
        return 1, '开门', 0
    if phase <= 8:
        return 1 + (phase - 5) / TRAVEL, '上行', 1
    if phase <= 11:
        return 2, '开门', 0
    if phase <= 14:
        return 2 + (phase - 11) / TRAVEL, '上行', 1
    if phase <= 17:
        return 3, '开门', 0
    if phase <= 20:
        return 3 - (phase - 17) / TRAVEL, '下行', -1
    if phase <= 23:
        return 2, '开门', 0
    return 2 - (phase - 23) / 3, '下行', -1


def walk(path, target, corridor_first=False):
    x, y, floor = path[-1]
    tx, ty, _ = target
    if corridor_first:
        while x != tx:
            x += 1 if tx > x else -1
            path.append((x, y, floor))
    while y != ty:
        y += 1 if ty > y else -1
        path.append((x, y, floor))
    while x != tx:
        x += 1 if tx > x else -1
        path.append((x, y, floor))


def stairs(index, shaft):
    path = [STARTS[index]]
    walk(path, (shaft, 9, 1))
    for step in range(1, 13):
        path.append((shaft, 9, 1 + step / 6))
    walk(path, GOALS[index], corridor_first=True)
    return path


def elevator_run(crowd, riders, seed, start_tick=0):
    """Pedestrians board first; robots take two of the eight available places."""
    rng = random.Random(seed)
    people = [{'origin': 1, 'destination': rng.choice((2, 3)),
               'arrival': rng.randrange(4), 'boarded': False, 'finished': False}
              for _ in range(crowd)]
    for _ in range(crowd // 4):
        origin = rng.choice((2, 3))
        destination = rng.choice([floor for floor in (1, 2, 3) if floor != origin])
        people.append({'origin': origin, 'destination': destination,
                       'arrival': rng.randrange(8), 'boarded': False, 'finished': False})
    aboard_people = []
    aboard_robots = []
    boarded = {}
    arrived = {}
    timeline = []
    lobby_arrival = {index: 4 + abs(STARTS[index][0] - 15) for index in riders}
    for tick in range(240):
        global_tick = tick + start_tick
        floor, phase, direction = car_at(global_tick)
        if phase == '开门':
            for person in aboard_people[:]:
                if person['destination'] == floor:
                    person['finished'] = True
                    aboard_people.remove(person)
        if floor == 3 and phase == '开门':
            for index in aboard_robots:
                arrived[index] = tick
            aboard_robots.clear()
        if phase == '开门':
            direction = 1 if global_tick % 27 in range(0, 12) else -1
            for person in people:
                if (not person['boarded'] and person['arrival'] <= tick
                        and person['origin'] == floor
                        and (person['destination'] - floor) * direction > 0
                        and len(aboard_people) + 2 * len(aboard_robots) < CAPACITY):
                    person['boarded'] = True
                    aboard_people.append(person)
        if floor == 1 and phase == '开门':
            for index in sorted(riders):
                if (index not in boarded and tick >= lobby_arrival[index]
                        and len(aboard_people) + 2 * (len(aboard_robots) + 1) <= CAPACITY):
                    boarded[index] = tick
                    aboard_robots.append(index)
        timeline.append({'floor': round(floor, 3), 'phase': phase,
                         'direction': direction, 'people': len(aboard_people),
                         'robots': [index + 1 for index in aboard_robots],
                         'waiting_people': sum(not person['boarded'] and not person['finished']
                                               and person['origin'] == 1 and person['arrival'] <= tick
                                               for person in people),
                         'free_places': CAPACITY - len(aboard_people) - 2 * len(aboard_robots)})
    return timeline, boarded, arrived


def elevator_path(index, timeline, boarded, arrived):
    path = [STARTS[index]]
    walk(path, (15, 9, 1))
    if len(path) - 1 > boarded:
        raise ValueError('电梯到达时机器人尚未抵达候梯区')
    path.extend([(15, 9, 1)] * (boarded - len(path) + 1))
    for tick in range(boarded + 1, arrived + 1):
        path.append((15, 9, timeline[tick]['floor']))
    walk(path, GOALS[index], corridor_first=True)
    return path


def plan(building, crowd, can_climb, buildings, seed=1,
         active_indices=(0, 1), start_tick=0):
    if building not in buildings:
        raise ValueError('未知建筑')
    if type(crowd) is not int or not 0 <= crowd <= 30:
        raise ValueError('候梯行人数量必须为 0 到 30 的整数')
    if type(can_climb) is not bool:
        raise ValueError('爬楼梯参数必须是布尔值')
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError('随机种子必须为非负整数')
    if not active_indices or any(index not in (0, 1) for index in active_indices):
        raise ValueError('室内机器人编号无效')
    if type(start_tick) is not int or start_tick < 0:
        raise ValueError('室内开始时间步无效')

    stair_options = [[(name, stairs(index, shaft)) for name, shaft in (('楼梯 A', 3), ('楼梯 B', 27))]
                     for index in range(2)]
    chosen_stairs = [min(options, key=lambda item: len(item[1])) for options in stair_options]
    riders = set(active_indices)
    while True:
        timeline, boarded, arrived = elevator_run(crowd, riders, seed, start_tick)
        switch = {index for index in riders if can_climb and
                  (index not in arrived or
                   arrived[index] + abs(GOALS[index][0] - 15) + 5 > len(chosen_stairs[index][1]) - 1)}
        if not switch:
            break
        riders -= switch
    timeline, boarded, arrived = elevator_run(crowd, riders, seed, start_tick)
    results = []
    for index in active_indices:
        if index in riders:
            path = elevator_path(index, timeline, boarded[index], arrived[index])
            route = '电梯'
        else:
            route, path = chosen_stairs[index]
        results.append({'id': index + 1, 'route': route, 'path': path,
                        'arrival_step': len(path) - 1,
                        'distance_m': round(sum(dist(a, b) for a, b in zip(path, path[1:])), 2),
                        'board_step': boarded.get(index)})
    return {'building': building, 'floors': FLOORS, 'capacity': CAPACITY,
            'crowd': crowd, 'can_climb': can_climb, 'robots': results,
            'elevator': timeline, 'makespan_steps': max(robot['arrival_step'] for robot in results)}
