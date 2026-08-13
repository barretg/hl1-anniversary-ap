# Half-Life — Archipelago

An Archipelago randomizer for retail Half-Life on Steam, the 25th anniversary
build. The campaign is cut into 18 missions, each locked behind a received item;
every weapon but the crowbar has to be found in the multiworld; and you travel
between missions from a hub rather than playing straight through.

Player-facing docs: [setup guide](apworld/half_life/docs/setup_en.md)

This is a fork of [hl1-sven-ap](https://github.com/xLander/hl1-sven-ap), the same
game played inside Sven Co-op. Roughly 70 percent of that project has no engine
dependency and is reused as is: the world, the client, the file bridge and the
data generators. What is new here is the mission layout against retail's own maps
and the game side, which is a Half-Life server dll rather than an AngelScript
plugin.

**Status: playable, unfinished.** The world, the client and the data pipeline
are ported and tested. The game side is written and runs: the mod loads, missions
warp, checks fire, items arrive, and pickups are refused until the multiworld
sends them. What has not been proved in play is the far end of a run -- the
mission-boundary interception, the finale's seal, DeathLink -- and nothing has
had a full run-through yet. See [docs/PORT_PLAN.md](docs/PORT_PLAN.md) for what
is left and [game/README.md](game/README.md) for how the game side is built. // TODO: update, all of these things are tested working

## The target

Retail Half-Life on Steam, current build. Not `steam_legacy`, not WON, not Xash.
Opposing Force and Blue Shift are separate games with their own dlls and are out
of scope until this one ships.

The mod installs as its own game folder, `hlap`, with `fallback_dir "valve"`, so
your Half-Life install is never written to and every map, model and sound is
inherited from your own copy of the game.

## Missions

18, from Black Mesa Inbound to Nihilanth, taken from the game's own chapter
boundaries: a map that carries a `chaptertitle` on its `worldspawn` starts a
mission, and the names are the strings those keys resolve to in `titles.txt`.
Endgame (`c5a1`) is folded into Nihilanth, because arriving on it is exactly the
moment Nihilanth dies. The hazard course is not part of the campaign and is left
out.

Nihilanth has no unlock item: it opens once `missions_required` other missions
are finished, and clearing it wins the seed.

A mission is entered from the hub with a fresh `map` load, so it is repeatable
and carries no state in from anywhere else. Transitions *inside* a mission are
the game's own -- inventory and level state carry exactly as retail does.

## The hub

New Game starts in `stalkyard`, not on the tram, and every mission is reached
from there with `ap_warp`. Until there is an authored hub map it is a stock
deathmatch map, chosen against the map files rather than by taste: no
`trigger_changelevel` (`lambda_bunker` has one straight into the middle of Forget
About Freeman), nothing that hurts you while you stand still (`pool_party` has a
`dmg 200` trigger), and small, because it is reloaded after every mission.

Nothing in the hub can fire a check. Its weapons are not the campaign's weapons,
and its two chargers are not in `checkdata.txt` at all.

## Layout

```
apworld/half_life/         the Archipelago world
  data/campaign.json       generated: chapters, items, locations, logic groups
  client/                  the AP client and the file bridge
  mod/                     the hlap game folder, plus its installer
    files/                 liblist.gam, checkdata.txt, and the built dll
  docs/                    setup guide
game/                      the server dll: sources, build, and its own README
tools/                     generators, packaging, installer CLI
tests/                     bridge, data consistency and install tests
docs/protocol.md           the file bridge between client and game
docs/PORT_PLAN.md          what is being built, and in what order
```

## How the pieces fit

```
Archipelago server
      | AP protocol
Python client  (Launcher component)
      | two text files in hlap/archipelago/
hlap server dll
      | SDK hooks
Half-Life running c0a0 ... c5a1
```

The client is the source of truth; the game holds no state across map changes or
saves. See [docs/protocol.md](docs/protocol.md).

## Locations

Three kinds, 240 in all against at most 32 progression items:

| Type | Count | Fires when |
| --- | --- | --- |
| `map_reached` / `chapter_complete` | 114 | you reach a map division, or finish a mission |
| `charger` | 111 | you press use on a health or HEV wall unit |
| `weapon_pickup` | 15 | you reach the weapon Half-Life would first have given you |

Chargers fire on the `+use`, empty or not, so they are about finding one rather
than needing it. They can be switched off wholesale with `chargesanity: false`.

**Chargers are identified by where they stand, not by brush model index.** They
have no targetname, so the only two candidate handles are the brush model and the
position. The anniversary update recompiled single-player maps, and a recompile
renumbers brush models, so keying on the model would leave data that silently
stops matching after any future Valve patch. Position survives any recompile that
does not physically move the unit. The generator snaps its key to a 4-unit grid
so ids stay stable; the game matches by nearest unit rather than by equal
coordinates, since no two chargers of the same kind are within 204 units of each
other and two languages agreeing on how to round a float is a silent bug waiting
to happen.

Weapon checks sit at the *vanilla* first location: the earliest map in campaign
order that contains that weapon, and only there. Picking the same weapon up later
sends nothing, and neither does the arsenal lying around the hub. The crowbar has
one too, despite being starting inventory, which is why the game sweeps for
pickups within arm's reach -- a weapon you already hold never fires a touch.

Richer location types are already implemented and derived from the map files
themselves: `tools/bsp_entities.py` reads the entity lump out of each shipped
`.bsp`, so a check can only exist where the entity behind it provably exists.
That produced individual weapon pickups, notable-enemy kills and kill-count
milestones, but too many of them read as arbitrary in play, so they are switched
off via `ENABLED_LOCATION_TYPES` in `tools/campaign_layout.py`.

Editorial decisions that *cannot* be derived from the maps -- mission grouping
and names, which classnames map to which item, and the logic gates -- live in one
file, [`tools/campaign_layout.py`](tools/campaign_layout.py). That is the file to
edit when tuning logic.

Chapter keys there are permanent: `data/ids.json` keys every location by chapter,
so renaming one renumbers a location. Keys are the first map of the chapter;
names are free to change.

## Working on it

```bash
python -m pytest tests -q

# after editing tools/campaign_layout.py
python tools/build_campaign_data.py --maps "<Half-Life>/valve/maps"
python tools/gen_checkdata.py

# package, and optionally drop straight into an Archipelago install
python tools/build_apworld.py --install "<Archipelago>/custom_worlds"

# the server dll, 32-bit, against a checkout of Valve's SDK with sdk.patch on it
cmake -S game -B build/game-msvc -A Win32 -DHLSDK_DIR=../halflife
cmake --build build/game-msvc --config Release
copy build/game-msvc/Release/hl.dll apworld/half_life/mod/files/dlls/

# install the hlap mod folder, without going through the Launcher
# (same code path as the client's /install)
python tools/install_mod.py --game "<Half-Life>"
```

`campaign.json` and `checkdata.txt` are both committed, so neither the apworld
nor the client needs Half-Life installed -- only the generators do. The built
`hl.dll` is *not* committed; drop one into `apworld/half_life/mod/files/dlls/`
and packaging picks it up, so a released apworld installs a working mod while a
development checkout installs everything but the dll and says so.

Playing needs the mod running: launch Half-Life with `-game hlap -console`, or
pick Half-Life Archipelago from the Custom Game menu.

## AI Usage Disclosure

Claude Code was used in the production of this apworld and client integrated into
the IDE. No images/assets or other such content were created with generative AI.
This apworld is fully human designed with no creative design input from
generative AI.
