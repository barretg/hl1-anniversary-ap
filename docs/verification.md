# Verification

## What has been verified

| Area | How | Status |
| --- | --- | --- |
| Bridge protocol | `pytest tests/test_bridge.py` | passing |
| Data consistency (`campaign.json` ↔ `checkdata.txt`) | `pytest tests/test_campaign_data.py` | passing |
| World generation, AP 0.6.7 | `ArchipelagoGenerate` on real seeds | passing |
| Option matrix | `missions_required` 1 / 8 / 17, strict + loose, suit and long jump on and off, 3-slot multiworld | passing |
| Campaign matrix | all four enabled, Opposing Force alone, They Hunger alone, every campaign switched off, and a pre-campaign YAML | passing |
| AngelScript plugin | — | **multi-campaign half not yet run in-game** |

The location and item tables are derived from the shipped `.bsp` files rather
than written by hand, so "does this entity exist in this map" is verified by
construction.

## In-game checklist

The AngelScript half has been written against the API as documented and as used
by Sven Co-op's own shipped scripts, but has not been executed. Work through this
in order — each step depends on the one above it.

### 0. Campaigns, first

Everything below assumes a Half-Life seed, which is still the default. Do these
first on a seed with **all four campaigns enabled**, because they are the parts
that have never run in-game at all.

- **The consoles go where they say.** This is the one with a real chance of being
  wrong, and it *was* wrong once already: no campaign has a console for its intro
  mission, and wiring them as though it did put every Opposing Force panel a
  mission early, so the one labelled Welcome To Black Mesa opened boot camp.
  Press each Opposing Force console in turn and confirm the mission you arrive in
  is the one on the panel. Blue Shift too. The fix is one line of `consoles=` in
  `tools/campaign_layout.py` followed by a regenerate.
- **The intro missions have no console at all** and are reached only by `!warp`:
  0 Black Mesa Inbound, 18 Boot Camp, 29 Living Quarters Outbound.
- **Four missions are open at the start**, one per campaign, and `!ap` lists all
  37 missions grouped under campaign headings.
- **Weapons cross over.** This is the untested engine question: receive an
  Opposing Force weapon (displacer, sniper rifle, spore launcher) while standing
  in a Half-Life map and confirm it arrives, draws, and fires rather than erroring
  or dropping the server. Those classnames are all in `server.dll`, so the risk
  is precaching rather than existence: models and sounds a Half-Life map never
  loaded. Test the reverse too, a crossbow or Tau cannon on `of1a1`.
- **They Hunger's weapons deliberately do not cross over.** Receive a tommy gun
  or tesla gun while in Black Mesa: nothing should happen, no error, no crash.
  Warp to a They Hunger episode and it should be in your hands on the next spawn.
  Its arsenal is custom entities its own map scripts register, so asking for one
  elsewhere would ask the engine to build something that does not exist. If one
  *does* arrive on a Half-Life map, the `R` records are not being honoured.
- **A finale ends its campaign, not the run.** Finish one campaign's last mission
  and confirm chat says that campaign is complete, the client logs how many are
  left, and the slot is **not** marked goal-complete. Only the last one should
  send `CLIENT_GOAL`.
- **Blue Shift's ending is sealed as a pair.** Power Struggle has no unlock item
  at all: it opens on `blue_shift_missions_required` like the finale behind it.
  Before the count is met, `!ap` should read `sealed (...)` for both and both
  consoles should refuse, saying "sealed until more missions are done" rather
  than "locked" -- there is no item coming. Meet the count and Power Struggle
  opens; with it still unfinished, A Leap Of Faith should read
  `sealed (finish more missions, including Power Struggle)` however many other
  missions are done. Clear Power Struggle and it opens.
- **A Leap Of Faith is credited when it ends, not when it loads.** Warp in and
  confirm nothing is sent on arrival -- the campaign used to be won by
  connecting, because the outro is one map and arriving on a finale's last map
  is normally the only moment there is. Watch it through to the credits: the
  completion, the goal and the trip back to the hub should all land after the
  map's `game_end`, from the next map load if the server cycled somewhere else.
  Leaving early with `!hub` or `!warp` must credit nothing.
- **The counts stay separate.** With `missions_required: 1` and
  `opposing_force_missions_required: 9`, one Half-Life mission opens Nihilanth
  and does nothing at all for Worlds Collide.
- **A campaign left out of the seed** shows every one of its missions as "not in
  this seed" in `!ap`, and its consoles refuse with that message.
