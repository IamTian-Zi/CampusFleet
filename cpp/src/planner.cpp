#include "campusfleet/planner.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <deque>
#include <iomanip>
#include <limits>
#include <map>
#include <optional>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace campusfleet {
namespace {

constexpr double eps = 1e-8;
constexpr std::array<Direction, 8> moves{{{1, 0}, {-1, 0}, {0, 1}, {0, -1},
                                           {1, 1}, {1, -1}, {-1, 1}, {-1, -1}}};

bool same(Point a, Point b) {
    return std::abs(a.x - b.x) < eps && std::abs(a.y - b.y) < eps &&
           std::abs(a.z - b.z) < eps;
}

Point lerp(Point a, Point b, double fraction) {
    return {a.x + (b.x - a.x) * fraction,
            a.y + (b.y - a.y) * fraction,
            a.z + (b.z - a.z) * fraction};
}

double distance(Point a, Point b) {
    return std::hypot(std::hypot(a.x - b.x, a.y - b.y), a.z - b.z);
}

Point position(const Path& path, int tick) {
    return path[std::min<std::size_t>(static_cast<std::size_t>(tick), path.size() - 1)];
}

struct NodeLess {
    bool operator()(Node a, Node b) const {
        return std::tie(a.x, a.y, a.deck) < std::tie(b.x, b.y, b.deck);
    }
};

class Graph {
public:
    explicit Graph(const GridMap& map) : map_(map) {}

    bool inside(int x, int y) const {
        return x >= 0 && y >= 0 && x < map_.width && y < map_.height;
    }

    bool blocked(int x, int y) const {
        return !inside(x, y) || map_.blocked[index(x, y)] != 0;
    }

    Point point(Node node) const {
        return {static_cast<double>(node.x), static_cast<double>(node.y),
                node.deck ? surface_height(node.x) : 0.0};
    }

    bool valid(Node node) const {
        if (!inside(node.x, node.y)) return false;
        if (!node.deck) {
            if (blocked(node.x, node.y)) return false;
            if (map_.layered && node.x > map_.bridge.start && node.x < map_.bridge.end &&
                node.y >= map_.bridge.y_min - map_.radius &&
                node.y <= map_.bridge.y_max + map_.radius) {
                double low = std::min(surface_height(std::max<double>(map_.bridge.start, node.x - map_.radius)),
                                      surface_height(std::min<double>(map_.bridge.end, node.x + map_.radius)));
                return low - map_.bridge.thickness >= map_.robot_height + map_.margin;
            }
            return true;
        }
        if (!map_.layered || node.x <= map_.bridge.start || node.x >= map_.bridge.end ||
            node.y < map_.bridge.y_min || node.y > map_.bridge.y_max ||
            node.y + .5 < map_.bridge.y_min + map_.radius + map_.margin ||
            node.y + .5 > map_.bridge.y_max + 1 - map_.radius - map_.margin ||
            (!map_.deck_blocked.empty() && map_.deck_blocked[index(node.x, node.y)])) return false;
        if (node.x < map_.bridge.plateau_start || node.x > map_.bridge.plateau_end) {
            double rise = map_.bridge.height /
                          static_cast<double>(map_.bridge.plateau_start - map_.bridge.start);
            double slope = std::atan(rise) * 180.0 / std::acos(-1.0);
            return slope <= map_.max_slope_deg;
        }
        return true;
    }

    std::vector<Node> neighbours(Node node) const {
        std::vector<Node> result;
        if (!node.deck) {
            for (Direction move : moves) {
                Node target{node.x + move.dx, node.y + move.dy, false};
                if (!valid(target)) continue;
                if (move.dx && move.dy &&
                    (blocked(node.x + move.dx, node.y) || blocked(node.x, node.y + move.dy))) continue;
                Direction from = direction(node.x, node.y);
                Direction to = direction(target.x, target.y);
                if ((from.dx || from.dy) && move.dx * from.dx + move.dy * from.dy <= 0) continue;
                if ((to.dx || to.dy) && move.dx * to.dx + move.dy * to.dy <= 0) continue;
                result.push_back(target);
            }
        }
        if (map_.layered && node.x >= map_.bridge.start && node.x <= map_.bridge.end &&
            node.y >= map_.bridge.y_min && node.y <= map_.bridge.y_max &&
            std::abs(point(node).z - surface_height(node.x)) < eps) {
            for (int i = 0; i < 4; ++i) {
                Node target{node.x + moves[i].dx, node.y + moves[i].dy, true};
                if (target.x < map_.bridge.start || target.x > map_.bridge.end) continue;
                if (std::abs(surface_height(target.x)) < eps) target.deck = false;
                if (valid(target) && std::find(result.begin(), result.end(), target) == result.end())
                    result.push_back(target);
            }
        }
        return result;
    }

