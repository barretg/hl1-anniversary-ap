# Builds hlap.dll, the Valve Server Plugin for Half-Life: Source.
#
# Headers come from Valve's Source SDK 2013 at the last commit that still had
# the singleplayer tree (sp/), whose interface versions match HL:S exactly. The
# SDK is not vendored; clone it next to this repository:
#
#   git clone https://github.com/ValveSoftware/source-sdk-2013.git ../source-sdk-2013
#   git -C ../source-sdk-2013 checkout 0d8dceea
#
# HL:S is 32-bit. From Linux, with the repo's clang-cl toolchain:
#
#   cmake -S hl-source/plugin -B build/hlsource -G Ninja \
#         -DCMAKE_TOOLCHAIN_FILE=game/toolchain-clangcl-x86.cmake \
#         -DSOURCESDK_DIR=../source-sdk-2013
#   cmake --build build/hlsource
#
# The result is staged at hl-source/mod/files/addons/hlap.dll.

cmake_minimum_required(VERSION 3.20)
project(hlap_source CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(SOURCESDK_DIR "" CACHE PATH "Path to a checkout of ValveSoftware/source-sdk-2013")
set(SDK "${SOURCESDK_DIR}/sp/src")
if(NOT SOURCESDK_DIR OR NOT EXISTS "${SDK}/public/engine/iserverplugin.h")
    message(FATAL_ERROR
        "Set SOURCESDK_DIR to a source-sdk-2013 checkout at commit 0d8dceea "
        "(the last one with sp/)")
endif()
if(NOT MSVC OR CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "HL:S loads a 32-bit MSVC-ABI dll; use clang-cl or MSVC, Win32")
endif()

add_library(hlap SHARED
    src/plugin.cpp
    src/vtable_hook.cpp
    src/log.cpp)

target_include_directories(hlap PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${SDK}/public"
    "${SDK}/public/tier0"
    "${SDK}/public/tier1")

target_compile_definitions(hlap PRIVATE
    _WIN32 WIN32 _WINDOWS COMPILER_MSVC COMPILER_MSVC32 _CRT_SECURE_NO_WARNINGS
    _ALLOW_KEYWORD_MACROS NOMINMAX)

# tier0 only: Msg and Warning, imported from the engine's tier0.dll.
target_link_libraries(hlap PRIVATE "${SDK}/lib/public/tier0.lib")

# Valve's headers are 2013 MSVC C++; keep their warnings out of ours.
target_compile_options(hlap PRIVATE -Wno-everything)

set_target_properties(hlap PROPERTIES OUTPUT_NAME "hlap" PREFIX "")
# Static CRT, for the reason given in game/CMakeLists.txt.
set_property(TARGET hlap PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")

set(HLAP_STAGE "${CMAKE_CURRENT_SOURCE_DIR}/../mod/files/addons")
add_custom_command(TARGET hlap POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${HLAP_STAGE}"
    COMMAND ${CMAKE_COMMAND} -E copy "$<TARGET_FILE:hlap>" "${HLAP_STAGE}/hlap.dll"
    COMMENT "Staging hlap.dll in hl-source/mod/files/addons")