- **Shared weapons still arrive without Half-Life.** On an Opposing Force only
  seed, receive the Shotgun and confirm you can pick one up. Attributing shared
  weapons to whichever campaign declared them left this seed with shotguns and no
  shotgun item, so every one of them was refused for the whole run.

With `random_starting_weapon: true` and Opposing Force or They Hunger enabled:

- **You spawn holding the rolled weapon**, not a crowbar, and it is the same
  weapon after a map change and after dying.
- **Crowbars are refused.** Walk over one: the `First Crowbar` check still sends,
  the weapon is not kept. That is the point of the swap.
- **The rolled weapon never arrives as an item**, because it left the pool.
- With `allow_restricted_starting_weapon: true` and They Hunger enabled, the
  spanner becomes possible. If it rolls, expect to be **empty-handed outside They
  Hunger** until a weapon arrives: that is the documented rough edge, not a bug.
  Check the medkit is still there.

`!tracker`:

- Prints to console grouped by mission and map, `[x]` for found. The chat line
  reports the same totals.
- Charger lines are absent entirely on a `chargesanity: false` seed, rather than
  listed and permanently unticked. Same for a campaign left out.
- `!tracker hl_c03` and `!tracker office` both narrow it; the totals at the
  bottom stay for the whole seed.
- Send a check and run it again: that location flips to `[x]` without a map
  change, since the client rewrites the snapshot as soon as the check lands.

Console spellings (`~`), which do the same work without opening chat:

- **`.ap`, `.ap_tracker`, `.ap_find`, `.ap_warp`, `.ap_hub`, `.ap_help` — with
  the leading dot.** Sven namespaces a plugin's console commands from
  `concommandns` in `default_plugins.txt`; we set none, so the separator dot
  survives on its own and the bare name is an unknown command. The server prints
  the qualified list at load, and that line is the truth:

  ```
  Angelscript: Adding console command '.ap'
  [AP] console commands ready (6): .ap, .ap_tracker, ...
  ```

- Each must behave exactly as its `!` twin, and `.ap_find hev charger` must take
  the whole phrase rather than only the first word.
- `!` commands work in chat only, `.` commands in the console only. Typing `!ap`
  into the console is an unknown command and always will be.
- They register when the module loads, not per map — and the module only loads
  on server start or `as_reloadplugins`, so copying new script files over a
  running server changes nothing.

`!find`:

- `!find` with no argument names the nearest unfound check on your map, where
  "nearest" counts height several times over: something 800 units above you is a
  hunt for the stairs, not a walk. Ranking by the straight line offered Office
  Complex's shotgun (677 out, 791 up) ahead of two chargers on the player's own
  floor. Stand at the Office Complex spawn and confirm it offers a charger rather
  than the shotgun.
- Walk toward whatever it named and run it again: the distance must fall. That is the whole test of
  whether the coordinates are right, and it is worth doing in one Half-Life map,
  one Opposing Force map and one They Hunger map, since the position comes from
  the BSP rather than anything the game tells us.
- Stand next to a charger and `!find` it: a few dozen units, "right about where
  you are standing", clear line.
- Turn 180 degrees on the spot and run the same `!find`: the distance must not
  change and the bearing must flip to "behind you". Left and right come from your
  own facing, so this is the check that they are not reversed.
- `!find hev charger 3` matches by name; `!find shotgun` on a seed with several
  campaigns lists the matches to console rather than guessing.
- `!find` for something in another mission names the mission and its `!warp`
  number instead of pointing.
- The line is a straight one and will happily point through a wall. "Something
  solid is in the way" is the tracer saying so, and is expected in corridors.
- With only Half-Life or Blue Shift enabled it is always the crowbar, and the
  seed is indistinguishable from one with the option off.

### 1. The plugin loads

Start a listen server on `-sp_campaign_portal` and check the server console for:

```
[AP] loaded 37 chapters, 353 locations
```

If it is missing, the plugin is not registered or `checkdata.txt` is not in
`svencoop/scripts/plugins/store/archipelago/`. The counts are for all four
campaigns, which the data file always describes in full; a seed that leaves some
out says so through `excluded`, not by shrinking this file.

### 1a. Chat output is not truncated

The engine's client print buffer is **128 bytes** and cuts a longer message off
without a word, which is why every multi-line message is now one call per line.
Run `!help` and count: eight lines, ending with "Or press a mission console's
button in the hub." Anything ending mid-word means a print grew past the limit
again.

