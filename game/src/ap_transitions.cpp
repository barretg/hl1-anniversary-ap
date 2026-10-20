#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"

#include "ap_transitions.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <set>
#include <sstream>
#include <unordered_map>
#include <vector>

#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

extern int gmsgAPLabel;  // player.cpp

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
// The maps of the seed's chapters, and its ending map. A transition outside
// them is inert too: see `OutsideSeed`.
std::set<std::string> g_seed_maps;
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
// Monsters this far past the trigger, following or not, cross with the
// player. The engine's volume stays at `kVolumePad`: anything else it carries
// is not ours to widen.
constexpr float kCarryPad = 144.0f;
// A player kept this far inside a trigger's edge, across it.
constexpr float kLateralMargin = 16.0f;
// How long the arrival end ignores the player after they are placed.
constexpr float kArrivalGuard = 0.5f;

// What crosses with the player, measured from the exit's frame.
struct Follower {
    std::string classname;
    Vector offset;        // from the exit's landmark, where it stood
    bool parked = false;     // moved onto the landmark to cross
    bool following = false;  // placed within `kFollowerSpan`, else `kCarryPad`
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
    bool orb = false;    // by a backtrack orb: placed at the frame, facing in
};
Pending g_pending;

// The arrival end, ignored for a moment after the player is placed beside it.
std::string g_guard_id;
float g_guard_until = -1.0f;
// The last in-map move, so a trigger still touched does not bounce back.
float g_last_move = -1.0f;
// The map and seed this level's orbs were made for. See `RunOrbs`.
std::string g_orbs_key;

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
// How far below an arrival to look for the ground.
constexpr float kArrivalDrop = 4096.0f;
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
// at `toward`). It comes no further than `span` from the player, and
// only somewhere its hull reaches from the player in a straight line: that
// keeps it out of walls, off the player and in the player's room. Failing
// that, spots closer to the player are tried; one that fits nowhere is left
// where it was, or with `remove` removed rather than left in a wall. Each
// is at the player's height, dropped to the
// floor: monsters do not fall, and the offset's height is from the trigger's
// centre.
bool PlaceFollower(CBaseEntity* entity, Vector origin, float dyaw, const Vector& toward,
                   float span = kFollowerSpan, bool remove = false) {
    origin.z = toward.z;
    Vector reach = origin - toward;
    if (reach.Length() > span) {
        origin = toward + reach.Normalize() * span;
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
    bool ducked = (player->pev->flags & FL_DUCKING) != 0;
    int hull = ducked ? head_hull : human_hull;
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
    // A vent: no room to stand, room to crouch. Arrive crouched, as the
    // movement code leaves a player with no room to stand up.
    if (!ducked && !HullFits(player, spot, hull)) {
        const Vector low = spot + Vector(0, 0, VEC_HULL_MIN.z - VEC_DUCK_HULL_MIN.z);
        if (HullFits(player, low, head_hull)) {
            ducked = true;
            hull = head_hull;
            spot = low;
            player->pev->flags |= FL_DUCKING;
            player->pev->view_ofs = VEC_DUCK_VIEW;
            UTIL_SetSize(player->pev, VEC_DUCK_HULL_MIN, VEC_DUCK_HULL_MAX);
            Trace(("  arriving crouched at " + b.id).c_str());
        }
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
    // On the ground, however far below: an arrival in the air (c1a0c's, over
    // the test chamber) would fall out of the player's control and hurt.
    TraceResult tr;
    UTIL_TraceHull(spot, spot - Vector(0, 0, kArrivalDrop), ignore_monsters, hull,
                   player->edict(), &tr);
    if (!tr.fStartSolid && tr.flFraction < 1.0f) {
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

// What crosses a transition with the player: the monsters following the
// player from anywhere in the map, and those walking about within `kCarryPad`
// of the trigger. Not one that cannot walk (a turret, a barnacle, a flier) or
// is playing a script: moved, it would be stuck or break the script.
std::vector<CBaseEntity*> CarriedBy(CBaseEntity* trigger, CBaseEntity* player) {
    std::vector<CBaseEntity*> out;
    const Vector lo = trigger->pev->absmin - Vector(kCarryPad, kCarryPad, kCarryPad);
    const Vector hi = trigger->pev->absmax + Vector(kCarryPad, kCarryPad, kCarryPad);
    for (int i = 1; i < gpGlobals->maxEntities; ++i) {
        edict_t* edict = INDEXENT(i);
        if (edict == nullptr || edict->free || !(edict->v.flags & FL_MONSTER)) {
            continue;
        }
        CBaseEntity* entity = CBaseEntity::Instance(edict);
        if (entity == nullptr || entity == player || entity->IsPlayer() || !entity->IsAlive()) {
            continue;
        }
        if (Follows(entity, player)) {
            out.push_back(entity);
            continue;
        }
        CBaseMonster* monster = entity->MyMonsterPointer();
        if (monster != nullptr && entity->pev->movetype == MOVETYPE_STEP &&
            monster->m_pCine == nullptr && monster->m_MonsterState != MONSTERSTATE_SCRIPT &&
            Overlaps(entity->pev->absmin, entity->pev->absmax, lo, hi)) {
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
                      player->pev->origin,
                      Follows(carried[i], player) ? kFollowerSpan : kCarryPad);
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
            g_seed_maps.clear();
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
    key += "|";
    for (const std::string& chapter : state.transition_chapters) {
        key += chapter + ";";
    }
    key += "|" + state.orbs_raw;
    if (g_seeded && key == g_seed_key && !force) {
        return;
    }
    SetTransitionPairs(state.transition_pairs, state.one_way_transitions);
    g_inert = state.inert_transitions;
    g_seed_maps.clear();
    for (const Chapter& chapter : Data().chapters) {
        if (state.transition_chapters.count(chapter.key)) {
            g_seed_maps.insert(chapter.maps.begin(), chapter.maps.end());
        }
    }
    if (!state.ending_map.empty()) {
        g_seed_maps.insert(state.ending_map);
    }
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

bool OutsideSeed(const Transition& t) {
    if (!g_seeded || g_seed_maps.empty()) {
        return false;
    }
    // On a map the seed has none of, or left unlisted (vanilla) but leading
    // to one: a dead trigger's vanilla way out, say.
    return !g_seed_maps.count(t.map) ||
           (SeedPartner(t.id) == nullptr && !g_seed_maps.count(t.to));
}

bool Inert(const std::string& id) {
    if (g_inert.find(id) != g_inert.end()) {
        return true;
    }
    const Transition* t = Data().TransitionById(id);
    return t != nullptr && OutsideSeed(*t);
}

void RewriteLevelTransitions() {
    if (!Data().Loaded()) {
        return;
    }
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByClassname(entity, "trigger_changelevel")) != nullptr) {
        OnChangeLevelSpawned(entity);
    }
}

// Whether a placed orb's key names `id`: a green arrival can serve several
// transitions, `a+b`.
bool KeyHas(const std::string& key, const std::string& id) {
    size_t start = 0;
    while (start <= key.size()) {
        const size_t end = key.find('+', start);
        const size_t stop = end == std::string::npos ? key.size() : end;
        if (key.compare(start, stop - start, id) == 0 && stop - start == id.size()) {
            return true;
        }
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    return false;
}

const std::string* SeedPartner(const std::string& id) {
    const auto found = g_pairs.find(id);
    return found == g_pairs.end() ? nullptr : &found->second;
}

// Where an orb at `id` leads: back the way a one-way arrival came, or else
// through the seed's pair.
const std::string* OrbPartner(const std::string& id) {
    const auto in = g_one_way_in.find(id);
    if (in != g_one_way_in.end() && !in->second.empty()) {
        return &in->second.front();
    }
    if (const std::string* partner = SeedPartner(id)) {
        return partner;
    }
    // Left vanilla by the seed: its own partner, unless it is dead here.
    const Transition* t = Data().TransitionById(id);
    if (t == nullptr || t->partner.empty() || Inert(id)) {
        return nullptr;
    }
    return &t->partner;
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

// A keyvalue set as a map's own are, through the entity's `KeyValue`.
void SetKey(CBaseEntity* entity, const char* key, const std::string& value) {
    KeyValueData kvd;
    kvd.szClassName = const_cast<char*>(STRING(entity->pev->classname));
    kvd.szKeyName = const_cast<char*>(key);
    kvd.szValue = const_cast<char*>(value.c_str());
    kvd.fHandled = FALSE;
    DispatchKeyValue(entity->edict(), &kvd);
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
    // A backtrack orb elsewhere that returns here arrives by the pair's
    // landmark, which an exit left vanilla would not have.
    for (const auto& orb : State().backtrack_orbs) {
        const Transition* from = Data().TransitionById(orb.first);
        const std::string name = PairLandmark(t->id, orb.first);
        if (orb.second == t->id && from != nullptr && from->map != t->map &&
            !NamedExists("info_landmark", name)) {
            SpawnNamed("info_landmark", name, LandmarkSpot(*t), nullptr);
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
    // What vanilla fires on arriving at `b` (an elevator starting, a door
    // opening), not what this changelevel fired where it used to lead. None
    // is a name nothing has: an empty one is still fired, and matches by it.
    const Transition* inbound = Data().TransitionById(b->partner);
    const bool fires = inbound != nullptr && !inbound->changetarget.empty();
    SetKey(trigger, "changetarget", fires ? inbound->changetarget : "ap_nothing");
    SetKey(trigger, "changedelay", std::to_string(fires ? inbound->changedelay : 0.0f));
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

int DecideTransition(CBaseEntity* trigger);

#ifdef HLAP_TEST_BUILD
// Each changelevel's first firing on a map, and what then stops it: ours, or
// the engine's two refusals (fired twice in a frame, or the player outside the
// landmark's volume), which it reports only in developer mode.
void TraceTouch(CBaseEntity* trigger, int decision) {
    static std::string level;
    static float last = 0.0f;
    static std::set<CBaseEntity*> seen;
    if (level != CurrentMap() || gpGlobals->time < last) {  // a new map, or a load
        seen.clear();
        level = CurrentMap();
    }
    last = gpGlobals->time;
    if (!seen.insert(trigger).second) {
        return;
    }
    const Transition* t = TransitionOfTrigger(trigger);
    const char* landmark = ChangeLevelLandmark(trigger);
    CBaseEntity* player = Player();
    int volumes = 0;
    bool inside = false;
    CBaseEntity* volume = nullptr;
    while ((volume = UTIL_FindEntityByTargetname(volume, landmark)) != nullptr) {
        if (FClassnameIs(volume->pev, "trigger_transition")) {
            ++volumes;
            inside = inside || (player != nullptr && volume->Intersects(player));
        }
    }
    char line[256];
    std::snprintf(line, sizeof(line),
                  "  changelevel %s fired: %s; landmark %s, %d volumes%s, same frame %d",
                  t != nullptr ? t->id.c_str() : "(unknown)",
                  decision == kTransitionSwallowed ? "swallowed"
                  : decision == kTransitionNotOurs ? "vanilla" : "ours",
                  landmark, volumes, volumes == 0 ? "" : inside ? " (player in)" : " (player OUT)",
                  trigger->pev->dmgtime == gpGlobals->time ? 1 : 0);
    Trace(line);
}
#endif

int OnTransition(CBaseEntity* trigger) {
    const int decision = DecideTransition(trigger);
#ifdef HLAP_TEST_BUILD
    TraceTouch(trigger, decision);
#endif
    return decision;
}

int DecideTransition(CBaseEntity* trigger) {
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
    // The engine changes level only with the player in the landmark's volume,
    // which is sized from the changelevel's brush. One fired by name from a
    // trigger elsewhere (c1a2b's way to c1a3, fired from below its brush)
    // would abort, so the volume takes in the player first.
    if (CBasePlayer* player = Player()) {
        CBaseEntity* volume = nullptr;
        while ((volume = UTIL_FindEntityByTargetname(volume, ChangeLevelLandmark(trigger))) !=
               nullptr) {
            if (FClassnameIs(volume->pev, "trigger_transition")) {
                Vector lo = volume->pev->absmin;
                Vector hi = volume->pev->absmax;
                for (int k = 0; k < 3; ++k) {
                    lo[k] = (std::min)(lo[k], player->pev->absmin[k]);
                    hi[k] = (std::max)(hi[k], player->pev->absmax[k]);
                }
                UTIL_SetSize(volume->pev, lo - volume->pev->origin, hi - volume->pev->origin);
            }
        }
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
        // and frees whatever that lands in solid. Each crosses on the landmark,
        // which is open on both sides, and is placed near the player on arrival.
        const bool following = Follows(entity, player);
        g_pending.followers.push_back(
            {STRING(entity->pev->classname), entity->pev->origin - frame, true, following});
        entity->pev->velocity = g_vecZero;
        UTIL_SetOrigin(entity->pev, frame);
        Trace(("  carrying " + std::string(STRING(entity->pev->classname)) +
               (following ? " (following)" : "")).c_str());
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
    g_orbs_key.clear();  // labels again, and the level's own sprites found
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
    if (pending.orb) {
        // At the frame, standing still, facing into the map: the stash's yaw is
        // the way out of the orb's end, which the turn makes the way in here.
        Place(player, *a, *b, g_vecZero, g_vecZero, pending.angles, pending.v_angle, 0.0f);
    } else {
        Place(player, *a, *b, player->pev->origin - frame + pending.shift, pending.velocity,
              pending.angles, pending.v_angle, pending.above);
    }
    // A green arrival placed for this transition is where it puts the player,
    // as it is for an orb sent here: a trigger out of reach, say.
    for (const Snapshot::WorkshopOrb& arrival : State().orbs) {
        if (arrival.departs || arrival.map != b->map || !KeyHas(arrival.key, b->id)) {
            continue;
        }
        Vector spot(arrival.at[0], arrival.at[1], arrival.at[2]);
        Vector found;
        if (!HullFits(player, spot, human_hull) && FindStandSpot(player, spot, found, human_hull)) {
            spot = found;
        }
        UTIL_SetOrigin(player->pev, spot);
        player->pev->velocity = g_vecZero;
        player->pev->angles = player->pev->v_angle = Vector(0, arrival.yaw, 0);
        player->pev->fixangle = 1;
        Trace(("  arrival at the green orb for " + b->id).c_str());
        break;
    }
    // The engine has already translated everything by the frames' difference.
    const float dyaw = (b->yaw + 180.0f) - a->yaw;
    // Each by its translated spot: the nearest of its class not yet placed.
    std::vector<CBaseEntity*> placed;
    for (const Follower& follower : pending.followers) {
        const Vector at = follower.parked ? frame : frame + follower.offset;
        CBaseEntity* list[64];
        const int count = UTIL_EntitiesInBox(list, 64, at - Vector(32, 32, 32),
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
                      dyaw, player->pev->origin,
                      follower.following ? kFollowerSpan : kCarryPad);
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

// Orbs (TRANSITION_RANDO.md 7.2, 7.2a): Lambda Core's teleporter sprites where
// a one-way can only be gone back through by teleport, the orange entrance
// stepped into and the green exit where it puts the player. A teleport that is
// one-way both ways (Xen's) so has both at each end. A backtrack orb by a
// one-way arrival changes level to the exit it came from; a return teleporter
// moves the player within the map, up a lift or drop that will not take them
// back. Spawned in transitions mode once the seed is known, named so a level
// restored from a save keeps its own rather than gaining a second.
namespace {
const char* const kOrbSprite = "sprites/enter1.spr";      // entrance, orange
const char* const kOrbExitSprite = "sprites/exit1.spr";   // exit, green
const char* const kOrbSound = "debris/beamstart7.wav";
const char* const kOrbPrefix = "ap_orb_";
// How near the orb's centre counts as standing in it, across and up.
constexpr float kOrbReach = 32.0f;
constexpr float kOrbReachUp = 48.0f;
// Point label indices, clear of the scenario harness's.
constexpr int kOrbLabelBase = 1000;

struct Orb {
    std::string name;
    Vector at;
    std::string label;
    // A backtrack orb: from the arrival `from`, back to the exit `to`.
    std::string from, to;
    // A teleporter within this map: where it sends the player, and their facing.
    Vector dest;
    float yaw = 0.0f;
    bool has_dest = false;  // `dest` set: a spot rather than an arrival
    // An exit: only marks where an entrance puts the player.
    bool exit = false;
};
std::vector<Orb> g_orbs;
float g_orb_labels_at = -1.0f;
bool g_in_orb = false;

void SpawnOrbSprite(const Orb& orb) {
    if (NamedExists("env_sprite", orb.name)) {
        return;
    }
    edict_t* edict = CREATE_NAMED_ENTITY(MAKE_STRING("env_sprite"));
    if (FNullEnt(edict)) {
        Trace("  could not create an orb sprite");
        return;
    }
    edict->v.origin = orb.at;
    edict->v.targetname = ALLOC_STRING(orb.name.c_str());
    CBaseEntity* sprite = CBaseEntity::Instance(edict);
    // Lambda Core's, as c3a2c sets its teleporters.
    SetKey(sprite, "model", orb.exit ? kOrbExitSprite : kOrbSprite);
    SetKey(sprite, "rendermode", "5");
    SetKey(sprite, "renderamt", "128");
    SetKey(sprite, "renderfx", "2");
    SetKey(sprite, "framerate", "40");
    SetKey(sprite, "spawnflags", "1");  // on: a named sprite starts off
    DispatchSpawn(edict);
    Trace(("  orb " + orb.name + " (" + orb.label + ")").c_str());
}

// Roughly where an arrival at `t` stands: clear of its trigger on the map's
// side, on the floor. For the exit sprite; `Place` decides the real spot.
Vector ArrivalSpot(CBasePlayer* player, const Transition& t) {
    Vector spot = Vec(t.origin) - Vector(0, 0, VEC_HULL_MIN.z - 1.0f);
    if (CBaseEntity* trigger = TriggerOf(t)) {
        for (int step = 0; step < 64 && Overlaps(spot + VEC_HULL_MIN, spot + VEC_HULL_MAX,
                                                 trigger->pev->absmin, trigger->pev->absmax);
             ++step) {
            spot = spot - Normal(t) * 8.0f;
        }
        spot = spot - Normal(t) * 8.0f;
    }
    TraceResult tr;
    UTIL_TraceHull(spot, spot - Vector(0, 0, kArrivalDrop), ignore_monsters, human_hull,
                   player->edict(), &tr);
    return !tr.fStartSolid && tr.flFraction < 1.0f ? tr.vecEndPos : spot;
}

// The orbs this map wants under this seed.
// Names an orb or door opener waits on, once fired on a map: a marker kept in
// the level's save, so a reload or a return to the map still has it.
const char* const kFiredPrefix = "ap_fired_";

bool Fired(const std::string& name) {
    if (name.empty()) {
        return true;
    }
    const std::string marker = kFiredPrefix + name;
    return UTIL_FindEntityByTargetname(nullptr, marker.c_str()) != nullptr;
}

void BuildOrbs(CBasePlayer* player, const std::string& map) {
    g_orbs.clear();
    int n = 0;
    for (const ReturnTeleporter& tp : Data().return_teleporters) {
        ++n;
        if (tp.map != map) {
            continue;
        }
        Orb orb;
        orb.name = kOrbPrefix + map + "_" + std::to_string(n);
        orb.at = Vec(tp.at);
        orb.label = tp.label;
        orb.dest = Vec(tp.to);
        orb.yaw = tp.yaw;
        g_orbs.push_back(orb);
        Orb exit;
        exit.name = std::string(kOrbPrefix) + "x_" + map + "_" + std::to_string(n);
        exit.at = Vec(tp.to);
        exit.exit = true;
        g_orbs.push_back(exit);
    }
    // Orbs placed in testing. An entrance goes where its transition leads
    // in this seed, so the same orb links differently from seed to seed.
    for (const Snapshot::WorkshopOrb& placed : State().orbs) {
        if (placed.map != map || (placed.departs && !Fired(placed.after))) {
            continue;
        }
        Orb orb;
        orb.name = kOrbPrefix + std::string(placed.departs ? "w_" : "wx_") + placed.key;
        orb.at = Vector(placed.at[0], placed.at[1], placed.at[2]);
        if (!placed.departs) {
            orb.exit = true;
            g_orbs.push_back(orb);
            continue;
        }
        orb.label = map;  // a `#` pair stays on this map
        std::string dest_key;
        std::string dest_map = map;
        if (placed.key[0] == '#') {
            dest_key = placed.key;
        } else {
            const std::string* partner = OrbPartner(placed.key);
            const Transition* to = partner != nullptr ? Data().TransitionById(*partner) : nullptr;
            if (to == nullptr) {
                Trace(("  orb at " + placed.key + ": no partner in this seed").c_str());
                continue;
            }
            dest_key = to->id;
            dest_map = to->map;
            orb.label = to->map;
            orb.from = placed.key;
            orb.to = to->id;
        }
        // Within this map, onto the green exit placed for where it leads. To
        // another map it changes level by the pair's landmark, so followers
        // cross, and the arrival puts the player on that map's green exit.
        for (const Snapshot::WorkshopOrb& exit : State().orbs) {
            if (!exit.departs && KeyHas(exit.key, dest_key) && exit.map == dest_map &&
                dest_map == map) {
                orb.dest = Vector(exit.at[0], exit.at[1], exit.at[2]);
                orb.yaw = exit.yaw;
                orb.from.clear();
                orb.has_dest = true;
            }
        }
        // A partner on this same map with no green exit: moved within the map
        // to just inside its trigger, facing in, not a level change into the
        // map already loaded.
        if (!orb.has_dest && placed.key[0] != '#' && dest_map == map) {
            const Transition* to = Data().TransitionById(dest_key);
            orb.dest = ArrivalSpot(player, *to);
            orb.yaw = UTIL_VecToAngles(Normal(*to) * -1.0f).y;
            orb.from.clear();
            orb.has_dest = true;
            Trace(("  orb at " + placed.key + ": partner " + dest_key + " on this map").c_str());
        }
        if (placed.key[0] == '#' && !orb.has_dest) {
            Trace(("  orb " + placed.key + " on " + map + ": no exit placed").c_str());
            continue;
        }
        g_orbs.push_back(orb);
    }
    // Any left from another seed's orbs go.
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByClassname(entity, "env_sprite")) != nullptr) {
        const char* name = STRING(entity->pev->targetname);
        if (std::strncmp(name, kOrbPrefix, std::strlen(kOrbPrefix)) == 0 &&
            std::none_of(g_orbs.begin(), g_orbs.end(),
                         [name](const Orb& orb) { return orb.name == name; })) {
            UTIL_Remove(entity);
        }
    }
    for (const Orb& orb : g_orbs) {
        SpawnOrbSprite(orb);
    }
}

void SendOrbLabels(CBasePlayer* player) {
    for (size_t i = 0; i < g_orbs.size(); ++i) {
        if (g_orbs[i].exit) {
            continue;
        }
        MESSAGE_BEGIN(MSG_ONE, gmsgAPLabel, nullptr, player->pev);
        WRITE_SHORT(-(kOrbLabelBase + static_cast<int>(i)));
        WRITE_COORD(g_orbs[i].at.x);
        WRITE_COORD(g_orbs[i].at.y);
        WRITE_COORD(g_orbs[i].at.z + 24.0f);
        WRITE_STRING(g_orbs[i].label.c_str());
        MESSAGE_END();
    }
}

// Back through the one-way the player arrived by: a level change by the pair's
// landmark, stashed as a transition's is, so followers and the arrival guard
// work alike.
void TravelBack(CBasePlayer* player, const Orb& orb) {
    const Transition* b = Data().TransitionById(orb.from);
    const Transition* a = Data().TransitionById(orb.to);
    if (a == nullptr || b == nullptr) {
        return;
    }
    const std::string landmark = PairLandmark(a->id, b->id);
    if (!NamedExists("info_landmark", landmark)) {
        SpawnNamed("info_landmark", landmark, LandmarkSpot(*b), nullptr);
    }
    const Vector frame = LandmarkOrigin(landmark, *b);
    // What crosses touches the landmark's volume: one from the arrival's
    // trigger, shrunk to the landmark and grown to what is carried.
    CBaseEntity* volume = nullptr;
    while ((volume = UTIL_FindEntityByTargetname(volume, landmark.c_str())) != nullptr &&
           !FClassnameIs(volume->pev, "trigger_transition")) {
    }
    if (volume == nullptr) {
        if (CBaseEntity* trigger = TriggerOf(*b)) {
            SpawnNamed("trigger_transition", landmark, g_vecZero, trigger);
            while ((volume = UTIL_FindEntityByTargetname(volume, landmark.c_str())) != nullptr &&
                   !FClassnameIs(volume->pev, "trigger_transition")) {
            }
        }
    }
    g_pending = Pending();
    g_pending.active = true;
    g_pending.orb = true;
    g_pending.from = b->id;
    g_pending.to = a->id;
    g_pending.map = a->map;
    g_pending.angles = g_pending.v_angle = Vector(0, b->yaw, 0);
    g_pending.shift = frame - Vec(b->origin);
    Vector lo = frame - Vector(16, 16, 16);
    Vector hi = frame + Vector(16, 16, 16);
    CBaseEntity* sprite = UTIL_FindEntityByTargetname(nullptr, orb.name.c_str());
    if (sprite != nullptr) {
        for (CBaseEntity* entity : CarriedBy(sprite, player)) {
            const bool following = Follows(entity, player);
            g_pending.followers.push_back(
                {STRING(entity->pev->classname), entity->pev->origin - frame, true, following});
            entity->pev->velocity = g_vecZero;
            UTIL_SetOrigin(entity->pev, frame);
            for (int k = 0; k < 3; ++k) {
                lo[k] = (std::min)(lo[k], entity->pev->absmin[k]);
                hi[k] = (std::max)(hi[k], entity->pev->absmax[k]);
            }
        }
    }
    for (int k = 0; k < 3; ++k) {
        lo[k] = (std::min)(lo[k], player->pev->absmin[k]);
        hi[k] = (std::max)(hi[k], player->pev->absmax[k]);
    }
    if (volume != nullptr) {
        UTIL_SetOrigin(volume->pev, frame);
        UTIL_SetSize(volume->pev, lo - frame, hi - frame);
    }
    EMIT_SOUND(player->edict(), CHAN_STATIC, kOrbSound, 1, ATTN_NORM);
    Trace(("  backtrack orb " + b->id + " -> " + a->id + " via " + landmark).c_str());
    CHANGE_LEVEL(const_cast<char*>(a->map.c_str()), const_cast<char*>(landmark.c_str()));
}

void TeleportWithin(CBasePlayer* player, const Orb& orb) {
    Vector spot = orb.dest;
    Vector found;
    if (!HullFits(player, spot, human_hull) && FindStandSpot(player, spot, found, human_hull)) {
        spot = found;
    }
    // Followers come too, turned with the player, as a same-map move's do.
    std::vector<CBaseEntity*> carried;
    if (CBaseEntity* sprite = UTIL_FindEntityByTargetname(nullptr, orb.name.c_str())) {
        carried = CarriedBy(sprite, player);
    }
    const float dyaw = orb.yaw - player->pev->angles.y;
    std::vector<Vector> rels;
    for (CBaseEntity* entity : carried) {
        rels.push_back(Rotate(entity->pev->origin - player->pev->origin, dyaw));
    }
    UTIL_SetOrigin(player->pev, spot);
    player->pev->velocity = g_vecZero;
    player->pev->basevelocity = g_vecZero;
    player->pev->angles = player->pev->v_angle = Vector(0, orb.yaw, 0);
    player->pev->fixangle = 1;
    for (size_t i = 0; i < carried.size(); ++i) {
        PlaceFollower(carried[i], spot + rels[i], dyaw, spot,
                      Follows(carried[i], player) ? kFollowerSpan : kCarryPad);
    }
    EMIT_SOUND(player->edict(), CHAN_STATIC, kOrbSound, 1, ATTN_NORM);
    Trace(("  return teleporter " + orb.name).c_str());
}

// Whether this game is a transitions seed, for precaching. On the first map
// after launch the snapshot has not been polled yet, so ap_in.txt is read here.
bool TransitionsSeedForPrecache() {
    if (!State().session.empty()) {
        return TransitionsMode();
    }
    std::FILE* file = std::fopen((StoreDir() + "/ap_in.txt").c_str(), "rb");
    if (file == nullptr) {
        return false;
    }
    bool found = false;
    char line[512];
    while (!found && std::fgets(line, sizeof line, file) != nullptr) {
        found = std::strncmp(line, "progression_mode=transitions", 28) == 0;
    }
    std::fclose(file);
    return found;
}

bool g_orbs_precached = false;
}  // namespace

void PrecacheOrbs() {
    // Every map of a transitions seed: it may put an orb on any of them, and
    // precaching is only open while the level loads. Hub games skip it, since
    // some Opposing Force maps are within two slots of the 511 model cap.
    g_orbs_precached = TransitionsSeedForPrecache();
    if (!g_orbs_precached) {
        return;
    }
    PRECACHE_MODEL(const_cast<char*>(kOrbSprite));
    PRECACHE_MODEL(const_cast<char*>(kOrbExitSprite));
    PRECACHE_SOUND(const_cast<char*>(kOrbSound));
}

void RunOrbs() {
    if (!TransitionsMode() || !g_seeded || !g_orbs_precached) {
        return;  // a seed that arrived after this level loaded: next level
    }
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }
    const std::string map = CurrentMap();
    const std::string key = map + "|" + g_seed_key;
    if (key != g_orbs_key) {
        g_orbs_key = key;
        BuildOrbs(player, map);
        g_orb_labels_at = gpGlobals->time + 1.0f;  // once the client is in
        g_in_orb = true;  // not entered until stepped out of once
    }
    if (g_orb_labels_at >= 0.0f && gpGlobals->time >= g_orb_labels_at) {
        g_orb_labels_at = -1.0f;
        SendOrbLabels(player);
    }
    const Vector at = player->pev->origin;
    const Orb* touched = nullptr;
    for (const Orb& orb : g_orbs) {
        if (!orb.exit && (at - orb.at).Length2D() <= kOrbReach && std::fabs(at.z - orb.at.z) <= kOrbReachUp) {
            touched = &orb;
        }
    }
    const bool entered = touched != nullptr && !g_in_orb;
    g_in_orb = touched != nullptr;
    if (!entered) {
        return;
    }
    if (touched->from.empty() || touched->has_dest) {
        TeleportWithin(player, *touched);
    } else {
        TravelBack(player, *touched);
    }
}

// Door openers (TRANSITION_RANDO.md 3.3): a one-way door is not given a
// teleporter, it is opened for the player from its far side. Each opener fires
// once per approach: coming within reach of a shut door uses it, as its own
// trigger would. From the near side it only opens once the door has been
// opened in play, so it never skips the door's own way of opening it.
namespace {
constexpr float kDoorReach = 64.0f;
const char* const kDoorOpenedPrefix = "ap_door_opened_";
std::set<std::string> g_doors_near;
std::string g_doors_map;

// Whether `point` and the player stand on the same side of the door, across
// its thinner horizontal axis.
bool SameSideOfDoor(const CBaseEntity* door, const Vector& point, const Vector& player) {
    const Vector size = door->pev->absmax - door->pev->absmin;
    const Vector mid = (door->pev->absmin + door->pev->absmax) * 0.5f;
    const int axis = size.x < size.y ? 0 : 1;
    return (point[axis] - mid[axis] >= 0) == (player[axis] - mid[axis] >= 0);
}

// A marker kept in the level's save, so "opened once" survives a reload.
bool DoorOpened(const std::string& model) {
    const std::string name = kDoorOpenedPrefix + model;
    return UTIL_FindEntityByTargetname(nullptr, name.c_str()) != nullptr;
}

void MarkDoorOpened(const CBaseEntity* door, const std::string& model) {
    if (DoorOpened(model)) {
        return;
    }
    CBaseEntity* mark = CBaseEntity::Create("info_target", door->pev->origin, g_vecZero);
    if (mark != nullptr) {
        mark->pev->targetname = ALLOC_STRING((kDoorOpenedPrefix + model).c_str());
    }
}
}  // namespace

void RunDoorOpeners() {
    if (!TransitionsMode() || State().door_openers.empty()) {
        return;
    }
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }
    const std::string map = CurrentMap();
    if (map != g_doors_map) {
        g_doors_map = map;
        g_doors_near.clear();
    }
    const Vector lo = player->pev->absmin - Vector(kDoorReach, kDoorReach, kDoorReach);
    const Vector hi = player->pev->absmax + Vector(kDoorReach, kDoorReach, kDoorReach);
    for (const auto& door : State().door_openers) {
        if (door.first != map) {
            continue;
        }
        // `*N`, `*N,x,y,z` or `*N,x,y,z,after`: the brush model, a spot on its
        // far side, and a name it waits on firing.
        std::vector<std::string> fields;
        std::stringstream parts(door.second);
        for (std::string part; std::getline(parts, part, ',');) {
            fields.push_back(part);
        }
        if (fields.empty()) {
            continue;
        }
        const std::string& key = fields[0];
        const bool sided = fields.size() >= 4;
        if (fields.size() >= 5 && !Fired(fields[4])) {
            continue;  // waits on its map's sequence
        }
        const Vector far_side = sided ? Vector(std::atof(fields[1].c_str()),
                                               std::atof(fields[2].c_str()),
                                               std::atof(fields[3].c_str()))
                                      : g_vecZero;
        CBaseEntity* entity = nullptr;
        while ((entity = UTIL_FindEntityByString(entity, "model", key.c_str())) != nullptr) {
            const char* cls = STRING(entity->pev->classname);
            if (std::strncmp(cls, "func_door", 9) != 0) {
                continue;
            }
            CBaseToggle* toggle = static_cast<CBaseToggle*>(entity);
            if (toggle->m_toggle_state != TS_AT_BOTTOM) {
                MarkDoorOpened(entity, key);
            }
            const bool close = Overlaps(lo, hi, entity->pev->absmin, entity->pev->absmax);
            if (!close) {
                g_doors_near.erase(key);
                continue;
            }
            if (!g_doors_near.insert(key).second) {
                continue;  // still near since the last opening
            }
            if (toggle->m_toggle_state != TS_AT_BOTTOM) {
                Trace(("  door opener " + map + " " + key + ": not shut, left alone").c_str());
                continue;
            }
            if (sided && !SameSideOfDoor(entity, far_side, player->pev->origin) &&
                !DoorOpened(key)) {
                Trace(("  door opener " + map + " " + key +
                       ": near side and never opened, left shut").c_str());
                continue;
            }
            entity->Use(player, player, USE_ON, 0);
            Trace(("  door opener " + map + " " + key).c_str());
        }
    }
}

void OnTransitionTargetFired(const char* targetname) {
    if (targetname == nullptr || !TransitionsMode()) {
        return;
    }
    const std::string name = targetname;
    const std::string map = CurrentMap();
    bool wanted = false;
    for (const Snapshot::WorkshopOrb& orb : State().orbs) {
        wanted = wanted || (orb.map == map && orb.after == name);
    }
    for (const auto& door : State().door_openers) {
        const size_t comma = door.second.rfind(',');
        wanted = wanted || (door.first == map && comma != std::string::npos &&
                            door.second.substr(comma + 1) == name);
    }
    if (!wanted || Fired(name)) {
        return;
    }
    CBaseEntity* mark = CBaseEntity::Create("info_target", g_vecZero, g_vecZero);
    if (mark != nullptr) {
        mark->pev->targetname = ALLOC_STRING((kFiredPrefix + name).c_str());
    }
    g_orbs_key.clear();  // its orbs appear
    Trace(("  fired " + name + " on " + map).c_str());
}

// One-way lips (TRANSITION_RANDO.md 3.3). A one-way crossed back with an item
// warns a player who reaches its lip without one: set back once, with the
// reason, and let through if they go over again. Logic never expects the
// crossing without it; this is the player choosing an older save as the way
// back. The confirmation holds until they wander off or the map changes.
namespace {
constexpr float kLipStillNear = 256.0f;  // past this from the box, warn again

struct LipState {
    std::string map;
    bool warned = false;
};
std::vector<LipState> g_lips;
Vector g_last_clear;
bool g_have_clear = false;

bool Owns(CBasePlayer* player, const std::string& classname) {
    if (classname == "item_longjump") {
        return player->m_fLongJump != FALSE;
    }
    if (classname == "item_suit") {
        return (player->pev->weapons & (1 << WEAPON_SUIT)) != 0;
    }
    return player->HasNamedPlayerItem(classname.c_str()) != FALSE;
}

bool CanCrossBack(CBasePlayer* player, const OneWayLip& lip) {
    for (const std::vector<std::string>& group : lip.needs) {
        bool any = false;
        for (const std::string& classname : group) {
            any = any || Owns(player, classname);
        }
        if (!any) {
            return false;
        }
    }
    return true;
}

// How far `at` is from the box, 0 inside it.
float FromBox(const OneWayLip& lip, const Vector& at) {
    float out = 0.0f;
    for (int i = 0; i < 3; ++i) {
        const float d = (std::max)(lip.mins[i] - at[i], at[i] - lip.maxs[i]);
        out = (std::max)(out, d);
    }
    return (std::max)(out, 0.0f);
}
}  // namespace

void RunOneWayLips() {
    const std::vector<OneWayLip>& lips = Data().one_way_lips;
    if (lips.empty() || !TransitionsMode()) {
        return;
    }
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }
    const std::string map = CurrentMap();
    if (g_lips.size() != lips.size() || (!g_lips.empty() && g_lips[0].map != map)) {
        g_lips.assign(lips.size(), LipState());
        for (LipState& state : g_lips) {
            state.map = map;
        }
        g_have_clear = false;
    }
    const Vector at = player->pev->origin;
    bool inside_any = false;
    for (size_t i = 0; i < lips.size(); ++i) {
        const OneWayLip& lip = lips[i];
        if (lip.map != map) {
            continue;
        }
        const float from = FromBox(lip, at);
        if (from > kLipStillNear) {
            g_lips[i].warned = false;
        }
        if (from > 0.0f) {
            continue;
        }
        inside_any = true;
        if (g_lips[i].warned || CanCrossBack(player, lip) || !g_have_clear) {
            continue;
        }
        g_lips[i].warned = true;
        UTIL_SetOrigin(player->pev, g_last_clear);
        player->pev->velocity = g_vecZero;
        Notify("You can't come back this way without " + lip.names +
               ". Go over again to cross anyway; only an older save would bring you back.");
        Trace(("one-way lip on " + map + ": warned").c_str());
        return;
    }
    if (!inside_any) {
        g_last_clear = at;
        g_have_clear = true;
    }
}

void RegisterTransitionCommands() {
#ifdef HLAP_TEST_BUILD
    g_engfuncs.pfnAddServerCommand((char*)"ap_transition_pair", Cmd_TransitionPair);
#endif
}

}  // namespace ap
