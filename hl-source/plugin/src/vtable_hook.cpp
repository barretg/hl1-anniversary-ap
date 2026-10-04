#include "vtable_hook.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdint>
#include <cstring>
#include <string>

namespace hlap {
namespace {

struct Section {
    uintptr_t begin = 0, end = 0;
    bool code = false;
};

struct Module {
    uintptr_t base = 0;
    Section sections[32];
    int count = 0;

    bool Load(const void *addr) {
        HMODULE mod = nullptr;
        if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                                    GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                static_cast<LPCSTR>(addr), &mod))
            return false;
        base = reinterpret_cast<uintptr_t>(mod);
        auto *dos = reinterpret_cast<IMAGE_DOS_HEADER *>(base);
        auto *nt = reinterpret_cast<IMAGE_NT_HEADERS32 *>(base + dos->e_lfanew);
        IMAGE_SECTION_HEADER *s = IMAGE_FIRST_SECTION(nt);
        for (int i = 0; i < nt->FileHeader.NumberOfSections && count < 32; ++i, ++s) {
            Section &out = sections[count++];
            out.begin = base + s->VirtualAddress;
            out.end = out.begin + s->Misc.VirtualSize;
            out.code = (s->Characteristics & IMAGE_SCN_MEM_EXECUTE) != 0;
        }
        return true;
    }

    bool IsCode(uintptr_t a) const {
        for (int i = 0; i < count; ++i)
            if (sections[i].code && a >= sections[i].begin && a < sections[i].end) return true;
        return false;
    }

    // Every 4-byte-aligned address in non-code sections holding `value`.
    template <typename F>
    void ForEachDword(uintptr_t value, F &&f) const {
        for (int i = 0; i < count; ++i) {
            if (sections[i].code) continue;
            for (uintptr_t p = sections[i].begin; p + 4 <= sections[i].end; p += 4)
                if (*reinterpret_cast<const uint32_t *>(p) == value && f(p)) return;
        }
    }

    // The first occurrence of `bytes` in non-code sections.
    uintptr_t Find(const char *bytes, size_t n) const {
        for (int i = 0; i < count; ++i) {
            if (sections[i].code) continue;
            for (uintptr_t p = sections[i].begin; p + n <= sections[i].end; ++p)
                if (std::memcmp(reinterpret_cast<const void *>(p), bytes, n) == 0) return p;
        }
        return 0;
    }
};

}  // namespace

void **FindVftable(const void *any_address_in_module, const char *cls) {
    Module m;
    if (!m.Load(any_address_in_module)) return nullptr;

    // TypeDescriptor: { pVFTable, spare, name[] }, name ".?AV<cls>@@".
    std::string name = std::string(".?AV") + cls + "@@";
    uintptr_t str = m.Find(name.c_str(), name.size() + 1);
    if (!str) return nullptr;
    uintptr_t td = str - 8;

    void **result = nullptr;
    // CompleteObjectLocator: { signature, offset, cdOffset, pTypeDescriptor,
    // pClassDescriptor }. The primary table's locator has offset 0.
    m.ForEachDword(td, [&](uintptr_t ref) {
        auto *col = reinterpret_cast<const uint32_t *>(ref - 12);
        if (col[0] != 0 || col[1] != 0) return false;
        uintptr_t col_addr = reinterpret_cast<uintptr_t>(col);
        // The vftable is preceded by a pointer to its locator.
        m.ForEachDword(col_addr, [&](uintptr_t meta) {
            auto **vft = reinterpret_cast<void **>(meta + 4);
            if (!m.IsCode(reinterpret_cast<uintptr_t>(vft[0]))) return false;
            result = vft;
            return true;
        });
        return result != nullptr;
    });
    return result;
}

void *PatchSlot(void **vftable, int index, void *replacement) {
    void **slot = vftable + index;
    DWORD old = 0;
    if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old)) return nullptr;
    void *previous = *slot;
    *slot = replacement;
    VirtualProtect(slot, sizeof(void *), old, &old);
    return previous;
}

}  // namespace hlap