    std::vector<Node> predecessors(Node target) const {
        std::vector<Node> result;
        for (Direction move : moves) {
            for (bool deck : {false, true}) {
                Node source{target.x + move.dx, target.y + move.dy, deck};
                if (!valid(source)) continue;
                auto next = neighbours(source);
                if (std::find(next.begin(), next.end(), target) != next.end()) result.push_back(source);
            }
        }
        return result;
    }

private:
    const GridMap& map_;

    std::size_t index(int x, int y) const {
        return static_cast<std::size_t>(y) * map_.width + x;
    }

    Direction direction(int x, int y) const {
        return map_.directions.empty() ? Direction{} : map_.directions[index(x, y)];
    }

    double surface_height(double x) const {
        const Bridge& bridge = map_.bridge;
        if (x < bridge.plateau_start)
            return bridge.height * (x - bridge.start) / (bridge.plateau_start - bridge.start);
        if (x > bridge.plateau_end)
            return bridge.height * (bridge.end - x) / (bridge.end - bridge.plateau_end);
        return bridge.height;
    }
};

struct SearchLimit {};

class Budget {
public:
    explicit Budget(double seconds)
        : deadline_(std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds)) {}

    void check() const {
        if (std::chrono::steady_clock::now() > deadline_ || explored >= 500000) throw SearchLimit{};
    }

    std::size_t explored = 0;

private:
    std::chrono::time_point<std::chrono::steady_clock, std::chrono::duration<double>> deadline_;
};

using Distances = std::map<Node, int, NodeLess>;

Distances reverse_distances(const Graph& graph, Node goal, Budget& budget) {
    Distances distances{{goal, 0}};
    std::deque<Node> queue{goal};
    while (!queue.empty()) {
        budget.check();
        Node target = queue.front();
        queue.pop_front();
        for (Node source : graph.predecessors(target)) {
            if (distances.emplace(source, distances.at(target) + 1).second) queue.push_back(source);
        }
    }
    return distances;
}

struct Constraint {
    int tick;
    Point from;
    Point to;
};

using Constraints = std::vector<Constraint>;
using Corridor = std::set<Node, NodeLess>;

struct State {
    Node node;
    int tick;
};

struct StateLess {
    bool operator()(const State& a, const State& b) const {
        return std::tie(a.node.x, a.node.y, a.node.deck, a.tick) <
               std::tie(b.node.x, b.node.y, b.node.deck, b.tick);
    }
};

struct Cost {
    int waits;
    double length;
};

bool better(Cost a, Cost b) {
    return a.waits < b.waits || (a.waits == b.waits && a.length < b.length - 1e-10);
}

struct QueueEntry {
    int estimate;
    Cost cost;
    std::size_t serial;
    State state;
};

struct QueueGreater {
    bool operator()(const QueueEntry& a, const QueueEntry& b) const {
        return std::tie(a.estimate, a.cost.waits, a.cost.length, a.serial) >
               std::tie(b.estimate, b.cost.waits, b.cost.length, b.serial);
    }
};

struct Previous {
    State parent;
    std::vector<Point> samples;
};

