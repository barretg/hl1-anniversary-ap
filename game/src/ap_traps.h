// The three traps. All nuisances rather than punishments: none can cost a run.
//
//   Scientist Trap      four scientists appear and follow the player about
//   Headcrab Trap       four headcrabs, same idea, considerably less friendly
//   Butterfingers Trap  the player loses what they are holding; the suit
//                       reissues it after half a minute
//
// The hazard is precache. GoldSrc fatally errors on an unprecached model and the
// precache table is finite, so everything a trap can spawn is precached at map
// load whether or not a trap ever arrives -- the alternative is a crash at the
// worst possible moment. Keep the set small and fixed; a precache pass was
// written and reverted once on the Sven Co-op side.

#pragma once

#include <string>

namespace ap {

// Called during the map's precache pass, before any entity spawns.
void PrecacheTraps();

// A TRAP delivery from the client. Queued rather than sprung: arriving during a
// level load means spawning into geometry that is not settled yet.
void QueueTrap(const std::string& trap_name);

// Springs whatever is due, and hands back a Butterfingers victim's weapon.
void RunTrapTimers();

// How long a trap waits after arriving, so the level has settled first.
constexpr float kTrapDelaySeconds = 5.0f;

// How long a Butterfingers victim goes without their weapon.
constexpr float kButterfingersReturnSeconds = 30.0f;

// How many of a thing a trap spawns.
constexpr int kTrapSpawnCount = 4;

}  // namespace ap
