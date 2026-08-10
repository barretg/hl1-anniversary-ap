# Half-Life (Sven Co-op) Setup Guide

## Requirements

- Sven Co-op (free on Steam). The Half-Life campaign maps ship with it — there is
  nothing extra to download.
- Archipelago 0.6.7 or newer.
- The `half_life_sven.apworld` file.

## Install

1. Put `half_life_sven.apworld` in your Archipelago `custom_worlds` folder.
2. Install the AngelScript plugin into Sven Co-op:

   ```
   python tools/install_plugin.py --game "C:/Program Files (x86)/Steam/steamapps/common/Sven Co-op"
   ```

   That copies `scripts/plugins/archipelago/` and `scripts/plugins/store/archipelago/`
   into your Sven Co-op install and adds this block to `svencoop/default_plugins.txt`:

   ```
   "plugin"
   {
       "name" "Archipelago"
       "script" "archipelago/ap_main"
   }
   ```

   To do it by hand, copy the contents of the repo's `angelscript/scripts/` over
   `svencoop/scripts/` and add that block yourself.

## Play

1. Generate and host a multiworld containing your Half-Life (Sven Co-op) slot.
2. Start Sven Co-op and create a **listen server** (New Game) on the map
   `-sp_campaign_portal`. This is the Sven Co-op campaign portal, and it is your
   hub. Plugins only run on servers, so joining someone else's server means
   *their* machine needs the plugin and the client.
3. Open the Archipelago Launcher and start **Half-Life (Sven Co-op) Client**.
   Connect it to the room.
4. If the client cannot find your game, point it at the install:

   ```
   /gamedir F:/SteamLibrary/steamapps/common/Sven Co-op
   ```

   The client says `Bridging through ...` once it is happy.

You should see `[AP] Connected to the multiworld.` in the game chat.

## Playing the randomizer

You start with the crowbar, the medkit, and **one random mission unlock**.

- Type `!ap` in chat to list every mission and its status (printed to your
  console, press `~`).
- Type `!warp <number>` to travel to an unlocked mission.
- Type `!hub` to return to the campaign portal.

The portal map's physical consoles work too, but they need two players standing
on a console at once — `!warp` is there so a solo run does not need a second
person.

Finishing a mission sends you back to the hub automatically and sends its
completion check. Trying to enter a locked mission is refused.

**Weapons are items.** A weapon lying in the world still sends its check when you
walk over it, but you cannot keep it until the multiworld gives you that weapon.
The campaign's own per-map loadouts are stripped for the same reason.

**Nihilanth is not unlocked by an item.** It opens once you have completed
`missions_required` missions (set in your YAML; the default is all 17 others).

## DeathLink

Any death gibs the entire Sven Co-op lobby, and if DeathLink is on it is also
sent to the multiworld. A DeathLink arriving from another world gibs everyone in
the lobby too. Toggle it live with `/deathlink` in the client.

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
