# Porting to retail Half-Life: the plan

This repository is a fork of `hl1-sven-ap`, the Archipelago world for the
campaigns shipped inside Sven Co-op. The goal here is the same game played on
Valve's own Half-Life, for players who want the original rather than Sven's
version of it.

Read this file first.

**Phases 1 and 2 are done, and Phases 3 to 5 are written and building.**
The strip list below has been executed, the layout table is retail's, the data is
regenerated against `valve/maps`, the client and world are repointed at the
`hlap` mod folder, and `game/` now holds the whole server dll: the bridge, the
checkdata parser, the checks, the gating, the hub commands, DeathLink and the
traps, plus `game/sdk.patch` for the hooks into Valve's sources.

**Phase 0 is done, and a seed is playable.** The dll builds 32-bit with MSVC,
installs, and the game runs it: the hub comes up, `ap_warp` travels, checks fire
and reach the server, items arrive and announce themselves, pickups are refused
until sent, saves and level transitions work. The SDK-built-dll approach is
settled and Metamod stays where it belongs, in the rejected column.

Four bugs found on the way, and they are the shape of bug to expect from the
rest:

- **The trap precache was hooked into `ClientPrecache`,** an assets-only
  callback, and `UTIL_PrecacheOther` creates a real entity. That crashed the
  engine on every map load -- inside `hw.dll`, with nothing of ours on the
  stack. It hooks `CWorld::Precache` now.
- **MinGW cannot build this.** Its dll loads and runs but cannot save, and in
  GoldSrc a level transition *is* a save. See `game/README.md`; the branch is
  kept but MSVC is the toolchain.
- **Notifications were sent inline from hooks,** which crashed on the first
  death: a user message written from `CBasePlayer::Killed` is
  `SZ_GetSpace: Tried to write to an uninitialized sizebuf_t`. They queue now
  and go out from `StartFrame`, which is the same rule the deferred level change
  already followed.
- **Gating waited on the client.** Warps and pickups were only refused while
  connected, so closing the client was a way around every lock in the game. It
  fails closed now: with checkdata present and no client, you get your starting
  weapons and nowhere to warp to.

`hlap/archipelago/ap_boot.txt` exists because of the first one: one line per
hook, so a load crash names itself instead of being guessed at.

What actually landed, and where it differs from the plan below, is recorded in
"Where the port stands" at the end of this file.

## Target, fixed

**Retail Half-Life on Steam, the current 25th anniversary build. One target, no
others.**

Not `steam_legacy`, not WON, not Xash. The legacy branch stays in this document
only as a documented escape hatch if the anniversary build ever proves hostile,
and if it is ever used it needs its own dll build and its own generated data
(see the map recompile note under Risks). Do not spend effort supporting both.

Opposing Force, Blue Shift and They Hunger are out of scope. Retail versions of
the first two are separate games with their own game directories and their own
dlls, and each would need its own mod folder and plugin build. The architecture
extends to them the same way it did in the Sven project, but only after
Half-Life ships.

## What this port keeps

The architecture is not being rethought. It works, it is tested, and roughly 70
percent of it has no engine dependency.

| Piece | Status |
| --- | --- |
| `tools/bsp_entities.py` | keep as is. Sven and retail both ship GoldSrc BSP v30; lump 14 parses identically |
| `tools/build_campaign_data.py` | keep. Already driven entirely by `CAMPAIGNS` plus a maps directory. One change, the charger key (below) |
| `tools/gen_checkdata.py` | keep as is |
| `client/bridge.py` | keep as is. It has no Archipelago and no game dependency, and `tests/test_bridge.py` covers it |
| `client/launcher.py`, `client/settings.py` | keep, repoint. Paths, install routine and game name change; the rest stands |
| `docs/protocol.md` | keep as the contract. The game side of it is reimplemented in C++ |
| `items.py`, `locations.py`, `regions.py`, `rules.py`, `options.py` | keep the structure, delete the three campaigns |
| `tools/campaign_layout.py` | rewrite for one campaign against retail's map names |
| `apworld/half_life_sven/plugin/**` | delete. 4300 lines of AngelScript with no counterpart here |

So the port is: one new layout table, one new game-side plugin in C++, and
packaging.

## Decision 1: how the game gets a hook surface

**A server dll built from the official Half-Life SDK, inside its own mod
folder.**

