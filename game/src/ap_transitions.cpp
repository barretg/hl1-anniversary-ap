#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_transitions.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <set>
#include <unordered_map>
#include <vector>

#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

namespace ap {

namespace {

// Where each transition leads in this seed: a pair both ways, a one-way
// exit only from the exit. Unlisted means its vanilla partner.
std::unordered_map<std::string, std::string> g_pairs;
// The exits that lead one way into an arrival, by arrival. The arrival's map
// needs a landmark for each, since its own trigger leads somewhere else.
std::unordered_map<std::string, std::vector<std::string>> g_one_way_in;
// Triggers that do nothing in this seed.
std::set<std::string> g_inert;
// Whether the pairing above came from a seed rather than `ap_transition_pair`,
// and which snapshot section it was, so an unchanged one is not reapplied.
bool g_seeded = false;
std::string g_seed_key;

// How far a trigger's brush centre may sit from the recorded one. The record
// is rounded to whole units.
constexpr float kCentreSlack = 2.0f;
// The transition volume reaches this far past the trigger on every side, so a
// follower right behind the player comes too.
constexpr float kVolumePad = 48.0f;
// A monster following the player crosses from this far away. Followers trail
// by about 128 units, well outside the padded volume.
constexpr float kFollowReach = 384.0f;
// A player kept this far inside a trigger's edge, across it.
constexpr float kLateralMargin = 16.0f;
// How long the arrival end ignores the player after they are placed.
constexpr float kArrivalGuard = 0.5f;

// What crosses with the player, measured from the exit's frame.
struct Follower {
    std::string classname;
    Vector offset;
};

// The pending arrival. Set as the engine is told to change level, used on the
// first frame the player is in the new one, then cleared.
struct Pending {
    bool active = false;
    std::string from;  // exit transition id
    std::string to;    // arrival transition id
    std::string map;   // the arrival's map
    Vector velocity;
    Vector angles;
    Vector v_angle;
    std::vector<Follower> followers;
};
Pending g_pending;

// The arrival end, ignored for a moment after the player is placed beside it.
std::string g_guard_id;
float g_guard_until = -1.0f;
// The last in-map move, so a trigger still touched does not bounce back.
float g_last_move = -1.0f;

Vector Rotate(const Vector& v, float degrees) {
    const float r = degrees * static_cast<float>(M_PI) / 180.0f;
    const float c = std::cos(r), s = std::sin(r);
    return Vector(v.x * c - v.y * s, v.x * s + v.y * c, v.z);
}

Vector Vec(const float v[3]) { return Vector(v[0], v[1], v[2]); }

Vector Normal(const Transition& t) {
    const float r = t.yaw * static_cast<float>(M_PI) / 180.0f;
    return Vector(std::cos(r), std::sin(r), 0.0f);
}

bool Walkish(const Transition& t) { return t.kind == "walk" || t.kind == "scripted"; }

bool Overlaps(const Vector& amin, const Vector& amax, const Vector& bmin,
              const Vector& bmax) {
    return amin.x <= bmax.x && amax.x >= bmin.x && amin.y <= bmax.y &&
           amax.y >= bmin.y && amin.z <= bmax.z && amax.z >= bmin.z;
}

// This map's trigger for a transition id, found again by its brush centre.
CBaseEntity* TriggerOf(const Transition& t) {
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByClassname(entity, "trigger_changelevel")) != nullptr) {
        if (TransitionOfTrigger(entity) == &t) {
            return entity;
        }
    }
    return nullptr;
}

bool NamedExists(const char* classname, const std::string& name) {
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByTargetname(entity, name.c_str())) != nullptr) {
        if (FClassnameIs(entity->pev, classname)) {
            return true;
        }
    }
    return false;
}

void SpawnNamed(const char* classname, const std::string& name, const Vector& origin,
                CBaseEntity* model_from) {
    edict_t* edict = CREATE_NAMED_ENTITY(MAKE_STRING(classname));
    if (FNullEnt(edict)) {
        Trace((std::string("  could not create ") + classname).c_str());
        return;
    }
    edict->v.origin = origin;
    edict->v.targetname = ALLOC_STRING(name.c_str());
    if (model_from != nullptr) {
        edict->v.model = model_from->pev->model;
    }
    DispatchSpawn(edict);
}

