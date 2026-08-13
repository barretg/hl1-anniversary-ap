// The loadout, and refusing what has not been sent yet.
//
// Retail carries inventory across a level transition and Half-Life hands weapons
// out itself, so this is the half of the project that fights the game rather
// than extending it. Four rules:
//
//   - The loadout is reapplied from the client's snapshot on every spawn and
//     whenever the snapshot changes. The game side holds nothing across a load.
//   - A pickup whose classname is gated and whose item has not arrived is
//     refused: no pickup sound, no HUD flash, the entity stays where it is. The
//     refusal happens in the game rules, which is the one question every path
//     into the player's inventory already asks -- including a weapon handed over
//     by `GiveNamedItem` from map logic.
//   - The HEV suit is granted and never removed. It draws the weapon HUD and
//     owns weapon switching; a player without it cannot use what they hold.
//   - The `HEV Suit` item controls armour instead, which is held at zero from
//     every source until it arrives.

#pragma once

#include <string>

class CBasePlayer;
class CBaseEntity;

namespace ap {

// Give the player exactly what the seed says they should have. Called from
// CBasePlayer::Spawn, and again after anything that strips weapons -- c2a3d
// (Apprehension) has a player_weaponstrip in the middle of a mission.
void ApplyLoadout(CBasePlayer* player);

// May this pickup be collected? False refuses it, leaving it in the world.
// Checked in order: are we the ones granting it, is it a starting weapon, did
// the seed leave it ungated, is it gated at all, and only then whether the item
// has arrived.
bool CanCollect(CBasePlayer* player, CBaseEntity* pickup);
bool CanCollect(CBasePlayer* player, const std::string& classname);

// One filler delivery: ammo, health, armour. Named as the item list names them.
void GrantFiller(CBasePlayer* player, const std::string& item_name);

// Armour is held at zero from every source -- the map's own loadout, batteries,
// charge panels and filler grants alike -- until the HEV Suit item arrives.
// Called every frame rather than on the poll clock, so a charge panel cannot
// visibly fill the bar before it is emptied again.
void ClampArmour();
bool ArmourAllowed();

}  // namespace ap
