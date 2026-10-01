# Feature comparison: hl1-sven-ap vs hl1-anniversary-ap

Scope: what each apworld adds on top of its host game. Vanilla differences
between Sven Co-op and retail Half-Life are ignored except where they force an
apworld design difference.

Sources: `hl1-sven-ap` at `8e05853`, `hl1-anniversary-ap` at `ca64e9b`. Counts
come from the generated data files (`data/campaigns/*.json` for Sven,
`data/campaign.json` here), before any YAML exclusions.

## At a glance

| Area | Sven (`Half-Life (Sven Co-op)`) | Anniversary (`Half-Life`) |
| --- | --- | --- |
| Game side | AngelScript server plugin | Server dll + client dll (`hlap` mod folder) |
| Campaigns | Half-Life, Opposing Force, Blue Shift, They Hunger | Half-Life, Opposing Force, Blue Shift (OF/BS marked experimental) |
| Arcade content | Suspension (optional, large option set) | None |
| Players | Co-op lobby is the slot | Single player |
| Hub | Sven's campaign portal, existing consoles | Custom lobby map `ap_lobby_alpha`, randomised whiteboard |
| Starting missions | One per included campaign | One for the whole seed |
| Traps | 3 | 4 (adds Bot Swarm) |
| Extra items | None beyond HEV / long jump | Flashlight, Night Vision Goggles, PCV, Security Armor, Melee Throw |
| Extra options | Lobby DeathLink, Suspension suite, restricted starting weapon | Ammo Relief, Viewmodel Style, Shuffle Flashlight, Melee Throw |

## Campaigns and missions

| | Sven | Anniversary |
| --- | --- | --- |
| Half-Life | 18 missions over Sven's 35 recombined maps | 18 missions over retail maps, cut at `chaptertitle` boundaries |
| Opposing Force | 13 missions / 34 maps (boot camp and Crush Depth have no console) | 12 missions, boot camp excluded |
| Blue Shift | 7 missions / 31 maps | 6 missions |
| They Hunger | 3 episodes / 19 maps | not present |
| Finale seal | Per campaign count; Blue Shift's Power Struggle is a `GOAL_COMPANION` sealed alongside the finale | Per campaign count; Power Struggle folded together with A Leap of Faith |
| Starting mission | One random startable mission per campaign | One random startable mission for the whole seed |
| Intro missions | `exclude_intro_missions` (default on), plus hidden deprecated `include_black_mesa_inbound` | `exclude_intro_missions` (default on) only |
| Victory | One named Victory event per campaign, plus a Suspension victory | Count of a single `Victory` event equal to number of campaigns |

Both use the same `missions_required` / `opposing_force_missions_required` /
`blue_shift_missions_required` naming; Sven adds `they_hunger_missions_required`.

## Locations

### Totals by type (raw data, all campaigns)

| Type | Sven HL | Sven OF | Sven BS | Sven TH | Anniv HL | Anniv OF | Anniv BS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `map_reached` | 35 | 33 | 31 | 19 | 96 | 38 | 31 |
| `chapter_complete` | 18 | 12 | 7 | 3 | 18 | 12 | 6 |
| `charger` | 106 | 20 | 12 | 2 | 122 | 24 | 17 |
| `weapon_pickup` | 16 | 18 | 10 | 13 | 16 | 18 | 10 |

Sven additionally has Suspension: 288 section, 36 clear and 24 award
locations in the data, filtered per seed by difficulty cap, medal cap and
classanity.

Retail Half-Life has far more map divisions than Sven's recombined maps, so
`map_reached` is roughly 3x denser here.

### Chargers

| | Sven | Anniversary |
| --- | --- | --- |
| Identity | `classname:*<brush model index>`, with an `@origin` suffix for offset copies of one brush | Position, snapped to a 4-unit grid; runtime matches nearest unit of that classname |
| Why | Sven maps are fixed | Anniversary recompile renumbered brush models; position survives future patches |
| Xen healing pools | Not checks | Checks (15 in HL). `trigger_hurt` with negative damage, fired on touch |
| Blue Shift HEV-style wall units | Checks | Not checks (only `func_healthcharger`) |
| Unreachable / sealed | n/a | Generator drops unreachable chargers and OF's sealed healing volumes |

### Weapon pickups (the main behavioural difference)