bool HullFits(CBasePlayer* player, const Vector& at, int hull) {
    TraceResult tr;
    UTIL_TraceHull(at, at, ignore_monsters, hull, player->edict(), &tr);
    return !tr.fStartSolid && !tr.fAllSolid;
}

// Put a carried monster where its offset says, turned with the player
// (placed first, at `toward`). A spot must fit the monster's hull, which keeps it
// off the player and out of walls, and see the player, which keeps it in the
// player's room. Failing that, spots around it and then closer to the player
// are tried; one that fits nowhere is removed rather than left in a wall.
void PlaceFollower(CBaseEntity* entity, const Vector& origin, float dyaw, const Vector& toward) {
    static const Vector kTries[] = {
        Vector(0, 0, 0),    Vector(0, 0, 16),    Vector(24, 0, 0),    Vector(-24, 0, 0),
        Vector(0, 24, 0),   Vector(0, -24, 0),   Vector(48, 0, 0),    Vector(-48, 0, 0),
        Vector(0, 48, 0),   Vector(0, -48, 0),   Vector(34, 34, 0),   Vector(-34, 34, 0),
        Vector(34, -34, 0), Vector(-34, -34, 0)};
    for (float pull : {0.0f, 0.25f, 0.5f, 0.75f}) {
        const Vector base = origin + (toward - origin) * pull;
        for (const Vector& offset : kTries) {
            const Vector spot = base + offset;
            TraceResult tr;
            TRACE_MONSTER_HULL(entity->edict(), spot, spot, dont_ignore_monsters,
                               entity->edict(), &tr);
            if (tr.fStartSolid || tr.fAllSolid) {
                continue;
            }
            UTIL_TraceLine(spot + entity->pev->view_ofs, toward, ignore_monsters,
                           entity->edict(), &tr);
            if (tr.flFraction < 1.0f) {
                continue;
            }
            UTIL_SetOrigin(entity->pev, spot);
            entity->pev->angles.y += dyaw;
            entity->pev->ideal_yaw += dyaw;
            entity->pev->velocity = Rotate(entity->pev->velocity, dyaw);
            return;
        }
    }
    Trace(("  carried " + std::string(STRING(entity->pev->classname)) +
           " does not fit; removed").c_str());
    UTIL_Remove(entity);
}

// Section 5.2: the player's offset from exit `a` becomes the same offset from
// arrival `b`, turned so walking out of `a` is walking into `b`.
void Place(CBasePlayer* player, const Transition& a, const Transition& b, Vector rel,
           const Vector& velocity, const Vector& angles, const Vector& v_angle) {
    const float dyaw = (b.yaw + 180.0f) - a.yaw;
    const bool seamless = Walkish(a) && Walkish(b);
    const bool ducked = (player->pev->flags & FL_DUCKING) != 0;
    const Vector normal = Normal(b);
    const Vector lateral(-normal.y, normal.x, 0.0f);

    rel = Rotate(rel, dyaw);
    float across = DotProduct(rel, lateral);
    float along = DotProduct(rel, normal);
    float up = rel.z;
    const float half = (std::max)(b.width / 2.0f - kLateralMargin, 0.0f);
    across = (std::max)(-half, (std::min)(half, across));
    if (!seamless) {
        across = along = 0.0f;
        up = ducked ? 18.0f : 36.0f;
    }
    up = (std::max)(0.0f, (std::min)((std::max)(b.height, 72.0f), up));
    Vector spot = Vec(b.origin) + lateral * across + normal * along + Vector(0, 0, up);

    // Out of the arrival trigger, inwards, as a vanilla arrival lands.
    CBaseEntity* trigger = TriggerOf(b);
    if (trigger != nullptr) {
        for (int step = 0; step < 48; ++step) {
            if (!Overlaps(spot + player->pev->mins, spot + player->pev->maxs,
                          trigger->pev->absmin, trigger->pev->absmax)) {
                break;
            }
            spot = spot - normal * 8.0f;
        }
    }
    const int hull = ducked ? head_hull : human_hull;
    if (!HullFits(player, spot, hull)) {
        Vector found;
        if (FindStandSpot(player, spot, found, hull)) {
            spot = found;
        }
    }

    UTIL_SetOrigin(player->pev, spot);
    Vector moved = Rotate(velocity, dyaw);
    if (!seamless) {
        moved.z = 0.0f;
    }
    player->pev->velocity = moved;
    player->pev->basevelocity = g_vecZero;
    // No roll: strafing tilts the view, and fixangle would keep the tilt.
    player->pev->angles = Vector(angles.x, angles.y + dyaw, 0.0f);
    player->pev->v_angle = Vector(v_angle.x, v_angle.y + dyaw, 0.0f);
    player->pev->fixangle = 1;

    g_guard_id = b.id;
    g_guard_until = gpGlobals->time + kArrivalGuard;
    Trace(("  transition " + a.id + " -> " + b.id).c_str());
}

