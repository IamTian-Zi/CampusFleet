# Python 扩展试编译

`bindings.cpp` 用 pybind11 将 C++ API 暴露为 `campusfleet_native`。当前 `.pyd` 在 Windows / MSYS2 UCRT64 Python 3.14.7 + MinGW GCC 16.2 环境编译，并成功执行过一次导入和 `solve()` 调用。Python 服务已增加选择 C++ 后端的适配代码；是否成功加载可从 `/api/fleet`、`/api/path` 返回的 `planner_backend` 字段查看。`CAMPUSFLEET_PLANNER_BACKEND=python` 可强制原 Python 后端，`=cpp` 可要求必须加载 C++ 扩展；默认在扩展可加载时选 C++，否则回退 Python。此次接入尚未测试。

PowerShell 下的复现命令（根据本机 MSYS2 安装位置调整编译器路径）：

```powershell
python -m venv .venv-pybind
.\.venv-pybind\bin\python.exe -m pip install pybind11
cmake -S .\cpp\python -B .\cpp\python\build-mingw -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe -DPython_EXECUTABLE="$((Resolve-Path .\.venv-pybind\bin\python.exe).Path)"
cmake --build .\cpp\python\build-mingw --config Release -j 4
```

使用时把 `build-mingw` 加入 `sys.path`，再 `import campusfleet_native`。此 `.pyd` 与当前 CPython 3.14、64 位 MinGW UCRT 环境绑定；其他 Python 版本、MSVC Python 或不同架构需重新编译。MSYS2 Python 使用 PEP 668 环境保护，因此依赖安装在项目虚拟环境内。试验环境产生的 `.venv-pybind` 和中间构建文件不应并入源码版本管理。

模块目前暴露地图、节点、机器人、规划参数、结果对象，以及 `solve`、`find_static_path`、`inflate_obstacles`、`collides`。服务器适配会把校园 JSON 映射为 C++ 数据结构；任务室内段与行人随机轨迹仍由 Python 处理。
