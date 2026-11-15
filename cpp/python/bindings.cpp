#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "campusfleet/planner.hpp"

namespace py = pybind11;
using namespace campusfleet;

PYBIND11_MODULE(campusfleet_native, module) {
    module.doc() = "CampusFleet native C++ path planner";

    py::class_<Point>(module, "Point")
        .def(py::init<>())
        .def(py::init<double, double, double>(), py::arg("x"), py::arg("y"), py::arg("z") = 0)
        .def_readwrite("x", &Point::x)
        .def_readwrite("y", &Point::y)
        .def_readwrite("z", &Point::z)
        .def("as_tuple", [](const Point& point) { return py::make_tuple(point.x, point.y, point.z); });

    py::class_<Node>(module, "Node")
        .def(py::init<>())
        .def(py::init<int, int, bool>(), py::arg("x"), py::arg("y"), py::arg("deck") = false)
        .def_readwrite("x", &Node::x)
        .def_readwrite("y", &Node::y)
        .def_readwrite("deck", &Node::deck);

    py::class_<Direction>(module, "Direction")
        .def(py::init<>())
        .def(py::init<int, int>())
        .def_readwrite("dx", &Direction::dx)
        .def_readwrite("dy", &Direction::dy);

    py::class_<Bridge>(module, "Bridge")
        .def(py::init<>())
        .def_readwrite("start", &Bridge::start)
        .def_readwrite("end", &Bridge::end)
        .def_readwrite("plateau_start", &Bridge::plateau_start)
        .def_readwrite("plateau_end", &Bridge::plateau_end)
        .def_readwrite("y_min", &Bridge::y_min)
        .def_readwrite("y_max", &Bridge::y_max)
        .def_readwrite("height", &Bridge::height)
        .def_readwrite("thickness", &Bridge::thickness);

    py::class_<GridMap>(module, "GridMap")
        .def(py::init<>())
        .def_readwrite("width", &GridMap::width)
        .def_readwrite("height", &GridMap::height)
        .def_readwrite("resolution_m", &GridMap::resolution_m)
        .def_readwrite("blocked", &GridMap::blocked)
        .def_readwrite("directions", &GridMap::directions)
        .def_readwrite("deck_blocked", &GridMap::deck_blocked)
        .def_readwrite("layered", &GridMap::layered)
        .def_readwrite("bridge", &GridMap::bridge)
        .def_readwrite("radius", &GridMap::radius)
        .def_readwrite("robot_height", &GridMap::robot_height)
        .def_readwrite("margin", &GridMap::margin)
        .def_readwrite("max_slope_deg", &GridMap::max_slope_deg);

    py::class_<Agent>(module, "Agent")
        .def(py::init<>())
        .def(py::init<std::string, Node, Node>(), py::arg("id"), py::arg("start"), py::arg("goal"))
        .def_readwrite("id", &Agent::id)
        .def_readwrite("start", &Agent::start)
        .def_readwrite("goal", &Agent::goal);

    py::enum_<Method>(module, "Method")
        .value("CBS", Method::Cbs)
        .value("PRIORITY", Method::Priority)
        .export_values();

    py::class_<Options>(module, "Options")
        .def(py::init<>())
        .def_readwrite("method", &Options::method)
        .def_readwrite("horizon", &Options::horizon)
        .def_readwrite("time_limit_s", &Options::time_limit_s)
        .def_readwrite("robot_clearance", &Options::robot_clearance)
        .def_readwrite("pedestrian_clearance", &Options::pedestrian_clearance)
        .def_readwrite("vertical_clearance", &Options::vertical_clearance)
        .def_readwrite("allow_slowdown", &Options::allow_slowdown);

    py::class_<AgentResult>(module, "AgentResult")
        .def_readonly("id", &AgentResult::id)
        .def_readonly("path", &AgentResult::path)
        .def_readonly("arrival_step", &AgentResult::arrival_step)
        .def_readonly("wait_steps", &AgentResult::wait_steps)
        .def_readonly("slow_steps", &AgentResult::slow_steps)
        .def_readonly("distance_m", &AgentResult::distance_m)
        .def_readonly("speed_profile_mps", &AgentResult::speed_profile_mps);

    py::class_<StaticPathResult>(module, "StaticPathResult")
        .def_readonly("found", &StaticPathResult::found)
        .def_readonly("path", &StaticPathResult::path)
        .def_readonly("explored", &StaticPathResult::explored);

    py::class_<DStarLite>(module, "DStarLite")
        .def(py::init<const GridMap&, Node, Node>(), py::arg("map"), py::arg("start"), py::arg("goal"))
        .def("move_start", &DStarLite::move_start, py::arg("start"))
        .def("set_blocked", &DStarLite::set_blocked, py::arg("x"), py::arg("y"), py::arg("blocked"))
        .def("plan", &DStarLite::plan);

    py::class_<Result>(module, "Result")
        .def_readonly("found", &Result::found)
        .def_readonly("reason", &Result::reason)
        .def_readonly("used_method", &Result::used_method)
        .def_readonly("warning", &Result::warning)
        .def_readonly("agents", &Result::agents)
        .def_readonly("sum_arrival_steps", &Result::sum_arrival_steps)
        .def_readonly("makespan_steps", &Result::makespan_steps)
        .def_readonly("explored", &Result::explored)
        .def_readonly("cbs_nodes", &Result::cbs_nodes)
        .def_readonly("planning_ms", &Result::planning_ms);

    module.def("solve", [](const GridMap& map, const std::vector<Agent>& agents,
                            const Options& options, const std::vector<Path>& pedestrians) {
        return campusfleet::solve(map, agents, options, pedestrians);
    }, py::arg("map"), py::arg("agents"), py::arg("options"), py::arg("pedestrians") = std::vector<Path>{});

    module.def("find_static_path", &find_static_path, py::arg("map"), py::arg("start"), py::arg("goal"));
    module.def("inflate_obstacles", &inflate_obstacles, py::arg("map"), py::arg("clearance_m"));
    module.def("collides", &collides, py::arg("a"), py::arg("b"), py::arg("c"), py::arg("d"),
               py::arg("clearance"), py::arg("vertical_clearance") = 1.2);
}
