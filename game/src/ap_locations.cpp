#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "nodes.h"

#include "ap_locations.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <set>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_items.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"
#include "ap_traps.h"
#include "ap_warpsave.h"

namespace ap {
namespace {

// Ids sent since this map loaded. Only to keep ap_out.txt from repeating itself;
// correctness does not depend on it, since a repeated check is a no-op on the
// server and that is what makes quickloads safe.
std::set<long> g_sent;
std::string g_map;

// May anything on this map fire at all?
//
// A warp is checked at the warp, but that is not the only way into a mission.
// The engine restores the last save when the player dies, and that save can be
// from a different seed entirely: dying in the lobby of a brand new run restored
// a quicksave from a previous one and sent its arrival check. So arriving is
// held until the client confirms the mission is open, which is `AuthoriseMap`.
//
// The hub authorises itself, since there is nothing there to fire and nowhere
// illegitimate to have arrived from.
bool g_map_authorised = false;

// The arrival is owed but has not been allowed yet. Held rather than dropped:
// on a legitimate warp the snapshot arrives a poll later and the check is real.
bool g_arrival_owed = false;

// The bounce is announced and requested once per map, not once per poll: the
// level change is deferred a frame, so without this every poll in between says
// it again and asks again.
bool g_bounce_announced = false;

float WalkScore(const Vector& from, const Vector& to) {
    const float dx = to.x - from.x;
    const float dy = to.y - from.y;
    const float dz = to.z - from.z;
    return std::sqrt(dx * dx + dy * dy) + kVerticalPenalty * std::fabs(dz);
}

// A brush entity has no origin of its own, so its position is the centre of the
// bounding box the engine gives it -- which already includes whatever `origin`
// the mapper set. Exactly what the generator computed from the BSP.
Vector CentreOf(CBaseEntity* entity) {
    return (entity->pev->absmin + entity->pev->absmax) * 0.5f;
}

const char* Bearing(CBasePlayer* player, const Vector& target) {
    Vector delta = target - player->pev->origin;
    delta.z = 0;
    if (delta.Length() < 1.0f) {
        return "right here";
    }

    UTIL_MakeVectors(player->pev->v_angle);
    Vector forward = gpGlobals->v_forward;
    forward.z = 0;
    forward = forward.Normalize();
    Vector right = gpGlobals->v_right;
    right.z = 0;
    right = right.Normalize();

    delta = delta.Normalize();
    const float ahead = DotProduct(delta, forward);
    const float across = DotProduct(delta, right);

    if (ahead > 0.85f) return "ahead";
    if (ahead < -0.85f) return "behind you";
    if (ahead > 0.0f) return across > 0 ? "ahead and right" : "ahead and left";
    return across > 0 ? "behind you and right" : "behind you and left";
}

// How far up or down it is, as the Sven plugin says it. Empty when roughly level.
const char* HeightTo(CBasePlayer* player, const Vector& target) {
    const float rise = target.z - player->pev->origin.z;
    if (rise > 128.0f) return ", well above you";
    if (rise > 48.0f) return ", a little above you";
    if (rise < -128.0f) return ", well below you";
    if (rise < -48.0f) return ", a little below you";
    return "";
}

// Whether a straight line from the player's eyes reaches it.
bool ClearLineTo(CBasePlayer* player, const Vector& target) {
    TraceResult tr;
    UTIL_TraceLine(player->pev->origin + player->pev->view_ofs, target,
                   ignore_monsters, player->edict(), &tr);
    return tr.flFraction >= 1.0f;
}

struct Colour {
    int r, g, b;
};

// What `Find` pointed at, when it is a spot on this map.
struct FindTarget {
    bool found = false;
    Vector at;
    long location_id = 0;
    Colour colour = {255, 255, 255};
};

// The line takes the colour of what is at the end of it.
Colour LineColour(const Location& location) {
    if (location.type == TriggerType::WeaponPickup) {
        return {40, 110, 255};
    }
    if (location.type == TriggerType::Charger) {
        // Xen's healing pools heal, so they are red with the wall units.
        return location.charger_classname == "func_recharge" ? Colour{255, 130, 0}
                                                             : Colour{255, 30, 30};
    }
    return {255, 255, 255};
}

// How often the line is redrawn from where the player now stands, and how long
// each drawing lasts. A little longer than the interval so it never blinks, and
// short, because turning the trace off is just not drawing it again.
constexpr float kTraceInterval = 1.0f;
constexpr int kTraceLife = 12;  // tenths of a second
// Nodes on the way are drawn this far above the floor they sit on.
constexpr float kTraceLift = 20.0f;
// A segment is let through when it ends this close to the point it aimed at.
// The check's own spot is often inside something: a charger's centre is inside
// its brush, and a weapon's origin can sit a few units into its shelf.
constexpr float kTraceSlack = 40.0f;
// Nearest nodes tried, closest first, before giving up on a point.
constexpr int kNodeCandidates = 24;
// More than this many segments goes out over several frames anyway, but a line
// past it is no longer helping.
constexpr size_t kMaxSegments = 64;
// A short-cut between two points on the route needs ground under it every so
// often, or the line would cross a pit the route walks around.
constexpr float kGroundStep = 48.0f;
constexpr float kGroundDepth = 80.0f;
// How far along the route a short-cut may reach.
constexpr size_t kPullLookahead = 12;

struct TraceState {
    bool on = false;
    std::string map;
    FindTarget target;
    float next_draw = 0.0f;
    // Whether the last drawing followed the graph, so the fallback is said once.
    bool routed = true;
    bool said_fallback = false;
    // Already found when the trace began, so finding it again does not end it.
    bool was_collected = false;
};
TraceState g_trace;
int g_beam_sprite = 0;

// Segments waiting to be sent, a few per frame.
struct Segment {
    Vector a, b;
    Colour colour;
};
std::vector<Segment> g_segments;
constexpr size_t kSegmentsPerFrame = 16;

bool GraphReady() {
    return WorldGraph.m_fGraphPresent && WorldGraph.m_fGraphPointersSet &&
           WorldGraph.m_cNodes > 0;
}

Vector NodePoint(int node) {
    return WorldGraph.m_pNodes[node].m_vecOrigin + Vector(0, 0, kTraceLift);
}

// Can a line go from `from` to `to`? Brushes stop it; monsters do not. With
// `slack`, stopping just short of `to` counts, for points inside something.
bool Clear(const Vector& from, const Vector& to, bool slack) {
    TraceResult tr;
    UTIL_TraceLine(from, to, ignore_monsters, nullptr, &tr);
    if (tr.fAllSolid) {
        return false;
    }
    if (tr.flFraction >= 1.0f) {
        return true;
    }
    return slack && (tr.vecEndPos - to).Length() <= kTraceSlack;
}

// Floor under every step of a segment, so a short-cut does not fly over a gap.
bool Grounded(const Vector& a, const Vector& b) {
    const Vector delta = b - a;
    const int steps = static_cast<int>(delta.Length() / kGroundStep);
    for (int i = 1; i < steps; ++i) {
        const Vector at = a + delta * (static_cast<float>(i) / steps);
        TraceResult tr;
        UTIL_TraceLine(at, at - Vector(0, 0, kGroundDepth), ignore_monsters,
                       nullptr, &tr);
        if (tr.flFraction >= 1.0f) {
            return false;
        }
    }
    return true;
}

// The nearest land node a line reaches from `point`, or -1. Every node is
// looked at rather than `FindNearestNode`'s, which traces only from the point
// outward and so never finds one from inside a charger.
int NearestNode(const Vector& point) {
    std::vector<std::pair<float, int>> by_distance;
    by_distance.reserve(WorldGraph.m_cNodes);
    for (int i = 0; i < WorldGraph.m_cNodes; ++i) {
        if (WorldGraph.m_pNodes[i].m_afNodeInfo & bits_NODE_AIR) {
            continue;
        }
        by_distance.push_back({(NodePoint(i) - point).Length(), i});
    }
    const size_t keep = by_distance.size() < kNodeCandidates
                            ? by_distance.size()
                            : static_cast<size_t>(kNodeCandidates);
    std::partial_sort(by_distance.begin(), by_distance.begin() + keep,
                      by_distance.end());
    for (size_t i = 0; i < keep; ++i) {
        const Vector node = NodePoint(by_distance[i].second);
        // From the node to the point, so a point inside a brush still counts
        // when the line stops at its face.
        if (Clear(node, point, true)) {
            return by_distance[i].second;
        }
    }
    return -1;
}

// The nodes from `start` to `dest` inclusive, or empty. Walks the route table
// itself: `FindShortestPath` stops at `MAX_PATH_SIZE`, ten nodes, which is a
// monster's next few steps and not a way across a map.
std::vector<int> Route(int start, int dest, int hull) {
    std::vector<int> path;
    if (WorldGraph.m_fRoutingComplete) {
        const int cap = WorldGraph.CapIndex(bits_CAP_DOORS_GROUP);
        path.push_back(start);
        int current = start;
        while (current != dest) {
            const int next = WorldGraph.NextNodeInRoute(current, dest, hull, cap);
            if (next == current || next < 0 ||
                path.size() > static_cast<size_t>(WorldGraph.m_cNodes)) {
                return {};
            }
            path.push_back(next);
            current = next;
        }
        return path;
    }
    // No route table: the SDK's Dijkstra, which has no length limit but writes
    // the whole path, so the buffer is as long as the graph.
    path.resize(WorldGraph.m_cNodes + 2);
    const int count = WorldGraph.FindShortestPath(path.data(), start, dest, hull,
                                                  bits_CAP_DOORS_GROUP);
    path.resize(count > 0 ? count : 0);
    return path;
}

// Points from the player to the target: along the graph when there is one and
// it connects them, a straight line otherwise. `routed` says which.
std::vector<Vector> TracePoints(const Vector& from, const Vector& to, bool& routed) {
    routed = false;
    std::vector<Vector> points;
    points.push_back(from);
    // In plain sight with floor all the way: the straight line is the route.
    const bool sight = Clear(from, to, true) && Grounded(from, to);
    if (sight) {
        routed = true;
    } else if (GraphReady()) {
        const int start = NearestNode(from);
        const int dest = NearestNode(to);
        if (start >= 0 && dest >= 0) {
            // The player's own size first; a crouch fits where it does not.
            std::vector<int> path = Route(start, dest, NODE_HUMAN_HULL);
            if (path.empty()) {
                path = Route(start, dest, NODE_SMALL_HULL);
            }
            for (int node : path) {
                points.push_back(NodePoint(node));
            }
            routed = !path.empty();
        }
    }
    points.push_back(to);

    // Pull it tight: from each point, on to the furthest one in sight with
    // ground all the way. The graph's nodes zigzag; a player would not.
    std::vector<Vector> tight;
    tight.push_back(points.front());
    size_t at = 0;
    while (at + 1 < points.size()) {
        size_t next = at + 1;
        // A few points ahead at most: this runs every second, and a long
        // route checked end to end from every point is thousands of traces.
        const size_t last = at + kPullLookahead < points.size() - 1
                                ? at + kPullLookahead
                                : points.size() - 1;
        for (size_t j = last; j > at + 1; --j) {
            if (Clear(points[at], points[j], j + 1 == points.size()) &&
                Grounded(points[at], points[j])) {
                next = j;
                break;
            }
        }
        tight.push_back(points[next]);
        at = next;
    }
    return tight;
}

void QueueTraceLine() {
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }
    // About the height the nodes are drawn at, rather than the eyes.
    const Vector from = player->pev->origin - Vector(0, 0, 16);
    bool routed = false;
    const std::vector<Vector> points = TracePoints(from, g_trace.target.at, routed);
    if (!routed && !g_trace.said_fallback) {
        g_trace.said_fallback = true;
        Notify("No walking route known from here; the line points straight at it.");
    }
    g_trace.routed = routed;
    g_segments.clear();
    for (size_t i = 0; i + 1 < points.size() && i < kMaxSegments; ++i) {
        g_segments.push_back(Segment{points[i], points[i + 1], g_trace.target.colour});
    }
}

void SendSegments() {
    if (g_segments.empty() || g_beam_sprite == 0 || !ClientReady()) {
        return;
    }
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }
    const size_t take = g_segments.size() < kSegmentsPerFrame ? g_segments.size()
                                                              : kSegmentsPerFrame;
    for (size_t i = 0; i < take; ++i) {
        const Segment& s = g_segments[i];
        MESSAGE_BEGIN(MSG_ONE, SVC_TEMPENTITY, nullptr, player->edict());
        WRITE_BYTE(TE_BEAMPOINTS);
        WRITE_COORD(s.a.x);
        WRITE_COORD(s.a.y);
        WRITE_COORD(s.a.z);
        WRITE_COORD(s.b.x);
        WRITE_COORD(s.b.y);
        WRITE_COORD(s.b.z);
        WRITE_SHORT(g_beam_sprite);
        WRITE_BYTE(0);           // starting frame
        WRITE_BYTE(10);          // frame rate
        WRITE_BYTE(kTraceLife);  // life, tenths of a second
        WRITE_BYTE(6);           // width
        WRITE_BYTE(0);           // noise
        WRITE_BYTE(s.colour.r);
        WRITE_BYTE(s.colour.g);
        WRITE_BYTE(s.colour.b);
        WRITE_BYTE(200);         // brightness
        WRITE_BYTE(10);          // scroll speed: shows which way is forward
        MESSAGE_END();
    }
    g_segments.erase(g_segments.begin(), g_segments.begin() + take);
}

}  // namespace

