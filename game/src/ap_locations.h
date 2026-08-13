// Firing checks.
//
// Four kinds, and each has exactly one moment it can be observed:
//
//   map_reached       ServerActivate, once the map is up
//   chapter_complete  arriving on a mission's last map
//   charger           +use on a func_healthcharger or func_recharge, empty or
//                     not: this is about finding one, not needing it
//   weapon_pickup     the first time a weapon is collected in the run
//
// A check is sent every time it is observed. The server treats a repeat as a
// no-op, which is what makes quicksaves and reloads safe to allow.

#pragma once

#include <string>

class CBaseEntity;
class CBasePlayer;

namespace ap {
struct Chapter;
}

namespace ap {

// The map is up and checkdata has been read. Fires the arrival check, and the
// mission's completion where arriving *is* finishing -- the finale, and nowhere
// else.
void OnMapStart(const std::string& map_name);

// This mission is over: send its completion check and tell the client. Called
// from the mission-boundary interception, which is where finishing normally
// happens, and from `OnMapStart` for the finale.
void SendChapterComplete(const Chapter& chapter);

// The player pressed +use on something. Matches it against the charger table by
// classname and by where it stands.
void OnPlayerUse(CBasePlayer* player, CBaseEntity* target);

// A weapon entered the player's inventory.
void OnWeaponCollected(CBasePlayer* player, const std::string& classname);

// Weapons lying within reach that the player already holds. Their touch never
// fires, so without this the crowbar's check could never be sent.
void SweepNearbyPickups();

// Send a check by id, once per map load. Repeats are harmless on the server but
// noisy in the log, and the log is append-only.
void SendCheck(long id);

// Has the player ever been to this map in this seed?
//
// Answered by that map's own `map_reached` check: arriving is what fires it, and
// the client's `checked` list is the durable record of it across sessions. Used
// to keep `ap_warp <mission> <part>` to parts already walked to, so a partial
// warp is a way back rather than a way past.
bool Visited(const std::string& map_name);

// `ap_find`: the nearest check in this map that the seed still wants, or the one
// whose name contains `text`. Prints a bearing and a distance.
void Find(const std::string& text);

// `ap_tracker`: what has been found and what is still out there.
void Tracker(const std::string& map_filter);

// How far a weapon may be from the player and still count as collected by the
// sweep. Arm's reach, so it cannot fire across a room through a wall.
constexpr float kPickupSweepRadius = 72.0f;

// How much dearer a unit of height is than a unit of floor when judging how far
// away a check is. 800 units across a floor is a walk; 800 units up is a hunt
// for the stairs. The generator weights `ap_find` the same way.
constexpr float kVerticalPenalty = 3.0f;

}  // namespace ap
