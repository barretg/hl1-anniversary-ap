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

// Called at map start. Re-times anything still queued against the new level's
// clock, because `gpGlobals->time` restarts with the map and this queue does
// not: a due time carried over from the previous map is measured against a
// clock that no longer exists, and the trap springs at an arbitrary moment much
// later, in a map that had nothing to do with it.
void RearmQueuedTraps();

// Is this classname currently out of the player's hands because Butterfingers
// took it? The loadout asks, because it is reapplied on every snapshot change --
// which happens whenever a check is sent -- and would otherwise hand the weapon
// straight back and leave the trap doing nothing at all.
bool Withheld(const std::string& classname);

// Forget any withheld weapon. Called on map load: the dropped copy is gone with
// the level, and a player who arrives somewhere new should arrive whole.
void ClearWithheld();

// How long a trap waits after arriving, so the level has settled first.
constexpr float kTrapDelaySeconds = 5.0f;

// How long a Butterfingers victim goes without their weapon.
constexpr float kButterfingersReturnSeconds = 30.0f;

// How many of a thing a trap spawns.
constexpr int kTrapSpawnCount = 4;

// --- where they land ------------------------------------------------------
//
// Ported from the Sven Co-op project, which had already been through this: a
// fixed ring of four spawns reads as a summoning circle, spawns things inside
// walls, and in a corridor produces one monster instead of four.
//
// Each spawn is rolled separately -- its own bearing, its own distance -- and
// checked with three traces before anything is created.

// The band a spawn lands in: far enough out not to telefrag, close enough to be
// the player's problem immediately.
constexpr float kTrapSpawnMinRadius = 72.0f;
constexpr float kTrapSpawnMaxRadius = 160.0f;

// How many bearings to try before giving up on one monster. A random bearing
// indoors points at a wall more often than not, and one roll per monster would
// mean a trap in a corridor spawning one of them.
constexpr int kTrapPlaceAttempts = 10;

// How far apart two spawns of the same trap have to be, so they read as
// scattered rather than stacked and are not born shoving each other.
constexpr float kTrapMinSeparation = 40.0f;

// Backed off whatever the outward trace hit, so nobody arrives inside a wall.
constexpr float kTrapWallMargin = 16.0f;

// How far a chosen spot may fall and still count as the same room. A short drop
// is a step or a kerb; a long one is the monster leaving down a lift shaft the
// moment it arrives.
constexpr float kTrapDropHeight = 128.0f;

// Half the height of the engine's standing hulls: the distance between the point
// a hull trace works with, which is the centre of the box, and a monster's own
// origin, which is at its feet. Hull 1 is 32x32x72, hull 3 is 32x32x36.
constexpr float kHumanHullHalf = 36.0f;
constexpr float kHeadHullHalf = 18.0f;

// Scientist sub-models: glasses, Einstein, Luther, slick. One of each, in a
// random order, which is what makes four of them read as a crowd rather than as
// a clone.
constexpr int kScientistHeads = 4;

}  // namespace ap
