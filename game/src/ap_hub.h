// The hub: console commands, warps, and the mission-boundary choke point.
//
// There is no campaign portal in retail, so the console is the primary surface:
// properly registered server commands rather than the dot-prefixed workaround
// Sven Co-op forced on the previous project. The authored lobby adds a panel per
// mission on top of that, through the `P` records in checkdata.txt, and both go
// through the same gate -- a panel cannot be a way past a lock `ap_warp` honours.
//
// The choke point is `CChangeLevel::ChangeLevelNow`. A transition inside a
// mission is left alone -- inventory and level state carry exactly as retail
// does. A transition that would leave the mission is taken over instead: report
// the mission finished and return the player to the hub.
//
// Never act inline. Issuing a level change from inside code the engine is
// already running a level change through is a crash. Set the flag, act on the
// next frame.

#pragma once

#include <string>

namespace ap {

// Registered with the engine once, at GameDLLInit.
//   ap                 every mission and its unlock status
//   ap_tracker [text]  every location in the seed; filter by mission or map
//   ap_find [text]     the nearest check here, or one named anywhere in the seed
//   ap_warp <n|name>   travel to an unlocked mission
//   ap_hub             return to the hub
//   ap_help            these, in game
void RegisterCommands();

// A line the player typed in chat. True when it was one of ours and has been
// dealt with, in which case it must not be broadcast as chat.
//
// The same commands as the console, with `!` or `/` in front, and the short
// names allowed: `!ap`, `!warp 3`, `!warp unforeseen 6`, `!hub`, `!find`,
// `!tracker`, `!help`. Single-player chat has nobody else in it, but it is a
// text box that opens with one key and does not pause the game, which is more
// than can be said for the console.
bool HandleChat(CBasePlayer* player, const std::string& said);

// Ask for a level change. Always deferred to the next frame. `map`, never
// `changelevel`: a clean load with no carried state is what makes a mission
// repeatable and independent of how the player got there.
void RequestMap(const std::string& map_name);

// Did we ask the engine for this map, as opposed to the engine arriving at it by
// itself? True exactly once per request, and consumed by the asking.
//
// This is what tells a warp apart from a save the engine restored after a death.
// A warp has already been through the gate in `MissionOpen`, so it needs no
// second opinion -- and a second opinion is worse than none, because it is drawn
// from a snapshot that may be a poll behind the warp that just happened.
bool WasRequested(const std::string& map_name);

// A map we warped into arrives cold: `map` starts a level with an empty global
// table, where `changelevel` carries the seam's state across. These reopen the
// doors that state would have left open. `RequestSeamDoors` marks it wanted at
// map start; `RunSeamDoors` acts once the level has settled, from StartFrame.
void RequestSeamDoors();
void RunSeamDoors();

// Called from CChangeLevel::ChangeLevelNow. False lets the game's own transition
// proceed, which is what happens for every transition inside a mission. True
// when we have taken it over.
bool InterceptChangeLevel(const std::string& from_map, const std::string& to_map);

// One frame's worth of deferred work: a queued map change, and nothing else.
void RunDeferred();

// A lobby panel was pressed. True when it was one of ours and has been dealt
// with; false for every other entity in the world, including the lobby's own
// doors and anything the campaign puts under a player's crosshair.
//
// Matched on the entity's targetname against the `P` records, which is the one
// handle the map and `checkdata.txt` share.
bool PressHubButton(CBasePlayer* player, CBaseEntity* target);

// The hub map: one room, a labelled panel per mission, shipped in the mod
// folder rather than inherited from `valve` because it is ours.
//
// It is also `startmap` in liblist.gam, so New Game begins here rather than on
// the tram: every mission is entered by warping, and starting inside one would
// hand it over for free and fire its arrival check before the run had begun.
// The two must agree; tests/test_mod_install.py fails if they drift apart, and
// `HUB_MAP` in tools/campaign_layout.py is the third name that has to match.
extern const char* const kHubMap;

// Is the player in the hub rather than in a mission?
bool InHub();

}  // namespace ap
