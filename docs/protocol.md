# The file bridge

Sven Co-op's AngelScript API has no sockets, but plugins may read and write
inside `scripts/plugins/store/`. The Python client owns the connection to the
Archipelago server; the plugin and the client talk through two files in

```
<Sven Co-op>/svencoop/scripts/plugins/store/archipelago/
    checkdata.txt   generated, read-only at runtime
    ap_in.txt       client -> game
    ap_out.txt      game -> client
    ap_pending.txt  plugin-owned, survives a map change
    ap_amnesty.txt  plugin-owned, DeathLink amnesty remaining
```

The client polls every 0.2 s, the plugin every 0.25 s, so a check reaches the
server and an item reaches the player in well under a second.

## Design rules

**The client is the source of truth.** That cuts both ways: the plugin must not
make decisions by consulting its cached copy of a client-owned flag. `DEATH` is
reported on every death and the client decides whether it becomes a DeathLink,
because gating in the plugin means a stale snapshot silently swallows deaths with
nothing in either log to explain it. DeathLink amnesty is the one exception, and
only because the death message has to name the remaining allowance at the instant
of the death: the client sends the allowance, the plugin counts it down and tags
the `DEATH` line, and the client still has the final say on whether anything
leaves the lobby.

The plugin holds no state in memory that matters across a map change. On every map load it re-reads `checkdata.txt` and waits for
the next snapshot. A plugin reload, a map change, or a server restart therefore
costs nothing. The two things that genuinely must outlive a map change are small
files alongside the bridge: `ap_pending.txt` (a queued return to the hub) and
`ap_amnesty.txt` (how much DeathLink amnesty is left).

**The snapshot is idempotent, events are not.** `ap_in.txt` is a complete
picture, rewritten whenever it changes and safe to apply any number of times.
Anything that must happen exactly once — a filler item grant, an incoming
DeathLink — cannot live there, because it would fire again on the next map load.
Those ride as sequenced `event=` lines instead.

**Events are acknowledged, not counted.** The plugin acts on an event, writes
`ACK|<seq>` and the client then drops that line from the snapshot. The plugin
does not have to persist a cursor: if it restarts mid-flight, the event is still
in the snapshot and gets applied on the way back up.

**The snapshot is written only when it changes.** Not when `now=` moves on. An
earlier version rewrote it on every poll while anything was pending, so the
plugin reparsed and re-ACKed the entire pending set several times a second. With
the few hundred filler items a finished game releases at once, that saturated the
bridge and starved everything else going through it.

**At most 16 events are in flight at a time.** The rest wait in a backlog and
drain as the game acknowledges what it has. Nothing is dropped. `DEATHLINK` and
`CHAT` bypass the window, because both are time-sensitive and the plugin discards
a DeathLink older than ten seconds.

## `ap_out.txt` — game to client

Append-only. The client keeps a byte cursor and only consumes complete lines, so
a line the plugin is midway through writing is picked up whole on the next poll.
If the file shrinks, the client treats it as a new game session and rewinds.

| Line | Meaning |
| --- | --- |
| `HELLO\|<map>` | plugin started on this map; client replies with a forced snapshot |
| `CHECK\|<location id>` | a location was collected |
| `COMPLETE\|<chapter key>` | a mission was finished |
| `GOAL\|<chapter key>` | Nihilanth is dead; client sends `StatusUpdate: CLIENT_GOAL` |
| `DEATH\|<player>\|<cause>\|<forgiven>` | a player died; sent unconditionally. `forgiven` is `1` when DeathLink amnesty absorbed it, so the client does not report it onward |
| `CHAT\|<player>\|<message>` | in-game chat, for relaying to multiworld chat |
| `ACK\|<seq>` | event consumed; client may drop it |

## `ap_in.txt` — client to game

A full snapshot, written to a temp file and renamed so the plugin never reads a
half-written one. The plugin reads it whole every poll and early-outs if the text
is byte-identical to what it last parsed.

It compares content, never length. `connected=1` and `connected=0` are the same
size, as are the other flags, so a size check would let the plugin freeze on a
stale snapshot indefinitely with no symptom other than things quietly not
happening.

`session` identifies one run of the client. The client's event sequence restarts
at 1 each launch, so when the session changes the plugin resets its
high-water mark; otherwise every event from a restarted client would look
already-applied and be ACKed away without running.

```
session=9f3c1ab2
connected=1
goal_open=0
death_link=1
death_link_amnesty=4
chapters=blast_pit,office_complex
goals_open=nihilanth
excluded=black_mesa_inbound
items=RPG;Shotgun
ungated=item_longjump
starting=weapon_crowbar;weapon_medkit
now=1786000000
event=4|ITEM|Ammo Cache|1786000000
event=5|DEATHLINK|PlayerTwo~a gargantua|1786000001
```

`chapters` and `excluded` are comma separated; `items` and `ungated` are
semicolon separated because item names may legitimately contain commas.

`excluded` is the missions the seed left out. It is not the same as "locked": no
item will ever unlock them, so the game reports "not in this seed" rather than
leaving the player waiting for a key that does not exist. A campaign switched off
in the YAML arrives as every one of its missions listed here, which is why
campaign toggles needed no plugin changes at all.

`goals_open` is the finales that are unsealed, one per campaign. Each campaign
has its own `missions_required` setting and its own count, so they open
independently; `goal_open` above is the same answer collapsed into one bool for a
plugin that predates the list, and it is deliberately true only when *every*
finale is open, since an older plugin cannot tell which one is meant and opening
the wrong one early is worse than opening the right one late.

