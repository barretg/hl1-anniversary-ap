# Half-Life (Sven Co-op)

## What is this game?

Half-Life's campaign, as rebuilt for co-op play inside Sven Co-op. Sven Co-op
ships the whole 1998 campaign — Black Mesa Inbound through Nihilanth — recombined
into 35 larger maps across 18 missions, played co-operatively.

## A note on multiplayer

Sven Co-op is a multiplayer game, and its version of the Half-Life campaign is
built to be played co-operatively. Some of what it asks of you is there on purpose
to keep it that way.

This randomizer is made for co-op lobbies. We do not endorse using it, or any
convenience it adds, to work around Sven Co-op's multiplayer design or to treat
the campaign as a free single-player Half-Life. Play it with other people. If you
want Half-Life on its own, buy Half-Life.

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

Mission 0, Black Mesa Inbound, has no console in the campaign portal — `!warp 0`
in Sven Co-op chat is the only way to travel there. It can be dropped from the
seed with `include_black_mesa_inbound: false`.

## What items and locations get shuffled?

**Items** — 17 mission unlocks, 13 weapons (Glock, .357, MP5, shotgun, crossbow,
RPG, Tau cannon, gluon gun, hivehand, satchel charges, tripmines, snarks, hand
grenades), and optionally the HEV suit and long jump module. Everything else is
filler: ammo caches, medkits and armour batteries.

`trap_percentage` turns some of that filler into traps. There are three. Like
DeathLink, they are the whole lobby's problem rather than one player's, and all
of them are nuisances rather than punishments — none can cost you a run:

- **Scientist Trap** — four scientists, one of each variant, appear around every
  player and start following them about.
- **Headcrab Trap** — four headcrabs each, same idea, considerably less friendly.
- **Butterfingers Trap** — everyone drops the weapon they are holding. The suit
  reissues it after thirty seconds if you cannot find it again.

**Locations** — 173 of them:

- reaching each part of a mission (Surface Tension has five, Office Complex one)
- completing each mission
- reaching each weapon where Half-Life would first have given it to you, the
  crowbar included
- using each health charger and HEV charge panel, 107 in all

Sven Co-op splits Half-Life's campaign into 35 maps across 18 missions, so
progress through a mission is itself the check. Every wall-mounted charger is a
check too, whether or not it still has juice in it — pressing use is enough. Set
`chargesanity: false` if you want a shorter run without them.

Weapon checks are pinned to where the original campaign hands each weapon over:
"First Shotgun" is the Office Complex shotgun, and no other shotgun in the game
will send it. You do not have to be allowed to keep the gun for the check to
count.

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

The HEV suit is the exception worth knowing about. You always wear it, because in
GoldSrc the suit is what draws the weapon HUD and without it you cannot change
weapons at all. What the item grants is armour: until it arrives your armour is
held at zero, and batteries, wall chargers and armour filler all do nothing.

## What is the goal?

Kill Nihilanth. Its mission only opens once you have completed enough of the
others, so the run is a tour of Black Mesa rather than a beeline.