bool Follows(CBaseEntity* entity, CBaseEntity* player) {
    CBaseMonster* monster = entity->MyMonsterPointer();
    return monster != nullptr && monster->m_hTargetEnt == player;
}

// What crosses a transition with the player: the monsters standing in its
// padded volume, and those following the player from within reach.
std::vector<CBaseEntity*> CarriedBy(CBaseEntity* trigger, CBaseEntity* player) {
    std::vector<CBaseEntity*> out;
    const Vector lo = trigger->pev->absmin - Vector(kVolumePad, kVolumePad, 0);
    const Vector hi = trigger->pev->absmax + Vector(kVolumePad, kVolumePad, 0);
    const Vector reach(kFollowReach, kFollowReach, kFollowReach);
    CBaseEntity* list[128];
    const int count = UTIL_EntitiesInBox(list, 128, player->pev->origin - reach,
                                         player->pev->origin + reach, FL_MONSTER);
    for (int i = 0; i < count; ++i) {
        CBaseEntity* entity = list[i];
        if (entity == player || entity->IsPlayer() || !entity->IsAlive()) {
            continue;
        }
        if (Overlaps(entity->pev->absmin, entity->pev->absmax, lo, hi) ||
            Follows(entity, player)) {
            out.push_back(entity);
        }
    }
    // A trigger bigger than the reach box: what stands in it beyond the box.
    const int inside = UTIL_EntitiesInBox(list, 128, lo, hi, FL_MONSTER);
    for (int i = 0; i < inside; ++i) {
        CBaseEntity* entity = list[i];
        if (entity != player && !entity->IsPlayer() && entity->IsAlive() &&
            std::find(out.begin(), out.end(), entity) == out.end()) {
            out.push_back(entity);
        }
    }
    return out;
}

void MoveWithinMap(CBasePlayer* player, CBaseEntity* trigger, const Transition& a,
                   const Transition& b) {
    const float dyaw = (b.yaw + 180.0f) - a.yaw;
    const std::vector<CBaseEntity*> carried = CarriedBy(trigger, player);
    std::vector<Vector> rels;
    for (CBaseEntity* entity : carried) {
        rels.push_back(Rotate(entity->pev->origin - Vec(a.origin), dyaw));
    }
    Place(player, a, b, player->pev->origin - Vec(a.origin), player->pev->velocity,
          player->pev->angles, player->pev->v_angle);
    for (size_t i = 0; i < carried.size(); ++i) {
        PlaceFollower(carried[i], Vec(b.origin) + rels[i], dyaw, player->pev->origin);
    }
    g_last_move = gpGlobals->time;
}

}  // namespace

void SetTransitionPairs(const std::vector<std::pair<std::string, std::string>>& pairs,
                        const std::vector<std::pair<std::string, std::string>>& one_way) {
    g_pairs.clear();
    g_one_way_in.clear();
    for (const auto& pair : pairs) {
        g_pairs[pair.first] = pair.second;
        g_pairs[pair.second] = pair.first;
    }
    for (const auto& entry : one_way) {
        g_pairs[entry.first] = entry.second;
        g_one_way_in[entry.second].push_back(entry.first);
    }
}

void ApplySeedTransitions(const Snapshot& state, bool force) {
    if (!state.transitions_mode) {
        if (g_seeded) {  // a hub seed now: nothing of the last one stands
            SetTransitionPairs({});
            g_inert.clear();
            g_seeded = false;
            g_seed_key.clear();
        }
        return;
    }
    std::string key;
    for (const auto& pair : state.transition_pairs) {
        key += pair.first + "," + pair.second + ";";
    }
    key += "|";
    for (const auto& entry : state.one_way_transitions) {
        key += entry.first + "," + entry.second + ";";
    }
    key += "|";
    for (const std::string& id : state.inert_transitions) {
        key += id + ";";
    }
    if (g_seeded && key == g_seed_key && !force) {
        return;
    }
    SetTransitionPairs(state.transition_pairs, state.one_way_transitions);
    g_inert = state.inert_transitions;
    g_seeded = true;
    g_seed_key = key;
    // The snapshot is usually already here when a level spawns, but not on the
    // first map after launch: rewrite what has spawned without it.
    RewriteLevelTransitions();
}

