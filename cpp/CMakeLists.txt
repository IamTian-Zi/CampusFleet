cmake_minimum_required(VERSION 3.16)
project(campusfleet_planner LANGUAGES CXX)

add_library(campusfleet_planner STATIC src/planner.cpp)
target_include_directories(campusfleet_planner PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(campusfleet_planner PUBLIC cxx_std_17)

if(MSVC)
    target_compile_options(campusfleet_planner PRIVATE /W4)
else()
    target_compile_options(campusfleet_planner PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(campusfleet_demo examples/demo.cpp)
target_link_libraries(campusfleet_demo PRIVATE campusfleet_planner)

include(CTest)
if(BUILD_TESTING)
    add_executable(campusfleet_native_tests tests/planner_tests.cpp)
    target_link_libraries(campusfleet_native_tests PRIVATE campusfleet_planner)
    add_test(NAME campusfleet_native_tests COMMAND campusfleet_native_tests)
endif()