Path space_time_path(const Graph& graph, Node start, Node goal, const Distances& distances,
                     const Constraints& constraints, int horizon, Budget& budget,
                     const std::vector<Path>& reservations, const std::vector<Path>& pedestrians,
                     double clearance, double pedestrian_clearance, double vertical_clearance,
                     bool allow_slowdown, const Corridor* corridor) {
    if (!distances.count(start)) return {};
    int latest = -1, reserved_until = 0;
    for (const auto& constraint : constraints) latest = std::max(latest, constraint.tick);
    for (const auto& path : reservations) reserved_until = std::max(reserved_until, static_cast<int>(path.size()) - 1);
    for (const auto& path : pedestrians) reserved_until = std::max(reserved_until, static_cast<int>(path.size()) - 1);

    auto allowed = [&](Point a, Point b, int tick) {
        for (const auto& constraint : constraints)
            if (constraint.tick == tick && same(a, constraint.from) && same(b, constraint.to)) return false;
        for (const auto& path : reservations)
            if (collides(a, b, position(path, tick), position(path, tick + 1), clearance, vertical_clearance)) return false;
        for (const auto& path : pedestrians)
            if (collides(a, b, position(path, tick), position(path, tick + 1), pedestrian_clearance, vertical_clearance)) return false;
        return true;
    };

    std::priority_queue<QueueEntry, std::vector<QueueEntry>, QueueGreater> queue;
    std::map<State, Cost, StateLess> costs;
    std::map<State, Previous, StateLess> previous;
    State initial{start, 0};
    costs[initial] = {0, 0};
    queue.push({distances.at(start), {0, 0}, 0, initial});
    std::size_t serial = 1;
    while (!queue.empty()) {
        budget.check();
        QueueEntry current = queue.top();
        queue.pop();
        auto found = costs.find(current.state);
        if (found == costs.end() || current.cost.waits != found->second.waits ||
            std::abs(current.cost.length - found->second.length) > 1e-10) continue;
        ++budget.explored;
        Node node = current.state.node;
        int tick = current.state.tick;
        if (node == goal) {
            Point at_goal = graph.point(goal);
            bool safe = true;
            for (int future = tick; future < std::max(latest + 1, reserved_until + 1); ++future) {
                budget.check();
                if (!allowed(at_goal, at_goal, future)) { safe = false; break; }
            }
            if (safe) {
                std::vector<std::vector<Point>> segments;
                State state = current.state;
                while (true) {
                    auto prev = previous.find(state);
                    if (prev == previous.end()) break;
                    segments.push_back(prev->second.samples);
                    state = prev->second.parent;
                }
                Path path{graph.point(start)};
                for (auto it = segments.rbegin(); it != segments.rend(); ++it)
                    path.insert(path.end(), it->begin(), it->end());
                return path;
            }
        }
        if (tick >= horizon) continue;
        auto next = graph.neighbours(node);
        next.push_back(node);
        for (Node target : next) {
            auto heuristic = distances.find(target);
            if (heuristic == distances.end() || (corridor && !corridor->count(target))) continue;
            for (int duration = 1; duration <= ((allow_slowdown && !(target == node)) ? 2 : 1); ++duration) {
                int arrival = tick + duration;
                if (arrival + heuristic->second > horizon) continue;
                Point from = graph.point(node), to = graph.point(target);
                std::vector<Point> samples{from};
                for (int step = 1; step <= duration; ++step)
                    samples.push_back(lerp(from, to, static_cast<double>(step) / duration));
                bool safe = true;
                for (int step = 0; step < duration; ++step) {
                    if (!allowed(samples[step], samples[step + 1], tick + step)) { safe = false; break; }
                }
                if (!safe) continue;
                State state{target, arrival};
                Cost cost{current.cost.waits + static_cast<int>(target == node),
                          current.cost.length + distance(from, to)};
                auto old = costs.find(state);
                if (old != costs.end() && !better(cost, old->second)) continue;
                costs[state] = cost;
                previous[state] = {current.state, {samples.begin() + 1, samples.end()}};
                queue.push({arrival + heuristic->second, cost, serial++, state});
            }
        }
    }
    return {};
}

Corridor near_route(const Graph& graph, const Path& path) {
    Corridor corridor;
    Corridor frontier;
    for (Point point : path) {
        if (std::abs(point.x - std::round(point.x)) > eps ||
            std::abs(point.y - std::round(point.y)) > eps) continue;
        Node node{static_cast<int>(point.x), static_cast<int>(point.y), point.z > eps};
        corridor.insert(node);
        frontier.insert(node);
    }
    for (int radius = 0; radius < 3; ++radius) {
        Corridor next;
        for (Node node : frontier)
            for (Node target : graph.neighbours(node)) next.insert(target);
        corridor.insert(next.begin(), next.end());
        frontier = std::move(next);
    }
    return corridor;
}

struct Conflict {
    int i, j, tick;
    Point a, b, c, d;
};