Both name them `First <weapon>` (Sven prefixes `Opposing Force - `, anniversary
prefixes `Opposing Force: `), both anchor each one at the earliest map in that
campaign's order containing the weapon, and both send the check whether or not
the weapon item has been received. The differences:

**Which copy counts**

- Sven: map-scoped. `IndexCurrentMap` only loads weapon checks whose `map` is
  the current map, so only a copy picked up in the anchor map sends "First
  Shotgun". The same weapon in any later map sends nothing.
- Anniversary: campaign-scoped. `CheckData::WeaponPickupFor` accepts the weapon
  on *any* map of the same game (not the hub, not the hazard course). Office
  Complex has five shotguns across four maps; any of them sends it. Blue Shift
  crowbars do not send Half-Life's crowbar check. Note: the README "Locations"
  section still says "only there", which no longer matches the code.

**Proximity sweep (for weapons you already hold, e.g. the crowbar)**

- Sven: one-second sweep of the current map's unsent weapon checks, any
  connected living player within 72 units *and* with a clear trace line to the
  entity. Skips held weapons and is disabled on Suspension.
- Anniversary: sweep within 72 units of the single player, no line-of-sight
  trace. Skips followed/attached entities and Butterfingers drops.

**What is excluded from counting**

- Sven: held weapons only.
- Anniversary: weapons being granted by the game itself (`g_granting`),
  Butterfingers trap drops (both at touch and in the sweep, and anything
  `Withheld`), and anything in the hub.

**Crowbar and melee weapons**

- Sven: every weapon, the crowbar included, is a normal item. The starting
  melee is removed from the pool; the others (crowbar, pipe wrench, combat
  knife, spanner) are items. HL has "First Crowbar" at `hl_c02_a1`.
- Anniversary: crowbar, pipe wrench and combat knife are "unrandomised" weapon
  locations (always a check, never an item by default). Only melee candidates
  that did *not* start the run become items (`Melee Weapons` group). With only
  HL/BS there is no Crowbar item at all.
- Anniversary defaults `random_starting_weapon` to **on**; Sven defaults it off
  and has `allow_restricted_starting_weapon` for They Hunger's spanner.

**Equipment locations**

| Check | Sven | Anniversary |
| --- | --- | --- |
| HL HEV suit | `First HEV Suit` (hl_c01_a1) | `First HEV Suit` (c1a0d) |
| OF suit | `Opposing Force - First HEV Suit` | `Opposing Force: First PCV` (own armour item) |
| BS suit | `Blue Shift - First HEV Suit` (ba_tram1) | none; BS `item_suit` is HUD only. `Blue Shift: First Security Armor` (vest/helmet) instead |
| Long jump | `First Long Jump Module` (hl_c13_a4) | `First Long Jump Module` (c3a2d) |

**Weapon set differences**

- OF: Sven has the Minigun, no Shock Roach. Anniversary has the Shock Roach
  (anchored via `WEAPON_ANCHORS` to `of4a1`, since it is only ever dropped by a
  shock trooper), no Minigun. Sven calls it SAW/Displacer Cannon/Barnacle
  Grapple; anniversary M249/Displacer/Barnacle.
- TH: 13 weapon checks in Sven, 9 of them restricted to They Hunger maps
  (granted only on arrival in an episode). No equivalent here.
- Pool membership: Sven includes a weapon if any included campaign's maps
  contain it. Anniversary always includes Half-Life's weapons regardless of
  which campaigns are on, plus each included game's own.

**Unshuffled equipment**

- Sven: unshuffled long jump / HEV are "ungated" classnames; the campaign
  hands them over natively and the `First ...` location holds a random item.
- Anniversary: unshuffled HEV is granted up front. Unshuffled long jump is a
  real item *locked* at `First Long Jump Module` (`VANILLA_WHEN_UNSHUFFLED`),
  so it persists across hub warps into Xen. Slot data carries
  `placed_at_vanilla`.

**Refusal and loadouts**

- Sven: strips Sven's per-map `.cfg` loadouts on spawn and re-grants owned
  weapons.
- Anniversary: refuses the touch with a rate-limited "You need the X from the
  multiworld" message; `item_suit` touch is always allowed (so `c1a0d`'s
  multisource still fires) while armour is clamped instead.

## Items

