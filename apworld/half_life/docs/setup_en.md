# Half-Life Archipelago Setup Guide

## What you need

- **Half-Life** on Steam, current build. Not the `steam_legacy` beta branch.
- **Archipelago** 0.6.7 or newer.
- The **Half-Life apworld**, in `<Archipelago>/custom_worlds/`.

The mod installs as its own game folder, `hlap`, alongside `valve`. Your own
Half-Life is never modified: the mod folder inherits every map, model and sound
from it through `fallback_dir "valve"`. Removing the mod is deleting one folder,
and the client's `/uninstall` does exactly that.

> **Not written yet.** The game side of this project is still being built, so
> there is no server dll to install today and none of the in-game half of this
> guide works. The world generates seeds and the client connects; that is as far
> as it goes. See `docs/PORT_PLAN.md` in the repository.

## Installing

1. Put the apworld in `<Archipelago>/custom_worlds/`.
2. Start the **Half-Life Client** from the Archipelago Launcher.
3. It looks for your Half-Life folder and asks for it if it cannot find one. Pick
   the folder that contains `valve`. It is remembered in `host.yaml`, so you are
   only asked once.
4. Type `/install` in the client. It creates `<Half-Life>/hlap/` and fills it in.
5. Start Half-Life with `-game hlap` (right-click the game in Steam →
   Properties → Launch Options), or pick **Half-Life Archipelago** from the game
   list under Custom Game.

## Playing

Connect the client to your room, then load a map. The client prints what to type
in the game console (`~`):

| Command | What it does |
| --- | --- |
| `ap` | every mission and its unlock status |
| `ap_warp <number or name>` | travel to an unlocked mission |
| `ap_hub` | return to the hub |
| `ap_tracker [map]` | locations found and still out there |
| `ap_find [text]` | point at the nearest unfound check, or one you name |
| `ap_help` | these, in game |

Client-side commands, typed in the client rather than the game:

| Command | What it does |
| --- | --- |
| `/install`, `/uninstall` | add or remove the `hlap` folder |
| `/gamedir [path]` | change the Half-Life folder, or open a picker |
| `/where` | show the folder, the bridge path and whether the mod is installed |
| `/missions` | mission unlock status |
| `/deathlink`, `/amnesty <n>` | toggle DeathLink, set the forgiven-deaths allowance |
| `/chat` | toggle relaying chat between the game and the multiworld |

## How a run goes

You start with one mission open, the crowbar, and nothing else. Missions are
unlocked by items from the multiworld. Weapons are refused until the multiworld
has sent them: walking over a shotgun you have not been sent leaves it where it
is, and the check for it still fires.

Nihilanth is not unlocked by an item. It opens once you have finished
`missions_required` other missions, and clearing it wins your slot.

Warping into a mission loads the map fresh, so you always arrive with exactly
what the seed says you should have and can replay a mission freely. Transitions
*inside* a mission are Half-Life's own, so the level-to-level flow is unchanged.

Quicksave and quickload work normally. The game holds nothing across a load: the
client's snapshot is reapplied, and a check you make twice is a no-op on the
server.

## Options worth knowing

| Option | Default | What it does |
| --- | --- | --- |
| `missions_required` | all of them | how many missions open Nihilanth |
| `chargesanity` | on | every health and HEV wall unit is a check (111 of them) |
| `exclude_intro_missions` | on | drop Black Mesa Inbound, the tram ride |
| `logic_difficulty` | strict | whether logic expects a suitable weapon per mission |
| `shuffle_hev_suit` | off | armour stays at zero until the item arrives |
| `shuffle_longjump` | off | on: the module is an item. Off: Half-Life hands it out as it always did |
| `trap_percentage` | 15 | share of your filler replaced by traps |
| `death_link_amnesty` | 4 | deaths forgiven before one goes out to the multiworld |

The HEV suit is never taken away from you, whatever `shuffle_hev_suit` says: in
GoldSrc the suit draws the weapon HUD and owns weapon switching, so a player
without one cannot use what they are holding. What the item controls is armour.

## Troubleshooting

**The client says the mod folder is not installed.** Run `/install`. If it says
there is no server dll, this build of the apworld does not ship one yet.

**The game starts on the wrong content.** Check the launch option is `-game
hlap`, and that `<Half-Life>/hlap/liblist.gam` exists.

**Checks are not being sent.** `/where` shows the bridge path; both `ap_in.txt`
and `ap_out.txt` should be there and recently modified. If the client logs a data
version mismatch, the apworld that generated the seed and the one installed are
different builds -- reinstall the mod with `/install`.
