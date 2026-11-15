"""Regression checks for directions, swept collisions, persistent goals and HTTP inputs."""
import json
import math
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server
from terrain import TerrainGraph
from generate_map import generate
from planner import (Budget, collides, first_conflict, neighbours, road_directions,
                     solve, space_time_path, reverse_distances, SearchLimit)
from pedestrians import generate as generate_pedestrians


class PlannerTests(unittest.TestCase):
    def test_pedestrian_detour_preserves_clearance(self):
        agents = [{'id': '1', 'start': (0, 2), 'goal': (6, 2)}]
        pedestrian = [[(3, 2)] * 21]
        result = solve(agents, 8, 5, set(), {}, .8, method='priority',
                       horizon=20, seconds=2, allow_slowdown=True,
                       pedestrians=pedestrian, pedestrian_clearance=.8)
        self.assertTrue(result['found'], result)
        path = result['agents'][0]['path']
        self.assertNotIn((3, 2), path)
        self.assertIsNone(first_conflict([path, pedestrian[0]], .8))

    def test_generated_pedestrians_repeat_and_keep_clearance(self):
        args = (4, 7, 12, 20, 20, set(), {}, [(2, 2), (17, 17)], .8)
        paths = generate_pedestrians(*args)
        self.assertEqual(paths, generate_pedestrians(*args))
        self.assertEqual(len(paths), 4)
        self.assertTrue(all(len(path) == 13 for path in paths))
        self.assertIsNone(first_conflict(paths, .8))

    def test_layered_geometry_and_constraints(self):
        data = server.MAP
        blocked = server.inflated_map(data['cells'], .5)
        graph = TerrainGraph(data, blocked, road_directions(data), .3, 1, .2, 20)
        self.assertTrue(graph.valid((230,148,0)))
        self.assertTrue(graph.valid((230,148,6)))
        self.assertFalse(graph.valid((230,148,3)))
        self.assertFalse(graph.valid((188,148,0)))
        steep = TerrainGraph(data, blocked, road_directions(data), .3, 1, .2, 10)
        self.assertFalse(steep.valid((190,148,1)))
        low_bridge = {**data, 'bridge': {**data['bridge'], 'height': 1.5}}
        low = TerrainGraph(low_bridge, blocked, road_directions(data), .3, 1, .2, 20)
        self.assertFalse(low.valid((230,148,0)))
        self.assertIn((187,148,.25), graph.neighbours((186,148,0)))
        self.assertNotIn((210,148,6), graph.neighbours((210,148,0)))

    def test_vertical_collision_during_interval(self):
        self.assertFalse(collides((0,0,6),(2,0,6),(1,-1,0),(1,1,0),.8,1.2))
        self.assertTrue(collides((0,0,0),(2,0,2),(1,-1,0),(1,1,0),.8,1.2))

    def test_layered_presets(self):
        data = server.MAP
        blocked = server.inflated_map(data['cells'], .5)
        for scenario in data['scenarios']:
            if len(scenario['agents'][0]['start']) != 3:
                continue
            graph = TerrainGraph(data, blocked, road_directions(data), .3, 1, .2, 20)
            agents = [dict(agent,id=str(i+1)) for i,agent in enumerate(scenario['agents'])]
            result = solve(agents,data['width'],data['height'],blocked,graph,.8,
                           seconds=8,allow_slowdown=True,vertical_clearance=1.2)
            self.assertTrue(result['found'],result)
            self.assertIsNone(first_conflict([a['path'] for a in result['agents']],.8,vertical_clearance=1.2))
            for agent in result['agents']:
                self.assertTrue(all(speed <= 1+1e-8 for speed in agent['speed_profile_mps']))
                for point in agent['path']:
                    if point[0] == int(point[0]) and point[1] == int(point[1]):
                        self.assertTrue(graph.valid(tuple(point)),point)

    def test_swept_collision_types(self):
        self.assertTrue(collides((0, 0), (1, 1), (1, 0), (0, 1), .8))
        self.assertTrue(collides((0, 0), (1, 0), (1, 0), (0, 0), 0))
        self.assertTrue(collides((0, 0), (0, 0), (1, 0), (0, 0), .8))
        self.assertFalse(collides((0, 0), (1, 0), (0, 1), (1, 1), .8))
        self.assertTrue(collides((0, 0), (1, 0), (0, 1), (1, 1), 1.1))

    def test_no_corner_cutting(self):
        self.assertNotIn((1, 1), list(neighbours((0, 0), 3, 3, {(1, 0)}, {})))

    def test_direction_applies_on_entry_and_exit(self):
        directions = {(1, 1): (1, 0)}
        self.assertNotIn((1, 1), list(neighbours((2, 1), 3, 3, set(), directions)))
        self.assertNotIn((0, 1), list(neighbours((1, 1), 3, 3, set(), directions)))
        self.assertIn((2, 1), list(neighbours((1, 1), 3, 3, set(), directions)))

    def test_goal_occupancy_is_checked_after_arrival(self):
        paths = [[(0, 0), (1, 0)], [(3, 0), (2, 0), (1, 0)]]
        self.assertIsNotNone(first_conflict(paths, .8))
        budget = Budget(2)
        distances = reverse_distances((1, 0), 4, 2, set(), {}, budget)
        path = space_time_path((0, 0), (1, 0), 4, 2, set(), {},
                               {(3, (1, 0), (1, 0))}, 10, distances, budget)
        self.assertTrue(path)
        self.assertGreater(len(path) - 1, 3)

    def test_wait_required_in_cross_corridor(self):
        blocked = {(0, 0), (0, 2), (2, 0), (2, 2)}
        agents = [{'id': '1', 'start': (0, 1), 'goal': (2, 1)},
                  {'id': '2', 'start': (1, 0), 'goal': (1, 2)}]
        for method in ('cbs', 'priority'):
            result = solve(agents, 3, 3, blocked, {}, .8, method, 12, 2)
            self.assertTrue(result['found'], result)
            self.assertGreater(sum(a['wait_steps'] for a in result['agents']), 0)
            self.assertIsNone(first_conflict([a['path'] for a in result['agents']], .8))

    def test_closed_corridor_swap_has_no_solution_within_horizon(self):
        agents = [{'id': '1', 'start': (0, 0), 'goal': (2, 0)},
                  {'id': '2', 'start': (2, 0), 'goal': (0, 0)}]
        result = solve(agents, 3, 1, set(), {}, .8, horizon=5, seconds=2)
        self.assertFalse(result['found'])

    def test_half_speed_changes_motion_instead_of_inserting_wait(self):
        blocked = {(0, 0), (0, 2), (2, 0), (2, 2)}
        crossing = [[(1, 0), (1, 1), (1, 2)]]
        budget = Budget(2)
        distances = reverse_distances((2, 1), 3, 3, blocked, {}, budget)
        fixed = space_time_path((0, 1), (2, 1), 3, 3, blocked, {}, set(), 12,
                                distances, budget, crossing, .4)
        variable = space_time_path((0, 1), (2, 1), 3, 3, blocked, {}, set(), 12,
                                   distances, budget, crossing, .4, True)
        self.assertEqual(len(fixed), len(variable))
        self.assertTrue(any(a == b for a, b in zip(fixed, fixed[1:])))
        self.assertFalse(any(a == b for a, b in zip(variable, variable[1:])))
        self.assertIn((.5, 1), variable)
        self.assertIsNone(first_conflict([variable, crossing[0]], .4))

    def test_slow_action_obeys_intermediate_time_constraint(self):
        budget = Budget(2)
        distances = reverse_distances((1, 0), 2, 1, set(), {}, budget)
        constraints = {(0, (0, 0), (1, 0)), (1, (0, 0), (1, 0)),
                       (1, (.5, 0), (1, 0))}
        path = space_time_path((0, 0), (1, 0), 2, 1, set(), {}, constraints,
                               8, distances, budget, allow_slowdown=True)
        self.assertGreaterEqual(len(path) - 1, 3)
        for tick, (a, b) in enumerate(zip(path, path[1:])):
            self.assertNotIn((tick, a, b), constraints)

    def test_five_robots_with_speed_control(self):
        data = server.MAP
        scenario = next(s for s in data['scenarios'] if s['name'].startswith('窄道调速'))
        blocked = server.inflated_map(data['cells'], .5)
        agents = [dict(agent, id=str(i + 1)) for i, agent in enumerate(scenario['agents'])]
        for method in ('cbs', 'priority'):
            result = solve(agents, data['width'], data['height'], blocked,
                           road_directions(data), .8, method, seconds=8, allow_slowdown=True)
            self.assertTrue(result['found'], result)
            self.assertEqual(len(result['agents']), 5)
            self.assertIsNone(first_conflict([a['path'] for a in result['agents']], .8))
            self.assertGreater(sum(a['slow_steps'] for a in result['agents']), 0)
            for agent in result['agents']:
                self.assertEqual(len(agent['speed_profile_mps']), agent['arrival_step'])
                self.assertTrue(all(0 <= speed <= 1 + 1e-8 for speed in agent['speed_profile_mps']))
                self.assertAlmostEqual(sum(agent['speed_profile_mps']) * math.sqrt(2),
                                       agent['distance_m'], places=1)
                # A half-speed interval is a real intermediate position.
                for a, b in zip(agent['path'], agent['path'][1:]):
                    self.assertIn(max(abs(a[0] - b[0]), abs(a[1] - b[1])), (0, .5, 1))

    def test_limit_returns_verified_incumbent_with_warning(self):
        agents = [{'id': '1', 'start': (0, 1), 'goal': (2, 1)},
                  {'id': '2', 'start': (1, 0), 'goal': (1, 2)}]
        blocked = {(0, 0), (0, 2), (2, 0), (2, 2)}
        calls = 0

        def limited_check(paths, clearance, budget=None, vertical_clearance=1.2):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise SearchLimit
            return first_conflict(paths, clearance, budget)

        with patch('planner.first_conflict', side_effect=limited_check):
            result = solve(agents, 3, 3, blocked, {}, .4, allow_slowdown=True)
        self.assertTrue(result['found'])
        self.assertEqual(result['used_method'], 'priority')
        self.assertTrue(result['warning'])
        self.assertIsNone(first_conflict([a['path'] for a in result['agents']], .4))

    def test_all_presets_and_legacy_single_path(self):
        data = generate()
        self.assertEqual(data, server.MAP)
        blocked = server.inflated_map(data['cells'], .5)
        directions = road_directions(data)
        for scenario in data['scenarios']:
            if len(scenario['agents'][0]['start']) == 3:
                continue
            agents = [dict(agent, id=str(i + 1)) for i, agent in enumerate(scenario['agents'])]
            for agent in agents:
                self.assertNotIn(tuple(agent['start']), blocked)
                self.assertNotIn(tuple(agent['goal']), blocked)
            for method in ('cbs', 'priority'):
                with self.subTest(scenario=scenario['name'], method=method):
                    result = solve(agents, data['width'], data['height'], blocked,
                                   directions, .8, method, seconds=8)
                    self.assertTrue(result['found'], result)
                    paths = [a['path'] for a in result['agents']]
                    self.assertIsNone(first_conflict(paths, .8))
                    for agent, path in zip(agents, paths):
                        self.assertEqual(path[0], tuple(agent['start']))
                        self.assertEqual(path[-1], tuple(agent['goal']))
                        for a, b in zip(path, path[1:]):
                            self.assertNotIn(b, blocked)
                            self.assertTrue(a == b or b in neighbours(a, data['width'], data['height'], blocked, directions))
        path, _ = server.find_path(data['cells'], tuple(data['default_start']),
                                   tuple(data['default_goal']), blocked, directions)
        self.assertTrue(path)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def request(self, route, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + route, data=data,
                                         headers={'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(request, timeout=25)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_normal_endpoints(self):
        code, data = self.request('/api/map')
        self.assertEqual((code, data['width'], data['height']), (200, 420, 280))
        code, data = self.request('/api/path', {'start': [16, 34], 'goal': [100, 39]})
        self.assertEqual(code, 200)
        self.assertTrue(data['found'])
        code, data = self.request('/api/fleet', {'agents': server.MAP['default_agents']})
        self.assertEqual(code, 200)
        self.assertTrue(data['found'], data)
        self.assertEqual(len(data['agents']), 4)
        code, data = self.request('/api/fleet', {'agents': server.MAP['default_agents'], 'allow_slowdown': True})
        self.assertEqual(code, 200)
        self.assertTrue(data['found'], data)
        self.assertTrue(data['allow_slowdown'])
        self.assertIn('speed_profile_mps', data['agents'][0])
        scenario = next(s for s in server.MAP['scenarios'] if s['name'].startswith('立体校园'))
        code, data = self.request('/api/fleet', {'agents':scenario['agents'],'use_terrain':True,'allow_slowdown':True})
        self.assertEqual(code,200)
        self.assertTrue(data['found'],data)

    def test_layered_fleet_with_pedestrians(self):
        scenario = next(s for s in server.MAP['scenarios'] if s['name'].startswith('立体校园'))
        body = {'agents': scenario['agents'], 'use_terrain': True,
                'allow_slowdown': True, 'pedestrian_count': 4, 'pedestrian_seed': 1}
        code, result = self.request('/api/fleet', body)
        self.assertEqual(code, 200)
        self.assertTrue(result['found'], result)
        self.assertEqual(len(result['pedestrians']), 4)
        for agent in result['agents']:
            for pedestrian in result['pedestrians']:
                self.assertIsNone(first_conflict([agent['path'], pedestrian['path']], .75,
                                                  vertical_clearance=1.2))

    def test_invalid_payloads(self):
        valid = {'agents': server.MAP['default_agents']}
        invalid = [[], {'agents': []}, {**valid, 'radius': True},
                   {**valid, 'margin': float('nan')}, {**valid, 'max_steps': 1.5},
                   {**valid, 'time_limit_s': float('inf')}, {**valid, 'method': 'unknown'},
                   {**valid, 'allow_slowdown': 'true'},
                   {**valid, 'obstacles': [[999, 0]]},
                   {'agents': [{'start': [16, 34], 'goal': [100, 39]}] * 2}]
        for body in invalid:
            with self.subTest(body=body):
                code, result = self.request('/api/fleet', body)
                self.assertEqual(code, 400, result)
        code, result = self.request('/api/path', {'start': [-1, 2], 'goal': [16, 34]})
        self.assertEqual(code, 400)


if __name__ == '__main__':
    unittest.main()