| | Sven | Anniversary |
| --- | --- | --- |
| Mission unlocks | Yes | Yes |
| Weapons | HL + OF + TH pooled | HL always + OF when included |
| HEV Suit (armour gate) | One item for all campaigns | HEV Suit (HL), PCV (OF), Security Armor (BS) |
| Long Jump Module | Yes | Yes |
| Flashlight / NVG | No | `shuffle_flashlight`: Flashlight (HL/BS), Night Vision Goggles (OF) |
| Melee Throw | No | `melee_throw`: secondary fire throws crowbar/knife, returns after 10s |
| Suspension classes / difficulty | 7 class items + Progressive Suspension Difficulty | n/a |
| Filler | Ammo Cache, Armor Battery, Health Charge, Medkit | same |
| Traps | Scientist, Headcrab, Butterfingers (lobby-wide) | same three + Bot Swarm (6 crowbar bots) |
| Default `trap_percentage` | 20 | 15 |

## Options only in one world

Sven only:

- `include_they_hunger`, `they_hunger_missions_required`
- `allow_restricted_starting_weapon`
- `include_black_mesa_inbound` (hidden, deprecated)
- `lobby_death_link` (on / non_arcade / off)
- Suspension: `suspension`, `suspension_classanity`,
  `suspension_max_difficulty`, `suspension_required_award`,
  `suspension_goal_classes`, `suspension_goal_requires_award`,
  `suspension_max_awards_are_priority`, `suspension_difficulty_rolldown`,
  `suspension_starting_class`

Anniversary only:

- `viewmodel_style` (per_campaign / always_gordon)
- `shuffle_flashlight`
- `melee_throw`
- `ammo_relief` (experimental timed refill for guns the level has no ammo for)
- "Experimental Features" option group on the web page

Shared: include toggles, missions required, `logic_difficulty` (strict/loose),
`chargesanity`, `exclude_intro_missions`, `random_starting_weapon`,
`shuffle_hev_suit`, `shuffle_longjump`, `trap_percentage`, `death_link`,
`death_link_amnesty`, `start_inventory_from_pool`.

## Logic

Both share the same `EQUIPMENT_GATES` shape and strict/loose weapon-group
model. Anniversary differences:

- Per-map gates and per-map check gates (`map_gates`, `map_check_gates`), e.g.
  Barnacle required past arriving in Vicarious Reality Part 2 at any logic
  level.
- Sven adds the Suspension logic: explosives classes (Grenadier, Pointman,
  Engineer) gate section 4 onward, clears and medals; Juggernaut stands behind
  the other seven.

## Hub, travel and in-game tools

| | Sven | Anniversary |
| --- | --- | --- |
| Hub | Campaign portal; console-to-mission is a generated table | `ap_lobby_alpha` with walk-in/button entrances per HL mission; OF/BS by `ap_warp` |
| Lobby decoration | none | Random whiteboard art redrawn each load (client dll) |
| Commands | `!ap`, `!warp`, `!hub`, `!tracker`, `!find`, `!help` (chat; `.ap_*` in console) | `ap`, `ap_warp`, `ap_hub`, `ap_tracker`, `ap_find`, `ap_help`, plus `ap_setwarp`, `ap_warps` (console or `!` in chat) |
| Part warps | By name, number or map name, only to parts already reached | Same gate, but loads a real engine save of the moment you entered that part |
| Custom warp points | No | `!setwarp [name]` |
| Game-per-mission numbering | Global mission numbers | Also `ap_warp of 3` / `ap_warp bs 2` |
| Missing-game handling | n/a | Refuses missions of games not installed; client warns on connect |

## DeathLink

- Sven: death gibs the whole lobby, `lobby_death_link` splits local wipe from
  outgoing link, amnesty forgives N deaths.
- Anniversary: single player, amnesty only.

## Install / client

- Sven: installs an AngelScript plugin into `svencoop/scripts`; needs
  `as_command spcp_*` for non-HL campaigns.
- Anniversary: installs the `hlap` mod folder (`fallback_dir "valve"`); links
  OF/BS content in, converts Blue Shift map lumps, relocates colliding content,
  and ships its own client dll. Deletes warp saves on goal and on `/uninstall`.
- Both: same file-bridge protocol shape (`docs/protocol.md`), Universal Tracker
  passthrough via `interpret_slot_data`.