void SendCheck(long id) {
    if (!Live()) {
        return;
    }
    // Nothing fires until the client has confirmed we are allowed to be on this
    // map. See `AuthoriseMap`: arriving by warp is checked at the warp, but the
    // engine can drop us into a mission map without one -- a save restored after
    // a death is the way it happens, and the save may belong to another seed
    // entirely.
    if (!g_map_authorised) {
        return;
    }
    if (g_sent.find(id) != g_sent.end()) {
        return;
    }
    // Already on the server. `checked` is the client's `checked_locations`,
    // resent with every snapshot and replaced wholesale when the slot changes,
    // so it is the server's answer rather than a local memory that a restarted
    // seed could leave stale. `Live` above means one has arrived. Sending it
    // again would be a no-op; saying "Found:" again is the part that is wrong,
    // every time the player walks back past a weapon they took an hour ago.
    if (State().checked.find(id) != State().checked.end()) {
        g_sent.insert(id);
        return;
    }
    // A location the seed does not contain -- chargesanity off, or an excluded
    // mission. The client would drop it anyway; not sending it keeps the log
    // readable.
    if (!State().InSeed(id)) {
        return;
    }

    g_sent.insert(id);

    char text[32];
    std::snprintf(text, sizeof(text), "%ld", id);
    Wire().Send("CHECK", text);

    const Location* location = Data().LocationById(id);
    if (location != nullptr) {
        Notify(std::string("Found: ") + location->name);
    }
}

