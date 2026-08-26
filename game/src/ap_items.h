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

// Ask for the loadout to be applied. This is what `CBasePlayer::Spawn` calls.
//
// Never applied on the spot. Handing a weapon over sends a `WeapPickup` user
// message, and a user message written from inside `Spawn` -- before the client
// is in the server -- is
// `SZ_GetSpace: Tried to write to an uninitialized sizebuf_t` and a dead game.
// Typing `kill` at the console is enough to reach it.
void RequestLoadout();

// Apply it, if one was asked for and the player can receive messages.
// StartFrame only.
void RunLoadout();

// Give the player exactly what the seed says they should have. Safe to call from
// anywhere `RunLoadout` would be: StartFrame and below, never from a hook.
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

// The suit bit, held on every frame. "Granted, never removed" is the rule, and
// this is where it is kept rather than only on a spawn and a snapshot change.
//
// In GoldSrc the bit draws the HUD as well as marking the suit owned, so a
// player who loses it loses health, ammo and the message area with it -- the
// game goes quiet while still running. `CanCollect` clears it for exactly one
// synchronous call so the real suit pickup can fire the map logic that hangs off
// it; this is what puts it back if that call does not finish the job.
void EnforceSuit();

}  // namespace ap