The plugin reports a finished finale as `GOAL|<chapter key>` but never decides
what it amounts to: only the client knows which other campaigns are in the seed,
so it is the client that holds back `CLIENT_GOAL` until all of them are done.

`ungated` is classnames, not item names, and it is the seed saying "this one is
not mine". The plugin neither grants nor removes them and lets their pickups be
collected, so the campaign hands them out on its own schedule. It exists because
"not shuffled" has two possible meanings and the equipment splits between them:
the HEV suit has to be reported in `items`, since the suit item is the only thing
that ever turns armour on, while the long jump module is handed out by the
campaign itself from Forget About Freeman onward and only needs to be left alone.
Reporting the module as owned instead granted it from the first spawn of the run.

An older client sends no `ungated` line, which parses as an empty list and
reproduces the previous behaviour exactly.

`checked` and `missing` are location ids, and they are what `!tracker` prints.
Both are sent because between them they say which locations the seed contains at
all: an id in neither list was dropped by `chargesanity` or by a campaign left
out, and the tracker skips those rather than showing a check nobody can make.
They are the client's own `checked_locations` and `missing_locations`, so the
plugin never has to infer progress from the checks it happens to have sent this
session.

`starting` is the classnames the run opens with and the plugin must never take
away, which `random_starting_weapon` turns into a per-seed answer: the melee half
can be a pipe wrench or a spanner rather than the crowbar. It overrides the `S`
records in `checkdata.txt`, which are the default rather than the truth. An empty
list means the client has nothing to say and the file's records stand — never
"start with nothing", since taking a player's only melee weapon away is not a
state the bridge should be able to express.

Starting weapons are checked before gates, which is what lets the crowbar be both
a starting weapon and a `K` record: by default it is yours, and in a seed that
started you with something else the gate refuses it, because no item named
"Crowbar" is ever in a pool.

`now` is the client's wall clock at write time. Event freshness is judged by
comparing an event's timestamp against `now` from the same snapshot, so the two
sides never have to agree on a clock — and a DeathLink that arrived during a map
load is correctly recognised as stale rather than killing you on arrival.

### Event lines

`event=<seq>|<kind>|<payload>|<unixtime>`

| Kind | Payload |
| --- | --- |
| `ITEM` | filler item name |
| `TRAP` | trap name, sprung once on arrival |
| `DEATHLINK` | `<source>~<cause>` |
| `CHAT` | a line of multiworld chat to print in game |

Player names and chat text are the only operator-controlled values in the
protocol, so both sides strip `|` and newlines out of them before they are
written. Everything else is generated and cannot desync the parser.

The DeathLink payload joins its two fields with `~` because the plugin splits the
event line on `|`.

## `checkdata.txt`

Generated by `tools/gen_checkdata.py` from the same `campaign.json` the apworld
reads, which is what stops location ids drifting between the two halves.
Pipe-delimited so AngelScript can parse it with a single `string.Split("|")`.

| Record | Fields |
| --- | --- |
| `V` | format version (2 since campaigns; `M`, `P` and `C`'s last field are the additions, and all three are ignored harmlessly by an older plugin) |
| `M` | campaign key, name, goal chapter |
| `C` | index, key, name, comma-separated maps, is_goal, campaign key |
| `P` | hub console targetname, the chapter its button enters |
| `L` | id, map, trigger type, trigger arg, name |
| | `map_reached` has no arg; `chapter_complete` carries the chapter key; `charger` carries `<classname>:<brush model>`, e.g. `func_recharge:*79`; `weapon_pickup` carries the comma-separated classnames |
| `K` | classname, item name — pickup refused until that item is held |
| `S` | classname always granted (the crowbar and the medkit), the default a snapshot's `starting` may override |
| `R` | classname, comma-separated campaigns whose maps it may be granted on |

`R` exists because They Hunger's weapons are not weapons Sven Co-op ships. Its
spanner, tommy gun, tesla gun and the rest are custom entities registered by
`scripts/maps/hunger/weapons/`, so the classnames only exist while one of its
maps is running and `GiveNamedItem` anywhere else has nothing to build. The
plugin holds such an item back rather than dropping it: the loadout is reapplied
on every spawn and map change, so it lands the moment the player is somewhere the
weapon is real. Half-Life's and Opposing Force's weapons are all in `server.dll`
and carry no `R` record.

Every `L` record carries a map, but `weapon_pickup` is the one type the plugin
does **not** filter by it: that field is only where the apworld anchors the
check's logic, and the plugin matches on classname anywhere in the campaign.

`P` is a table rather than a rule because the hub numbers its consoles
differently in each campaign it fronts: Half-Life's are unpadded and start at
`hl_ch1` (its mission 0 has no console), Opposing Force's are zero padded and
skip `of_ch06` entirely, Blue Shift runs `bs_ch01`-`bs_ch06` and They Hunger
`th_ep01`-`th_ep03`. Deriving the mission from the digits in a targetname was
correct for Half-Life alone and would silently send an Opposing Force player one
mission past the console they pressed.

`index` stays global across every campaign, because it is what `!warp <n>` takes
in game and a number has to mean one mission whichever campaigns a seed contains.
Half-Life is first, so its numbering is unchanged.

A seed does not necessarily contain every location in this file — `chargesanity`,
`include_black_mesa_inbound` and the campaign toggles can drop whole groups, and
the file always describes all four campaigns whether or not a seed uses them. The
plugin still fires them; the client drops any check that is not in its slot's
location list rather than reporting a location the seed has never heard of.

`tests/test_campaign_data.py` fails if this file and `campaign.json` disagree, so
regenerate after any data change:

```
python tools/build_campaign_data.py --maps "<Sven Co-op>/svencoop/maps"
python tools/gen_checkdata.py
```
