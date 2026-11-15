"""Seeded moving pedestrians on the ground-level walkable road graph."""
import random

from planner import collides, neighbours


def generate(count, seed, horizon, width, height, blocked, directions,
             robot_endpoints, clearance):
    rng = random.Random(seed)
    endpoints = {(point[0], point[1]) for point in robot_endpoints}
    candidates = [(x, y) for y in range(2, height - 2)
                  for x in range(2, width - 2)
                  if (x, y) not in blocked
                  and all(not collides((x, y), (x, y), endpoint, endpoint, clearance)
                          for endpoint in endpoints)]
    rng.shuffle(candidates)
    paths = []
    for candidate in candidates:
        if len(paths) == count:
            break
        if any(collides(candidate, candidate, path[0], path[0], clearance)
               for path in paths):
            continue
        paths.append([candidate])
    if len(paths) != count:
        raise ValueError('可供行人出发的道路不足')

    headings = [(0, 0)] * count
    for tick in range(horizon):
        for index, path in enumerate(paths):
            current = path[-1]
            options = [point for point in neighbours(current, width, height, blocked, directions)
                       if all(not collides(point, point, endpoint, endpoint, clearance)
                              for endpoint in endpoints)]
            rng.shuffle(options)
            options.sort(key=lambda point: (point[0] - current[0], point[1] - current[1])
                         != headings[index])
            options.append(current)
            for target in options:
                if all(not collides(current, target, other[tick], other[tick + 1], clearance)
                       for other in paths[:index]):
                    path.append(target)
                    headings[index] = (target[0] - current[0], target[1] - current[1])
                    break
            else:
                raise ValueError('行人之间无法保持安全间距，请更换随机种子或减少人数')
    return paths
