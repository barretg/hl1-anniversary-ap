// The hub: console commands, warps, and the mission-boundary choke point.
//
// There is no campaign portal in retail, so v1's hub is the console. These are
// properly registered server commands rather than the dot-prefixed workaround
// Sven Co-op forced on the previous project, and in single-player the console is
// the primary surface rather than a fallback. An authored hub map is v2 and adds
// a `P` record to checkdata.txt; nothing else about this changes when it lands.
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
//   ap_tracker [map]   locations found and still out there
//   ap_find [text]     point at the nearest unfound check, or one you name
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

// Called from CChangeLevel::ChangeLevelNow. False lets the game's own transition
// proceed, which is what happens for every transition inside a mission. True
// when we have taken it over.
bool InterceptChangeLevel(const std::string& from_map, const std::string& to_map);

// One frame's worth of deferred work: a queued map change, and nothing else.
void RunDeferred();

// Where "the hub" is until an authored map exists.
//
// The hazard course entrance: a real, small, empty map that is deliberately not
// part of the campaign, so no check can fire there and no mission can be
// completed by standing in it. v2 replaces this with one room and a button per
// mission, shipped in the mod folder.
//
// It is also `startmap` in liblist.gam, so New Game begins here rather than on
// the tram: every mission is entered by warping, and starting inside one would
// hand it over for free and fire its arrival check before the run had begun.
// The two must agree; tests/test_mod_install.py fails if they drift apart.
extern const char* const kHubMap;

// Is the player in the hub rather than in a mission?
bool InHub();

}  // namespace ap
