#include "log.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "tier0/dbg.h"

namespace hlap {
namespace {

FILE *Open() {
    static FILE *f = nullptr;
    static bool tried = false;
    if (tried) return f;
    tried = true;
    HMODULE self = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       reinterpret_cast<LPCSTR>(&Open), &self);
    char path[MAX_PATH] = {};
    GetModuleFileNameA(self, path, MAX_PATH);
    char *slash = std::strrchr(path, '\\');
    if (!slash) slash = std::strrchr(path, '/');
    if (!slash) return nullptr;
    std::snprintf(slash + 1, path + MAX_PATH - slash - 1, "hlap_log.txt");
    f = std::fopen(path, "w");
    // Phase 0 diagnostics: a second copy at Z:\tmp (Proton maps Z: to /), in
    // case the plugin's own folder is not writable through the mod path.
    static FILE *tmp = std::fopen("Z:\\tmp\\hlap_log.txt", "w");
    if (!f) f = tmp;
    else if (tmp) std::fclose(tmp);
    return f;
}

}  // namespace

void Log(const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (FILE *f = Open()) {
        std::fprintf(f, "%s\n", buf);
        std::fflush(f);
    }
    Msg("[hlap] %s\n", buf);
}

}  // namespace hlap
