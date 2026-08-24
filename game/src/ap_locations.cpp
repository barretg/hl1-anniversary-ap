#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_locations.h"

#include <cmath>
#include <cstdio>
#include <set>
#include <string>

#include "ap_bridge.h"
#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

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

void OnMapStart(const std::string& map_name) {
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
    g_arrival_owed = true;
    g_bounce_announced = false;

    if (requested) {
        // A warp starts the level cold, without the seam state a transition
        // would have carried in. See `RunSeamDoors`.
        RequestSeamDoors();
    }
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

        const bool open = chapter->is_goal ? state.goal_open
                                           : state.ChapterOpen(chapter->key);
        if (state.ChapterExcluded(chapter->key) || !open) {
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

void OnWeaponCollected(CBasePlayer* player, const std::string& classname) {
    if (player == nullptr || !Live()) {
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
        OnWeaponCollected(player, classname);
    }
}

void Find(const std::string& text) {
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }
    // `Find` answers on screen rather than in the console alone, which is the
    // one place the Say/Notify split goes the other way. It is a single line
    // that points at somewhere in the room, and it is read by a player who is
    // standing in the level turning around -- not one who has the console open.
    // `ap` and `ap_tracker` stay in the console: those are lists.
    if (!Data().Loaded()) {
        Notify("No checkdata.txt, so there is nothing to find.");
        return;
    }

    const std::string wanted = Lower(Trim(text));
    const Location* best = nullptr;
    float best_score = 0.0f;

    for (const Location& location : Data().locations) {
        if (!location.has_position) {
            continue;  // reaching a map is not somewhere a player can be pointed
        }
        if (location.map != g_map) {
            continue;
        }
        if (g_sent.find(location.id) != g_sent.end()) {
            continue;
        }
        if (!State().InSeed(location.id)) {
            continue;
        }
        if (State().checked.find(location.id) != State().checked.end()) {
            continue;
        }
        if (!wanted.empty() && Lower(location.name).find(wanted) == std::string::npos) {
            continue;
        }

        const Vector at(location.position[0], location.position[1],
                        location.position[2]);
        const float score = WalkScore(player->pev->origin, at);
        if (best == nullptr || score < best_score) {
            best = &location;
            best_score = score;
        }
    }

    if (best == nullptr) {
        Notify(wanted.empty() ? "Nothing left to find in this map."
                              : "No unfound check here matches that.");
        return;
    }

    const Vector at(best->position[0], best->position[1], best->position[2]);
    char line[256];
    std::snprintf(line, sizeof(line), "%s: %s, about %d units away.",
                  best->name.c_str(), Bearing(player, at),
                  static_cast<int>(best_score));
    Notify(line);
}

void Tracker(const std::string& map_filter) {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is nothing to track.");
        return;
    }

    const std::string filter = Trim(map_filter);
    const std::string map = filter.empty() ? g_map : filter;

    int found = 0;
    int left = 0;
    Say(std::string("Locations in ") + map + ":");

    for (const Location& location : Data().locations) {
        if (location.map != map) {
            continue;
        }
        if (!State().InSeed(location.id)) {
            continue;  // not in this seed at all; showing it would be a lie
        }
        const bool done = State().checked.find(location.id) != State().checked.end() ||
                          g_sent.find(location.id) != g_sent.end();
        if (done) {
            ++found;
        } else {
            ++left;
            Say(std::string("  still out there: ") + location.name);
        }
    }

    char line[128];
    std::snprintf(line, sizeof(line), "%d found, %d to go.", found, left);
    Say(line);
}

}  // namespace ap
