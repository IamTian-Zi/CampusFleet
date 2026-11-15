#include "campusfleet/planner.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace campusfleet;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

GridMap blank(int width, int height) {
    GridMap map;
    map.width = width;
    map.height = height;
    map.blocked.assign(width * height, 0);
    return map;
}

void collision_geometry() {
    require(collides({0, 0, 0}, {1, 1, 0}, {1, 0, 0}, {0, 1, 0}, .8), "diagonal swap");
    require(!collides({0, 0, 6}, {2, 0, 6}, {1, -1, 0}, {1, 1, 0}, .8), "bridge separation");
    require(collides({0, 0, 0}, {2, 0, 2}, {1, -1, 0}, {1, 1, 0}, .8), "ramp crossing");
    require(has_conflict({{{0, 0, 0}, {1, 0, 0}},
                          {{3, 0, 0}, {2, 0, 0}, {1, 0, 0}}}, .8), "persistent goal");
}

void one_way_and_corner() {
    GridMap map = blank(3, 1);
    map.directions.assign(3, {});
    map.directions[1] = {1, 0};
    Options options;
    options.method = Method::Priority;
    options.horizon = 8;
    require(find_static_path(map, {1, 0}, {2, 0}).found, "static A* east");
    require(!find_static_path(map, {2, 0}, {1, 0}).found, "static A* one-way");
    require(solve(map, {{"east", {1, 0}, {2, 0}}}, options).found, "one-way departure");
    require(!solve(map, {{"west", {2, 0}, {1, 0}}}, options).found, "one-way entry");

    map = blank(2, 2);
    map.blocked[1] = 1;
    map.blocked[2] = 1;
    require(!find_static_path(map, {0, 0}, {1, 1}).found, "static A* corner");
    require(!solve(map, {{"corner", {0, 0}, {1, 1}}}, options).found, "corner cutting");
}

void crossing_and_horizon() {
    GridMap map = blank(3, 3);
    for (int index : {0, 2, 6, 8}) map.blocked[index] = 1;
    std::vector<Agent> agents{{"a", {0, 1}, {2, 1}}, {"b", {1, 0}, {1, 2}}};
    for (Method method : {Method::Cbs, Method::Priority}) {
        Options options;
        options.method = method;
        options.horizon = 12;
        Result result = solve(map, agents, options);
        require(result.found, "crossing route");
        require(!has_conflict({result.agents[0].path, result.agents[1].path}, .8), "crossing clearance");
        require(result.agents[0].wait_steps + result.agents[1].wait_steps > 0, "crossing wait");
    }
    map = blank(3, 1);
    Options options;
    options.horizon = 5;
    require(!solve(map, {{"a", {0, 0}, {2, 0}}, {"b", {2, 0}, {0, 0}}}, options).found,
            "closed swap must fail");
}

void pedestrian_slowdown() {
    GridMap map = blank(3, 3);
    for (int index : {0, 2, 6, 8}) map.blocked[index] = 1;
    Options options;
    options.method = Method::Priority;
    options.horizon = 12;
    options.robot_clearance = .4;
    options.pedestrian_clearance = .4;
    options.allow_slowdown = true;
    Path pedestrian{{1, 0, 0}, {1, 1, 0}, {1, 2, 0}};
    Result result = solve(map, {{"robot", {0, 1}, {2, 1}}}, options, {pedestrian});
    require(result.found, "pedestrian route");
    require(result.agents[0].slow_steps > 0, "real half-speed samples");
    require(!has_conflict({result.agents[0].path, pedestrian}, .4), "pedestrian clearance");
}

void five_robot_schedule() {
    GridMap map = blank(9, 9);
    std::vector<Agent> agents{{"east", {0, 4}, {8, 4}},
                              {"west", {8, 4}, {0, 4}},
                              {"south", {4, 0}, {4, 8}},
                              {"north", {4, 8}, {4, 0}},
                              {"diagonal", {0, 0}, {8, 8}}};
    Options options;
    options.method = Method::Priority;
    options.horizon = 35;
    options.allow_slowdown = true;
    Result result = solve(map, agents, options);
    require(result.found && result.agents.size() == 5, "five robot schedule");
    std::vector<Path> paths;
    for (const auto& robot : result.agents) {
        require(robot.arrival_step == static_cast<int>(robot.speed_profile_mps.size()), "speed samples");
        for (double speed : robot.speed_profile_mps) require(speed <= 1 + 1e-8, "speed limit");
        paths.push_back(robot.path);
    }
    require(!has_conflict(paths, .8), "five robot clearance");
}

void bridge_and_inflation() {
    GridMap map = blank(9, 5);
    map.blocked.assign(45, 1);
    map.blocked[2 * 9 + 1] = 0;
    map.blocked[2 * 9 + 7] = 0;
    map.layered = true;
    map.bridge = {1, 7, 3, 5, 2, 3, 2, .2};
    map.radius = .1;
    map.margin = 0;
    map.max_slope_deg = 50;
    Options options;
    options.method = Method::Priority;
    options.horizon = 15;
    Result result = solve(map, {{"bridge", {1, 2}, {7, 2}}}, options);
    require(result.found, "raised bridge route");
    require(find_static_path(map, {1, 2}, {7, 2}).found, "static A* bridge");
    bool raised = false;
    for (Point point : result.agents[0].path) raised |= point.z > 1;
    require(raised, "bridge height in path");

    GridMap small = blank(5, 5);
    small.blocked[2 * 5 + 2] = 1;
    auto inflated = inflate_obstacles(small, 1.1);
    require(inflated[2 * 5 + 1] && inflated[1 * 5 + 1], "obstacle inflation");
    require(!small.blocked[2 * 5 + 1], "source map unchanged");
}

void incremental_replanning() {
    GridMap map = blank(12, 5);
    DStarLite planner(map, {0, 2}, {11, 2});
    auto original = planner.plan();
    require(original.found, "D* Lite initial route");
    planner.set_blocked(5, 2, true);
    auto detour = planner.plan();
    require(detour.found, "D* Lite detour");
    for (Point point : detour.path)
        require(!(point.x == 5 && point.y == 2), "D* Lite avoids new obstacle");
    map.blocked[2 * 12 + 5] = 1;
    auto fresh = find_static_path(map, {0, 2}, {11, 2});
    require(fresh.found && detour.path.size() == fresh.path.size(), "D* Lite matches fresh A*");
    planner.move_start({2, 2});
    planner.set_blocked(5, 2, false);
    auto restored = planner.plan();
    require(restored.found && restored.path.front().x == 2 && restored.path.back().x == 11,
            "D* Lite moving start and reopened road");
}

int main() {
    try {
        collision_geometry();
        one_way_and_corner();
        crossing_and_horizon();
        pedestrian_slowdown();
        five_robot_schedule();
        bridge_and_inflation();
        incremental_replanning();
        std::cout << "CampusFleet native planner checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "CampusFleet native planner check failed: " << error.what() << '\n';
        return 1;
    }
}
