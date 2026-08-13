// The three traps. All nuisances rather than punishments: none can cost a run.
//
//   Scientist Trap      four scientists appear and follow the player about
//   Headcrab Trap       four headcrabs, same idea, considerably less friendly
//   Butterfingers Trap  the player drops what they are holding; the suit
//                       reissues it after half a minute
//
// The hazard is precache. GoldSrc fatally errors on an unprecached model and the
// precache table is finite, so every model a trap can spawn is precached at map
// load whether or not a trap ever arrives -- the alternative is a crash at the
// worst possible moment. A precache pass was written and reverted once on the
// Sven Co-op side; treat this as the same class of hazard and keep the set small
// and fixed.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

// Called during the map's precache pass, before any entity spawns.
void PrecacheTraps();

// A TRAP delivery from the client.
void Spring(CBasePlayer* player, const std::string& trap_name);

// How long a Butterfingers victim goes without their weapon.
constexpr float kButterfingersReturnSeconds = 30.0f;

}  // namespace ap
