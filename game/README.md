# The game side: `hlap`

A Half-Life server dll, built from Valve's own SDK, that talks to the
Archipelago client through the file bridge in `<Half-Life>/hlap/archipelago/`.

Nothing here is written yet. This directory is the shape of the work, and the
headers under `src/` are the interfaces the modules will present; the phases are
in `docs/PORT_PLAN.md`.

## Why a dll rather than a plugin

Valve's [ValveSoftware/halflife](https://github.com/ValveSoftware/halflife)
repository tracks the 25th anniversary game, so a dll built from it is the
shipped game's own logic rather than the 2003 SDK's. That is what makes this
acceptable to a player who specifically wants the original game, and it gives
full C++ class access -- `GiveNamedItem`, `RemovePlayerItem`, `PlayerUse`,
`ItemPreFrame` -- with no third-party dependency.

The mod folder inherits everything else through `fallback_dir "valve"`, so the
player's install is never written to. See `apworld/half_life/mod/` for the
installer and `liblist.gam`.

## Building

The SDK is not vendored here. Clone it alongside this repository and point the
build at it:

    git clone https://github.com/ValveSoftware/halflife.git ../halflife
    cmake -S game -B build -A Win32 -DHLSDK_DIR=../halflife
    cmake --build build --config Release

The result is `hl.dll`, which goes to `<Half-Life>/hlap/dlls/hl.dll`. Dropping a
built dll into `apworld/half_life/mod/files/dlls/` makes the apworld install it
for the player; that path is gitignored, so a development checkout installs
everything but the dll and the client says so.

32-bit is not optional: GoldSrc loads a 32-bit dll.

## Layout

| File | What it owns | Where it attaches |
| --- | --- | --- |
| `src/ap_main.*` | wiring, the poll clock | `ServerActivate`, `StartFrame` |
| `src/ap_bridge.*` | the file protocol, both directions | nothing; pure file I/O |
| `src/ap_checkdata.*` | parsing `checkdata.txt` | read once per map load |
| `src/ap_state.*` | what the client last said: unlocks, items, excluded missions | fed by `ap_bridge` |
| `src/ap_locations.*` | firing checks: map reached, mission complete, charger, weapon | `ServerActivate`, `PlayerUse` |
| `src/ap_items.*` | the loadout, weapon refusal, grants | `CBasePlayer::Spawn`, `CBasePlayerItem::AddToPlayer` |
| `src/ap_hub.*` | console commands, warps, the mission-boundary choke point | `ClientCommand`, `CChangeLevel::ChangeLevelNow` |
| `src/ap_deathlink.*` | deaths out, deaths in | `CBasePlayer::Killed` |
| `src/ap_traps.*` | the three traps, and their precache set | `StartFrame`, precache at map load |

`ap_bridge` and `ap_checkdata` depend on nothing but the C++ standard library,
which is deliberate: they are the two pieces that can be tested without the game.

## Rules that are not negotiable

- **Never change level inline.** A level change issued from inside code the
  engine is already running a level change through is a crash. Set a flag and act
  on the next `StartFrame`. This is the single hardest-won rule from the Sven
  Co-op project.
- **The suit is granted, never removed.** It owns the weapon HUD and weapon
  switching; a player without it cannot use what they have. The `HEV Suit` item
  controls armour, not the suit.
- **Warps use `map`, not `changelevel`.** A clean load with no carried state is
  what makes a mission repeatable and independent. Transitions *inside* a mission
  stay the game's own.
- **Hold nothing across a save.** The client's snapshot is reapplied on spawn, so
  a quickload cannot desync. A re-sent check is a no-op on the server.
- **Precache everything a trap can spawn, at map load.** GoldSrc fatally errors
  on an unprecached model and the precache table is finite.

## Known map facts worth knowing before Phase 4

- `c2a3d` (Apprehension) has a `player_weaponstrip`: the game takes the player's
  weapons and the loadout has to survive that.
- `c5a1` (Endgame) has one too, which is fine -- it is the ending.
- There is no `game_player_equip` anywhere in the campaign.
- There is no `item_suit` entity anywhere in the campaign either, so the HEV suit
  is granted some other way in `c1a0d`. Find out how before gating armour.
