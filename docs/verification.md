# Verification

## What has been verified

| Area | How | Status |
| --- | --- | --- |
| Bridge protocol | `pytest tests/test_bridge.py` | passing |
| Data consistency (`campaign.json` ↔ `checkdata.txt`) | `pytest tests/test_campaign_data.py` | passing |
| World generation, AP 0.6.7 | `ArchipelagoGenerate` on real seeds | passing |
| Option matrix | `missions_required` 1 / 8 / 17, strict + loose, suit and long jump on and off, 3-slot multiworld | passing |
| AngelScript plugin | — | **not yet run in-game** |

The location and item tables are derived from the shipped `.bsp` files rather
than written by hand, so "does this entity exist in this map" is verified by
construction.

## In-game checklist

The AngelScript half has been written against the API as documented and as used
by Sven Co-op's own shipped scripts, but has not been executed. Work through this
in order — each step depends on the one above it.

### 1. The plugin loads

Start a listen server on `-sp_campaign_portal` and check the server console for:

```
[AP] loaded 18 chapters, 174 locations
```

If it is missing, the plugin is not registered or `checkdata.txt` is not in
`svencoop/scripts/plugins/store/archipelago/`.

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