bool Visited(const std::string& map_name) {
    for (const Location& location : Data().locations) {
        if (location.type != TriggerType::MapReached) continue;
        if (location.map != map_name) continue;

        // Either the server has it -- which survives a restart, a reconnect and
        // a new session -- or we sent it since this map loaded and the snapshot
        // has not caught up yet.
        return State().checked.find(location.id) != State().checked.end() ||
               g_sent.find(location.id) != g_sent.end();
    }
    return false;  // no arrival check for it, so no record of ever being there
}

void ForgetSentChecks() { g_sent.clear(); }

void OnMapStart(const std::string& map_name) {
    // The map before this one. The dll outlives the level, so this is still the
    // last map's name until it is overwritten below, and it is the only way to
    // tell a transition into part 3 from a warp straight to it.
    const std::string previous = g_map;

    // Beams meant for the last level, or for before this load.
    g_segments.clear();
    if (map_name != g_map) {
        g_sent.clear();
        g_map = map_name;
    }

    const Chapter* chapter = Data().ChapterOfMap(map_name);
    if (chapter == nullptr) {
        // The hub, the hazard course, a deathmatch map: nothing to fire, and no
        // way to have got here that needs questioning.
        g_map_authorised = true;
        g_arrival_owed = false;
        ResetConsumables();
        NoteArrival(previous, map_name, true);
        return;
    }

    // A map we asked for is authorised by the asking: `ap_warp` and the lobby
    // panels have already been through `MissionOpen`, and re-deriving that here
    // from a snapshot which may still be a poll behind the warp is how a
    // perfectly legal trip to Office Complex bounced straight back out of it.
    //
    // Anything else, the engine reached on its own -- which in practice means a
    // save it restored after a death, possibly from another seed entirely. That
    // is the case worth questioning, and `AuthoriseMap` questions it.
    const bool requested = WasRequested(map_name);
    g_map_authorised = requested;
    // A mission load the mod asked for (a warp, a part warp, a warp point)
    // starts a new stay; the engine's own transition between parts does not.
    if (requested) {
        ResetConsumables();
    }
    g_arrival_owed = true;
    g_bounce_announced = false;

    if (requested && LastRequestCold()) {
        // A `map` warp starts the level cold, without the seam state a
        // transition would have carried in. See `RunSeamDoors`. A warp that
        // restored a savegame needs none of it: the save *is* that state.
        RequestSeamDoors();
    }

    // Whether this arrival is worth keeping as a warp point. Only an engine
    // transition from another part of this mission is, which is why it needs
    // both names.
    NoteArrival(previous, map_name, requested);
}

