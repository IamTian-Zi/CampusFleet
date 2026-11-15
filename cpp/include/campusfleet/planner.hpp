#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace campusfleet {

struct Point {
    double x = 0;
    double y = 0;
    double z = 0;
};

// Grid nodes have integer x/y. A raised bridge node has deck=true; its z is
// derived from Bridge. Ramp mouths at z=0 are shared with ground nodes.
struct Node {
    int x = 0;
    int y = 0;
    bool deck = false;

    bool operator==(const Node& other) const noexcept {
        return x == other.x && y == other.y && deck == other.deck;
    }
};

struct Direction {
    int dx = 0;
    int dy = 0;
};

struct Bridge {
    int start = 0;
    int end = 0;
    int plateau_start = 0;
    int plateau_end = 0;
    int y_min = 0;
    int y_max = 0;
    double height = 0;
    double thickness = 0;
};

struct GridMap {
    int width = 0;
    int height = 0;
    double resolution_m = 1;
    // Flat row-major arrays, each with width*height entries.
    std::vector<unsigned char> blocked;
    std::vector<Direction> directions;
    std::vector<unsigned char> deck_blocked;
    bool layered = false;
    Bridge bridge;
    double radius = .3;
    double robot_height = 1;
    double margin = .2;
    double max_slope_deg = 20;
};

struct Agent {
    std::string id;
    Node start;
    Node goal;
};

enum class Method { Cbs, Priority };

struct Options {
    Method method = Method::Cbs;
    int horizon = 400;
    double time_limit_s = 8;
    double robot_clearance = .8;
    double pedestrian_clearance = .75;
    double vertical_clearance = 1.2;
    bool allow_slowdown = false;
};

using Path = std::vector<Point>;

struct StaticPathResult {
    bool found = false;
    Path path;
    std::size_t explored = 0;
};

// Single-agent geometric A*, without time reservations or moving obstacles.
StaticPathResult find_static_path(const GridMap& map, Node start, Node goal);

// Incremental single-robot geometric replanning for changed map cells.
// Moving agents and time reservations remain the responsibility of solve().
class DStarLite {
public:
    DStarLite(const GridMap& map, Node start, Node goal);
    ~DStarLite();
    DStarLite(DStarLite&&) noexcept;
    DStarLite& operator=(DStarLite&&) noexcept;
    DStarLite(const DStarLite&) = delete;
    DStarLite& operator=(const DStarLite&) = delete;
    void move_start(Node start);
    void set_blocked(int x, int y, bool blocked);
    StaticPathResult plan();
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// Inflate map.blocked by a physical robot radius plus margin. The returned
// array can replace map.blocked before planning, leaving the source map intact.
std::vector<unsigned char> inflate_obstacles(const GridMap& map, double clearance_m);

struct AgentResult {
    std::string id;
    Path path;
    int arrival_step = 0;
    int wait_steps = 0;
    int slow_steps = 0;
    double distance_m = 0;
    std::vector<double> speed_profile_mps;
};

struct Result {
    bool found = false;
    std::string reason;
    Method used_method = Method::Cbs;
    std::string warning;
    std::vector<AgentResult> agents;
    int sum_arrival_steps = 0;
    int makespan_steps = 0;
    std::size_t explored = 0;
    int cbs_nodes = 0;
    double planning_ms = 0;
};

// Inputs are validated and copied only by the caller. No Python/HTTP dependency.
// Pedestrian paths are precomputed: one position per time step, then the final
// position remains occupied. This mirrors the current Python planner boundary.
Result solve(const GridMap& map, const std::vector<Agent>& agents,
             const Options& options, const std::vector<Path>& pedestrians = {});

bool collides(Point a, Point b, Point c, Point d,
              double clearance, double vertical_clearance = 1.2);
bool has_conflict(const std::vector<Path>& paths, double clearance,
                  double vertical_clearance = 1.2);

}  // namespace campusfleet
