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
// A player kept this far inside a trigger's edge, across it.
constexpr float kLateralMargin = 16.0f;
// How long the arrival end ignores the player after they are placed.
constexpr float kArrivalGuard = 0.5f;

// What crosses with the player, measured from the exit's frame.
struct Follower {
    std::string classname;
    Vector offset;        // from the exit's landmark, where it stood
    bool parked = false;  // moved onto the landmark to cross
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
    float above = 0.0f;  // the player's height above the floor
    Vector shift;        // the exit's landmark from its trigger's centre
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

// The least gap kept between a follower and the player, side to side.
constexpr float kFollowerGap = 40.0f;

// Where a follower goes beside the player (just placed at `player_spot`) by
// its offset from them, turned into `b`'s frame. Only the side to side part is
// kept: behind the player is the arrival trigger and its stub, and ahead is in
// their way.
Vector BesidePlayer(const Transition& b, const Vector& rel, const Vector& player_spot) {
    const Vector normal = Normal(b);
    const Vector lateral(-normal.y, normal.x, 0.0f);
    float across = DotProduct(rel, lateral);
    if (std::fabs(across) < kFollowerGap) {
        across = across < 0.0f ? -kFollowerGap : kFollowerGap;
    }
    return player_spot + lateral * across;
}

bool HullFits(CBasePlayer* player, const Vector& at, int hull) {
    TraceResult tr;
    UTIL_TraceHull(at, at, ignore_monsters, hull, player->edict(), &tr);
    return !tr.fStartSolid && !tr.fAllSolid;
}

// The furthest a follower is put from the player. They trail at about 128;
// further than this and a corner can stand between them.
constexpr float kFollowerSpan = 96.0f;
// How far below the player's height a follower's floor may be.
constexpr float kFollowerDrop = 128.0f;
// How high above the floor a player in the air arrives, at most.
constexpr float kArrivalLift = 48.0f;
// How far above a frame's floor point its landmark sits.
constexpr float kLandmarkLift = 16.0f;

// How far above the floor `player` stands, for an arrival at the same height.
float AboveFloor(CBasePlayer* player) {
    const int hull = (player->pev->flags & FL_DUCKING) ? head_hull : human_hull;
    TraceResult tr;
    UTIL_TraceHull(player->pev->origin, player->pev->origin - Vector(0, 0, 512),
                   ignore_monsters, hull, player->edict(), &tr);
    return tr.fStartSolid ? 0.0f : player->pev->origin.z - tr.vecEndPos.z;
}

// Put a carried monster near its offset, turned with the player (placed first,
// at `toward`). It comes no further than `kFollowerSpan` from the player, and
// only somewhere its hull reaches from the player in a straight line: that
// keeps it out of walls, off the player and in the player's room. Failing
// that, spots closer to the player are tried; one that fits nowhere is left
// where it was, or with `remove` removed rather than left in a wall. Each
// is at the player's height, dropped to the
// floor: monsters do not fall, and the offset's height is from the trigger's
// centre.
bool PlaceFollower(CBaseEntity* entity, Vector origin, float dyaw, const Vector& toward,
                   bool remove = false) {
    origin.z = toward.z;
    Vector reach = origin - toward;
    if (reach.Length() > kFollowerSpan) {
        origin = toward + reach.Normalize() * kFollowerSpan;
    }
    static const Vector kTries[] = {
        Vector(0, 0, 0),    Vector(0, 0, 16),    Vector(24, 0, 0),    Vector(-24, 0, 0),
        Vector(0, 24, 0),   Vector(0, -24, 0),   Vector(34, 34, 0),   Vector(-34, 34, 0),
        Vector(34, -34, 0), Vector(-34, -34, 0)};
    // Then closer in, then the same spot on the player's other side.
    for (float pull : {0.0f, 0.25f, 0.5f, 2.0f}) {
        const Vector base = origin + (toward - origin) * pull;
        for (const Vector& offset : kTries) {
            const Vector spot = base + offset;
            TraceResult tr;
            TRACE_MONSTER_HULL(entity->edict(), spot, spot, dont_ignore_monsters,
                               entity->edict(), &tr);
            if (tr.fStartSolid || tr.fAllSolid) {
                continue;
            }
            TRACE_MONSTER_HULL(entity->edict(), toward, spot, ignore_monsters,
                               entity->edict(), &tr);
            if (tr.flFraction < 1.0f && !tr.fStartSolid) {
                continue;  // a wall between them
            }
            UTIL_TraceLine(spot + entity->pev->view_ofs, toward, ignore_monsters,
                           entity->edict(), &tr);
            if (tr.flFraction < 1.0f) {
                continue;
            }
            TRACE_MONSTER_HULL(entity->edict(), spot, spot - Vector(0, 0, kFollowerDrop),
                               ignore_monsters, entity->edict(), &tr);
            if (tr.fStartSolid || tr.flFraction >= 1.0f) {
                continue;  // no floor in reach: a ledge or a pit
            }
            UTIL_SetOrigin(entity->pev, tr.vecEndPos);
            entity->pev->flags |= FL_ONGROUND;
            entity->pev->angles.y += dyaw;
            entity->pev->ideal_yaw += dyaw;
            entity->pev->velocity = Rotate(entity->pev->velocity, dyaw);
            return true;
        }
    }
    Trace(("  carried " + std::string(STRING(entity->pev->classname)) + " does not fit" +
           (remove ? "; removed" : "")).c_str());
    if (remove) {
        UTIL_Remove(entity);
    }
    return false;
}

// Section 5.2: the player's offset from exit `a` becomes the same offset from
// arrival `b`, turned so walking out of `a` is walking into `b`. Built from a
// spot known to be good: just clear of `b` on the map's side, on the floor.
// From there the offset across is a hull trace, so a wall stops it, and the
// height is the player's above the floor at `a` (`above`), capped.
void Place(CBasePlayer* player, const Transition& a, const Transition& b, Vector rel,
           const Vector& velocity, const Vector& angles, const Vector& v_angle, float above) {
    const float dyaw = (b.yaw + 180.0f) - a.yaw;
    const bool seamless = Walkish(a) && Walkish(b);
    const bool ducked = (player->pev->flags & FL_DUCKING) != 0;
    const int hull = ducked ? head_hull : human_hull;
    const Vector normal = Normal(b);
    const Vector lateral(-normal.y, normal.x, 0.0f);

    rel = Rotate(rel, dyaw);
    float across = DotProduct(rel, lateral);
    const float half = (std::max)(b.width / 2.0f - kLateralMargin, 0.0f);
    across = (std::max)(-half, (std::min)(half, across));
    if (!seamless) {
        across = 0.0f;
        above = 0.0f;
    }

    // Out of the arrival trigger, inwards, as a vanilla arrival lands, and a
    // step further so the player is not touching it. The frame's origin is the
    // floor; the player's is their hull's centre.
    Vector spot = Vec(b.origin) - Vector(0, 0, player->pev->mins.z - 1.0f);
    CBaseEntity* trigger = TriggerOf(b);
    if (trigger != nullptr) {
        for (int step = 0; step < 64; ++step) {
            if (!Overlaps(spot + player->pev->mins, spot + player->pev->maxs,
                          trigger->pev->absmin, trigger->pev->absmax)) {
                break;
            }
            spot = spot - normal * 8.0f;
        }
        spot = spot - normal * 8.0f;
    }
    if (!HullFits(player, spot, hull)) {
        // Not one in the trigger or past it, in the stub.
        Vector found;
        if (FindStandSpot(player, spot, found, hull) &&
            DotProduct(found - Vec(b.origin), normal) < 0.0f &&
            (trigger == nullptr ||
             !Overlaps(found + player->pev->mins, found + player->pev->maxs,
                       trigger->pev->absmin, trigger->pev->absmax))) {
            spot = found;
        }
    }
    TraceResult tr;
    UTIL_TraceHull(spot, spot - Vector(0, 0, 512), ignore_monsters, hull, player->edict(), &tr);
    if (!tr.fStartSolid) {
        spot = tr.vecEndPos;
    }
    if (across != 0.0f) {
        UTIL_TraceHull(spot, spot + lateral * across, ignore_monsters, hull, player->edict(),
                       &tr);
        if (!tr.fStartSolid) {
            spot = tr.vecEndPos;
        }
    }
    above = (std::max)(0.0f, (std::min)(kArrivalLift, above));
    if (above > 0.0f) {
        UTIL_TraceHull(spot, spot + Vector(0, 0, above), ignore_monsters, hull,
                       player->edict(), &tr);
        if (!tr.fStartSolid) {
            spot = tr.vecEndPos;
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
// padded volume, and those following the player from anywhere in the map.
std::vector<CBaseEntity*> CarriedBy(CBaseEntity* trigger, CBaseEntity* player) {
    std::vector<CBaseEntity*> out;
    const Vector lo = trigger->pev->absmin - Vector(kVolumePad, kVolumePad, 0);
    const Vector hi = trigger->pev->absmax + Vector(kVolumePad, kVolumePad, 0);
    for (int i = 1; i < gpGlobals->maxEntities; ++i) {
        edict_t* edict = INDEXENT(i);
        if (edict == nullptr || edict->free || !(edict->v.flags & FL_MONSTER)) {
            continue;
        }
        CBaseEntity* entity = CBaseEntity::Instance(edict);
        if (entity == nullptr || entity == player || entity->IsPlayer() || !entity->IsAlive()) {
            continue;
        }
        if (Overlaps(entity->pev->absmin, entity->pev->absmax, lo, hi) ||
            Follows(entity, player)) {
            out.push_back(entity);
        }
    }
    return out;
}

void MoveWithinMap(CBasePlayer* player, CBaseEntity* trigger, const Transition& a,
                   const Transition& b) {
    const float dyaw = (b.yaw + 180.0f) - a.yaw;
    const std::vector<CBaseEntity*> carried = CarriedBy(trigger, player);
    std::vector<Vector> rels;  // from the player
    for (CBaseEntity* entity : carried) {
        rels.push_back(Rotate(entity->pev->origin - player->pev->origin, dyaw));
    }
    Place(player, a, b, player->pev->origin - Vec(a.origin), player->pev->velocity,
          player->pev->angles, player->pev->v_angle, AboveFloor(player));
    for (size_t i = 0; i < carried.size(); ++i) {
        PlaceFollower(carried[i], BesidePlayer(b, rels[i], player->pev->origin), dyaw,
                      player->pev->origin);
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

// Where a transition's landmark goes: its trigger's centre, or inwards from it
// to the first open point. The engine carries only what the landmark can see,
// and from inside a wall it sees nothing.
Vector LandmarkSpot(const Transition& t) {
    // Above the frame's origin, the floor, as followers cross standing on it.
    Vector spot = Vec(t.origin) + Vector(0, 0, kLandmarkLift);
    for (int step = 0; step < 32 && POINT_CONTENTS(spot) == CONTENTS_SOLID; ++step) {
        spot = spot - Normal(t) * 8.0f;
    }
    if (POINT_CONTENTS(spot) == CONTENTS_SOLID) {
        Trace(("  landmark for " + t.id + " is in solid").c_str());
        return Vec(t.origin) + Vector(0, 0, kLandmarkLift);
    }
    if (spot.x != t.origin[0] || spot.y != t.origin[1]) {
        char line[128];
        std::snprintf(line, sizeof(line), "  landmark for %s moved %.0f out of solid",
                      t.id.c_str(), (spot - Vec(t.origin)).Length2D());
        Trace(line);
    }
    return spot;
}

// This map's landmark by name, or the transition's centre when it has none.
Vector LandmarkOrigin(const std::string& name, const Transition& t) {
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByTargetname(entity, name.c_str())) != nullptr) {
        if (FClassnameIs(entity->pev, "info_landmark")) {
            return entity->pev->origin;
        }
    }
    return Vec(t.origin);
}

#ifdef HLAP_TEST_BUILD
// The engine's own test for what crosses, run on each carried monster, for why
// one is left behind: seen from the landmark, saveable, and touching a volume.
void TraceCarryTest(const char* landmark, const std::vector<CBaseEntity*>& carried) {
    CBaseEntity* mark = nullptr;
    int marks = 0;
    std::vector<CBaseEntity*> volumes;
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByTargetname(entity, landmark)) != nullptr) {
        if (FClassnameIs(entity->pev, "info_landmark")) {
            mark = mark != nullptr ? mark : entity;
            ++marks;
        } else if (FClassnameIs(entity->pev, "trigger_transition")) {
            volumes.push_back(entity);
        }
    }
    char line[256];
    std::snprintf(line, sizeof(line), "  landmark %s: %d landmarks, %d volumes%s", landmark,
                  marks, static_cast<int>(volumes.size()), mark == nullptr ? ", none found" : "");
    Trace(line);
    std::set<edict_t*> seen;
    if (mark != nullptr) {
        for (edict_t* pent = UTIL_EntitiesInPVS(mark->edict()); !FNullEnt(pent);
             pent = pent->v.chain) {
            seen.insert(pent);
        }
    }
    for (CBaseEntity* monster : carried) {
        const int caps = monster->ObjectCaps();
        bool touches = volumes.empty();
        for (CBaseEntity* volume : volumes) {
            touches = touches || volume->Intersects(monster) != 0;
        }
        const Vector& at = monster->pev->origin;
        std::snprintf(line, sizeof(line),
                      "  carry test %s: seen %d, moveable %d, dontsave %d, volume %d, "
                      "%.0f from landmark, at %.0f %.0f %.0f",
                      STRING(monster->pev->classname), seen.count(monster->edict()) ? 1 : 0,
                      (caps & FCAP_ACROSS_TRANSITION) ? 1 : 0, (caps & FCAP_DONT_SAVE) ? 1 : 0,
                      touches ? 1 : 0,
                      mark != nullptr ? (at - mark->pev->origin).Length() : -1.0f,
                      at.x, at.y, at.z);
        Trace(line);
    }
}
#endif

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
                SpawnNamed("info_landmark", name, LandmarkSpot(*t), nullptr);
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
    SpawnNamed("info_landmark", landmark, LandmarkSpot(*t), nullptr);
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

// Whether the player is walking out through `t`, towards its stub. A guard
// that ignored them then would let them walk through it into the stub.
bool Outward(const Transition& t) {
    CBasePlayer* player = Player();
    return player != nullptr && DotProduct(player->pev->velocity, Normal(t)) > 0.0f;
}

int OnTransition(CBaseEntity* trigger) {
    if (!Data().Loaded()) {
        return kTransitionNotOurs;
    }
    const Transition* t = TransitionOfTrigger(trigger);
    // The arrival end, touched before or just after the player is placed, and
    // not being walked back out through.
    if (t != nullptr && (g_pending.active ? g_pending.to == t->id && g_pending.map == CurrentMap()
                                          : g_guard_id == t->id &&
                                                gpGlobals->time < g_guard_until &&
                                                gpGlobals->time + 5.0f > g_guard_until &&
                                                !Outward(*t))) {
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
                                  gpGlobals->time - g_last_move > kArrivalGuard ||
                                  Outward(*t))) {
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
    if (CBasePlayer* p = Player()) {
        g_pending.above = AboveFloor(p);
    }
    // The engine carries only what touches the landmark's trigger_transition,
    // so it grows to take in every follower.
    CBaseEntity* volume = nullptr;
    const char* landmark = ChangeLevelLandmark(trigger);
    while ((volume = UTIL_FindEntityByTargetname(volume, landmark)) != nullptr) {
        if (FClassnameIs(volume->pev, "trigger_transition")) {
            break;
        }
    }
#ifdef HLAP_TEST_BUILD
    // Every monster near the player, for why one did or did not cross.
    {
        CBaseEntity* list[128];
        const Vector reach(1024, 1024, 1024);
        const int count = UTIL_EntitiesInBox(list, 128, player->pev->origin - reach,
                                             player->pev->origin + reach, FL_MONSTER);
        for (int i = 0; i < count; ++i) {
            CBaseMonster* monster = list[i]->MyMonsterPointer();
            if (list[i] == player || monster == nullptr) {
                continue;
            }
            CBaseEntity* target = monster->m_hTargetEnt;
            char line[256];
            std::snprintf(line, sizeof(line), "  near: %s at %.0f, alive %d, target %s%s",
                          STRING(list[i]->pev->classname),
                          (list[i]->pev->origin - player->pev->origin).Length(),
                          list[i]->IsAlive() ? 1 : 0,
                          target != nullptr ? STRING(target->pev->classname) : "none",
                          target == player ? " (player)" : "");
            Trace(line);
        }
    }
#endif
    Vector lo = volume != nullptr ? volume->pev->absmin : g_vecZero;
    Vector hi = volume != nullptr ? volume->pev->absmax : g_vecZero;
    const std::vector<CBaseEntity*> carried = CarriedBy(trigger, player);
    const Vector frame = LandmarkOrigin(landmark, *t);
    g_pending.shift = frame - Vec(t->origin);
    for (CBaseEntity* entity : carried) {
        // The engine moves what crosses by the landmarks' difference, unturned,
        // and frees whatever that lands in solid. A follower crosses on the
        // landmark, which is open on both sides, and is placed beside the
        // player on arrival.
        const bool parked = Follows(entity, player);
        g_pending.followers.push_back(
            {STRING(entity->pev->classname), entity->pev->origin - frame, parked});
        if (parked) {
            entity->pev->velocity = g_vecZero;
            UTIL_SetOrigin(entity->pev, frame);
        }
        Trace(("  carrying " + std::string(STRING(entity->pev->classname)) +
               (parked ? " (following)" : "")).c_str());
        for (int k = 0; k < 3; ++k) {
            lo[k] = (std::min)(lo[k], entity->pev->absmin[k]);
            hi[k] = (std::max)(hi[k], entity->pev->absmax[k]);
        }
    }
    if (volume != nullptr) {
        UTIL_SetSize(volume->pev, lo - volume->pev->origin, hi - volume->pev->origin);
    }
#ifdef HLAP_TEST_BUILD
    TraceCarryTest(landmark, carried);
#endif
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
    // The engine moved everything by the landmarks' difference. Offsets back in
    // the exit's frame, its trigger's centre, are from this map's landmark plus
    // where the exit's sat from its centre.
    const Vector frame = LandmarkOrigin(PairLandmark(a->id, b->id), *b);
    // The player's offset from the landmark, as the followers' are.
    const Vector player_offset = player->pev->origin - frame;
    Place(player, *a, *b, player->pev->origin - frame + pending.shift, pending.velocity,
          pending.angles, pending.v_angle, pending.above);
    // The engine has already translated everything by the frames' difference.
    const float dyaw = (b->yaw + 180.0f) - a->yaw;
    // Each by its translated spot: the nearest of its class not yet placed.
    std::vector<CBaseEntity*> placed;
    for (const Follower& follower : pending.followers) {
        const Vector at = follower.parked ? frame : frame + follower.offset;
        CBaseEntity* list[16];
        const int count = UTIL_EntitiesInBox(list, 16, at - Vector(32, 32, 32),
                                             at + Vector(32, 32, 32), FL_MONSTER);
        CBaseEntity* best = nullptr;
        for (int i = 0; i < count; ++i) {
            if (follower.classname == STRING(list[i]->pev->classname) &&
                std::find(placed.begin(), placed.end(), list[i]) == placed.end() &&
                (best == nullptr || (list[i]->pev->origin - at).Length() <
                                        (best->pev->origin - at).Length())) {
                best = list[i];
            }
        }
        if (best == nullptr) {
            Trace(("  carried " + follower.classname + " not found on arrival").c_str());
            continue;
        }
        PlaceFollower(best,
                      BesidePlayer(*b, Rotate(follower.offset - player_offset, dyaw),
                                   player->pev->origin),
                      dyaw, player->pev->origin);
        placed.push_back(best);
    }
    // A follower that came across but was not matched: beside the player.
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityInSphere(entity, player->pev->origin, 8192.0f)) != nullptr) {
        if ((entity->pev->flags & FL_MONSTER) && entity->IsAlive() && Follows(entity, player) &&
            std::find(placed.begin(), placed.end(), entity) == placed.end()) {
            Trace(("  unmatched follower " + std::string(STRING(entity->pev->classname)) +
                   "; placed by the player").c_str());
            PlaceFollower(entity, BesidePlayer(*b, g_vecZero, player->pev->origin), 0.0f,
                          player->pev->origin);
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
