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

// Point the player at one location, wherever it is.
//
// Somewhere else in the campaign is a legitimate answer -- `ap_find crossbow`
// from the hub should say where the crossbow is, not that there is nothing here
// -- so this says which mission and part, and hands over the command that goes
// there rather than leaving the player to work it out.
void DescribeLocation(CBasePlayer* player, const Location& location) {
    Notify((Collected(location) ? "[found] " : "") + location.name);

    if (location.map != g_map) {
        const Chapter* chapter = Data().ChapterOfMap(location.map);
        if (chapter == nullptr) {
            Notify(std::string("It is on ") + location.map + ".");
            return;
        }

        const int part = PartOf(*chapter, location.map);
        char line[192];
        if (part > 0) {
            std::snprintf(line, sizeof(line), "In %s, part %d (%s).",
                          chapter->name.c_str(), part, location.map.c_str());
        } else {
            std::snprintf(line, sizeof(line), "In %s (%s).",
                          chapter->name.c_str(), location.map.c_str());
        }
        Notify(line);

        // A part warp only works somewhere already walked to, so offer it only
        // where it would be accepted. Otherwise the mission's own door.
        if (part > 0 && Visited(location.map)) {
            std::snprintf(line, sizeof(line), "Get there with ap_warp %d %d.",
                          chapter->index, part);
        } else {
            std::snprintf(line, sizeof(line), "Get there with ap_warp %d.",
                          chapter->index);
        }
        Notify(line);
        return;
    }

    if (!location.has_position) {
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

    const Vector at(location.position[0], location.position[1],
                    location.position[2]);
    char line[192];
    std::snprintf(line, sizeof(line), "%s, about %d units away.",
                  Bearing(player, at),
                  static_cast<int>(WalkScore(player->pev->origin, at)));
    Notify(line);
}

void Find(const std::string& text) {
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
            if (!location.has_position || location.map != g_map) {
                continue;
            }
            if (!State().InSeed(location.id) || Collected(location)) {
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
            Notify("Nothing left to find on this map.");
            return;
        }
        DescribeLocation(player, *best);
        return;
    }

    // A query searches the whole seed, not this map. The current map is the
    // default, not the limit: asking where something is from the hub, or from
    // six missions later, is exactly when the question is worth asking.
    std::vector<const Location*> matches;
    for (const Location& location : Data().locations) {
        if (!State().InSeed(location.id)) {
            continue;
        }
        if (Lower(location.name).find(wanted) == std::string::npos) {
            continue;
        }
        matches.push_back(&location);
    }

    if (matches.empty()) {
        Notify(std::string("Nothing in this seed matches \"") + Trim(text) + "\".");
        return;
    }
    if (matches.size() == 1) {
        DescribeLocation(player, *matches[0]);
        return;
    }

    // Several. Prefer this map when it settles it, since that is nearly always
    // what was meant; otherwise name them rather than guessing.
    const Location* here = nullptr;
    int here_count = 0;
    for (size_t i = 0; i < matches.size(); ++i) {
        if (matches[i]->map == g_map) {
            if (here == nullptr) {
                here = matches[i];
            }
            ++here_count;
        }
    }
    if (here_count == 1) {
        DescribeLocation(player, *here);
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

    if (shown == 0 && !wanted.empty()) {
        Say(std::string("Nothing matches \"") + filter + "\".");
    }

    char line[128];
    std::snprintf(line, sizeof(line), "Found %d of %d locations in this seed.",
                  found, total);
    Say(line);
}

}  // namespace ap
