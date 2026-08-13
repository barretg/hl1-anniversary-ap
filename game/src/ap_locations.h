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

// Called once the map is running and checkdata has been read.
void OnMapStart(const std::string& map_name);

// A player pressed +use on something. Matches the entity against the charger
// table by classname and rounded absolute-bounding-box centre.
void OnPlayerUse(CBasePlayer* player, CBaseEntity* target);

// A weapon entered the player's inventory.
void OnWeaponCollected(CBasePlayer* player, const std::string& classname);

// Where the nearest unfound check is, for `ap_find`. Distance is weighted:
// 800 units across a floor is a walk, 800 units up is a hunt for the stairs.
constexpr float kVerticalPenalty = 3.0f;

}  // namespace ap