bool TransitionsMode() { return State().transitions_mode; }

std::string LeadsTo(const Transition& t) {
    if (Inert(t.id)) {
        return "";
    }
    const std::string* partner = SeedPartner(t.id);
    const Transition* b = partner != nullptr ? Data().TransitionById(*partner) : nullptr;
    return b != nullptr ? b->map : t.to;
}

bool Inert(const std::string& id) { return g_inert.find(id) != g_inert.end(); }

void RewriteLevelTransitions() {
    if (!Data().Loaded()) {
        return;
    }
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByClassname(entity, "trigger_changelevel")) != nullptr) {
        OnChangeLevelSpawned(entity);
    }
}

const std::string* SeedPartner(const std::string& id) {
    const auto found = g_pairs.find(id);
    return found == g_pairs.end() ? nullptr : &found->second;
}

bool Randomized(const std::string& id) {
    const std::string* partner = SeedPartner(id);
    if (partner == nullptr) {
        return false;
    }
    const Transition* t = Data().TransitionById(id);
    return t != nullptr && t->partner != *partner && *partner != id;
}

const Transition* TransitionOfTrigger(CBaseEntity* trigger) {
    if (trigger == nullptr) {
        return nullptr;
    }
    const Vector centre = (trigger->pev->absmin + trigger->pev->absmax) * 0.5f;
    const std::string map = CurrentMap();
    for (const Transition& t : Data().transitions) {
        if (t.map == map && std::fabs(t.at[0] - centre.x) <= kCentreSlack &&
            std::fabs(t.at[1] - centre.y) <= kCentreSlack &&
            std::fabs(t.at[2] - centre.z) <= kCentreSlack) {
            return &t;
        }
    }
    return nullptr;
}

std::string PairLandmark(const std::string& a, const std::string& b) {
    // FNV-1a over the two ids in order, so both ends name it alike.
    const std::string key = a < b ? a + "|" + b : b + "|" + a;
    unsigned int hash = 2166136261u;
    for (char c : key) {
        hash = (hash ^ static_cast<unsigned char>(c)) * 16777619u;
    }
    char name[16];
    std::snprintf(name, sizeof(name), "aplm_%08x", hash);
    return name;
}

void OnChangeLevelSpawned(CBaseEntity* trigger) {
    EnsureData();
    const Transition* t = TransitionOfTrigger(trigger);
    if (t == nullptr) {
        return;
    }
    // Exits elsewhere that lead here one way land on this frame too.
    const auto in = g_one_way_in.find(t->id);
    if (in != g_one_way_in.end()) {
        for (const std::string& exit : in->second) {
            const Transition* x = Data().TransitionById(exit);
            const std::string name = PairLandmark(exit, t->id);
            if (x != nullptr && x->map != t->map && !NamedExists("info_landmark", name)) {
                SpawnNamed("info_landmark", name, Vec(t->origin), nullptr);
            }
        }
    }
    if (!Randomized(t->id)) {
        return;
    }
    const Transition* b = Data().TransitionById(*SeedPartner(t->id));
    if (b == nullptr || b->map == t->map) {
        return;  // a same-map pair never changes level; see `OnTransition`
    }
    const std::string landmark = PairLandmark(t->id, b->id);
    if (landmark == ChangeLevelLandmark(trigger) && NamedExists("info_landmark", landmark)) {
        return;  // already rewritten, by spawn or by a save
    }
    SetChangeLevelDestination(trigger, b->map.c_str(), landmark.c_str());
    SpawnNamed("info_landmark", landmark, Vec(t->origin), nullptr);
    // Only what stands at the trigger crosses, not the whole of what the
    // landmark can see.
    SpawnNamed("trigger_transition", landmark, g_vecZero, trigger);
    CBaseEntity* volume = nullptr;
    while ((volume = UTIL_FindEntityByTargetname(volume, landmark.c_str())) != nullptr) {
        if (FClassnameIs(volume->pev, "trigger_transition")) {
            UTIL_SetSize(volume->pev, trigger->pev->mins - Vector(kVolumePad, kVolumePad, 0),
                         trigger->pev->maxs + Vector(kVolumePad, kVolumePad, 0));
        }
    }
    Trace(("  rewrote " + t->id + " to " + b->id + " via " + landmark).c_str());
}