std::optional<Conflict> first_conflict(const std::vector<Path>& paths, double clearance,
                                       double vertical_clearance, Budget* budget = nullptr) {
    std::size_t max_size = 0;
    for (const auto& path : paths) max_size = std::max(max_size, path.size());
    for (std::size_t tick = 0; tick < max_size; ++tick) {
        if (budget) budget->check();
        for (std::size_t i = 0; i < paths.size(); ++i) {
            for (std::size_t j = i + 1; j < paths.size(); ++j) {
                Point a = position(paths[i], static_cast<int>(tick));
                Point b = position(paths[i], static_cast<int>(tick + 1));
                Point c = position(paths[j], static_cast<int>(tick));
                Point d = position(paths[j], static_cast<int>(tick + 1));
                if (collides(a, b, c, d, clearance, vertical_clearance))
                    return Conflict{static_cast<int>(i), static_cast<int>(j), static_cast<int>(tick), a, b, c, d};
            }
        }
    }
    return std::nullopt;
}

std::string constraint_key(const Constraint& c) {
    std::ostringstream out;
    out << c.tick << ':' << std::setprecision(17) << c.from.x << ',' << c.from.y << ',' << c.from.z
        << '>' << c.to.x << ',' << c.to.y << ',' << c.to.z;
    return out.str();
}

using ConstraintSets = std::vector<std::set<std::string>>;

std::string node_key(const ConstraintSets& sets) {
    std::string key;
    for (const auto& set : sets) {
        key += '[';
        for (const auto& item : set) key += item + ';';
        key += ']';
    }
    return key;
}

struct CbsNode {
    std::vector<Constraints> constraints;
    ConstraintSets keys;
    std::vector<Path> paths;
    int arrivals = 0;
    int waits = 0;
    double length = 0;
    std::size_t serial = 0;
};

void score(CbsNode& node) {
    node.arrivals = 0;
    node.waits = 0;
    node.length = 0;
    for (const auto& path : node.paths) {
        node.arrivals += static_cast<int>(path.size()) - 1;
        for (std::size_t i = 1; i < path.size(); ++i) {
            node.waits += same(path[i - 1], path[i]);
            node.length += distance(path[i - 1], path[i]);
        }
    }
}

struct CbsGreater {
    bool operator()(const CbsNode& a, const CbsNode& b) const {
        return std::tie(a.arrivals, a.waits, a.length, a.serial) >
               std::tie(b.arrivals, b.waits, b.length, b.serial);
    }
};

void validate(const GridMap& map, const std::vector<Agent>& agents, const Options& options,
              const std::vector<Path>& pedestrians, const Graph& graph) {
    if (map.width <= 0 || map.height <= 0 || map.resolution_m <= 0 ||
        map.blocked.size() != static_cast<std::size_t>(map.width) * map.height ||
        (!map.directions.empty() && map.directions.size() != map.blocked.size()) ||
        (!map.deck_blocked.empty() && map.deck_blocked.size() != map.blocked.size()))
        throw std::invalid_argument("Invalid grid dimensions or arrays");
    if (map.layered && !(map.bridge.start < map.bridge.plateau_start &&
                         map.bridge.plateau_start <= map.bridge.plateau_end &&
                         map.bridge.plateau_end < map.bridge.end &&
                         map.bridge.y_min <= map.bridge.y_max && map.bridge.height > 0))
        throw std::invalid_argument("Invalid bridge geometry");
    if (agents.empty() || agents.size() > 10 || options.horizon < 1 || options.horizon > 800 ||
        !std::isfinite(options.time_limit_s) || options.time_limit_s <= 0 ||
        !std::isfinite(options.robot_clearance) || options.robot_clearance < 0 ||
        !std::isfinite(options.pedestrian_clearance) || options.pedestrian_clearance < 0 ||
        !std::isfinite(options.vertical_clearance) || options.vertical_clearance <= 0)
        throw std::invalid_argument("Invalid agents or planning options");
    for (const auto& agent : agents)
        if (!graph.valid(agent.start) || !graph.valid(agent.goal))
            throw std::invalid_argument("Robot endpoint is not traversable");
    for (std::size_t i = 0; i < agents.size(); ++i)
        for (std::size_t j = i + 1; j < agents.size(); ++j)
            for (bool start : {true, false}) {
                Point a = graph.point(start ? agents[i].start : agents[i].goal);
                Point b = graph.point(start ? agents[j].start : agents[j].goal);
                if (collides(a, a, b, b, options.robot_clearance, options.vertical_clearance))
                    throw std::invalid_argument("Robot starts or goals overlap");
            }
    for (const auto& path : pedestrians)
        if (path.empty()) throw std::invalid_argument("Pedestrian path is empty");
}

}  // namespace