void SendArrival() {
    const Chapter* chapter = Data().ChapterOfMap(g_map);
    if (chapter == nullptr) {
        return;
    }

    for (const Location& location : Data().locations) {
        if (location.map == g_map && location.type == TriggerType::MapReached) {
            SendCheck(location.id);
        }
    }

    // Arriving finishes a mission only where there is nowhere further to walk:
    // the finale. Everywhere else the mission is over when the player leaves it
    // forwards, which `InterceptChangeLevel` sees. Arriving on "the last map"
    // would have finished Unforeseen Consequences in a dead-end side room.
    if (chapter->complete_on_arrival && chapter->IsLastMap(g_map)) {
        SendChapterComplete(*chapter);
    }
}

void AuthoriseMap() {
    if (!Data().Loaded()) {
        return;
    }

    const Chapter* chapter = Data().ChapterOfMap(g_map);
    if (chapter == nullptr) {
        g_map_authorised = true;
        g_arrival_owed = false;
        return;
    }

    if (!g_map_authorised) {
        const Snapshot& state = State();
        // No answer yet rather than a "no". Waiting costs nothing: `SendCheck`
        // refuses while unauthorised, so the map stays inert until this resolves.
        if (!state.connected) {
            return;
        }

        if (state.ChapterExcluded(chapter->key) || !ChapterIsOpen(*chapter)) {
            // We did not ask to come here and the seed does not allow it: a save
            // the engine restored, possibly from another run. Nothing has fired
            // and nothing will.
            if (!g_bounce_announced) {
                g_bounce_announced = true;
                Trace(("  not authorised on " + g_map + "; to the hub").c_str());
                Notify(chapter->name +
                       " is not open in this seed. Returning to the hub.");
                RequestMap(kHubMap);
            }
            return;
        }

        Trace(("  authorised on " + g_map).c_str());
        g_map_authorised = true;
    }

    // Held until it can actually be sent. `Live` wants a connected client and a
    // matching data version, and until then the arrival is still owed rather
    // than quietly dropped -- `SendCheck` would have discarded it.
    if (g_arrival_owed && Live()) {
        g_arrival_owed = false;
        SendArrival();
    }
}

void SendChapterComplete(const Chapter& chapter) {
    for (const Location& location : Data().locations) {
        if (location.type == TriggerType::ChapterComplete &&
            location.chapter == chapter.key) {
            SendCheck(location.id);
        }
    }

    // The check is the location; this is the mission itself, which is what the
    // client counts toward the finale's seal.
    Wire().Send("COMPLETE", chapter.key);
    if (chapter.is_goal) {
        Wire().Send("GOAL", chapter.key);
    }
}

void OnPlayerUse(CBasePlayer* player, CBaseEntity* target) {
    if (player == nullptr || target == nullptr) {
        return;
    }

    // A lobby panel, and *before* the `Live` guard below rather than after it.
    //
    // `Live` is false while the client is disconnected, which is precisely when
    // a panel has the most to say: the refusal is the whole point, and behind
    // that guard the press was swallowed and the panel looked broken. This is
    // the `Live` versus `Gated` distinction in ap_main.h -- sending a check
    // waits on the client, but telling the player why they may not travel must
    // not. `PressHubButton` asks `Data().Loaded()` for itself, which is what
    // `Gated` means, so an ordinary Half-Life install still falls through.
    if (PressHubButton(player, target)) {
        return;
    }

    // Everything below sends a check, so it does wait on the client.
    if (!Live()) {
        return;
    }

    const std::string classname(STRING(target->pev->classname));
    if (classname != "func_healthcharger" && classname != "func_recharge") {
        return;
    }

    const Vector centre = CentreOf(target);
    const float at[3] = {centre.x, centre.y, centre.z};
    const Location* location = Data().ChargerAt(g_map, classname, at);
    if (location != nullptr) {
        SendCheck(location->id);
    }
}

