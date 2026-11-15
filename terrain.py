"""Layered road graph with a raised bridge, ramps and conservative headroom."""
import math
from collections import deque

from planner import MOVES, neighbours


class TerrainGraph:
    def __init__(self, data, blocked, directions, radius, height, margin, max_slope, deck_blocked=()):
        self.data, self.blocked, self.directions = data, blocked, directions
        self.bridge = data['bridge']
        self.radius, self.height, self.margin = radius, height, margin
        self.max_slope = max_slope
        self.cache = {}
        self.deck_blocked = set(deck_blocked)

    def surface_height(self, x):
        bridge = self.bridge
        if x < bridge['plateau_start']:
            return bridge['height'] * (x - bridge['start']) / (bridge['plateau_start'] - bridge['start'])
        if x > bridge['plateau_end']:
            return bridge['height'] * (bridge['end'] - x) / (bridge['end'] - bridge['plateau_end'])
        return bridge['height']

    def valid(self, point):
        x, y, z = point
        if not (0 <= x < self.data['width'] and 0 <= y < self.data['height']):
            return False
        bridge = self.bridge
        if z == 0:
            if (x, y) in self.blocked:
                return False
            # The ramp mouths connect to ground. Beneath the rest of the deck,
            # use the lowest underside over the entire circular footprint's box.
            if bridge['start'] < x < bridge['end'] and bridge['y_min'] - self.radius <= y <= bridge['y_max'] + self.radius:
                minimum = min(self.surface_height(max(bridge['start'], x - self.radius)),
                              self.surface_height(min(bridge['end'], x + self.radius)))
                return minimum - bridge['thickness'] >= self.height + self.margin
            return True
        if not (bridge['start'] <= x <= bridge['end'] and
                bridge['y_min'] + self.radius + self.margin <= y + .5 <= bridge['y_max'] + 1 - self.radius - self.margin):
            return False
        if abs(z - self.surface_height(x)) > 1e-8:
            return False
        if (x,y) in self.deck_blocked:
            return False
        if x < bridge['plateau_start'] or x > bridge['plateau_end']:
            slope = math.degrees(math.atan(bridge['height'] / (bridge['plateau_start'] - bridge['start'])))
            return slope <= self.max_slope
        return True

    def neighbours(self, point):
        if point in self.cache:
            return self.cache[point]
        x, y, z = point
        result = []
        if z == 0:
            result.extend((nx, ny, 0) for nx, ny in neighbours((x, y), self.data['width'], self.data['height'], self.blocked, self.directions)
                          if self.valid((nx, ny, 0)))
        bridge = self.bridge
        if bridge['start'] <= x <= bridge['end'] and bridge['y_min'] <= y <= bridge['y_max'] and abs(z - self.surface_height(x)) < 1e-8:
            for dx, dy in MOVES[:4]:
                nx, ny = x + dx, y + dy
                target = (nx, ny, self.surface_height(nx))
                if bridge['start'] <= nx <= bridge['end'] and self.valid(target):
                    result.append(target)
        self.cache[point] = tuple(dict.fromkeys(result))
        return self.cache[point]

    def reverse_distances(self, goal, budget):
        distances, queue = {goal: 0}, deque([goal])
        while queue:
            budget.check()
            target = queue.popleft()
            x, y, z = target
            candidates = []
            if z == 0:
                for dx, dy in MOVES:
                    source = (x + dx, y + dy, 0)
                    if source in distances or not self.valid(source):
                        continue
                    diagonal_blocked = dx and dy and ((x + dx, y) in self.blocked or (x, y + dy) in self.blocked)
                    legal = all(not direction or -dx * direction[0] - dy * direction[1] > 0
                                for direction in (self.directions.get((x, y)), self.directions.get(source[:2])))
                    if not diagonal_blocked and legal:
                        candidates.append(source)
            # Surface edges are bidirectional. Only test elevated predecessors,
            # since ground predecessors were handled directly above.
            for source in self.neighbours(target):
                if (z != 0 or source[2] != 0) and source not in distances and target in self.neighbours(source):
                    candidates.append(source)
            for source in candidates:
                if source not in distances:
                    distances[source] = distances[target] + 1
                    queue.append(source)
        return distances