int OnTransition(CBaseEntity* trigger) {
    if (!Data().Loaded()) {
        return kTransitionNotOurs;
    }
    const Transition* t = TransitionOfTrigger(trigger);
    // The arrival end, touched before or just after the player is placed.
    if (t != nullptr && (g_pending.active ? g_pending.to == t->id && g_pending.map == CurrentMap()
                                          : g_guard_id == t->id &&
                                                gpGlobals->time < g_guard_until &&
                                                gpGlobals->time + 5.0f > g_guard_until)) {
        return kTransitionSwallowed;
    }
    if (t != nullptr && Inert(t->id)) {
        return kTransitionSwallowed;
    }
    if (t == nullptr || !Randomized(t->id)) {
        return kTransitionNotOurs;
    }
    const Transition* b = Data().TransitionById(*SeedPartner(t->id));
    if (b == nullptr) {
        return kTransitionNotOurs;
    }
    if (b->map == t->map) {
        CBasePlayer* player = Player();
        if (player != nullptr && (g_last_move < 0.0f || gpGlobals->time < g_last_move ||
                                  gpGlobals->time - g_last_move > kArrivalGuard)) {
            MoveWithinMap(player, trigger, *t, *b);
        }
        return kTransitionSwallowed;
    }
    // Rewritten at spawn. A level restored from a save made before the pair
    // was set keeps its vanilla names, and stays the game's own.
    if (std::strncmp(ChangeLevelLandmark(trigger), "aplm_", 5) != 0) {
        return kTransitionNotOurs;
    }
    return kTransitionChange;
}

bool CompletesChapter(const Transition& t) {
    const Chapter* from = Data().ChapterOfMap(t.map);
    const Chapter* to = Data().ChapterOfMap(t.to);
    // Endsection and arrival finales complete on their own triggers (7.5).
    return from != nullptr && to != nullptr && to->index > from->index &&
           !from->CompletesOnEndSection() && !from->complete_on_arrival;
}

void BeforeChangeLevel(CBaseEntity* trigger, CBaseEntity* player) {
    const Transition* t = TransitionOfTrigger(trigger);
    // Section 7.5: leaving through the vanilla way forwards out of a chapter
    // finishes it, wherever that way leads now.
    if (t != nullptr && TransitionsMode() && CompletesChapter(*t)) {
        const Chapter* chapter = Data().ChapterOfMap(t->map);
        if (SendChapterComplete(*chapter)) {
            Notify(chapter->name + " complete.");
        } else {
            Notify(chapter->name + " could not be recorded: the client is not connected.");
        }
    }
    if (std::strncmp(ChangeLevelLandmark(trigger), "aplm_", 5) != 0 || player == nullptr) {
        return;
    }
    if (t == nullptr || !Randomized(t->id)) {
        return;
    }
    const Transition* b = Data().TransitionById(*SeedPartner(t->id));
    if (b == nullptr) {
        return;
    }
    g_pending = Pending();
    g_pending.active = true;
    g_pending.from = t->id;
    g_pending.to = b->id;
    g_pending.map = b->map;
    g_pending.velocity = player->pev->velocity;
    g_pending.angles = player->pev->angles;
    g_pending.v_angle = player->pev->v_angle;
    // The engine carries only what touches the landmark's trigger_transition,
    // so it grows to take in every follower.
    CBaseEntity* volume = nullptr;
    const char* landmark = ChangeLevelLandmark(trigger);
    while ((volume = UTIL_FindEntityByTargetname(volume, landmark)) != nullptr) {
        if (FClassnameIs(volume->pev, "trigger_transition")) {
            break;
        }
    }
    Vector lo = volume != nullptr ? volume->pev->absmin : g_vecZero;
    Vector hi = volume != nullptr ? volume->pev->absmax : g_vecZero;
    for (CBaseEntity* entity : CarriedBy(trigger, player)) {
        g_pending.followers.push_back(
            {STRING(entity->pev->classname), entity->pev->origin - Vec(t->origin)});
        for (int k = 0; k < 3; ++k) {
            lo[k] = (std::min)(lo[k], entity->pev->absmin[k]);
            hi[k] = (std::max)(hi[k], entity->pev->absmax[k]);
        }
    }
    if (volume != nullptr) {
        UTIL_SetSize(volume->pev, lo - volume->pev->origin, hi - volume->pev->origin);
    }
}