bool collides(Point a, Point b, Point c, Point d, double clearance, double vertical_clearance) {
    double lower = 0, upper = 1;
    double height = a.z - c.z;
    double change = b.z - a.z - d.z + c.z;
    if (std::abs(change) < 1e-12) {
        if (std::abs(height) >= vertical_clearance) return false;
    } else {
        double first = (-vertical_clearance - height) / change;
        double second = (vertical_clearance - height) / change;
        lower = std::max(lower, std::min(first, second));
        upper = std::min(upper, std::max(first, second));
        if (lower >= upper) return false;
    }
    Point aa = lerp(a, b, lower), bb = lerp(a, b, upper);
    Point cc = lerp(c, d, lower), dd = lerp(c, d, upper);
    double rx = aa.x - cc.x, ry = aa.y - cc.y;
    double vx = bb.x - aa.x - dd.x + cc.x;
    double vy = bb.y - aa.y - dd.y + cc.y;
    double speed = vx * vx + vy * vy;
    double fraction = speed > 0 ? std::clamp(-(rx * vx + ry * vy) / speed, 0.0, 1.0) : 0.0;
    double closest = std::hypot(rx + fraction * vx, ry + fraction * vy);
    return closest < eps || closest < clearance - eps;
}

bool has_conflict(const std::vector<Path>& paths, double clearance, double vertical_clearance) {
    for (const auto& path : paths)
        if (path.empty()) throw std::invalid_argument("Path is empty");
    return first_conflict(paths, clearance, vertical_clearance).has_value();
}

StaticPathResult find_static_path(const GridMap& map, Node start, Node goal) {
    Graph graph(map);
    validate(map, {{"static", start, goal}}, Options{}, {}, graph);
    auto heuristic = [&](Node node) {
        double dx = std::abs(node.x - goal.x), dy = std::abs(node.y - goal.y);
        return std::max(dx, dy) + (std::sqrt(2.0) - 1) * std::min(dx, dy);
    };
    struct Entry { double estimate, cost; std::size_t serial; Node node; };
    auto greater = [](const Entry& a, const Entry& b) {
        return std::tie(a.estimate, a.cost, a.serial) >
               std::tie(b.estimate, b.cost, b.serial);
    };
    std::priority_queue<Entry, std::vector<Entry>, decltype(greater)> queue(greater);
    std::map<Node, double, NodeLess> costs{{start, 0}};
    std::map<Node, Node, NodeLess> previous;
    queue.push({heuristic(start), 0, 0, start});
    StaticPathResult result;
    std::size_t serial = 1;
    while (!queue.empty()) {
        Entry current = queue.top();
        queue.pop();
        if (current.cost > costs.at(current.node) + 1e-9) continue;
        ++result.explored;
        if (current.node == goal) {
            std::vector<Node> nodes{goal};
            while (previous.count(nodes.back())) nodes.push_back(previous.at(nodes.back()));
            for (auto it = nodes.rbegin(); it != nodes.rend(); ++it) result.path.push_back(graph.point(*it));
            result.found = true;
            return result;
        }
        for (Node target : graph.neighbours(current.node)) {
            double next_cost = current.cost + distance(graph.point(current.node), graph.point(target));
            auto old = costs.find(target);
            if (old != costs.end() && next_cost >= old->second - 1e-9) continue;
            costs[target] = next_cost;
            previous[target] = current.node;
            queue.push({next_cost + heuristic(target), next_cost, serial++, target});
        }
    }
    return result;
}