The mod folder is `hlap` (name not final), with `liblist.gam` carrying
`fallback_dir "valve"`. The player's own install is never touched, all maps and
assets are inherited through the fallback, the mod appears in the game list, and
the folder gives us somewhere to put a hub map later.

Valve's [ValveSoftware/halflife](https://github.com/ValveSoftware/halflife)
repository has been updated with the 25th anniversary changes and tracks the
shipped game as of the October 2024 patch, so a dll built from it is the current
game's own logic rather than the 2003 SDK's. That is what makes this option
acceptable to a player who specifically wants the original game.

It also gives full C++ class access: `GiveNamedItem`, `RemovePlayerItem`,
`PlayerUse`, `ItemPreFrame`, the same surface Sven's AngelScript API wraps, with
no third-party dependency.

Two alternatives were considered and are recorded here so they are not
relitigated:

- **Metamod plugin over retail's shipped `hl.dll`.** Higher fidelity in
  principle, since the game logic is Valve's actual binary. Rejected as primary:
  single-player Metamod is a niche path kept alive mostly for bots, anniversary
  support is probable but undocumented (metamod-p's last release was May 2024,
  post-anniversary, but its changelog stops in 2012 and its issue tracker never
  mentions the update), and it cannot remove a weapon the player already holds
  without offset hacks. Keep as the fallback if the SDK build will not run.
- **Client patching or a custom engine.** Rejected. Breaks on every Valve
  update, and nothing in this design needs to touch the client.

## Decision 2: keep the file bridge and the Python client

