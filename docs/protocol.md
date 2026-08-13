# The file bridge

The Python client owns the connection to the Archipelago server; the game side is
a server dll with no networking of its own. The two talk through files in the mod
folder:

```
<Half-Life>/hlap/archipelago/
    checkdata.txt   generated, read-only at runtime
    ap_in.txt       client -> game
    ap_out.txt      game -> client
    ap_amnesty.txt  game-owned, DeathLink amnesty remaining
```

This is a deliberate choice rather than a limitation of the engine: the protocol,
the event windowing, the ACK scheme and the DeathLink amnesty rule are all
already written and tested in Python, and `client/bridge.py` has no game
dependency at all. It also keeps the game side stateless across map loads, which
in retail buys save/load resilience for free.

The client polls every 0.2 s and the game every 0.2 s, so a check reaches the
server and an item reaches the player in well under a second.

## Design rules

**The client is the source of truth.** That cuts both ways: the game must not
make decisions by consulting its cached copy of a client-owned flag. `DEATH` is
reported on every death and the client decides whether it becomes a DeathLink,
because gating in the game means a stale snapshot silently swallows deaths with
nothing in either log to explain it. DeathLink amnesty is the one exception, and
only because the death message has to name the remaining allowance at the instant
of the death: the client sends the allowance, the game counts it down and tags
the `DEATH` line, and the client still has the final say on whether anything
leaves the slot.

**The game holds no state in memory that matters across a map change.** On every
map load it re-reads `checkdata.txt` and waits for the next snapshot. A map
change, a quickload or a crash therefore costs nothing, and a re-sent check is a
no-op on the server. The one thing that genuinely must outlive a map change is
`ap_amnesty.txt`, how much DeathLink amnesty is left, and it only has to because
the death message names the remaining allowance at the instant of the death.

**The snapshot is idempotent, events are not.** `ap_in.txt` is a complete
picture, rewritten whenever it changes and safe to apply any number of times.
Anything that must happen exactly once -- a filler item grant, an incoming
DeathLink -- cannot live there, because it would fire again on the next map load.
Those ride as sequenced `event=` lines instead.

**Events are acknowledged, not counted.** The game acts on an event, writes
`ACK|<seq>` and the client then drops that line from the snapshot. The game does
not have to persist a cursor: if it restarts mid-flight, the event is still in
the snapshot and gets applied on the way back up.

**The snapshot is written only when it changes.** Not when `now=` moves on. An
earlier version rewrote it on every poll while anything was pending, so the game
reparsed and re-ACKed the entire pending set several times a second. With the few
hundred filler items a finished game releases at once, that saturated the bridge
and starved everything else going through it.

**At most 16 events are in flight at a time.** The rest wait in a backlog and
drain as the game acknowledges what it has. Nothing is dropped. `DEATHLINK` and
`CHAT` bypass the window, because both are time-sensitive and the game discards a
DeathLink older than ten seconds.

## `ap_out.txt` — game to client

Append-only. The client keeps a byte cursor and only consumes complete lines, so
a line the game is midway through writing is picked up whole on the next poll.
If the file shrinks, the client treats it as a new game session and rewinds.

| Line | Meaning |
| --- | --- |
| `HELLO\|<map>` | the game started on this map; client replies with a forced snapshot |
| `CHECK\|<location id>` | a location was collected |
| `COMPLETE\|<chapter key>` | a mission was finished |
| `GOAL\|<chapter key>` | Nihilanth is dead; client sends `StatusUpdate: CLIENT_GOAL` |
| `DEATH\|<player>\|<cause>\|<forgiven>` | the player died; sent unconditionally. `forgiven` is `1` when DeathLink amnesty absorbed it, so the client does not report it onward |
| `CHAT\|<player>\|<message>` | in-game chat, for relaying to multiworld chat |
| `ACK\|<seq>` | event consumed; client may drop it |

## `ap_in.txt` — client to game

A full snapshot, written to a temp file and renamed so the game never reads a
half-written one. The game reads it whole every poll and early-outs if the text
is byte-identical to what it last parsed.

It compares content, never length. `connected=1` and `connected=0` are the same
size, as are the other flags, so a size check would let the game freeze on a
stale snapshot indefinitely with no symptom other than things quietly not
happening.

`session` identifies one run of the client. The client's event sequence restarts
at 1 each launch, so when the session changes the game resets its high-water
mark; otherwise every event from a restarted client would look already-applied
and be ACKed away without running.

```
session=9f3c1ab2
data_version=d645439896ec
connected=1
goal_open=0
death_link=1
death_link_amnesty=4
chapters=c1a2,c1a4
excluded=c0a0
items=RPG;Shotgun
ungated=item_longjump
starting=weapon_crowbar
checked=7760001,7760002
missing=7760003
now=1786000000
event=4|ITEM|Ammo Cache|1786000000
event=5|DEATHLINK|PlayerTwo~a gargantua|1786000001
```

`chapters` and `excluded` are comma separated; `items` and `ungated` are
semicolon separated because item names may legitimately contain commas.

`data_version` is the fingerprint of the id map the apworld was built from. The
game compares it against the one in its own `checkdata.txt` and stops sending
checks if they disagree, because a mismatched pair is numbering locations
differently and every check would land on the wrong location.

`excluded` is the missions the seed left out. It is not the same as "locked": no
item will ever unlock them, so the game reports "not in this seed" rather than
leaving the player waiting for a key that does not exist.

`goal_open` is whether Nihilanth's seal has lifted. No item unlocks the finale;
it opens once `missions_required` other missions are finished, and the client
owns that count.

