# Cross-build the 32-bit server dll on Linux with clang-cl + lld-link + xwin.
#
# The documented route is MSVC on Windows. This is the same target reached from
# a Linux box: clang-cl is MSVC-compatible down to the name decoration and the
# export table, which is the part that matters here -- the MinGW build produces
# a dll the engine cannot resolve function names in, so it cannot save or cross
# a level transition. See "Why not MinGW" in game/README.md.
#
# CMake sets MSVC=1 for clang-cl, so the CMakeLists takes its MSVC branch and
# the static CRT and the hand-named GiveFnptrsToDll export come along with it.
#
# Point XWIN_ROOT at a splatted Windows SDK + CRT if it is not in ~/.xwin.
#
#   cmake -S game -B build/game-clangcl -G Ninja \
#         -DCMAKE_TOOLCHAIN_FILE=game/toolchain-clangcl-x86.cmake \
#         -DHLSDK_DIR=../halflife
#   cmake --build build/game-clangcl

set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86)

if(NOT DEFINED XWIN_ROOT)
    set(XWIN_ROOT "$ENV{HOME}/.xwin" CACHE PATH "Splatted Windows SDK and CRT")
endif()
if(NOT EXISTS "${XWIN_ROOT}/crt/include")
    message(FATAL_ERROR "no splatted SDK at ${XWIN_ROOT}; run xwin, or set XWIN_ROOT")
endif()

set(CMAKE_C_COMPILER clang-cl)
set(CMAKE_CXX_COMPILER clang-cl)
set(CMAKE_LINKER lld-link)
set(CMAKE_C_COMPILER_TARGET i686-pc-windows-msvc)
set(CMAKE_CXX_COMPILER_TARGET i686-pc-windows-msvc)

# 32-bit is not optional: GoldSrc will not load anything else. `-m32` rather
# than the target triple alone, because CMake's compiler probe reads the
# pointer size from a compile and the CMakeLists refuses a 64-bit build.
set(_xwin_flags
    "-m32 --target=i686-pc-windows-msvc \
/imsvc ${XWIN_ROOT}/crt/include \
/imsvc ${XWIN_ROOT}/sdk/include/ucrt \
/imsvc ${XWIN_ROOT}/sdk/include/um \
/imsvc ${XWIN_ROOT}/sdk/include/shared")
# `pm_shared.c` passes its own `hull_t *` to an engine callback typed
# `struct hull_s *`. MSVC warns and builds it; clang 16 and later make that an
# error by default. The same file set needs the same kind of allowance from
# gcc -- see the `gnu17` note in game/README.md -- and the fix belongs here
# rather than in `sdk.patch`, which is hooks only and stays that way.
set(CMAKE_C_FLAGS_INIT "${_xwin_flags} -Wno-error=incompatible-pointer-types")
set(CMAKE_CXX_FLAGS_INIT "${_xwin_flags}")

# No manifest. `lld-link` can embed one, but CMake drives that through `rc` and
# `mt` from a Visual Studio install, which do not exist here -- and a Half-Life
# server dll has nothing to say in a manifest anyway.
set(_xwin_libs
    "/MACHINE:X86 /MANIFEST:NO \
/libpath:${XWIN_ROOT}/crt/lib/x86 \
/libpath:${XWIN_ROOT}/sdk/lib/ucrt/x86 \
/libpath:${XWIN_ROOT}/sdk/lib/um/x86")
set(CMAKE_EXE_LINKER_FLAGS_INIT "${_xwin_libs}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${_xwin_libs}")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "${_xwin_libs}")

# The static release CRT, everywhere. The CMakeLists already asks for it on the
# `hl` target and README.md says why, but CMake's own compiler probe does not
# inherit that: it links Debug by default, wants `msvcrtd.lib`, and an xwin
# splat carries no debug CRT because Microsoft does not redistribute one.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")

# Look for the SDK checkout and our own sources on the host, not in a sysroot.
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM BEFORE)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BEFORE)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BEFORE)
