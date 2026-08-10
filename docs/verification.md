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

- `!warp` into an unlocked mission, `!warp` into a locked one (must be refused).
- Play a multi-part mission to its end. The transition out of the mission's last
  map should send the completion check and return you to the hub rather than
  continuing to the next chapter.
- The `MapChange` hook's ability to *cancel* a transition by returning
  `HOOK_HANDLED` is the second unverified assumption. If cancellation does not
  work, you will land in the next chapter and be bounced back to the hub a few
  seconds later by the `MapStart` guard in `ap_main.as` — functional, but ugly.
  Fix by leaning on the `MapStart` path only.

### 5. DeathLink

With two players in the lobby and two AP slots on DeathLink:

- One player dies → everyone else gibs, and the other slot dies. Exactly one
  DeathLink is sent, not one per player.
- An inbound DeathLink gibs the whole lobby, in the hub and mid-mission.
- No bounce-back loop (watch the client log for a run of alternating deaths).
- Kill four players with one explosion → still exactly one DeathLink.
- Trigger a DeathLink during a map load → it must be ignored on arrival, not
  applied.

### 6. Goal

Set `missions_required: 1` for a short test seed. Confirm Nihilanth stays sealed
until one mission is complete, then opens, and that killing Nihilanth sends
`GOAL` and the client reports the goal to the server.
