#include "campusfleet/planner.hpp"

#include <iostream>
#include <vector>

int main() {
    using namespace campusfleet;
    GridMap map;
    map.width = 3;
    map.height = 3;
    map.blocked.assign(map.width * map.height, 0);
    // A narrow crossing makes the two robots coordinate their passage.
    for (int index : {0, 2, 6, 8}) map.blocked[index] = 1;

    std::vector<Agent> agents{{"R1", {0, 1, false}, {2, 1, false}},
                              {"R2", {1, 0, false}, {1, 2, false}}};
    Options options;
    options.method = Method::Cbs;
    options.allow_slowdown = true;
    options.horizon = 12;
    Result result = solve(map, agents, options);
    if (!result.found) {
        std::cerr << "Planning failed: " << result.reason << '\n';
        return 1;
    }
    for (const AgentResult& robot : result.agents) {
        std::cout << robot.id << " arrival=" << robot.arrival_step
                  << " waits=" << robot.wait_steps << " slow=" << robot.slow_steps << " path:";
        for (Point point : robot.path) std::cout << " (" << point.x << ',' << point.y << ',' << point.z << ')';
        std::cout << '\n';
    }
    std::cout << "Method=" << (result.used_method == Method::Cbs ? "CBS" : "priority")
              << " explored=" << result.explored << " planning_ms=" << result.planning_ms << '\n';
}
