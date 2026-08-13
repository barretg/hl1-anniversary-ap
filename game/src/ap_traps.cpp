#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"

#include "ap_traps.h"

#include <cmath>
#include <string>
#include <vector>

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

void SpawnAround(CBasePlayer* player, const char* classname, int count) {
    UTIL_MakeVectors(player->pev->angles);

    for (int i = 0; i < count; ++i) {
        // Spread around the player rather than on top of them: a monster spawned
        // inside the player is a monster stuck in the player.
        //
        // Not M_PI: it is not in the standard headers on MSVC without a define,
        // and this file is not the place to argue about that.
        const float kTwoPi = 6.2831853f;
        const float angle = (kTwoPi * i) / count;
        Vector offset(std::cos(angle) * 96.0f, std::sin(angle) * 96.0f, 8.0f);
        Vector at = player->pev->origin + offset;

        // Only where there is room. A trap that buries something in a wall is
        // worse than a trap that quietly spawns three instead of four.
        TraceResult tr;
        UTIL_TraceHull(player->pev->origin, at, ignore_monsters, human_hull,
                       player->edict(), &tr);
        if (tr.flFraction < 1.0f) {
            continue;
        }

        // Whatever they do next is theirs to decide: a scientist will follow you
        // if you use one and a headcrab will not wait to be asked.
        CBaseEntity::Create((char*)classname, at, player->pev->angles,
                            player->edict());
    }
}

void SpringNow(CBasePlayer* player, const std::string& name) {
    if (name == "Scientist Trap") {
        Say("Scientists!");
        SpawnAround(player, "monster_scientist", kTrapSpawnCount);
    } else if (name == "Headcrab Trap") {
        Say("Headcrabs!");
        SpawnAround(player, "monster_headcrab", kTrapSpawnCount);
    } else if (name == "Butterfingers Trap") {
        CBasePlayerItem* held = player->m_pActiveItem;
        if (held == nullptr) {
            return;  // nothing in hand; the trap is a no-op rather than a debt
        }
        g_owed_weapon = STRING(held->pev->classname);
        g_owed_at = gpGlobals->time + kButterfingersReturnSeconds;
        player->RemovePlayerItem(held);
        held->Kill();
        Say("Butterfingers. The suit will reissue it shortly.");
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
}

void QueueTrap(const std::string& trap_name) {
    Queued queued;
    queued.name = trap_name;
    queued.due = gpGlobals->time + kTrapDelaySeconds;
    g_queued.push_back(queued);
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

    if (!g_owed_weapon.empty() && gpGlobals->time >= g_owed_at) {
        g_owed_weapon.clear();
        if (player != nullptr) {
            // Through the loadout rather than by hand, so the reissue obeys the
            // same gate everything else does.
            ApplyLoadout(player);
        }
    }
}

}  // namespace ap
