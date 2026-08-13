# Builds the hlap server dll: Valve's Half-Life SDK plus the sources in src/.
#
# The SDK is not vendored. Clone it next to this repository and point HLSDK_DIR
# at it, then build 32-bit -- GoldSrc will not load anything else.
#
#   cmake -S game -B build -A Win32 -DHLSDK_DIR=../halflife
#   cmake --build build --config Release

cmake_minimum_required(VERSION 3.20)
project(hlap CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(HLSDK_DIR "" CACHE PATH "Path to a checkout of ValveSoftware/halflife")
if(NOT HLSDK_DIR OR NOT EXISTS "${HLSDK_DIR}/dlls")
    message(FATAL_ERROR
        "Set HLSDK_DIR to a checkout of https://github.com/ValveSoftware/halflife")
endif()

if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "GoldSrc loads a 32-bit dll. Configure with -A Win32.")
endif()

# Our own sources. Globbed rather than listed because this set is still growing;
# reconfigure after adding a file.
file(GLOB AP_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")

# The SDK's own server sources. Kept whole: this is the shipped game's logic and
# the point of the exercise is not to reimplement it.
file(GLOB SDK_SOURCES CONFIGURE_DEPENDS
    "${HLSDK_DIR}/dlls/*.cpp"
    "${HLSDK_DIR}/game_shared/*.cpp"
    "${HLSDK_DIR}/pm_shared/*.c")

add_library(hl SHARED ${SDK_SOURCES} ${AP_SOURCES})

target_include_directories(hl PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${HLSDK_DIR}/dlls"
    "${HLSDK_DIR}/engine"
    "${HLSDK_DIR}/common"
    "${HLSDK_DIR}/public"
    "${HLSDK_DIR}/pm_shared"
    "${HLSDK_DIR}/game_shared")

target_compile_definitions(hl PRIVATE CLIENT_WEAPONS VALVE_DLL _CRT_SECURE_NO_WARNINGS)

# The engine loads `hl.dll` by name, whatever the mod folder is called.
set_target_properties(hl PROPERTIES OUTPUT_NAME "hl" PREFIX "")
