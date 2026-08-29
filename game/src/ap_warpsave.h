// Warp points that are engine saves.
//
// `map <name>` starts a level cold at its `info_player_start`, which is not where
// a mission's part 3 begins: the transition into it lands the player at a
// landmark, holding what part 2 left them with, in a seam room whose doors are
// already open. Warping there with `map` therefore drops the player somewhere
// they have never actually stood, and the seam-door and carried-monster patches
// in ap_hub.cpp are two symptoms of the same gap.
//
// So the warp target is a real savegame instead. The first time the player walks
// through a transition into a part, the game takes an engine save of that
// moment, under a name keyed by the seed and slot. `ap_warp <mission> <part>`
// then `load`s it, and the player is exactly where they were.
//
// Where this state lives, and why it is the exception:
//
//   * These saves are local by nature. A save is the machine's, not the seed's,
//     so the multiworld cannot hold them and a second machine will not have
//     them. Whether a warp *may* be taken stays a server question -- the same
//     `MissionOpen` and `Visited` gate as before -- and the save answers only
//     "where to". A reset seed that hands the same slot back is covered by that
//     gate; the stale save on disk is unreachable until the mission is open
//     again.
//   * The key is a hash of the snapshot's `<seed>:<slot>`, so two slots on one
//     machine cannot restore each other's saves and a new seed starts empty.
//   * They are the player's disk, so somebody has to sweep them: the client
//     deletes this key's saves when the slot goals, and every key's on
//     `/uninstall`. See `apworld/half_life/mod/__init__.py`.
//
// The dll owns writing and reading them because only the dll can issue `save`
// and `load`; it owns no state about them across a map load. Which warps exist
// is a question answered by looking at the directory, every time it is asked.

#pragma once

#include <string>
#include <vector>

namespace ap {

// A warp point on disk: the savegame's base name, the map it is on, and the
// label a named one was given (empty for the per-part automatic ones).
struct WarpPoint {
    std::string save;
    std::string map;
    std::string label;
};

// Eight hex digits of the snapshot's slot identity, or empty while no slot has
// been named. Empty means no warp point can be written or found: without it we
// cannot tell one run's saves from another's.
std::string WarpKey();

// The automatic warp point for a map: the one taken on first arrival.
std::string AutoWarpName(const std::string& map);

// Is there a savegame by this base name?
bool WarpSaveExists(const std::string& save);

// Every named warp point this slot has, in name order.
std::vector<WarpPoint> NamedWarps();

// The named warp `label`, if there is one.
bool FindNamedWarp(const std::string& label, WarpPoint& out);

// What `!setwarp [label]` does. Refuses in the hub, while disconnected, and
// while dead, saying why.
void SetWarp(const std::string& label);

// `!warps`: what is on disk for this slot.
void ListWarps();

// A map has just started. `previous` is the map before it -- the dll outlives the
// level, so this is known -- and `requested` says whether we asked to come here.
// An automatic warp point is wanted when neither holds: an engine transition from
// another part of the same mission is the one arrival worth recording.
void NoteArrival(const std::string& previous, const std::string& map,
                 bool requested);

// From StartFrame. Takes any save that is owed, once the level has settled.
void RunWarpSave();

}  // namespace ap