struct DStarLite::Impl {
    struct Key { double first, second; };
    struct Entry { Key key; std::size_t generation; Node node; };
    struct Greater {
        bool operator()(const Entry& a, const Entry& b) const {
            return std::tie(a.key.first, a.key.second, a.generation) >
                   std::tie(b.key.first, b.key.second, b.generation);
        }
    };
    GridMap map;
    Graph graph;
    Node start, goal;
    double km = 0;
    std::map<Node, double, NodeLess> g, rhs;
    std::map<Node, std::size_t, NodeLess> generations;
    std::priority_queue<Entry, std::vector<Entry>, Greater> queue;
    std::size_t explored = 0;
    static constexpr double infinity = std::numeric_limits<double>::infinity();

    Impl(const GridMap& source, Node from, Node to)
        : map(source), graph(map), start(from), goal(to) {
        validate(map, {{"dstar", start, goal}}, Options{}, {}, graph);
        rhs[goal] = 0;
        push(goal);
    }
    double value(const std::map<Node, double, NodeLess>& values, Node node) const {
        auto it = values.find(node);
        return it == values.end() ? infinity : it->second;
    }
    double heuristic(Node a, Node b) const { return distance(graph.point(a), graph.point(b)); }
    Key key(Node node) const {
        double minimum = std::min(value(g, node), value(rhs, node));
        return {minimum + heuristic(start, node) + km, minimum};
    }
    static bool less(Key a, Key b) {
        return a.first < b.first - eps ||
               (std::abs(a.first - b.first) <= eps && a.second < b.second - eps);
    }
    void push(Node node) { queue.push({key(node), ++generations[node], node}); }
    void update(Node node) {
        if (!(node == goal)) {
            double best = infinity;
            if (graph.valid(node)) for (Node next : graph.neighbours(node))
                best = std::min(best, heuristic(node, next) + value(g, next));
            rhs[node] = best;
        } else rhs[node] = graph.valid(goal) ? 0 : infinity;
        ++generations[node];
        if (value(g, node) != value(rhs, node)) push(node);
    }
    void discard_stale() {
        while (!queue.empty() && queue.top().generation != generations[queue.top().node]) queue.pop();
    }
    void compute() {
        explored = 0;
        discard_stale();
        while ((!queue.empty() && less(queue.top().key, key(start))) ||
               value(rhs, start) != value(g, start)) {
            if (queue.empty()) break;
            if (++explored > static_cast<std::size_t>(map.width) * map.height * 80)
                throw std::runtime_error("D* Lite expansion limit exceeded");
            Entry item = queue.top(); queue.pop();
            Key newer = key(item.node);
            if (less(item.key, newer)) push(item.node);
            else if (value(g, item.node) > value(rhs, item.node)) {
                g[item.node] = value(rhs, item.node);
                for (Node predecessor : graph.predecessors(item.node)) update(predecessor);
            } else {
                g[item.node] = infinity;
                update(item.node);
                for (Node predecessor : graph.predecessors(item.node)) update(predecessor);
            }
            discard_stale();
        }
    }
    StaticPathResult plan() {
        compute();
        StaticPathResult result;
        result.explored = explored;
        if (!graph.valid(start) || !graph.valid(goal) || !std::isfinite(value(g, start))) return result;
        Node current = start;
        std::set<Node, NodeLess> visited;
        result.path.push_back(graph.point(current));
        while (!(current == goal)) {
            if (!visited.insert(current).second || visited.size() > static_cast<std::size_t>(map.width) * map.height * 2)
                return result;
            double best = infinity;
            std::optional<Node> choice;
            for (Node next : graph.neighbours(current)) {
                double candidate = heuristic(current, next) + value(g, next);
                if (candidate < best - eps) { best = candidate; choice = next; }
            }
            if (!choice || !std::isfinite(best)) { result.path.clear(); return result; }
            current = *choice;
            result.path.push_back(graph.point(current));
        }
        result.found = true;
        return result;
    }
    void set_blocked(int x, int y, bool blocked) {
        if (!graph.inside(x, y)) throw std::out_of_range("D* Lite cell outside map");
        auto& cell = map.blocked[static_cast<std::size_t>(y) * map.width + x];
        if (cell == static_cast<unsigned char>(blocked)) return;
        cell = blocked ? 1 : 0;
        for (int yy = y - 2; yy <= y + 2; ++yy)
            for (int xx = x - 2; xx <= x + 2; ++xx)
                if (graph.inside(xx, yy)) for (bool deck : {false, true})
                    if (!deck || map.layered) update({xx, yy, deck});
    }
};