void OnHealingTouch(CBaseEntity* toucher, CBaseEntity* pool) {
    // From `CBaseTrigger::HurtTouch`, and only down the branch where the damage
    // is negative -- which is what a healing pool is. Every hazard in the game
    // reaches that function, so the check has to be the sign of `dmg` rather
    // than the classname.
    if (pool == nullptr || !Live()) {
        return;
    }
    // Monsters touch it too, and heal from it.
    CBasePlayer* player = Player();
    if (player == nullptr || toucher != player) {
        return;
    }

    // Touch, not use, so this arrives twice a second for as long as the player
    // stands in it. `SendCheck` drops one already sent, which is what keeps that
    // from becoming a stream of writes to the bridge.
    const Vector centre = CentreOf(pool);
    const float at[3] = {centre.x, centre.y, centre.z};
    const Location* location = Data().ChargerAt(g_map, "trigger_hurt", at);
    if (location != nullptr) {
        SendCheck(location->id);
    }
}

void OnWeaponCollected(CBasePlayer* player, const std::string& classname) {
    if (player == nullptr || !Live()) {
        return;
    }
    // A weapon Butterfingers is holding a debt over is the player's own, wherever
    // it is lying. Nothing about it is a discovery until the trap is settled, and
    // this is the one place every route to a weapon check passes through.
    if (Withheld(classname)) {
        return;
    }
    // Only in the map where Half-Life would first have handed this weapon over.
    // The same shotgun six missions later is not that moment, and the RPG lying
    // in the hub is not it at all.
    const Location* location = Data().WeaponPickupFor(classname, g_map);
    if (location != nullptr) {
        SendCheck(location->id);
    }
}

void SweepNearbyPickups() {
    CBasePlayer* player = Player();
    if (player == nullptr || !Live()) {
        return;
    }

    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityInSphere(entity, player->pev->origin,
                                             kPickupSweepRadius)) != nullptr) {
        const std::string classname(STRING(entity->pev->classname));
        if (!StartsWith(classname, "weapon_") && !StartsWith(classname, "item_")) {
            continue;
        }
        // Only a pickup lying in the world. One attached to the player has no
        // model index, and standing next to a weapon we are carrying is not a
        // discovery.
        if (entity->pev->movetype == MOVETYPE_FOLLOW || entity->pev->modelindex == 0) {
            continue;
        }
        // The copy Butterfingers threw on the floor is not a weapon the player
        // has found: it is the one they were carrying a moment ago. This sweep
        // is why guarding the pickup was not enough -- it fires on a weapon
        // *lying near* the player, so the trap sent the map's weapon check
        // without the player touching anything.
        if (IsTrapDrop(entity)) {
            continue;
        }
        OnWeaponCollected(player, classname);
    }
}

// Has this location been collected, as far as either side knows?
bool Collected(const Location& location) {
    return State().checked.find(location.id) != State().checked.end() ||
           g_sent.find(location.id) != g_sent.end();
}

// 1-based part number of a map within its mission, or 0 for a one-map mission.
int PartOf(const Chapter& chapter, const std::string& map_name) {
    if (chapter.maps.size() <= 1) {
        return 0;
    }
    for (size_t i = 0; i < chapter.maps.size(); ++i) {
        if (chapter.maps[i] == map_name) {
            return static_cast<int>(i) + 1;
        }
    }
    return 0;
}

// The copy of a weapon check on this map, if it has one. Any mission's first
// copy sends it, so the one in front of the player is the one worth pointing at.
// An ally's drop only when the seed counts them: otherwise logic never expects
// it, and pointing at a guard to kill would be bad advice.
const Location::Source* SourceHere(const Location& location) {
    for (const Location::Source& source : location.sources) {
        if (source.drop == "ally" && !State().ally_weapon_drops) {
            continue;
        }
        if (source.map == g_map) {
            return &source;
        }
    }
    return nullptr;
}

// Every item named in a source's `needs` ("A or B and C") is held.
bool NeedsMet(const std::string& needs) {
    size_t start = 0;
    while (start <= needs.size()) {
        size_t end = needs.find(" and ", start);
        if (end == std::string::npos) {
            end = needs.size();
        }
        const std::string group = needs.substr(start, end - start);
        bool any = group.empty();
        size_t at = 0;
        while (!any && at <= group.size()) {
            size_t stop = group.find(" or ", at);
            if (stop == std::string::npos) {
                stop = group.size();
            }
            any = State().Has(group.substr(at, stop - at));
            at = stop + 4;
        }
        if (!any) {
            return false;
        }
        start = end + 5;
    }
    return true;
}

