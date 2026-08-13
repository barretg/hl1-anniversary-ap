# Builds the hlap server dll: Valve's Half-Life SDK plus the sources in src/.
#
# The SDK is not vendored. Clone it next to this repository, apply sdk.patch to
# it, and point HLSDK_DIR at it. The result must be 32-bit -- GoldSrc will not
# load anything else.
#
# MinGW (what this was first built with):
#
#   git clone https://github.com/ValveSoftware/halflife.git ../halflife
#   git -C ../halflife apply ../hl1-anniversary-ap/game/sdk.patch
#   cmake -S game -B build -G "MinGW Makefiles" -DHLSDK_DIR=../halflife \
#         -DCMAKE_C_COMPILER=C:/msys64/mingw32/bin/gcc.exe \
#         -DCMAKE_CXX_COMPILER=C:/msys64/mingw32/bin/g++.exe
#   cmake --build build
#
# MSVC:
#
#   cmake -S game -B build -A Win32 -DHLSDK_DIR=../halflife
#   cmake --build build --config Release

cmake_minimum_required(VERSION 3.20)
project(hlap CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(HLSDK_DIR "" CACHE PATH "Path to a checkout of ValveSoftware/halflife")
if(NOT HLSDK_DIR OR NOT EXISTS "${HLSDK_DIR}/dlls/client.cpp")
    message(FATAL_ERROR
        "Set HLSDK_DIR to a checkout of https://github.com/ValveSoftware/halflife")
endif()

if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR
        "GoldSrc loads a 32-bit dll. Use -A Win32 (MSVC) or a 32-bit toolchain "
        "such as MSYS2's mingw32 gcc.")
endif()

# The SDK's own server sources. Kept whole: this is the shipped game's logic and
# the point of the exercise is not to reimplement it.
file(GLOB SDK_SOURCES CONFIGURE_DEPENDS "${HLSDK_DIR}/dlls/*.cpp")

# The seven files in dlls/ that the server dll does not build, taken from Valve's
# own hldll.vcxproj rather than guessed. glock.cpp is superseded by
# wpn_shared/hl_wpn_glock.cpp and the rest belong to other mods or to tools;
# compiling them gives duplicate symbols.
set(SDK_EXCLUDED
    AI_BaseNPC_Schedule.cpp
    glock.cpp
    mpstubb.cpp
    playermonster.cpp
    stats.cpp
    vehicle.cpp
    Wxdebug.cpp)
foreach(name ${SDK_EXCLUDED})
    list(REMOVE_ITEM SDK_SOURCES "${HLSDK_DIR}/dlls/${name}")
endforeach()

list(APPEND SDK_SOURCES
    "${HLSDK_DIR}/dlls/wpn_shared/hl_wpn_glock.cpp"
    "${HLSDK_DIR}/game_shared/voice_gamemgr.cpp")

set(SDK_C_SOURCES
    "${HLSDK_DIR}/pm_shared/pm_debug.c"
    "${HLSDK_DIR}/pm_shared/pm_math.c"
    "${HLSDK_DIR}/pm_shared/pm_shared.c")

# Ours.
file(GLOB AP_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp")

add_library(hl SHARED ${SDK_SOURCES} ${SDK_C_SOURCES} ${AP_SOURCES})

target_include_directories(hl PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${HLSDK_DIR}/dlls"
    "${HLSDK_DIR}/engine"
    "${HLSDK_DIR}/common"
    "${HLSDK_DIR}/pm_shared"
    "${HLSDK_DIR}/game_shared"
    "${HLSDK_DIR}/public")

# Valve's own set for this target, plus one of ours.
target_compile_definitions(hl PRIVATE
    QUIVER VOXEL QUAKE2 VALVE_DLL CLIENT_WEAPONS _CRT_SECURE_NO_WARNINGS)

# The engine loads `hl.dll` by name, whatever the mod folder is called.
set_target_properties(hl PROPERTIES OUTPUT_NAME "hl" PREFIX "")

if(MSVC)
    # MSVC takes the exports from the SDK's own definition file.
    set_target_properties(hl PROPERTIES
        LINK_FLAGS "/DEF:\"${HLSDK_DIR}/dlls/hl.def\"")
else()
    # Two headers spell the MSVC-only `_declspec`, each behind an `#ifndef`, so
    # defining them here is enough to build them with a compiler that has never
    # heard of it.
    target_compile_definitions(hl PRIVATE
        "CBASE_DLLEXPORT=__declspec(dllexport)"
        "UTIL_DLLEXPORT=__declspec(dllexport)")

    # The SDK is 1998 C++ compiled by a 2025 front end. -fpermissive keeps the
    # old conversions legal; -w is not laziness but the only way to see our own
    # diagnostics in the noise of a hundred files of someone else's warnings.
    target_compile_options(hl PRIVATE -w -fpermissive -fno-strict-aliasing)
    # C23 made `false` a keyword and const.h uses it as an enumerator.
    set_source_files_properties(${SDK_C_SOURCES} PROPERTIES
        COMPILE_OPTIONS "-std=gnu17")

    # Fully static, because a player's Half-Life folder has none of MinGW's
    # runtime in it. `-static-libgcc -static-libstdc++` alone is not enough: the
    # posix-threads build of gcc still imports libwinpthread-1.dll, and the
    # engine's report of that is `LoadLibrary failed (126)` with no name --
    # error 126 is ERROR_MOD_NOT_FOUND, and it means a dependency, not this dll.
    # -s strips the symbols, 4.9 MB down to about 2.7.
    target_link_options(hl PRIVATE
        -static -static-libgcc -static-libstdc++ -s -Wl,--enable-stdcall-fixup)
    # See the comments in hl_mingw.def: GNU ld cannot parse the SDK's own.
    target_sources(hl PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/hl_mingw.def")
endif()