Worth the same glance at `!find` on a location with a long name, since
"They Hunger: Episode 1 - Health Charger 1 (Part 2)" plus a bearing is well over
128 on its own. It prints the name, the bearing and the line of sight as three
separate messages for exactly that reason.

### 2. The bridge round-trips

With the client connected, confirm `ap_in.txt` appears in the store folder and
that `!ap` in chat prints the mission list with one mission unlocked.

Watch for `HELLO|<map>` in `ap_out.txt` and `[AP] Connected to the multiworld.`
in chat.

### 3. Weapons are gated

The riskiest assumption in the plugin is that `Hooks::PickupObject::CanCollect`
fires for weapon entities and not only for item pickups. Walk over a shotgun in
Office Complex:

- **Check is sent** (chat shows the location name) — the pickup path works.
- **Weapon is refused** — `CanCollect` covers weapons. Good.
- **Weapon is kept for up to a second, then vanishes** — `CanCollect` does not
  cover weapons and `SweepIllegalWeapons` in `ap_items.as` is doing the work.
  That is the intended fallback; it is worth tightening `SWEEP_INTERVAL`.
- **Weapon is kept permanently** — neither path fired. Check that the classname
  appears as a `K` record in `checkdata.txt`.

Also confirm the campaign's own loadout is stripped: `hl_c11_a1` equips nine
weapons via its `.cfg`, and you should spawn there with only the crowbar.

### 4. Mission gating and completion

- Press a console button in the portal room. It should warp on the press, with no
  "Access Denied" clip. Pressing a locked mission's console should print the lock
  message instead.
- `!warp` into an unlocked mission, `!warp` into a locked one (must be refused).
- Play a multi-part mission to its end. The completion check should send, the
  next chapter's first map will load briefly, and you should then be returned to
  the hub. That brief load is deliberate: `MapChange` never cancels a transition,
  because doing so and then issuing our own `changelevel` crashed the game.
- Run `restart` mid-mission. Nothing should be sent and nothing should change
  level; a restart re-enters the same map and is not a transition.
- Type `!hub` from the middle of a mission. You should go back to the hub with
  **no** completion check, since you did not leave from the mission's last map.
- Type `!hub` from a **one-map** mission you just warped into (Office Complex).
  Still no completion: a transition we asked for is never a completion, however
  far into the map you got.
- Finish a mission the campaign chains straight into another (Unforeseen
  Consequences runs into Office Complex). Office Complex must send **nothing** —
  no "Reached" on the way through, no "Complete" on the way back to the hub. This
  is the phantom-check regression: reaching a mission you were bounced out of
  used to credit both.
- Repeat with the next mission **unlocked**. Still nothing: you were carried
  through it, not playing it.
- `MapChange` is observational only. Cancelling a transition with
  `HOOK_HANDLED` and then scheduling our own `changelevel` crashed the game, both
  on `restart` and on genuine mission completion, so the hook now only records
  what happened. Everything acts from `MapStart` on the far side of the
  transition, and `ChangeLevel` queues the command rather than calling
  `ServerExecute` to run it synchronously.

### 5. DeathLink

With two players in the lobby and two AP slots on DeathLink:

- One player dies → everyone else gibs, and the other slot dies. Exactly one
  DeathLink is sent, not one per player.
- An inbound DeathLink gibs the whole lobby, in the hub and mid-mission.
- No bounce-back loop (watch the client log for a run of alternating deaths).
- Kill four players with one explosion → still exactly one DeathLink.
- Trigger a DeathLink during a map load → it must be ignored on arrival, not
  applied.

With `death_link_amnesty: 2`:

- Die → lobby gibs, chat reads "Amnesty remaining: 1", **no** DeathLink in the
  client log. Die again → "Amnesty remaining: 0", still nothing sent. Die a third
  time → no amnesty line, and one DeathLink goes out.
- The fourth death starts the cycle again at "Amnesty remaining: 1".
- Spend one death, change level, die again → the countdown continues from where
  it was. It lives in `ap_amnesty.txt`, not in a global.
- An inbound DeathLink must not spend amnesty; only local deaths do.
- `/amnesty 0` in the client → the very next death goes straight out.

### 4b. HEV suit

With `shuffle_hev_suit: true` and the item not yet received:

- The weapon HUD is present and weapons can be switched with the number keys and
  the mouse wheel. This is the regression that made an unsuited run unplayable.
