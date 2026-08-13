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
// does. A transition that would leave the mission is taken over instead: send
// COMPLETE for the mission, and return the player to the hub.
//
// Never act inline. Issuing a level change from inside code the engine is
// already running a level change through is a crash. Set the flag, act on the
// next StartFrame.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

// Registered with the engine at load.
//   ap                 every mission and its unlock status
//   ap_tracker [map]   locations found and still out there
//   ap_find [text]     point at the nearest unfound check, or one you name
//   ap_warp <n|name>   travel to an unlocked mission
//   ap_hub             return to the hub
//   ap_help            these, in game
void RegisterCommands();

// True if the command was ours and has been handled.
bool HandleCommand(CBasePlayer* player, const std::string& command);

// Ask for a level change. Deferred to the next frame, always.
void RequestMap(const std::string& map_name);

// Called from CChangeLevel::ChangeLevelNow. Returns false to let the game's own
// transition proceed, true when we have taken it over.
bool InterceptChangeLevel(const std::string& from_map, const std::string& to_map);

// One frame's worth of deferred work: a queued map change, the bridge poll.
void RunFrame();

}  // namespace ap