Do not compile an Archipelago client into the game dll, which is what the other
vanilla effort at
[GoldSRC-Archipelago/halflife-archipelago](https://github.com/GoldSRC-Archipelago/halflife-archipelago)
does. The bridge protocol, the event windowing, the ACK scheme, the DeathLink
amnesty rule and Universal Tracker support are all working and tested here, and
`bridge.py` has no game dependency at all. In C++ the file half of it is easier
than it was in AngelScript, not harder.

Consequences to state in the setup guide: the player still runs the Archipelago
client alongside the game, and the game side stays stateless across map loads,
which in retail also buys save/load resilience for free.

The store directory moves from `svencoop/scripts/plugins/store/archipelago/` to
somewhere under the mod folder, `hlap/archipelago/`. Nothing else about the
protocol changes.

## Decision 3: what a mission is, and what happens at its edges

The largest behavioural difference, and it needs settling before any C++ is
written.

Sven ships each chapter as a self-contained map series with a hub in front of
it. Retail is one continuous game: `trigger_changelevel` with landmarks,
inventory carried across, level state preserved for the session, and quicksave
everywhere.

Rules, matching what the Sven project already does:

- **Warps use `map`, not `changelevel`.** A clean load, no carried state, no
  landmark. The plugin reapplies the loadout on spawn. This is what makes a
  mission repeatable and independent.
- **Transitions inside a mission stay the game's own.** Do not intercept `c1a1`
  to `c1a1a`. Inventory and level state carry exactly as retail does.
- **A transition crossing a mission boundary is intercepted.** Take over
  `CChangeLevel::ChangeLevelNow`, send `COMPLETE|<chapter>`, return the player to
  the hub. Direct analogue of the `MapChange` choke point in `ap_hub.as`, and it
  inherits that file's hard-won rule: never act inline, always defer the level
  change out of whatever observed it.
- **Saves are allowed and are not authoritative.** The plugin holds nothing
  across a load; the client's snapshot is reapplied. A reloaded save can re-send
  a check that is already collected, which the server treats as a no-op.

Health and armour on entering a mission are a design call to make explicitly
rather than inherit, since retail expects you to arrive from the previous
chapter with whatever you had. Start with a fixed 100 health, plus armour if the
suit is held, and add a YAML option if it plays badly.

## Decision 4: the hub

There is no `-sp_campaign_portal` in retail. Two stages, **and both have landed.**

- **v1, no hub map.** The hub is a console interface, and in retail those can be
  properly registered server commands (`ap`, `ap_warp`, `ap_tracker`, `ap_find`,
  `ap_hub`) rather than the dot-prefixed workaround Sven forced on us. Chat
  commands still work, but single-player has no chat worth speaking of, so the
  console is the primary surface here and should be treated as first class
  rather than as a fallback. "Returning to the hub" means loading a small idle
  map and printing the mission list.
- **v2, an authored hub map.** One room, one labelled button per mission,
  compiled with the standard tools and shipped in the mod folder. The game reads
  the button `targetname` through the same `P` records `checkdata.txt` already
  carries, so nothing in the data pipeline changes when it lands. Keep the map
  source in the repo.

  Landed as `ap_lobby_alpha`, and it went in as this said it would: `P` records
  and nothing else. It differs on one point, which is that the records are not
  written down at all. The generator reads them out of the shipped BSP, keyed
  `chapter_<n>_button` to the mission with index `n`, so the map is the only
  authority on what it contains and a mission without a panel fails the build.
  The map replaces `stalkyard` as `startmap` and as `kHubMap`, and it is the one
  map the mod folder ships rather than inheriting through the fallback.

Do not let the map block the port.

## Decision 5: charger identity changes

**Key chargers by rounded world-space centre, not by brush model index.**

The Sven project identifies a charger as `func_recharge:*79`, because brush
model index is the only per-entity handle the BSP and the running game share for
an entity with no targetname. That is safe there because Sven's maps are a fixed
shipped set nobody recompiles.

Retail's are not. The 25th anniversary update edited and recompiled
single-player maps (z-fighting on a door in `c1a0`, texture mapping in `c1a2b`, a
Barney sequence and geometry in `c2a2` and `c2a2a`, among others), and a
recompile can renumber brush models. Data generated against one build is
therefore not guaranteed valid against another, and the failure mode is chargers
that silently never fire.

The generator already computes the brush centre, and the plugin can compute the
same thing from the live entity's absolute bounding box. Position survives any
recompile that does not physically move the unit. This also deletes the
`ba_canal1` origin-offset special case entirely, since position already accounts
for it.

## The strip list

In order. Everything here is deletion or rename, no new behaviour, and it should
land before any C++ is written.

1. **Rename the world package.** `apworld/half_life_sven/` becomes
   `apworld/half_life/`. Update `archipelago.json`: `game` becomes `Half-Life`
   (check for a collision with the other vanilla effort before settling on it;
   `Half-Life (GoldSrc)` is the fallback), and reset `world_version` to `0.1.0`.
2. **Delete the plugin tree.** `apworld/half_life_sven/plugin/plugins/` and
   `tools/install_plugin.py`, plus `tests/test_plugin_install.py`. The C++
   project replaces all of it. Keep `plugin/__init__.py`'s role in mind: the
   installer pattern (client `/install` and a CLI entry point sharing one code
   path) is worth reproducing for the mod folder.
3. **Cut three campaigns from `tools/campaign_layout.py`.** Delete
   `OPPOSING_FORCE`, `BLUE_SHIFT`, `THEY_HUNGER` and everything only they need:
   `script_weapons`, `weapon_aliases`, `weapon_anchors`, `goal_requires`,
   `endgame_chapters`, the `R` record path in the generator, and the
   `ranged_they_hunger` group in the logic. `Campaign` collapses to a much
   smaller dataclass, and it is worth asking whether it stays a list at all.
4. **Cut the campaign options.** In `options.py`, delete `include_*` for all
   four campaigns and the three extra `missions_required` variants, and
   `allow_restricted_starting_weapon` (it exists solely for the They Hunger
   spanner). Keep `chargesanity`, `exclude_intro_missions`, `missions_required`,
   `random_starting_weapon`, `death_link_amnesty`, `trap_percentage`. Delete the
   hidden `include_black_mesa_inbound` compatibility shim: it exists to keep old
   Sven YAMLs generating, and no YAML for this game exists yet.
5. **Simplify the multi-campaign machinery.** `GOAL_COMPANIONS`, per-campaign
   goal tracking in the client, `goals_open` in the snapshot, the `M` record in
   `checkdata.txt`, and the item `campaign`/`campaigns` split all collapse when
   there is exactly one campaign. Do this deliberately rather than leaving dead
   generality: `tests/test_no_unreachable_code.py` exists for a reason.
6. **Rewrite the docs.** `README.md`, `apworld/*/docs/*`, `docs/verification.md`
   and `docs/releases/` all describe Sven. `docs/protocol.md` survives with the
   store path and the `M`/`R` records edited out.
7. **Reset the id space.** Delete `data/ids.json` and regenerate. Ids are only
   stable because that file pins them, and this is a different game with no
   released seeds, so this is the one and only chance to renumber cleanly. Pick
   an id base that does not collide with the Sven world's `7710000`.

## The new layout table

`tools/campaign_layout.py` becomes a one-campaign file against retail map names.
Retail's single-player campaign is roughly 65 to 70 maps against Sven's 35, so
every chapter has more parts and `map_reached` checks get finer grained.

1. Author the chapter table: 18 chapters from `c0a0` through `c5a1`, each with
   its ordered map list, plus `t0a0*` (the hazard course) if it is included at
   all. **Do not reuse the Sven chapter keys**, tempting as it is; a fresh id
   space wants fresh keys, and the two projects should never be diffable into
   each other by accident.
2. Re-derive the weapon table. Retail has no `weapon_m16`, no Sven-specific
   spellings and no script-registered weapons, so `R` records disappear and the
   classname aliasing shrinks to almost nothing.
3. Regenerate. Chargers, weapon first-locations and positions all fall out of
   the existing generator.

Expected shape: about 65 `map_reached`, 18 `chapter_complete`, 90ish `charger`
and 14 `weapon_pickup`, so roughly 190 locations against Half-Life's 173 in the
Sven world. A healthy ratio for the same item pool.

`ENABLED_LOCATION_TYPES` stays off, as it is in the Sven project, for the same
reason: the entity-derived location types read as arbitrary in play.

## Hook mapping

What the AngelScript plugin does, and where it goes in the SDK. Under a custom
dll most of these are direct overrides rather than hooks, which is why this
option was chosen.

| Sven hook | Used for | SDK equivalent |
| --- | --- | --- |
| `MapChange` | choke point for every transition | `CChangeLevel::ChangeLevelNow` |
| `MapStart` / `MapInit` | re-read `checkdata.txt`, rebuild charger table | `ServerActivate` |
| `PlayerSpawn` | reapply loadout | `CBasePlayer::Spawn` |
| `PlayerUse` | charger checks, hub buttons | `CBasePlayer::PlayerUse`, already a trace |
| `PickupCanCollect` | refuse an ungranted weapon | `CBasePlayerItem::AddToPlayer` / `CanAddToPlayer` |
| `PlayerKilled` | DeathLink out | `CBasePlayer::Killed` |
| `ClientSay` | chat commands | `ClientCommand` in `client.cpp` |
| `MonsterKilled` | disabled location types | `CBaseMonster::Killed`, only if ever re-enabled |
| `g_Scheduler` | polling, delayed traps | `StartFrame` with a time accumulator |
| `GiveNamedItem` | grant a weapon | `CBasePlayer::GiveNamedItem`, directly |
| `ClientPrint` | player-facing text | `ClientPrint` / `UTIL_ShowMessage` |
| `ChangeLevel` | warps | `SERVER_COMMAND("map <name>\n")` |

The suit stays an item in the pool and is granted, never removed. That rule is
not negotiable and it is not an implementation detail: the suit owns the weapon
HUD and weapon switching, and a player without it cannot use what they have.

## Phases

**Phase 0, the spike.** A `hlap` mod folder with `fallback_dir "valve"`, running
a dll built unmodified from the current SDK, that starts a retail single-player
map through the fallback and prints to the player. If that works, everything
else follows. If it does not, try Metamod before anything else is written. Do
not skip this: it is two days that de-risks the whole project.

**Phase 1, strip and regenerate.** The strip list above, then the new layout
table, then regenerate `campaign.json`, `ids.json` and `checkdata.txt` against
`valve/maps`. Port the test suite. No game and no C++ needed, and it ends with a
world that generates seeds.

**Phase 2, world and client.** Finish the option cuts, repoint the client at the
mod folder, reuse the launcher. Ends with a client that connects and writes
snapshots nothing reads yet.

**Phase 3, plugin core.** Bridge file I/O, `checkdata.txt` parsing,
`ServerActivate`, the poll loop, console commands, `map_reached` and
`chapter_complete`. First playable: missions enterable, checks flowing, nothing
gated.

**Phase 4, gating.** Weapon pickup refusal, loadout reapply on spawn, suit and
long jump module, the changelevel choke point. This is where retail's inventory
carry-over is fought and won. Allow schedule slack here.

**Phase 5, chargers and the rest.** Charger `+use` detection and position
matching, `!find` positions, DeathLink both directions, traps with their
precache constraint, chat relay.

**Phase 6, hub map and polish.** The authored hub, setup guide, and an in-game
verification checklist in the shape of `docs/verification.md`.

Phases 1 and 2 are mechanical and need no C++. Phases 3 through 5 are the real
work and are one person's job, since they are all the same file set.

## Risks, in the order they can hurt

1. **Charger identity across builds.** Handled by Decision 5, and only if that
   decision is actually implemented in Phase 1. Left as brush index, it surfaces
   as chargers that quietly never fire after any future Valve map patch, which
   is the hardest class of bug to notice.
2. **Trap spawns and precache.** GoldSrc fatally errors on an unprecached model,
   and the precache table is finite. Traps must precache their fixed set at map
   load or be restricted to entities the current map already has. A precache
   pass was written and reverted once on the Sven side; the situation here is
   different, but treat it as the same class of hazard and get agreement before
   adding one.
3. **`game_player_equip` and code-granted weapons.** Refusing a pickup does not
   catch a weapon handed over by map logic. Sweep the entity lumps for
   `game_player_equip` during Phase 1 so the exceptions are known before Phase 4
   rather than discovered in play.
4. **Mission boundary interception.** Issuing a level change from inside code
   the engine is already running a level change through is exactly the crash
   class documented in the Sven project. Same discipline: defer, never inline.
5. **Level state and the save system.** `map` for warps sidesteps most of it.
   The residual case is a player who quicksaves in a mission and quickloads after
   the client has moved on. The stateless design handles it; test it anyway.
6. **Hazard course.** `t0a0*` is a real map series with chargers in it. Decide
   early whether it is a mission, an excluded intro, or absent.
7. **A future Valve patch.** The anniversary build is maintained, not frozen.
   Anything keyed to map contents should degrade to "this check never fires"
   rather than to a crash.

## Effort

One developer who knows C++, working from the Sven project, with Phase 0 as a
gate.

| Phase | Estimate |
| --- | --- |
| 0, spike | 2 days |
| 1, strip and regenerate | 3 to 4 days |
| 2, world and client | 2 to 3 days |
| 3, plugin core | 1 to 2 weeks |
| 4, gating | 1 to 2 weeks |
| 5, chargers, DeathLink, traps | 1 week |
| 6, hub map and docs | 1 week |

Six to eight weeks part time to a state comparable with where the Sven world is
now, first playable at the end of Phase 3.

## Where the port stands

Phases 1 and 2 are complete. `python -m pytest tests -q` passes; the world's own
tests under `apworld/half_life/test/` need an Archipelago checkout to run and
have not been exercised yet.

### Done

- `apworld/half_life_sven/` is `apworld/half_life/`, game name `Half-Life`,
  world version reset to 0.1.0, id bases moved to 7,750,000 / 7,760,000 with a
  fresh `ids.json`.
- The AngelScript tree, `tools/install_plugin.py` and its test are gone.
  `apworld/half_life/mod/` replaces them: it owns the `hlap` folder, its
  `liblist.gam`, the generated `checkdata.txt` and the built dll, and it is the
  one code path behind both the client's `/install` and `tools/install_mod.py`.
- `tools/campaign_layout.py` is one campaign against retail's maps, and the
  multi-campaign machinery is gone from the world, the client, the generators and
  the bridge snapshot (`goals_open`, the `M` and `R` records, `GOAL_COMPANIONS`,
  the paired-finale pairing, the `campaign`/`campaigns` split on items).
- Chargers are keyed by rounded world-space centre. The `ba_canal1` origin
  special case went with it.
- Docs rewritten: `README.md`, `docs/protocol.md`, the setup guide and the game
  page. `docs/verification.md` and `docs/releases/` were deleted rather than
  rewritten -- they described in-game behaviour that does not exist yet, and the
  Phase 6 checklist should be written against the real thing.

### Where the port differs from the plan above

- **The chapter table came out of the maps, not out of memory.** A map's
  `worldspawn` carries a `chaptertitle` key when it starts a chapter, and the
  names those keys resolve to in `valve/titles.txt` are the mission names.
  Chapter keys are the first map of the chapter (`c1a0c`, `c2a4d`), which is
  permanent, unambiguous, and not diffable against the Sven world's keys.
- **18 chapters, not 18 plus an endgame.** `c5a1` is folded into Nihilanth,
  because arriving on it is exactly the moment Nihilanth dies. That also removed
  the need for the `endgame_chapters` machinery the Sven world needed for Blue
  Shift's outro.
- **The hazard course is out.** `t0a0*` is a training course, nothing
  changelevels into it, and Valve's own chapter list does not contain it. Risk 6
  is closed.
- **`random_starting_weapon` and `allow_restricted_starting_weapon` are gone,**
  where the plan kept the first. Retail has exactly one melee weapon, so the
  option could never do anything, and keeping it would have meant keeping
  `MELEE_STARTERS`, `melee_starters_for`, the per-seed starting weapon roll and
  its Universal Tracker passthrough for no effect. `STARTING_WEAPONS` is the
  constant `["weapon_crowbar"]`; the snapshot still carries `starting` as a
  per-seed field, so restoring the option later costs nothing.
- **240 locations, not the 190 estimated:** 96 `map_reached`, 111 `charger`, 18
  `chapter_complete`, 15 `weapon_pickup`, against 32 progression items. Retail's
  97 campaign maps are finer grained than the estimate assumed.

### Answers to things the plan left open

- **`game_player_equip`: there are none** anywhere in the campaign. Risk 3 is
  closed. What exists instead is two `player_weaponstrip` entities, in `c2a3d`
  (Apprehension, mid-mission -- the loadout has to survive it) and `c5a1` (the
  ending, where it is correct).
- **There is no `item_suit` entity in the campaign either.** The HEV suit is
  granted some other way in `c1a0d`, and Phase 4 has to find out how before it
  can gate armour. It also means there is no "First HEV Suit" check; the
  generator says so when it runs.
- **The game name is still `Half-Life`** in `archipelago.json`, and the possible
  collision with GoldSRC-Archipelago/halflife-archipelago has not been checked.
  `Half-Life (GoldSrc)` remains the fallback. Change it before the first release,
  not after.

### The game side, as written

`game/` is the whole of Phases 3 to 5, unbuilt. Decisions taken while writing it
that the plan above did not anticipate:

- **Pickups are refused in the game rules,** not at the touch functions.
  `CGameRules::CanHavePlayerItem` and `CHalfLifeRules::CanHaveItem` are the one
  question every path into the inventory already asks -- including a weapon
  handed over by `GiveNamedItem` from map logic, which the plan listed as risk 3
  and which is now closed by construction rather than by a sweep. Refusing there
  leaves the entity in the world with no pickup sound, which is exactly the
  wanted behaviour. Granting sets a flag so our own grants are not refused by the
  rule that exists to refuse the map's copy.
- **Chargers are matched by nearest unit,** not by rebuilding the generator's
  rounded key. Two languages agreeing on how to round a float at the boundary is
  a silent bug waiting to happen; nearest-within-32-units cannot be ambiguous
  when no two chargers of a kind are closer than 204.
- **The hub is `t0a0`,** the hazard course entrance, until there is an authored
  map: real, small, empty, and deliberately outside the campaign, so nothing can
  fire there.
- **`ap_pending.txt` is gone.** A queued map change never has to outlive a map
  load, since the load is the thing being queued. `ap_amnesty.txt` remains the
  only file the game side keeps.
- **The SDK edit is 42 lines** across six files, one include and one call per
  hook, generated by editing a clean clone so the patch applies by construction.
  `ap_main.h` redeclares the seven entry points the patch calls so that Valve's
  files never include more than one of ours.

### Next

Confirmed in play: the hub, `ap`, `ap_warp`, arrival checks, charger checks,
weapon refusal, item delivery, saves and intra-mission transitions.

Not yet, in the order a run-through will reach them:

1. **The mission boundary.** Play to the end of a mission's last map and let the
   game's own `trigger_changelevel` fire. It should be intercepted, report the
   mission complete, and return to the hub. Most moving parts, and the one place
   a mistake can still crash the engine.
2. **The finale's seal.** Finish `missions_required` missions and check that
   Nihilanth opens, that `ap_warp` into it works, and that clearing it sends the
   goal.
3. **DeathLink**, both directions, and the amnesty countdown across a map change.
4. **The traps.** Butterfingers is exercised; the two spawning traps are not, and
   they are the ones that depend on the precache.
5. **The known map facts**, from `game/README.md`. `c2a3d`'s mid-mission
   `player_weaponstrip` is the first thing to test, and how `c1a0d` actually
   grants the HEV suit is the first thing to find out.

Data work with no game side to it, parked until the above is done: the map
divisions are much finer than the Sven project's (96 against 35), so the
`map_reached` set wants a pass for whether every one of them earns a check.
Regenerating keeps existing ids and appends new ones, so it can happen whenever.