`ungated` is classnames, not item names, and it is the seed saying "this one is
not mine". The game neither grants nor removes them and lets their pickups be
collected, so the campaign hands them out on its own schedule. It exists because
"not shuffled" has two possible meanings and the equipment splits between them:
the HEV suit has to be reported in `items`, since the suit item is the only thing
that ever turns armour on, while the long jump module is handed out by the
campaign itself in Lambda Core and only needs to be left alone. Reporting the
module as owned instead granted it from the first spawn of the run.

`checked` and `missing` are location ids, and they are what `ap_tracker` prints.
Both are sent because between them they say which locations the seed contains at
all: an id in neither list was dropped by `chargesanity` or by an excluded
mission, and the tracker skips those rather than showing a check nobody can make.
They are the client's own `checked_locations` and `missing_locations`, so the
game never has to infer progress from the checks it happens to have sent this
session.

`starting` is the classnames the run opens with and the game must never take
away. It overrides the `S` records in `checkdata.txt`, which are the default
rather than the truth. An empty list means the client has nothing to say and the
file's records stand -- never "start with nothing", since taking a player's only
melee weapon away is not a state the bridge should be able to express.

Starting weapons are checked before gates, which is what lets the crowbar be both
a starting weapon and a `K` record: it is always yours, and the gate exists so
that the table is the single answer to "is this pickup gated", with no classname
falling through it unlisted.

`now` is the client's wall clock at write time. Event freshness is judged by
comparing an event's timestamp against `now` from the same snapshot, so the two
sides never have to agree on a clock -- and a DeathLink that arrived during a map
load is correctly recognised as stale rather than killing you on arrival.

### Event lines

`event=<seq>|<kind>|<payload>|<unixtime>`

| Kind | Payload |
| --- | --- |
| `ITEM` | filler item name |
| `TRAP` | trap name, queued on arrival and sprung once the level has been settled for five seconds |
| `DEATHLINK` | `<source>~<cause>` |
| `CHAT` | a line of multiworld chat to print in game |

Player names and chat text are the only operator-controlled values in the
protocol, so both sides strip `|` and newlines out of them before they are
written. Everything else is generated and cannot desync the parser.

The DeathLink payload joins its two fields with `~` because the game splits the
event line on `|`.

## `checkdata.txt`

Generated by `tools/gen_checkdata.py` from the same `campaign.json` the apworld
reads, which is what stops location ids drifting between the two halves.
Pipe-delimited so the game side can parse it with one pass and no JSON parser.

| Record | Fields |
| --- | --- |
| `V` | format version (1) |
| `D` | data version, the id-map fingerprint |
| `G` | the goal chapter's key |
| `C` | index, key, name, comma-separated maps, is_goal |
| `L` | id, map, trigger type, trigger arg, name |
| | `map_reached` has no arg; `chapter_complete` carries the chapter key; `charger` carries `<classname>@<x y z>`; `weapon_pickup` carries the comma-separated classnames |
| `K` | classname, item name — pickup refused until that item is held |
| `S` | classname always granted (the crowbar), the default a snapshot's `starting` may override |

The optional seventh field on `L` is `x y z`, and it is what `ap_find` points at.
Only the kinds that are a *place* carry one: a charger's centre, and the spot on
the floor where a weapon's earliest copy sits. Reaching a map is not somewhere a
player can be pointed, so those have none.

Chargers are the reason the generator parses BSP lump 14 at all: a
`func_healthcharger` has no `origin` key, so its bounding box is the only record
of where in the world it is.

**A charger's identity is where it stands, not its brush model index.** It has no
targetname, so the only two candidate handles are the brush model (`*79`) and the
position. The Sven Co-op project used the model, which is safe there because its
maps are a fixed shipped set nobody recompiles. Retail's are not: the 25th
anniversary update edited and recompiled single-player maps, and a recompile can
renumber brush models. Data generated against one build would then point at the
wrong brush in another, and the symptom is chargers that silently never fire.

So the key is the unit's world-space centre -- the brush model's bounding-box
centre plus whatever `origin` the mapper gave the entity, which is exactly what
the running game computes from the live entity's absolute bounding box. The
generator snaps it to a 4-unit grid, which is what keeps an id stable when the
same map is read again.

The game side does **not** reproduce that rounding, and deliberately: two
languages agreeing on how to round a float at the boundary is a bug waiting to
happen, and the failure mode is silent. It matches by nearest unit instead --
the closest charger of the same classname in the same map, within 32 units. Two
chargers of the same classname are never closer than 204 units anywhere in the
campaign, and any two chargers are never closer than 48, so the match cannot be
ambiguous, and a recompile that nudges a brush cannot break it either.

This also removes a special case the Sven project needed, where one brush shared
by two chargers had to be split by its `origin` key. Position already tells them
apart.

Every `L` record carries a map and every type is filtered by it, `weapon_pickup`
included. There is one weapon check per weapon for the whole run and it sits
where Half-Life would first have handed that weapon over -- the earliest map in
campaign order holding one -- so finding the same weapon later fires nothing, and
neither does the arsenal lying about in the deathmatch map used as the hub.

That is also what keeps the game honest with generation: the apworld places the
location in that map's region, so a check that fired anywhere would be a check
landing somewhere logic never put it. (The Sven Co-op project matched these on
classname alone, campaign-wide. That was a mistake carried across the fork before
being caught.)

`index` is what `ap_warp <n>` takes in game.

A seed does not necessarily contain every location in this file --
`chargesanity` and `exclude_intro_missions` drop whole groups. The game still
fires them; the client drops any check that is not in its slot's location list
rather than reporting a location the seed has never heard of.

`tests/test_campaign_data.py` fails if this file and `campaign.json` disagree, so
regenerate after any data change:

```
python tools/build_campaign_data.py --maps "<Half-Life>/valve/maps"
python tools/gen_checkdata.py
```
