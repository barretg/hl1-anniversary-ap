# Half-Life (Sven Co-op) Setup Guide

## Requirements

- Sven Co-op (free on Steam). The Half-Life campaign maps ship with it — there is
  nothing extra to download.
- Archipelago 0.6.7 or newer.
- The `half_life_sven.apworld` file.

## Install

1. Put `half_life_sven.apworld` in your Archipelago `custom_worlds` folder.
2. Open the Archipelago Launcher and start **Half-Life (Sven Co-op) Client**.
3. The first time it runs, a folder picker asks for your Sven Co-op folder (the
   one containing `svencoop`). It remembers the answer in your `host.yaml`, so it
   only asks once:

   ```yaml
   half_life_sven_settings:
     game_folder: F:/SteamLibrary/steamapps/common/Sven Co-op
   ```

   You can edit that by hand instead of using the picker if you prefer.
4. Type `/install` in the client. That copies the AngelScript plugin into your
   game and registers it in `svencoop/default_plugins.txt`.

`/uninstall` removes it again. Your live bridge files are left alone.

If you would rather do it by hand, the plugin tree is inside the apworld at
`half_life_sven/plugin/plugins/`, which mirrors `svencoop/scripts/`. Copy it
across and add this block to `svencoop/default_plugins.txt` yourself:

```
"plugin"
{
    "name" "Archipelago"
    "script" "archipelago/ap_main"
}
```

## Play

1. Generate and host a multiworld containing your Half-Life (Sven Co-op) slot.
2. Start Sven Co-op and create a **listen server** (New Game) on the map
   `-sp_campaign_portal`. This is the Sven Co-op campaign portal, and it is your
   hub. Plugins only run on servers, so joining someone else's server means
   *their* machine needs the plugin and the client.
3. Connect the client to the room.

You should see `[AP] Connected to the multiworld.` in the game chat.

## Client commands

| Command | Effect |
| --- | --- |
| `/install` | install the plugin into the selected game folder |
| `/uninstall` | remove the plugin, leaving your bridge files |
| `/gamedir` | reopen the folder picker to change installs |
| `/gamedir <path>` | set the folder directly, without the picker |
| `/where` | show the game folder, bridge path and plugin status |
| `/commands` | list the chat commands you type inside the game |
| `/missions` | show mission unlock status |
| `/deathlink` | toggle DeathLink |
| `/amnesty <n>` | show or change the DeathLink amnesty for this session |

## Playing the randomizer

You start with the crowbar, the medkit, and **one random mission unlock**.

Walk up to a chapter's console in the portal room and press either button. The
plugin rewires the consoles: one press travels to that mission if you have its
unlock, or tells you it is locked. The stock portal's "two players standing on
the same console" requirement no longer applies, so this works solo.

There is no console for Black Mesa Inbound — the portal map does not have one.
`!warp 0` is the only way to reach mission 0. If you would rather not have a
mission that can only be reached by typing a command, set
`include_black_mesa_inbound: false` in your YAML and it is left out of the seed
entirely, along with its checks and its unlock item.

Chat commands (press `Y` in game, not the console):

| Command | Effect |
| --- | --- |
| `!help` | list these commands |
| `!ap` | list every mission and its status, printed to your console (`~`) |
| `!warp <number>` | travel to an unlocked mission |
| `!hub` | return to the campaign portal |

The client also prints this list when it connects.

Finishing a mission sends you back to the hub automatically and sends its
completion check. Trying to enter a locked mission is refused.

**Weapons are items.** A weapon lying in the world still sends its check the first
time you walk over it — anywhere in the campaign, and whether or not you are
allowed to keep it. You cannot hold it until the multiworld gives you that weapon.
The campaign's own per-map loadouts are stripped for the same reason.

**Chargers are checks.** Every health charger and HEV charge panel sends a check
the first time someone presses use on it, even an empty one. That is 107 of the
173 locations; `chargesanity: false` in your YAML removes them all for a much
shorter run.

**Nihilanth is not unlocked by an item.** It opens once you have completed
`missions_required` missions (set in your YAML; the default is all 17 others).

## DeathLink

Any death gibs the entire Sven Co-op lobby, and if DeathLink is on it is also
sent to the multiworld. A DeathLink arriving from another world gibs everyone in
the lobby too. Toggle it live with `/deathlink` in the client.

**Amnesty.** `death_link_amnesty` in your YAML (default 4) is how many deaths the
lobby is forgiven before one is reported to the multiworld. It only affects
deaths going *out*: inside Sven Co-op the lobby still gibs every time, and the
death message says how much is left ("Amnesty remaining: 3"). When the allowance
runs out the next death goes to the multiworld and the allowance starts again.
The countdown is shared by everyone in the lobby, survives map changes, and can
be changed for the session with `/amnesty <n>`. Set it to 0 to send every death.

## Troubleshooting

**Nothing happens / no `[AP]` messages.** The plugin is not loading. Check the
server console for `[AP] loaded 18 chapters, 174 locations` at map start. If it
is missing, `default_plugins.txt` is wrong or the scripts were not copied.

**`[AP] FATAL: could not open .../checkdata.txt`.** `scripts/plugins/store/archipelago/checkdata.txt`
did not get copied. Rerun the installer.

**Client connects but the game never reacts.** `/gamedir` is pointing at the
wrong install. The client prints the bridge path it is using; check that
`ap_in.txt` is appearing there.

**You keep the weapons you pick up.** The plugin is not running, or that
classname is not in `checkdata.txt`. Only the classnames listed as `K` records
are gated.
