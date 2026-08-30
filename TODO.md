# TODO

Work that is understood but deliberately not done yet. Anything here is a
considered deferral rather than a bug: the reason for leaving it is part of the
entry.

## Warping cold could land on the landmark instead of the spawn

A mid-mission warp normally restores an engine savegame, which puts the player
exactly where the transition into that part would have left them, with the
inventory and the level state that transition carried. See
`game/src/ap_warpsave.h`.

When there is no savegame -- a part the player has never walked into on this
machine, or a save swept after goaling -- the warp falls back to a cold `map`
load, which starts the level at `info_player_start`. That is the old behaviour
and it is not the same place: the spawn point is where the *chapter* begins, not
where the seam does, so scripted openings hung off the transition do not fire.
Surface Tension Part 8 is the example, where the tank never emerges and the
soldiers never arrive.

The improvement, if it is ever wanted:

- find the `info_landmark` that the previous map's `trigger_changelevel` names
  for this map, and spawn the player on it rather than at `info_player_start`;
- fire the `trigger_auto` and seam logic the arrival would have run, which is
  what `RequestSeamDoors` and `PlaceCarriedMonsters` already approximate for two
  specific cases.

Not done because the savegame path covers the case that actually matters, and a
second, permanently worse route to the same place is a maintenance cost with a
small payoff. Deferred deliberately (2026-08-29); revisit only if the cold path
turns out to be common in play.

## More stuff

* Crowbar throw from jac's thing
* Movesanity: Lock crouch, strafe left/right/back, progressive air strafe
* Flashlight unlock
