// Refuses the "Enable HD models" switch while the map could not precache the
// other version's texture files (`ap_hd_locked`, set by the server dll in
// game/src/ap_content.cpp). Switching then would load a model the engine never
// listed, which is fatal.
//
// The option runs the engine's `_sethdmodels` command. The client cannot add a
// command under a name the engine already has, so the engine's own entry is
// found in its command list and its handler swapped for one that checks first.
#pragma once

// Called from HUD_VidInit. Installs the hook once the engine command exists.
void APHDLock_VidInit();