- Armour reads 0 on spawn even though the campaign's own loadout grants some.
- Pick up a battery → armour stays 0.
- Hold use on an HEV charge panel → the number does not climb.
- An `Armor Battery` filler grant → chat says it arrived, armour stays 0.
- Walk over the suit pickup in Anomalous Materials → refused, with the usual
  "you have not found the HEV Suit yet".

Then receive the item:

- Chat announces the suit, and armour starts accumulating from all four sources.
- Cross a map boundary → no second announcement.

With `shuffle_hev_suit: false`, armour must work from the first spawn. This used
to be gated on an item the seed never sends, leaving the player with no armour
for the entire run.

`shuffle_longjump: false` is deliberately *not* the same. The module is left to
the campaign rather than granted, so on a seed with it off:

- Anomalous Materials through Surface Tension: no long jump. Granting it here was
  the bug this split fixed, and it looked like the module being permanently on.
- Forget About Freeman (`hl_c14`) and everything after: the module works, from
  the map's own `.cfg`, with nothing from us.
- Check `ungated=item_longjump` is in `ap_in.txt`, and that it is absent with
  `shuffle_longjump: true`.

### 5a. Weapon pickups

- Walk over a weapon you have **not** been granted, in the mission that holds its
  vanilla first copy: the check sends and the centre-screen "you have not found
  the X yet" still appears.
- Walk over the same weapon type in **any other** mission: nothing sends. The
  check belongs to one place in the campaign, not to the weapon.
- Walk over a weapon you already own: the check still sends. The engine's pickup
  hook does not fire for a duplicate, so this is the proximity sweep doing it.
- `First Crowbar`, the case that only the sweep can send, since the crowbar is
  never collectable. Stand next to Half-Life's crowbar and wait a second.
- With `chargesanity: false`, charger presses send nothing and the client logs no
  rejected checks.

### 5b. Chargers

- **`ba_canal1`'s two health chargers.** They are built from one brush, `*196`,
  with the second shifted 80 units, so they are the only pair in the game the
  model alone cannot tell apart. Drink from both: each must send its own check,
  and neither may send the other's. If the second sends nothing, the engine is
  not reporting the `origin` the generator wrote into its key.
- Press use on a health charger and an HEV charger; each sends its own check
  once, and pressing it again sends nothing.
- An empty charger still sends its check.
- Chargers in a mission you re-enter later do not resend.
- Press use on ordinary buttons, doors and levers → no checks, no log spam.

### 5c. Traps

With the long jump module already received, spring any trap and watch the floor:
no module should appear. The loadout is reapplied on every snapshot change, and a
trap arriving is one, so this used to drop a module each time.

Check the module itself still works, since it is now switched on directly rather
than by handing over a pickup: with it received, duck-jump should long jump. With
`shuffle_longjump: true` and the item not yet received, it should not — including
on a map whose own .cfg hands one out.

The case that matters most is a map change, and `hl_c14` onward is where to test
it, since those maps hand a module out themselves. Long jump on one of them with
the item still locked, then cross a map boundary: the jump must be gone on the
far side. The player's flag is reset by the new map but the physics key the
engine actually reads is not, so a module picked up on one map can otherwise
follow the player into the next.


Generate with `trap_percentage: 100` for a seed that is nothing but traps.

- Scientist Trap: four scientists appear around **every** living player, and each
  set is four *different* scientists rather than four of the same model.
- Headcrab Trap: four headcrabs per player, same placement.
- With two players standing apart, both get their own four. Standing together,
  they get eight between them — that is intended, not a bug.
- Neither should spawn inside geometry. Stand with your back to a wall, in a
  corridor, and in a lift, and check nothing arrives stuck. Some bearings finding
  no room is expected and fine; all four failing is not.
- Butterfingers: every living player's held weapon lands on the floor, and stays
  there. Watch for a full second — the loadout sweep must not put it back.
- Wait thirty seconds without touching it: the weapon is reissued.
- Spring Butterfingers, then change level before the timer runs out. The weapon
  comes back on the new map rather than being withheld against a clock that
  restarted.
- Spring Butterfingers, then die. The weapon comes back on respawn.
- Springing any trap with nobody alive must not error; the trap is simply spent.

### 6. Goal

Set `missions_required: 1` for a short test seed. Confirm Nihilanth stays sealed
until one mission is complete, then opens, and that killing Nihilanth sends
`GOAL` and the client reports the goal to the server.
