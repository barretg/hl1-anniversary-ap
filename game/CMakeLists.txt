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
# Opposing Force and Blue Shift entities, ported from Sam Vanheer's
# halflife-op4-updated / halflife-bs-updated to this SDK's conventions. Valve's
# code under the same SDK license, kept apart from ours.
file(GLOB PORT_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/port/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/port/of/*.cpp")

add_library(hl SHARED ${SDK_SOURCES} ${SDK_C_SOURCES} ${AP_SOURCES} ${PORT_SOURCES})

target_include_directories(hl PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/port/of"
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

# The client dll: Valve's cl_dll, built the way hl_cdll.vcxproj builds it. Only
# with MSVC or clang-cl, because it links Valve's prebuilt MSVC vgui libraries.
option(HLAP_CLIENT "Build client.dll as well" ON)
if(HLAP_CLIENT AND MSVC)
    file(GLOB CL_SOURCES CONFIGURE_DEPENDS
        "${HLSDK_DIR}/cl_dll/*.cpp"
        "${HLSDK_DIR}/cl_dll/hl/*.cpp")
    # In cl_dll/ but not in hl_cdll.vcxproj: samples and other mods' code.
    foreach(name GameStudioModelRenderer_Sample.cpp MOTD.cpp overview.cpp
                 scoreboard.cpp soundsystem.cpp vgui_ConsolePanel.cpp)
        list(REMOVE_ITEM CL_SOURCES "${HLSDK_DIR}/cl_dll/${name}")
    endforeach()
    foreach(name crossbow crowbar egon gauss handgrenade hornetgun mp5 python
                 rpg satchel shotgun squeakgrenade tripmine)
        list(APPEND CL_SOURCES "${HLSDK_DIR}/dlls/${name}.cpp")
    endforeach()
    list(APPEND CL_SOURCES
        "${HLSDK_DIR}/dlls/wpn_shared/hl_wpn_glock.cpp"
        "${HLSDK_DIR}/common/parsemsg.cpp"
        "${HLSDK_DIR}/public/interface.cpp")
    # Opposing Force's weapons, predicted on the client like Valve's.
    foreach(name CDisplacer CEagle CGrapple CGrappleTip CKnife CM249 CPipewrench
                 CShockRifle CSniperRifle CSporeLauncher)
        list(APPEND CL_SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/src/port/of/${name}.cpp")
    endforeach()
    file(GLOB CL_SHARED CONFIGURE_DEPENDS "${HLSDK_DIR}/game_shared/vgui_*.cpp")
    list(APPEND CL_SOURCES ${CL_SHARED} "${HLSDK_DIR}/game_shared/voice_banmgr.cpp")

    add_library(client SHARED ${CL_SOURCES} ${SDK_C_SOURCES})
    target_include_directories(client PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src/port/of"
        "${HLSDK_DIR}/dlls" "${HLSDK_DIR}/cl_dll" "${HLSDK_DIR}/public"
        "${HLSDK_DIR}/common" "${HLSDK_DIR}/pm_shared" "${HLSDK_DIR}/engine"
        "${HLSDK_DIR}/utils/vgui/include" "${HLSDK_DIR}/game_shared"
        "${HLSDK_DIR}/external")
    target_compile_definitions(client PRIVATE
        WIN32 _WINDOWS NDEBUG CLIENT_DLL CLIENT_WEAPONS HL_DLL
        _CRT_SECURE_NO_WARNINGS)
    if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
        # SDL_endian.h defines `_m_prefetch` for old clangs; newer ones have it
        # built in and reject the redefinition. Its own guard skips it.
        target_compile_definitions(client PRIVATE __PRFCHWINTRIN_H)
        # See src/client/cexception.h.
        set_source_files_properties("${HLSDK_DIR}/cl_dll/vgui_TeamFortressViewport.cpp"
            TARGET_DIRECTORY client PROPERTIES COMPILE_OPTIONS
            "/FI${CMAKE_CURRENT_SOURCE_DIR}/src/client/cexception.h")
    endif()
    target_link_libraries(client PRIVATE
        "${HLSDK_DIR}/utils/vgui/lib/win32_vc16/vgui.lib"
        "${HLSDK_DIR}/lib/public/SDL2.lib"
        "${HLSDK_DIR}/lib/public/game_controls.lib"
        wsock32)
    set_target_properties(client PROPERTIES OUTPUT_NAME "client" PREFIX "")
    set_property(TARGET client PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
    # Staged like hl.dll below; mod.CLIENT_DLL_NAME is the same path.
    add_custom_command(TARGET client POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_SOURCE_DIR}/../apworld/half_life/mod/files/cl_dlls"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different "$<TARGET_FILE:client>"
                "${CMAKE_CURRENT_SOURCE_DIR}/../apworld/half_life/mod/files/cl_dlls/client.dll"
        COMMENT "Staging client.dll into the apworld")
endif()

# Stage every build where `tools/build_apworld.py` packages it from, so the
# apworld can never carry a dll older than the code. This used to be a manual
# copy, and a missed copy meant testing yesterday's dll with nothing to say so.
# `mod.DLL_NAME` in apworld/half_life/mod/__init__.py is the same path.
set(AP_STAGED_DLL
    "${CMAKE_CURRENT_SOURCE_DIR}/../apworld/half_life/mod/files/dlls/hl.dll")
add_custom_command(TARGET hl POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_SOURCE_DIR}/../apworld/half_life/mod/files/dlls"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "$<TARGET_FILE:hl>" "${AP_STAGED_DLL}"
    COMMENT "Staging hl.dll into the apworld")
