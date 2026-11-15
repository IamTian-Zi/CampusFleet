cmake_minimum_required(VERSION 3.18)
project(campusfleet_native LANGUAGES CXX)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
execute_process(
    COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
find_package(pybind11 CONFIG REQUIRED)

add_library(campusfleet_core STATIC ../src/planner.cpp)
target_include_directories(campusfleet_core PUBLIC ../include)
target_compile_features(campusfleet_core PUBLIC cxx_std_17)

pybind11_add_module(campusfleet_native bindings.cpp)
target_link_libraries(campusfleet_native PRIVATE campusfleet_core)
