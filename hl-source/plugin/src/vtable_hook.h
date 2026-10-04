// Find a class's vftable in a loaded module by its MSVC RTTI name, and swap
// one slot. No offsets, no signatures: the class name finds the table, and the
// slot index comes from hls_vtables.h, which source_rtti.py checks against the
// binary before writing.
#pragma once

#include <cstddef>

namespace hlap {

// The primary vftable of `cls` (e.g. "CHalfLife1") in the module that contains
// `any_address_in_module`, or nullptr.
void **FindVftable(const void *any_address_in_module, const char *cls);

// Replace slot `index` of `vftable` with `replacement`. Returns the previous
// entry, or nullptr if the page could not be made writable.
void *PatchSlot(void **vftable, int index, void *replacement);

}  // namespace hlap