void OnTransitionLevelStart() {
    if (g_pending.active && g_pending.map != CurrentMap()) {
        g_pending = Pending();  // the change went somewhere else
    }
    g_guard_until = -1.0f;
    g_last_move = -1.0f;
}

void RunTransitionArrival() {
    if (!g_pending.active || g_pending.map != CurrentMap()) {
        return;
    }
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }
    const Transition* a = Data().TransitionById(g_pending.from);
    const Transition* b = Data().TransitionById(g_pending.to);
    Pending pending = g_pending;
    g_pending = Pending();  // single frame: a quickload must not replay it
    if (a == nullptr || b == nullptr) {
        return;
    }
    Place(player, *a, *b, player->pev->origin - Vec(b->origin), pending.velocity,
          pending.angles, pending.v_angle);
    // The engine has already translated everything by the frames' difference.
    const float dyaw = (b->yaw + 180.0f) - a->yaw;
    for (const Follower& follower : pending.followers) {
        const Vector at = Vec(b->origin) + follower.offset;
        CBaseEntity* list[16];
        const int count = UTIL_EntitiesInBox(list, 16, at - Vector(4, 4, 4),
                                             at + Vector(4, 4, 4), FL_MONSTER);
        for (int i = 0; i < count; ++i) {
            if (follower.classname == STRING(list[i]->pev->classname)) {
                PlaceFollower(list[i], Vec(b->origin) + Rotate(follower.offset, dyaw), dyaw,
                              player->pev->origin);
                break;
            }
        }
    }
    // Seam doors on the far side may never have seen this route.
    RequestSeamDoors();
}

bool FindStandSpot(CBasePlayer* player, const Vector& target, Vector& out, int hull) {
    static const float kRadii[] = {0.0f, 24.0f, 48.0f, 80.0f, 128.0f};
    static const float kHeights[] = {36.0f, 72.0f, 0.0f, 128.0f};
    for (float height : kHeights) {
        for (float radius : kRadii) {
            const int steps = radius == 0.0f ? 1 : 8;
            for (int i = 0; i < steps; ++i) {
                const float angle = 6.2831853f * i / steps;
                const Vector spot = target + Vector(radius * std::cos(angle),
                                                    radius * std::sin(angle), height);
                TraceResult tr;
                UTIL_TraceHull(spot, spot, ignore_monsters, hull, player->edict(), &tr);
                if (tr.fStartSolid || tr.fAllSolid) {
                    continue;
                }
                UTIL_TraceHull(spot, spot - Vector(0, 0, 256), ignore_monsters, hull,
                               player->edict(), &tr);
                out = tr.vecEndPos;
                return true;
            }
        }
    }
    return false;
}

#ifdef HLAP_TEST_BUILD
namespace {
void Cmd_TransitionPair() {
    if (CMD_ARGC() == 2 && Lower(CMD_ARGV(1)) == "clear") {
        SetTransitionPairs({});
        g_seeded = false;
        g_seed_key.clear();
        Say("Transition pairs cleared.");
        return;
    }
    if (CMD_ARGC() != 3) {
        Say("ap_transition_pair <id> <id>, or ap_transition_pair clear. "
            "Takes effect on the next map load.");
        return;
    }
    const std::string a = CMD_ARGV(1), b = CMD_ARGV(2);
    if (Data().TransitionById(a) == nullptr || Data().TransitionById(b) == nullptr) {
        Say("No transition " + (Data().TransitionById(a) == nullptr ? a : b) + ".");
        return;
    }
    std::vector<std::pair<std::string, std::string>> pairs;
    for (const auto& entry : g_pairs) {
        if (entry.first < entry.second && entry.first != a && entry.first != b &&
            entry.second != a && entry.second != b) {
            pairs.push_back(entry);
        }
    }
    pairs.push_back({a, b});
    SetTransitionPairs(pairs);
    g_seeded = false;  // a seed's next snapshot section replaces this
    g_seed_key.clear();
    Say("Paired " + a + " with " + b + ". Takes effect on the next map load.");
}
}  // namespace
#endif

void RegisterTransitionCommands() {
#ifdef HLAP_TEST_BUILD
    g_engfuncs.pfnAddServerCommand((char*)"ap_transition_pair", Cmd_TransitionPair);
#endif
}

}  // namespace ap
