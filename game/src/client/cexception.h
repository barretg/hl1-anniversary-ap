// Force-included into vgui_TeamFortressViewport.cpp for clang-cl builds. It
// catches MFC's `CException *` after only a forward declaration; MSVC lets the
// incomplete type through, clang needs it complete. Nothing ever throws one.
#pragma once
class CException {};
