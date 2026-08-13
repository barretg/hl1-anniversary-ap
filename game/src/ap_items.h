// The loadout, and refusing what has not been sent yet.
//
// Retail carries inventory across a level transition and Half-Life hands weapons
// out itself, so this is the half of the project that fights the game rather
// than extending it. Three rules:
//
//   - The loadout is reapplied on every spawn from the client's snapshot. The
//     game side holds nothing across a load.
//   - A pickup whose classname is gated and whose item has not arrived is
//     refused: no pickup sound, no HUD flash, the entity stays where it is.
//   - The HEV suit is granted and never removed. It draws the weapon HUD and
//     owns weapon switching; a player without it cannot use what they hold. The
//     `HEV Suit` item controls armour, which is held at zero until it arrives.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

// Give the player exactly what the seed says they should have. Called from
// CBasePlayer::Spawn, and again after anything that strips weapons -- c2a3d
// (Apprehension) has a player_weaponstrip in the middle of a mission.
void ApplyLoadout(CBasePlayer* player);

// May this pickup be collected? False refuses it. Checked against, in order:
// the starting weapons, the ungated classnames the seed left to the game, then
// the item the classname is gated behind.
bool CanCollect(CBasePlayer* player, const std::string& classname);

// Hand over one item by name, as the client delivers them.
void GrantItem(CBasePlayer* player, const std::string& item_name);

// Armour is held at zero from every source until the HEV Suit item arrives:
// the map's own loadout, batteries, charge panels and filler grants alike.
bool ArmourAllowed();

}  // namespace ap
