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
    # One export needs naming by hand, and only one. Everything the engine looks
    # up -- GetEntityAPI, GetEntityAPI2, and every entity classname registered by
    # LINK_ENTITY_TO_CLASS -- already carries `__declspec(dllexport)` through the
    # SDK's own headers.
    #
    # `GiveFnptrsToDll` is the exception: eiface.h makes it `__stdcall` and does
    # not mark it exported, because MSVC took the export from `dlls/hl.def`. That
    # route works until it does not -- matching an undecorated name in a .def
    # against a decorated `_GiveFnptrsToDll@8` is left to the linker's judgement,
    # and it produced `LNK2001: unresolved external symbol GiveFnptrsToDll@8` on
    # a build that differed only in its CRT. Naming both sides removes the
    # judgement.
    set_target_properties(hl PROPERTIES
        LINK_FLAGS "/EXPORT:GiveFnptrsToDll=_GiveFnptrsToDll@8")

    # Static CRT. A dll linked against the dynamic one needs the 32-bit VC++
    # redistributable on the player's machine, and a player who does not have it
    # gets `LoadLibrary failed (126)` -- ERROR_MOD_NOT_FOUND, with no clue which
    # module is missing. Nobody installs a Half-Life mod expecting to chase a
    # redistributable, so the runtime rides along inside the dll.
    set_property(TARGET hl PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
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

    # NOTE: this build cannot save or load, which in GoldSrc also means it cannot
    # cross a level transition -- transitions run through the same save/restore
    # machinery. The engine maps an entity's think, touch and use functions to
    # names through this dll's export table, and with a MinGW-built dll it fails
    # to: saving floods the console with `Can't find address:`, writes those
    # functions as empty strings, and loading the result dies on
    # `PF_precache_model_I: Bad string ''`.
    #
    # `-Wl,--export-all-symbols` was tried and is worse: it takes the export
    # table from 978 names to 9,976, and the engine resolves map entities by
    # `GetProcAddress(dll, classname)`, so burying those among thousands of
    # unrelated symbols crashes it on map load instead. `-fno-ipa-icf` alone
    # changed nothing.
    #
    # MSVC is the answer, and the branch above is written for it. Keep this
    # branch: it built, loaded and ran the whole hook chain, which is what proved
    # the design, and it is a useful second opinion if MSVC ever misbehaves.

    # Fully static, because a player's Half-Life folder has none of MinGW's
    # runtime in it. `-static-libgcc -static-libstdc++` alone is not enough: the
    # posix-threads build of gcc still imports libwinpthread-1.dll, and the
    # engine's report of that is `LoadLibrary failed (126)` with no name --
    # error 126 is ERROR_MOD_NOT_FOUND, and it means a dependency, not this dll.
    #
    # Not stripped: `-s` would take the symbol table with it, and while exports
    # survive stripping, keeping the symbols makes a crash address nameable.
    target_link_options(hl PRIVATE
        -static -static-libgcc -static-libstdc++ -Wl,--enable-stdcall-fixup)
    # See the comments in hl_mingw.def: GNU ld cannot parse the SDK's own.
    target_sources(hl PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/hl_mingw.def")
endif()