DStarLite::DStarLite(const GridMap& map, Node start, Node goal)
    : impl_(std::make_unique<Impl>(map, start, goal)) {}
DStarLite::~DStarLite() = default;
DStarLite::DStarLite(DStarLite&&) noexcept = default;
DStarLite& DStarLite::operator=(DStarLite&&) noexcept = default;
void DStarLite::move_start(Node start) {
    if (!impl_->graph.valid(start)) throw std::invalid_argument("D* Lite start is blocked");
    impl_->km += impl_->heuristic(impl_->start, start);
    impl_->start = start;
}
void DStarLite::set_blocked(int x, int y, bool blocked) { impl_->set_blocked(x, y, blocked); }
StaticPathResult DStarLite::plan() { return impl_->plan(); }

std::vector<unsigned char> inflate_obstacles(const GridMap& map, double clearance_m) {
    if (map.width <= 0 || map.height <= 0 || map.resolution_m <= 0 ||
        map.blocked.size() != static_cast<std::size_t>(map.width) * map.height ||
        !std::isfinite(clearance_m) || clearance_m < 0)
        throw std::invalid_argument("Invalid map or inflation clearance");
    std::vector<unsigned char> result = map.blocked;
    int reach = static_cast<int>(std::ceil(clearance_m / map.resolution_m)) + 1;
    auto index = [&](int x, int y) { return static_cast<std::size_t>(y) * map.width + x; };
    for (int y = 0; y < map.height; ++y) {
        for (int x = 0; x < map.width; ++x) {
            if (!map.blocked[index(x, y)]) continue;
            for (int dy = -reach; dy <= reach; ++dy) {
                for (int dx = -reach; dx <= reach; ++dx) {
                    int nx = x + dx, ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= map.width || ny >= map.height) continue;
                    double gap_x = std::max(std::abs(dx) - 1, 0) * map.resolution_m;
                    double gap_y = std::max(std::abs(dy) - 1, 0) * map.resolution_m;
                    if (std::hypot(gap_x, gap_y) < clearance_m - 1e-9)
                        result[index(nx, ny)] = 1;
                }
            }
        }
    }
    if (clearance_m > 0) {
        for (int y = 0; y < map.height; ++y)
            for (int x = 0; x < map.width; ++x)
                if (std::min({x, y, map.width - 1 - x, map.height - 1 - y}) * map.resolution_m
                    < clearance_m - 1e-9) result[index(x, y)] = 1;
    }
    return result;
}

