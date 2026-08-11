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

- Press a console button in the portal room, solo. It should warp with no second
  player and no "Access Denied" clip. Pressing a locked mission's console should
  print the lock message instead.
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

### 6. Goal

Set `missions_required: 1` for a short test seed. Confirm Nihilanth stays sealed
until one mission is complete, then opens, and that killing Nihilanth sends
`GOAL` and the client reports the goal to the server.
