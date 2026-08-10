# Half-Life (Sven Co-op)

## What is this game?

Half-Life's single-player campaign, as rebuilt for co-op play inside Sven Co-op.
Sven Co-op ships the whole 1998 campaign — Black Mesa Inbound through Nihilanth —
recombined into 35 larger maps across 18 missions, playable alone or with others.

## Where is the options page?

The [player options page](../player-options) lets you configure your game.

## What does randomization do to this game?

The Sven Co-op campaign portal becomes a hub. Every mission is sealed until its
unlock item arrives from the multiworld, and you begin with exactly one random
mission open — so no two runs start in the same place.

Every weapon except the crowbar is also an item. Weapons lying in the levels can
still be walked over (that is what sends the check), but Gordon will not pick one
up until the multiworld has granted it, and the campaign's own per-map loadouts
are stripped to match. A shotgun found in Office Complex is worth nothing until
somebody, somewhere, sends you the Shotgun.

The final mission is not unlocked by an item at all. Nihilanth opens once you
have completed a configurable number of other missions.

## What items and locations get shuffled?

**Items** — 17 mission unlocks, 13 weapons (Glock, .357, MP5, shotgun, crossbow,
RPG, Tau cannon, gluon gun, hivehand, satchel charges, tripmines, snarks, hand
grenades), and optionally the HEV suit and long jump module. Everything else is
filler: ammo caches, medkits and armour batteries.

**Locations** — 174 of them, all derived from entities that actually exist in the
map files:

- every distinct weapon or equipment pickup in each map
- the first kill of each notable enemy present in a map — gargantuas, tentacles,
  ichthyosaurs, apaches, ospreys, assassins, alien grunts, Gonarch, Nihilanth
- reaching each later part of a multi-part mission
- completing each mission
- kill-count milestones, which is how the sparse Xen maps still carry checks

## Which items can be in another player's world?

Any of them.

## What does another world's item look like in Half-Life?

There is no world model for it. Collecting a location prints the check to chat,
and the item goes wherever the multiworld sends it.

## When the player receives an item, what happens?

Weapons and mission unlocks apply silently — the next time you spawn, or
immediately if you are already alive, your loadout is rebuilt to match what you
own. Filler is applied on the spot: health, armour, or a top-up of ammo for
whatever you are currently carrying.

## What is the goal?

Kill Nihilanth. Its mission only opens once you have completed enough of the
others, so the run is a tour of Black Mesa rather than a beeline.