// The earliest copy of a weapon check in campaign order, preferring one the
// player can reach now: its mission open and its `needs` held. `available` says
// which it was. Null if every copy is in a mission left out of the seed.
const Location::Source* EarliestSource(const Location& location, bool& available) {
    const Location::Source* best_open = nullptr;
    const Location::Source* best_any = nullptr;
    long open_rank = 0;
    long any_rank = 0;
    for (const Location::Source& source : location.sources) {
        if (source.drop == "ally" && !State().ally_weapon_drops) {
            continue;
        }
        const Chapter* chapter = Data().ChapterOfMap(source.map);
        if (chapter == nullptr || State().ChapterExcluded(chapter->key)) {
            continue;
        }
        const long rank = static_cast<long>(chapter->index) * 1000 +
                          PartOf(*chapter, source.map);
        if (best_any == nullptr || rank < any_rank) {
            best_any = &source;
            any_rank = rank;
        }
        if (ChapterIsOpen(*chapter) && NeedsMet(source.needs) &&
            (best_open == nullptr || rank < open_rank)) {
            best_open = &source;
            open_rank = rank;
        }
    }
    available = best_open != nullptr;
    return available ? best_open : best_any;
}

// Point the player at one location, wherever it is.
//
// Somewhere else in the campaign is a legitimate answer -- `ap_find crossbow`
// from the hub should say where the crossbow is, not that there is nothing here
// -- so this says which mission and part, and hands over the command that goes
// there rather than leaving the player to work it out.
//
// `target`, when given, is filled in if the answer is a spot on this map, which
// is the one case `PathTrace` can draw a line to.
void DescribeLocation(CBasePlayer* player, const Location& location,
                      FindTarget* target) {
    // A weapon check is sent by whichever copy is touched first, so once it is
    // found no copy anywhere is still a place to find it.
    if (location.type == TriggerType::WeaponPickup && Collected(location)) {
        Notify(location.name + ": already found.");
        return;
    }

    Notify((Collected(location) ? "[found] " : "") + location.name);

    // This map's copy if there is one, else the earliest one the player can
    // get to now, else the earliest at all. Not a weapon check: the check itself.
    const Location::Source* source = SourceHere(location);
    const bool here = source != nullptr;
    bool available = true;
    if (source == nullptr && !location.sources.empty()) {
        source = EarliestSource(location, available);
    }
    const std::string& map = source != nullptr ? source->map : location.map;
    const bool has_position = source != nullptr ? source->has_position
                                                : location.has_position;
    const float* position = source != nullptr ? source->position : location.position;
    const std::string& needs = source != nullptr ? source->needs : location.needs;

    // No copy reachable now: say why the earliest is not, a locked mission or
    // an item the player does not hold.
    const Chapter* source_chapter = Data().ChapterOfMap(map);
    const bool locked = !available && source_chapter != nullptr &&
                        !ChapterIsOpen(*source_chapter);
    const bool missing_item = !available && !locked && !needs.empty();
    if (!needs.empty() && !missing_item) {
        Notify("Needs the " + needs + " to reach.");
    }
    if (location.type == TriggerType::WeaponPickup && !location.sources.empty()) {
        Notify(here           ? "Any copy in this game sends it; one is here:"
               : available    ? "Any copy in this game sends it; the earliest available is in:"
               : locked       ? "Any copy in this game sends it; the earliest is in a locked map:"
               : missing_item ? "Any copy in this game sends it; the earliest needs the " +
                                    needs + ", which you do not have:"
                              : "Any copy in this game sends it; the earliest is in:");
    }

    if (map != g_map) {
        const Chapter* chapter = Data().ChapterOfMap(map);
        if (chapter == nullptr) {
            Notify(std::string("It is on ") + map + ".");
            return;
        }

        const int part = PartOf(*chapter, map);
        char line[192];
        if (part > 0) {
            std::snprintf(line, sizeof(line), "In %s, part %d (%s).",
                          chapter->name.c_str(), part, map.c_str());
        } else {
            std::snprintf(line, sizeof(line), "In %s (%s).",
                          chapter->name.c_str(), map.c_str());
        }
        Notify(line);

        // A locked mission's door would refuse the warp.
        if (!ChapterIsOpen(*chapter)) {
            return;
        }
        // A part warp only works somewhere already walked to, so offer it only
        // where it would be accepted. Otherwise the mission's own door.
        if (part > 0 && Visited(map)) {
            std::snprintf(line, sizeof(line), "Get there with !warp %d %d.",
                          chapter->index, part);
        } else {
            std::snprintf(line, sizeof(line), "Get there with !warp %d.",
                          chapter->index);
        }
        Notify(line);
        return;
    }

    if (source != nullptr && !source->drop.empty()) {
        Notify(source->drop == "ally"
                   ? "Carried by an ally here, dropped if they die."
                   : "Carried by an enemy here, dropped when killed.");
    }

    if (!has_position) {
        // Either the check is the map itself, or it is a weapon handed over
        // rather than one lying about. Nothing to point at either way, but they
        // are different answers.
        if (location.type == TriggerType::MapReached ||
            location.type == TriggerType::ChapterComplete) {
            Notify("That is this map itself. Keep going.");
        } else {
            Notify("Somewhere on this map, but it is given to you rather than "
                   "left lying about.");
        }
        return;
    }

    const Vector at(position[0], position[1], position[2]);
    if (target != nullptr) {
        target->found = true;
        target->at = at;
        target->location_id = location.id;
        target->colour = LineColour(location);
    }
    char line[192];
    std::snprintf(line, sizeof(line), "%s%s, about %d units away.",
                  Bearing(player, at), HeightTo(player, at),
                  static_cast<int>(WalkScore(player->pev->origin, at)));
    Notify(line);
    Notify(ClearLineTo(player, at) ? "You have a clear line to it."
                                   : "Something solid is in the way.");
}

