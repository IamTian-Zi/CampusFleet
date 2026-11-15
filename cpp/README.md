# CampusFleet C++ 规划核心

此目录是独立的 C++17 静态库。它将原 `planner.py`、`terrain.py` 及 `server.py` 中单车 A* 的核心路径规则迁移到原生代码：八方向道路与双端单向约束、禁止斜向穿角、障碍膨胀、桥面坡道和净高、静态 A*、时空搜索、等待与半速、CBS／优先级规划、连续线段碰撞检查、机器人到达后持续占用终点，以及输入的行人轨迹避让。行人随机轨迹生成器、室内楼梯电梯和订单调度仍由 Python 服务负责。

新增 `DStarLite` 类，保留 `g/rhs` 搜索状态，支持 `move_start` 和 `set_blocked` 后增量重规划。它用于单机器人道路状态变化演示；移动行人和多机器人时空避碰继续使用 `solve()`。服务提供 `/dstar` 演示页与 `/api/dstar/sessions` 接口。

## 构建与独立运行

在此目录执行：

```powershell
cmake -S . -B build-mingw -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe
cmake --build build-mingw --config Release
ctest --test-dir build-mingw -C Release --output-on-failure
```

`campusfleet_demo` 展示两个机器人在交叉路口调度。实际使用时创建 `GridMap`，填充行优先的 `blocked` 数组，可选 `directions`、`deck_blocked` 和 `Bridge`。调用 `find_static_path(map, start, goal)` 获取单车静态 A* 路径，或调用 `solve(map, agents, options, pedestrian_paths)` 获取多车时序路线。行人轨迹由调用方预先给出；每条轨迹末尾位置会持续占用。`solve` 对无路可达或达到计算上限返回 `found=false`，无效输入抛出 `std::invalid_argument`。`used_method=Priority` 且 `warning` 非空表示 CBS 到达上限后使用已验证的优先级可行解。

坐标以格为单位，`GridMap::resolution_m` 将轨迹长度换算成米。一个时间步取 `sqrt(2) * resolution_m` 秒；`speed_profile_mps` 是逐步速度。桥面状态由 `Node::deck` 指定，桥面高度由几何参数推导。`inflate_obstacles` 接收原始阻塞数组和米单位安全余量，返回供规划使用的新数组。

目前库提供 C++ 源码与静态库，并没有 Python 绑定。以后可给它增加 pybind11 或稳定 C ABI；编译成库后仍需绑定层，Python 才能调用。当前也没有直接读取 `campus_map.json` 的适配器，地图数据需由独立调用方填入 `GridMap`。不要把原 Python 任务流程的测试结果当作 C++ 规划器的验证。
