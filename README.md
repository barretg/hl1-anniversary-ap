# Half-Life (Sven Co-op) — Archipelago

An Archipelago randomizer for the Half-Life campaign as shipped inside
[Sven Co-op](https://store.steampowered.com/app/225840/Sven_Coop/). The campaign
portal map is the hub, every mission is locked behind a received item, and every
weapon but the crowbar has to be found in the multiworld.

Player-facing docs: [setup guide](apworld/half_life_sven/docs/setup_en.md) ·
[game page](<apworld/half_life_sven/docs/en_Half-Life (Sven Co-op).md>)

## Why Sven Co-op rather than vanilla Half-Life

Sven Co-op exposes a real server-plugin API (AngelScript) with the exact hooks
this needs — `PickupObject::CanCollect`, `Game::MapChange`, `Player::PlayerSpawn`,
`Monster::MonsterKilled` — plus sandboxed file I/O. That means no C++ engine fork
and no DLL patching: the whole game-side integration is text files you can edit
and reload. It also already ships the full campaign as co-op maps and a hub map
with a console per chapter. Vanilla Half-Life has a separate, engine-level effort
at [GoldSRC-Archipelago/halflife-archipelago](https://github.com/GoldSRC-Archipelago/halflife-archipelago).

## Layout

```
apworld/half_life_sven/     the Archipelago world
  data/campaign.json        generated: chapters, items, locations, logic groups
  client/                   the AP client and the file bridge
  plugin/                   the Sven Co-op server plugin, plus its installer
    plugins/                mirrors svencoop/scripts/
      archipelago/          ap_main, ap_bridge, ap_items, ap_locations, ap_hub, ap_deathlink
      store/archipelago/checkdata.txt   generated
  docs/                     setup guide and game page
tools/                      generators, packaging, installer CLI
tests/                      bridge, data consistency and install tests
docs/protocol.md            the file bridge between client and plugin
examples/                   a starter YAML
```

## How the pieces fit

```
Archipelago server
      | AP protocol
Python client  (Launcher component)
      | two text files in scripts/plugins/store/archipelago/
AngelScript plugin
      | hooks
Sven Co-op running hl_c00 ... hl_c18
```

The client is the source of truth; the plugin holds no state across map changes.
See [docs/protocol.md](docs/protocol.md).

## Locations

A location is currently "you reached this part of the campaign": one per map,
plus one per mission for finishing it. 53 locations against at most 32
progression items.

Richer location types are already implemented and derived from the map files
themselves: `tools/bsp_entities.py` reads the entity lump out of each shipped
`.bsp`, so a check can only exist where the entity behind it provably exists.
That produced individual weapon pickups, notable-enemy kills and kill-count
milestones, but too many of them read as arbitrary in play, so they are switched
off via `ENABLED_LOCATION_TYPES` in `tools/campaign_layout.py` pending a pass to
work out which ones actually earn a check.

Editorial decisions that *cannot* be derived from the maps — mission grouping,
which classnames map to which item, and the logic gates — live in one file,
[`tools/campaign_layout.py`](tools/campaign_layout.py). That is the file to edit
when tuning logic.

## Working on it

```bash
python -m pytest tests -q

# after editing tools/campaign_layout.py
python tools/build_campaign_data.py --maps "<Sven Co-op>/svencoop/maps"
python tools/gen_checkdata.py

# package, and optionally drop straight into an Archipelago install
python tools/build_apworld.py --install "<Archipelago>/custom_worlds"

# install the plugin into Sven Co-op, without going through the Launcher
# (same code path as the client's /install)
python tools/install_plugin.py --game "<Sven Co-op>"
```

`campaign.json` and `checkdata.txt` are both committed, so neither the apworld
nor the client needs Sven Co-op installed — only the generators do.

## Status

The world generates against Archipelago 0.6.7 (verified across
`missions_required` 1/8/17, strict and loose logic, with and without the HEV suit
and long jump module shuffled). The bridge protocol and the data consistency
between the two halves are covered by tests.

The AngelScript plugin has **not yet been run in-game**.
[docs/verification.md](docs/verification.md) lists what has been verified, and
gives an ordered in-game checklist that calls out the two assumptions most likely
to need adjusting.