Result solve(const GridMap& map, const std::vector<Agent>& agents, const Options& options,
             const std::vector<Path>& pedestrians) {
    auto begun = std::chrono::steady_clock::now();
    Graph graph(map);
    validate(map, agents, options, pedestrians, graph);
    Budget budget(options.time_limit_s);
    Result result;
    result.used_method = options.method;
    std::vector<Path> paths, incumbent;
    auto elapsed_ms = [&] {
        return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begun).count();
    };
    auto failure = [&](std::string reason) {
        result.reason = std::move(reason);
        result.explored = budget.explored;
        result.planning_ms = elapsed_ms();
        return result;
    };
    try {
        std::map<Node, Distances, NodeLess> heuristics;
        for (const auto& agent : agents)
            if (!heuristics.count(agent.goal)) heuristics[agent.goal] = reverse_distances(graph, agent.goal, budget);
        std::vector<std::optional<Corridor>> corridors(agents.size());
        if (!pedestrians.empty()) {
            for (std::size_t i = 0; i < agents.size(); ++i) {
                Path original = space_time_path(graph, agents[i].start, agents[i].goal,
                    heuristics.at(agents[i].goal), {}, options.horizon, budget, {}, {},
                    0, 0, options.vertical_clearance, false, nullptr);
                if (!original.empty()) corridors[i] = near_route(graph, original);
            }
        }
        auto plan = [&](std::size_t i, const Constraints& constraints, const std::vector<Path>& reservations) {
            const auto& agent = agents[i];
            auto run = [&](const Corridor* corridor) {
                return space_time_path(graph, agent.start, agent.goal, heuristics.at(agent.goal),
                    constraints, options.horizon, budget, reservations, pedestrians,
                    options.robot_clearance, options.pedestrian_clearance,
                    options.vertical_clearance, options.allow_slowdown, corridor);
            };
            if (corridors[i]) {
                Path path = run(&*corridors[i]);
                if (!path.empty()) return path;
            }
            return run(nullptr);
        };
        for (std::size_t i = 0; i < agents.size(); ++i) {
            Path path = plan(i, {}, options.method == Method::Priority ? paths : std::vector<Path>{});
            if (path.empty()) return failure("No route within the strategy and time horizon");
            paths.push_back(std::move(path));
        }
        if (options.method == Method::Cbs) {
            for (std::size_t i = 0; i < agents.size(); ++i) {
                Path path = plan(i, {}, incumbent);
                if (path.empty()) break;
                incumbent.push_back(std::move(path));
            }
            if (incumbent.size() != agents.size() ||
                first_conflict(incumbent, options.robot_clearance, options.vertical_clearance, &budget))
                incumbent.clear();
            CbsNode root;
            root.constraints.resize(agents.size());
            root.keys.resize(agents.size());
            root.paths = paths;
            score(root);
            std::priority_queue<CbsNode, std::vector<CbsNode>, CbsGreater> queue;
            queue.push(root);
            std::set<std::string> seen{node_key(root.keys)};
            std::size_t serial = 1;
            bool solved = false;
            while (!queue.empty()) {
                budget.check();
                if (result.cbs_nodes >= 1000) throw SearchLimit{};
                CbsNode node = queue.top();
                queue.pop();
                ++result.cbs_nodes;
                auto conflict = first_conflict(node.paths, options.robot_clearance,
                                               options.vertical_clearance, &budget);
                if (!conflict) { paths = std::move(node.paths); solved = true; break; }
                for (auto [index, from, to] : {std::tuple<int, Point, Point>{conflict->i, conflict->a, conflict->b},
                                               {conflict->j, conflict->c, conflict->d}}) {
                    CbsNode child = node;
                    Constraint constraint{conflict->tick, from, to};
                    if (!child.keys[index].insert(constraint_key(constraint)).second) continue;
                    child.constraints[index].push_back(constraint);
                    if (!seen.insert(node_key(child.keys)).second) continue;
                    Path path = plan(index, child.constraints[index], {});
                    if (path.empty()) continue;
                    child.paths[index] = std::move(path);
                    child.serial = serial++;
                    score(child);
                    queue.push(std::move(child));
                }
            }
            if (!solved) return failure("No joint route within the time horizon");
        }
        if (first_conflict(paths, options.robot_clearance, options.vertical_clearance, &budget))
            throw std::runtime_error("Robot trajectory safety check failed");
        for (const auto& path : paths)
            for (const auto& pedestrian : pedestrians)
                if (first_conflict({path, pedestrian}, options.pedestrian_clearance,
                                   options.vertical_clearance, &budget))
                    throw std::runtime_error("Pedestrian trajectory safety check failed");
    } catch (const SearchLimit&) {
        if (incumbent.empty()) return failure("Planning limit reached without a verified route");
        paths = std::move(incumbent);
        result.used_method = Method::Priority;
        result.warning = "CBS limit reached; returning a verified priority route, not a proven optimum";
    }
    result.found = true;
    for (std::size_t i = 0; i < agents.size(); ++i) {
        const Path& path = paths[i];
        AgentResult item;
        item.id = agents[i].id;
        item.path = path;
        item.arrival_step = static_cast<int>(path.size()) - 1;
        double length = 0;
        for (std::size_t step = 1; step < path.size(); ++step) {
            Point a = path[step - 1], b = path[step];
            double segment = distance(a, b) * map.resolution_m;
            length += segment;
            item.wait_steps += same(a, b);
            double delta = std::max(std::abs(b.x - a.x), std::abs(b.y - a.y));
            item.slow_steps += delta > eps && delta < 1 - eps;
            item.speed_profile_mps.push_back(segment / (std::sqrt(2.0) * map.resolution_m));
        }
        item.distance_m = std::round(length * 100) / 100;
        result.sum_arrival_steps += item.arrival_step;
        result.makespan_steps = std::max(result.makespan_steps, item.arrival_step);
        result.agents.push_back(std::move(item));
    }
    result.explored = budget.explored;
    result.planning_ms = elapsed_ms();
    return result;
}

}  // namespace campusfleet