// `Find`, also saying where it pointed when that is somewhere on this map.
void FindInto(const std::string& text, FindTarget* target) {
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }
    // `Find` answers on screen rather than in the console alone, which is the
    // one place the Say/Notify split goes the other way. It is a short answer
    // read by a player standing in the level turning around, not one with the
    // console open. `ap` and `ap_tracker` stay in the console: those are lists.
    if (!Data().Loaded()) {
        Notify("No checkdata.txt, so there is nothing to find.");
        return;
    }

    const std::string wanted = Lower(Trim(text));

    // No query: the nearest thing left on this map, which is the question people
    // actually have when they type it with nothing after it.
    if (wanted.empty()) {
        const Location* best = nullptr;
        float best_score = 0.0f;

        for (const Location& location : Data().locations) {
            if (!State().InSeed(location.id) || Collected(location)) {
                continue;
            }
            // A weapon check's copy on this map counts as being on this map.
            const Location::Source* source = SourceHere(location);
            const float* position = nullptr;
            if (source != nullptr && source->has_position) {
                position = source->position;
            } else if (location.has_position && location.map == g_map) {
                position = location.position;
            } else {
                continue;
            }

            const Vector at(position[0], position[1], position[2]);
            const float score = WalkScore(player->pev->origin, at);
            if (best == nullptr || score < best_score) {
                best = &location;
                best_score = score;
            }
        }

        if (best == nullptr) {
            Notify("Nothing left to find on this map.");
            return;
        }
        DescribeLocation(player, *best, target);
        return;
    }

    // A query searches the whole seed, not this map. The current map is the
    // default, not the limit: asking where something is from the hub, or from
    // six missions later, is exactly when the question is worth asking.
    // Punctuation is ignored, so the older `Mission - Thing` spelling still finds
    // `Mission: Thing`. A query of punctuation alone falls back to the raw text.
    const std::string simple = Simplify(wanted);
    std::vector<const Location*> matches;
    for (const Location& location : Data().locations) {
        if (!State().InSeed(location.id)) {
            continue;
        }
        const bool hit = simple.empty()
            ? Lower(location.name).find(wanted) != std::string::npos
            : Simplify(location.name).find(simple) != std::string::npos;
        if (!hit) {
            continue;
        }
        matches.push_back(&location);
    }

    if (matches.empty()) {
        Notify(std::string("Nothing in this seed matches \"") + Trim(text) + "\".");
        return;
    }
    if (matches.size() == 1) {
        DescribeLocation(player, *matches[0], target);
        return;
    }

    // Several. Prefer this map when it settles it, since that is nearly always
    // what was meant; otherwise name them rather than guessing.
    const Location* here = nullptr;
    int here_count = 0;
    for (size_t i = 0; i < matches.size(); ++i) {
        // A found weapon check has nowhere left to point at.
        if (matches[i]->type == TriggerType::WeaponPickup && Collected(*matches[i])) {
            continue;
        }
        if (matches[i]->map == g_map || SourceHere(*matches[i]) != nullptr) {
            if (here == nullptr) {
                here = matches[i];
            }
            ++here_count;
        }
    }
    if (here_count == 1) {
        DescribeLocation(player, *here, target);
        return;
    }

    char head[128];
    std::snprintf(head, sizeof(head),
                  "%d matches; the list is in your console (~).",
                  static_cast<int>(matches.size()));
    Notify(head);
    Say(std::string("Locations matching \"") + Trim(text) + "\":");
    for (size_t i = 0; i < matches.size(); ++i) {
        Say(std::string("  ") + (Collected(*matches[i]) ? "[x] " : "[ ] ") +
            matches[i]->name + "  (" + matches[i]->map + ")");
    }
}

void Find(const std::string& text) { FindInto(text, nullptr); }

bool PathTraceActive() { return g_trace.on; }

void StopPathTrace() {
    g_trace = TraceState();
    g_segments.clear();
}

// The location the trace points at, or null.
const Location* TracedLocation() {
    for (const Location& location : Data().locations) {
        if (location.id == g_trace.target.location_id) {
            return &location;
        }
    }
    return nullptr;
}

void PathTrace(const std::string& text) {
    // Off says nothing: the line going away is the answer.
    if (g_trace.on && Trim(text).empty()) {
        StopPathTrace();
        return;
    }
    StopPathTrace();
    FindTarget target;
    FindInto(text, &target);
    if (!target.found) {
        // `Find` has said where it is; there is just no line to draw to it.
        Notify("Nothing on this map to trace to.");
        return;
    }
    g_trace.on = true;
    g_trace.map = g_map;
    g_trace.target = target;
    g_trace.next_draw = 0.0f;
    const Location* location = TracedLocation();
    g_trace.was_collected = location != nullptr && Collected(*location);
}

void RunPathTrace() {
    SendSegments();
    if (!g_trace.on) {
        return;
    }
    // A check on the map just left is nowhere on this one.
    if (g_trace.map != g_map) {
        StopPathTrace();
        return;
    }
    // Got there: the check going out is the answer, so this says nothing.
    if (!g_trace.was_collected) {
        const Location* location = TracedLocation();
        if (location != nullptr && Collected(*location)) {
            StopPathTrace();
            return;
        }
    }
    // The clock restarts on a load; a draw due far in the future is a stale one.
    if (gpGlobals->time < g_trace.next_draw &&
        g_trace.next_draw - gpGlobals->time <= kTraceInterval) {
        return;
    }
    g_trace.next_draw = gpGlobals->time + kTraceInterval;
    QueueTraceLine();
}

