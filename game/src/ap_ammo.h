// Ammo relief: a way out of a gun the level cannot feed.
//
// A shuffled seed can hand you the crossbow in a map that holds no bolts, and
// nothing in Half-Life ever gives you more, so the weapon is scenery until the
// next map. When the option is on, a gun that runs dry on ammo this level does
// not stock is announced and refilled after five minutes.
//
// Off by default and off in every seed that does not ask for it: this is a
// comfort setting, not part of the game's balance. The client sends it in the
// snapshot, so nothing here reads a YAML.
//
// The 10-second grace after a refill exists for one case: dying immediately and
// reloading a save from before it. The ammo goes with the reload, and waiting
// another five minutes for it is the same problem again.

#pragma once

#include <string>

namespace ap {

// Called on every map load. The watch is rebuilt from what this level contains
// and what the player is carrying now -- like everything else on this side, it
// holds nothing across a load, and it must not: the timers are level time.
void ResetAmmoRelief();

// Every server frame; does its real work once a second at most. Cheap enough to
// leave in the frame loop with the option off, where it is one comparison.
void RunAmmoRelief();

// How long a dry gun waits for a refill, and how long after one arrives a second
// is issued for free if the ammo is gone again.
constexpr float kAmmoReliefDelaySeconds = 300.0f;
constexpr float kAmmoReliefGraceSeconds = 10.0f;

// How often the player's weapons are examined. A second is far below the time
// anything here measures, and the walk is a dozen pointers.
constexpr float kAmmoReliefCheckSeconds = 1.0f;

}  // namespace ap
