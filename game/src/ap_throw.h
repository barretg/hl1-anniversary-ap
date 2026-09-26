// Melee Throw: mouse2 throws the crowbar or the knife, once the item arrives.
//
// From halflife-murder's Crowbar Hunt. The thrown weapon hits for the same
// damage as a swing, then lies on the floor until the player walks back over it,
// or comes back by itself after a while so a throw into a pit costs nothing
// permanent. Server only: the client never predicts the throw.

#pragma once

#include <string>

class CBasePlayerWeapon;

namespace ap {

// From the weapon's SecondaryAttack. Throws it if the seed allows it and says
// so; false means nothing happened and the caller should do nothing either.
bool ThrowMelee(CBasePlayerWeapon* weapon);

// StartFrame: take a thrown weapon out of the inventory. Deferred, because the
// throw runs inside that weapon's own attack code.
void RunThrows();

// Is this classname out of the player's hands in flight or on the floor? The
// loadout asks, or it would hand the weapon straight back on the next check.
bool Thrown(const std::string& classname);

// Map load: a thrown weapon went with the old level, so the loadout returns it.
void ClearThrown();

// From the world's precache, with the traps.
void PrecacheThrow();

}  // namespace ap