void PrecachePathTrace() {
    g_beam_sprite = PRECACHE_MODEL((char*)"sprites/laserbeam.spr");
}

bool IsWeaponCheck(const Location& location) {
    return location.type == TriggerType::WeaponPickup && !location.sources.empty();
}

void FindById(long id) {
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }
    for (const Location& location : Data().locations) {
        if (location.id == id) {
            DescribeLocation(player, location, nullptr);
            return;
        }
    }
}

void Tracker(const std::string& map_filter) {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is nothing to track.");
        return;
    }
    if (State().checked.empty() && State().missing.empty()) {
        Say("No location data yet. Is the client connected?");
        Notify("No location data yet; check the client.");
        return;
    }

    // The whole seed by default. This used to show the current map only, which
    // made it useless from the hub -- where a player is most likely to be asking
    // what is left -- and gave no way to see anywhere else at all. A filter
    // narrows it, matching either a map name or a mission name, so `ap_tracker
    // office` and `ap_tracker c1a2b` both work.
    const std::string filter = Trim(map_filter);
    const std::string wanted = Lower(filter);

    Say("=== Archipelago: location tracker ===");

    int found = 0;
    int total = 0;
    int shown = 0;

    for (const Chapter& chapter : Data().chapters) {
        if (State().ChapterExcluded(chapter.key)) {
            continue;
        }

        for (size_t part = 0; part < chapter.maps.size(); ++part) {
            const std::string& map_name = chapter.maps[part];

            // Gathered before anything is printed: a map the seed put nothing in
            // should not print a heading with nothing under it.
            std::vector<const Location*> on_map;
            for (const Location& location : Data().locations) {
                if (location.map != map_name) {
                    continue;
                }
                if (!State().InSeed(location.id)) {
                    continue;  // not in this seed; showing it would be a lie
                }
                if (IsWeaponCheck(location)) {
                    continue;  // listed under its game's weapons, below
                }
                on_map.push_back(&location);
            }
            if (on_map.empty()) {
                continue;
            }

            int map_found = 0;
            for (size_t i = 0; i < on_map.size(); ++i) {
                if (Collected(*on_map[i])) {
                    ++map_found;
                }
            }

            // Counted whether or not it is shown, so the total at the end is the
            // seed's and not the filter's.
            found += map_found;
            total += static_cast<int>(on_map.size());

            if (!wanted.empty() &&
                Lower(map_name).find(wanted) == std::string::npos &&
                Lower(chapter.name).find(wanted) == std::string::npos) {
                continue;
            }

            ++shown;
            char head[192];
            if (chapter.maps.size() > 1) {
                std::snprintf(head, sizeof(head), "%s, part %d -- %s  (%d/%d)",
                              chapter.name.c_str(), static_cast<int>(part) + 1,
                              map_name.c_str(), map_found,
                              static_cast<int>(on_map.size()));
            } else {
                std::snprintf(head, sizeof(head), "%s -- %s  (%d/%d)",
                              chapter.name.c_str(), map_name.c_str(), map_found,
                              static_cast<int>(on_map.size()));
            }
            Say(head);

            for (size_t i = 0; i < on_map.size(); ++i) {
                Say(std::string("    ") +
                    (Collected(*on_map[i]) ? "[x] " : "[ ] ") + on_map[i]->name);
            }
        }
    }

    // Each game's weapon checks together, as the Sven plugin lists them: they
    // are found anywhere in their game, so no one map heading fits them.
    for (const Campaign& campaign : Data().campaigns) {
        std::vector<const Location*> weapons;
        for (const Location& location : Data().locations) {
            if (!IsWeaponCheck(location) || !State().InSeed(location.id)) {
                continue;
            }
            const Chapter* chapter = Data().ChapterByKey(location.chapter);
            if (chapter != nullptr && chapter->campaign == campaign.key) {
                weapons.push_back(&location);
            }
        }
        if (weapons.empty()) {
            continue;
        }

        int weapons_found = 0;
        for (const Location* location : weapons) {
            if (Collected(*location)) {
                ++weapons_found;
            }
        }
        found += weapons_found;
        total += static_cast<int>(weapons.size());

        if (!wanted.empty() &&
            Lower(campaign.name + " weapons").find(wanted) == std::string::npos) {
            continue;
        }

        ++shown;
        char head[192];
        std::snprintf(head, sizeof(head), "%s: Weapons  (%d/%d)",
                      campaign.name.c_str(), weapons_found,
                      static_cast<int>(weapons.size()));
        Say(head);
        for (const Location* location : weapons) {
            Say(std::string("    ") + (Collected(*location) ? "[x] " : "[ ] ") +
                location->name);
        }
    }

    if (shown == 0 && !wanted.empty()) {
        Say(std::string("Nothing matches \"") + filter + "\".");
    }

    char line[128];
    std::snprintf(line, sizeof(line), "Found %d of %d locations in this seed.",
                  found, total);
    Say(line);
}

}  // namespace ap
