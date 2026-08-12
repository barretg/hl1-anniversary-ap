# Half-Life (Sven Co-op) — Archipelago

An Archipelago randomizer for the single-player campaigns shipped inside
[Sven Co-op](https://store.steampowered.com/app/225840/Sven_Coop/): Half-Life,
Opposing Force, Blue Shift and They Hunger, in any combination. The campaign
portal map is the hub, every mission is locked behind a received item, and every
weapon but the crowbar has to be found in the multiworld.

Player-facing docs: [setup guide](apworld/half_life_sven/docs/setup_en.md) ·
[game page](<apworld/half_life_sven/docs/en_Half-Life (Sven Co-op).md>)

## A note on multiplayer

Sven Co-op is a multiplayer game, and its versions of these campaigns are built to
be played co-operatively. Some of what they ask of you is there on purpose to keep
it that way.

This randomizer is made for co-op lobbies. We do not endorse using it, or any
convenience it adds, to work around Sven Co-op's multiplayer design or to treat
these campaigns as free single-player games. Play it with other people. If you
want Half-Life on its own, buy Half-Life.

## Campaigns

| YAML option | Campaign | Missions | Maps | Finale |
| --- | --- | --- | --- | --- |
| `include_half_life` | Half-Life | 18 | 35 | Nihilanth |
| `include_opposing_force` | Opposing Force | 13 | 34 | Worlds Collide |
| `include_blue_shift` | Blue Shift | 7 | 31 | Power Struggle |
| `include_they_hunger` | They Hunger | 3 | 19 | Episode 3 |

Half-Life alone is the default, so an existing YAML generates the seed it always
did. Each enabled campaign opens with one of its own missions, has its own
independent `missions_required`, and contributes its finale as a goal: the seed is
won when every one of them is cleared. Weapons pool across campaigns.

The hub already has consoles for all four, so none of this needed a map edit. It
numbers them inconsistently, though, and does not have one for every mission:
Half-Life's are unpadded and start at `hl_ch1` because the tram ride has no panel,
Opposing Force's are padded and skip `of_ch06`, and three of its missions have no
panel at all. So console-to-mission is a generated table (`P` records in
`checkdata.txt`) rather than arithmetic, and the mission groupings are taken from
the panel labels themselves rather than from the map names.

## Why Sven Co-op rather than vanilla Half-Life

Sven Co-op exposes a real server-plugin API (AngelScript) with the exact hooks
this needs to function. It also already ships the full campaign as co-op maps and a hub map
with a console per chapter. Vanilla Half-Life has a separate, engine-level effort
at [GoldSRC-Archipelago/halflife-archipelago](https://github.com/GoldSRC-Archipelago/halflife-archipelago).

## Layout

```
apworld/half_life_sven/     the Archipelago world
  data/campaign.json        generated: chapters, items, locations, logic groups
  client/                   the AP client and the file bridge
  plugin/                   the Sven Co-op server plugin, plus its installer
    plugins/                mirrors svencoop/scripts/
      archipelago/          ap_main, ap_bridge, ap_items, ap_locations, ap_hub,
                            ap_deathlink, ap_traps
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

Three kinds of location, 357 across all four campaigns (173 of them Half-Life's)
against at most 69 progression items:

| Type | Count | Fires when |
| --- | --- | --- |
| `map_reached` / `chapter_complete` | 160 | you reach a map division, or finish a mission |
| `charger` | 144 | you press use on a health or HEV wall unit |
| `weapon_pickup` | 53 | you reach the weapon that campaign would first have given you |

Weapon checks are per campaign, not per seed: each campaign has its own "first
shotgun" at its own earliest map. Anchoring them once across everything would
have stranded every shared weapon's check in a Half-Life map, so a seed without
Half-Life would have lost them.

Chargers are identified by their brush model index (`func_recharge:*79`), which
is the only per-entity identity the BSP and the running game agree on — they have
no targetname. The check fires on the `+use`, not on draining the unit. They can
be switched off wholesale with `chargesanity: false`.

Weapon checks sit at the *vanilla* first location: the earliest map in campaign
order that contains that weapon, and only there. Picking the same weapon up later
sends nothing. The crowbar has one too, despite being starting inventory.

Walking over a weapon sends its check whether or not the multiworld has granted
it. Because the engine's pickup hook does not fire for a weapon you already
carry — the crowbar, always — a one-second proximity sweep backs it up, so no
weapon check can become unsendable.

Richer location types are already implemented and derived from the map files
themselves: `tools/bsp_entities.py` reads the entity lump out of each shipped
`.bsp`, so a check can only exist where the entity behind it provably exists.
That produced individual weapon pickups, notable-enemy kills and kill-count
milestones, but too many of them read as arbitrary in play, so they are switched
off via `ENABLED_LOCATION_TYPES` in `tools/campaign_layout.py` pending a pass to
work out which ones actually earn a check.

Editorial decisions that *cannot* be derived from the maps — which campaigns
exist, mission grouping, console-to-mission, which classnames map to which item,
and the logic gates — live in one file,
[`tools/campaign_layout.py`](tools/campaign_layout.py). That is the file to edit
when tuning logic or adding a campaign.

Chapter keys there are permanent: `data/ids.json` keys every location by chapter,
so renaming one renumbers a location and breaks existing seeds. Names are free to
change. Adding the three new campaigns appended 213 ids and moved none.

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

The AngelScript plugin has been tested in-game but requires further stress testing. Please ping @xLander in discord with any bugs.
[docs/verification.md](docs/verification.md) lists what has been verified (but it's kinda outdated, haha), and
gives an ordered in-game checklist that calls out the two assumptions most likely
to need adjusting.

## AI Usage Disclosure

Claude Code was used in the production of this apworld and client integrated into the IDE. No images/assets or other such content were created with generative AI. This apworld is fully human designed with no creative design input from generative AI. 
