#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"

#include "ap_traps.h"

#include <string>
#include <vector>

#include "ap_hub.h"
#include "ap_items.h"
#include "ap_main.h"

namespace ap {
namespace {

struct Queued {
    std::string name;
    float due = 0.0f;
};

std::vector<Queued> g_queued;

// What Butterfingers took, and when to hand it back. One at a time: taking a
// second weapon while the first is out would need a list, and a trap that can
// leave a player empty-handed for a minute stops being a nuisance.
std::string g_owed_weapon;
float g_owed_at = 0.0f;

// Everything a trap can spawn. Fixed, and precached at map load whether or not a
// trap ever arrives.
const char* const kTrapMonsters[] = {"monster_scientist", "monster_headcrab"};

// Somewhere on this bearing a monster can actually stand.
//
// Three traces, each rejecting a different way of arriving somewhere useless:
//
//   Outward, at chest height, using the monster's own hull. This is what keeps
//   them out of walls and in front of them rather than behind: it stops at the
//   first thing that hull cannot pass, so anywhere it reaches is connected to
//   the player by a gap that hull fits through. A spot beyond a wall is never
//   reached in the first place.
//
//   Downward, to find the floor. Without it, a spot chosen at chest height over
//   a staircase or a railing leaves the monster hanging, and a headcrab dropped
//   down a lift shaft is a trap nobody ever meets. Limited to a short fall, so
//   "the floor" means this room rather than the bottom of the map.
//
//   In place, at the resting spot. The belt-and-braces one: a drop can end with
//   the hull overlapping geometry it slid along, and a monster spawned inside
//   the world either sticks or gets pushed through it.
bool FindTrapSpot(CBasePlayer* player, int hull, float half_height,
                  float bearing, float range, Vector& spot) {
    UTIL_MakeVectors(Vector(0.0f, bearing, 0.0f));
    const Vector direction = gpGlobals->v_forward;
    const Vector start = player->pev->origin;

    TraceResult out;
    UTIL_TraceHull(start, start + direction * range, ignore_monsters, hull,
                   player->edict(), &out);

    // The player is inside something, so nothing measured from here means
    // anything. A trace that starts solid reports a fraction of zero, which
    // would otherwise read as "a wall right here".
    if (out.fStartSolid != 0 || out.fAllSolid != 0) {
        return false;
    }

    float reach = range * out.flFraction;
    if (out.flFraction < 1.0f) {
        reach -= kTrapWallMargin;
    }
    // The wall is close enough that anything short of it would be inside the
    // player. Another bearing will do better.
    if (reach < kTrapSpawnMinRadius) {
        return false;
    }

    const Vector centre = start + direction * reach;

    TraceResult drop;
    UTIL_TraceHull(centre, centre - Vector(0.0f, 0.0f, kTrapDropHeight),
                   ignore_monsters, hull, player->edict(), &drop);
    if (drop.fStartSolid != 0 || drop.fAllSolid != 0) {
        return false;
    }
    if (drop.flFraction >= 1.0f) {
        return false;  // a ledge, a pit, or open air
    }

    const Vector rest = drop.vecEndPos;

    TraceResult fit;
    UTIL_TraceHull(rest, rest, ignore_monsters, hull, player->edict(), &fit);
    if (fit.fStartSolid != 0 || fit.fAllSolid != 0) {
        return false;
    }

    // Every trace above works in hull space, where the traced point is the
    // centre of the box. A monster's origin is at its feet, so the same position
    // handed straight to the entity would bury it to the waist.
    spot = rest - Vector(0.0f, 0.0f, half_height - 1.0f);
    return true;
}

bool TooCloseToPlaced(const Vector& spot, const std::vector<Vector>& placed) {
    for (const Vector& other : placed) {
        if ((other - spot).Length() < kTrapMinSeparation) {
            return true;
        }
    }
    return false;
}

CBaseEntity* CreateMonster(const std::string& classname, const Vector& origin,
                           float bearing, int body) {
    // Built by hand rather than with `CBaseEntity::Create`, which spawns the
    // entity before anything can be set on it -- and a scientist picks its head
    // at random during `Spawn` unless one has already been chosen.
    edict_t* pent = CREATE_NAMED_ENTITY(MAKE_STRING(Intern(classname)));
    if (FNullEnt(pent)) {
        return nullptr;
    }

    CBaseEntity* monster = CBaseEntity::Instance(pent);
    if (monster == nullptr) {
        REMOVE_ENTITY(pent);
        return nullptr;
    }

    monster->pev->origin = origin;
    // Facing back down the bearing, so whatever arrives is looking at whoever it
    // arrived for.
    monster->pev->angles = Vector(0.0f, bearing + 180.0f, 0.0f);
    if (body >= 0) {
        monster->pev->body = body;
    }

    DispatchSpawn(pent);
    return monster;
}

bool SpawnOne(CBasePlayer* player, const std::string& classname, int body,
              std::vector<Vector>& placed) {
    int hull = human_hull;
    float half_height = kHumanHullHalf;

    // A headcrab is nothing like a person-shaped hole, and testing one against a
    // human hull turns down crawlspaces and vents it fits through easily.
    if (classname == "monster_headcrab") {
        hull = head_hull;
        half_height = kHeadHullHalf;
    }

    for (int attempt = 0; attempt < kTrapPlaceAttempts; ++attempt) {
        const float bearing = RANDOM_FLOAT(0.0f, 360.0f);
        const float range =
            RANDOM_FLOAT(kTrapSpawnMinRadius, kTrapSpawnMaxRadius);

        Vector spot;
        if (!FindTrapSpot(player, hull, half_height, bearing, range, spot)) {
            continue;
        }
        // Two monsters in one doorway read as a single lump and shove each other
        // through it. Cheaper to roll again than to sort out afterwards.
        if (TooCloseToPlaced(spot, placed)) {
            continue;
        }

        if (CreateMonster(classname, spot, bearing, body) == nullptr) {
            return false;
        }
        placed.push_back(spot);
        return true;
    }

    return false;
}

void SpawnAround(CBasePlayer* player, const std::string& classname, int count) {
    // One of each scientist head, in a random order. Four identical scientists
    // read as a bug; four different ones read as a crowd.
    std::vector<int> heads;
    if (classname == "monster_scientist") {
        for (int i = 0; i < kScientistHeads; ++i) {
            heads.push_back(i);
        }
        for (size_t i = heads.size(); i > 1; --i) {
            const int j = RANDOM_LONG(0, static_cast<int>(i) - 1);
            const int swap = heads[i - 1];
            heads[i - 1] = heads[j];
            heads[j] = swap;
        }
    }

    std::vector<Vector> placed;
    for (int i = 0; i < count; ++i) {
        const int body =
            i < static_cast<int>(heads.size()) ? heads[i] : -1;
        // A failure here is one monster that could not be placed anywhere in ten
        // tries, which in a tight corridor is a fair outcome. The rest still go.
        SpawnOne(player, classname, body, placed);
    }
}

void SpringNow(CBasePlayer* player, const std::string& name) {
    if (name == "Scientist Trap") {
        Notify("Scientists!");
        SpawnAround(player, "monster_scientist", kTrapSpawnCount);
    } else if (name == "Headcrab Trap") {
        Notify("Headcrabs!");
        SpawnAround(player, "monster_headcrab", kTrapSpawnCount);
    } else if (name == "Butterfingers Trap") {
        CBasePlayerItem* held = player->m_pActiveItem;
        if (held == nullptr) {
            return;  // nothing in hand; the trap is a no-op rather than a debt
        }
        const std::string classname(STRING(held->pev->classname));

        // Take it out of the inventory, then throw a fresh copy on the floor in
        // front of the player. `CBasePlayer::DropPlayerItem` cannot be used: it
        // begins `if ( !g_pGameRules->IsMultiplayer() ) return;`, so in
        // single-player it does nothing at all.
        //
        // A dropped weapon can be walked back onto, which is the point -- the
        // trap is meant to be a scramble, not a timed confiscation. Collecting
        // it goes through the same gate as any pickup and passes, because the
        // multiworld did send you this weapon.
        player->RemovePlayerItem(held);
        held->Kill();

        UTIL_MakeVectors(player->pev->v_angle);
        const Vector at = player->pev->origin + gpGlobals->v_forward * 48 +
                          Vector(0, 0, 16);
        // `Intern`, because `Create` stores the pointer rather than the
        // characters -- see the comment on `Intern` in ap_main.h. A dropped
        // weapon whose classname turned to freed heap could not be picked back
        // up, which is the entire trap.
        CBaseEntity* dropped = CBaseEntity::Create(
            (char*)Intern(classname), at, player->pev->angles);
        if (dropped != nullptr) {
            // A gentle toss. Hard enough to land somewhere else, soft enough
            // that it does not go over the railing every time.
            dropped->pev->velocity =
                gpGlobals->v_forward * 180 + Vector(0, 0, 160);
        }

        g_owed_weapon = classname;
        g_owed_at = gpGlobals->time + kButterfingersReturnSeconds;
        Notify("Butterfingers! Pick it back up, or the suit reissues it in "
               "half a minute.");
    }
    // An unknown trap name is a trap from a newer apworld. Nothing happens,
    // which is the right outcome: the alternative is guessing.
}

}  // namespace

void PrecacheTraps() {
    Trace("CWorld::Precache: ap::PrecacheTraps");
    for (const char* classname : kTrapMonsters) {
        // The SDK's own way of precaching an entity we may create later: it
        // spawns one, precaches it and throws it away.
        //
        // This runs from `CWorld::Precache` and not from `ClientPrecache`, which
        // is where it was first hooked and which crashed the engine on every map
        // load. `ClientPrecache` is an assets-only callback -- the SDK's own body
        // is 79 straight PRECACHE_SOUND and PRECACHE_MODEL calls -- and creating
        // an entity there asks the engine for one before it is ready to make any.
        // `CWorld::Precache` is where the SDK does mod-wide setup: it is the
        // worldspawn entity's own precache, so the entity system is up, and it
        // is still inside the window where precaching is legal.
        UTIL_PrecacheOther(classname);
    }
    Trace("  traps precached");

    // Not a trap, but the same window and the only hook we have into it. The
    // SDK patch calls this one function from `CWorld::Precache`; adding a second
    // call site there would mean repatching every SDK checkout for no gain.
    PrecacheCarriedMonsters();
}

void QueueTrap(const std::string& trap_name) {
    Queued queued;
    queued.name = trap_name;
    queued.due = gpGlobals->time + kTrapDelaySeconds;
    g_queued.push_back(queued);
}

void RearmQueuedTraps() {
    // `gpGlobals->time` is level time and starts again near zero on every map,
    // but this queue is in memory and outlives the level -- that is the point of
    // it, since a trap arriving during a load is exactly what it exists to hold.
    // A due time from the previous map is therefore measured against a clock
    // that no longer exists: a trap queued twenty minutes into a mission sat
    // dormant and then sprang twenty minutes into the *hub*, long after the item
    // that caused it, which reads as a trap nobody sent.
    //
    // Re-armed rather than dropped or sprung: the rule is "once things have
    // settled", and a map that has just loaded has not settled.
    for (size_t i = 0; i < g_queued.size(); ++i) {
        g_queued[i].due = gpGlobals->time + kTrapDelaySeconds;
    }
}

void RunTrapTimers() {
    CBasePlayer* player = Player();

    if (!g_queued.empty()) {
        if (player == nullptr || !player->IsAlive()) {
            // Wait. A trap sprung on a corpse or during a load is a trap wasted,
            // and the queue is short.
        } else {
            for (size_t i = 0; i < g_queued.size();) {
                if (gpGlobals->time >= g_queued[i].due) {
                    const std::string name = g_queued[i].name;
                    g_queued.erase(g_queued.begin() + i);
                    SpringNow(player, name);
                } else {
                    ++i;
                }
            }
        }
    }

    if (g_owed_weapon.empty()) {
        return;
    }

    // Found it again. Nothing owed, and no announcement: picking your own
    // weapon up off the floor speaks for itself.
    if (player != nullptr && player->HasNamedPlayerItem(g_owed_weapon.c_str())) {
        g_owed_weapon.clear();
        return;
    }

    if (gpGlobals->time >= g_owed_at) {
        g_owed_weapon.clear();
        if (player != nullptr) {
            // Through the loadout rather than by hand, so the reissue obeys the
            // same gate everything else does.
            ApplyLoadout(player);
            Notify("The suit reissues your weapon.");
        }
    }
}

bool Withheld(const std::string& classname) {
    return !g_owed_weapon.empty() && g_owed_weapon == classname;
}

void ClearWithheld() { g_owed_weapon.clear(); }

}  // namespace ap
