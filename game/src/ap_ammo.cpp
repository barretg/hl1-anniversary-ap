#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"

#include "ap_ammo.h"

#include <cstdio>
#include <map>
#include <set>
#include <string>

#include "ap_items.h"
#include "ap_main.h"
#include "ap_state.h"

namespace ap {
namespace {

// What each thing lying in a map can put in the player's pockets.
//
// Written down rather than derived, because the question is asked of an entity
// that has not been touched: an ammo box knows what it gives only inside its own
// `AddAmmo`, which runs when a player walks into it. Every classname here comes
// straight from the SDK's `LINK_ENTITY_TO_CLASS` lines and the `pszAmmo1`
// strings beside them, so the two lists cannot drift without an SDK change.
struct AmmoSource {
    const char* classname;
    const char* ammo;
};

const AmmoSource kAmmoSources[] = {
    // Boxes and clips.
    {"ammo_glockclip", "9mm"},
    {"ammo_9mmclip", "9mm"},
    {"ammo_mp5clip", "9mm"},
    {"ammo_9mmAR", "9mm"},
    {"ammo_9mmbox", "9mm"},
    {"ammo_357", "357"},
    {"ammo_buckshot", "buckshot"},
    {"ammo_crossbow", "bolts"},
    {"ammo_rpgclip", "rockets"},
    {"ammo_gaussclip", "uranium"},
    {"ammo_egonclip", "uranium"},
    {"ammo_mp5grenades", "ARgrenades"},
    {"ammo_ARgrenades", "ARgrenades"},

    // A weapon lying in the world comes with ammo, and for the throwables the
    // weapon *is* the ammo.
    {"weapon_9mmhandgun", "9mm"},
    {"weapon_glock", "9mm"},
    {"weapon_9mmAR", "9mm"},
    {"weapon_mp5", "9mm"},
    {"weapon_357", "357"},
    {"weapon_python", "357"},
    {"weapon_shotgun", "buckshot"},
    {"weapon_crossbow", "bolts"},
    {"weapon_rpg", "rockets"},
    {"weapon_gauss", "uranium"},
    {"weapon_egon", "uranium"},
    {"weapon_handgrenade", "Hand Grenade"},
    {"weapon_satchel", "Satchel Charge"},
    {"weapon_tripmine", "Trip Mine"},
    {"weapon_snark", "Snarks"},

    // What the marines are carrying. Killing one leaves the gun and its ammo on
    // the floor, which is a supply the entity list would otherwise not show --
    // and a map full of grunts is exactly where "this level has no 9mm" would
    // read as a bug.
    {"monster_human_grunt", "9mm"},
    {"monster_human_grunt", "buckshot"},
    {"monster_human_grunt", "ARgrenades"},
};

// The one ammo type nothing has to supply: the hivehand grows its own.
const char* const kSelfFeedingAmmo = "Hornets";

// What this level can hand out, filled once per map load.
std::set<std::string> g_available;

// A gun of this ammo type has been dry since `due` was set.
struct Watch {
    float due = 0.0f;           // when the refill is owed; 0 while not waiting
    float grace_until = 0.0f;   // a second refill is free until here
};

std::map<std::string, Watch> g_watch;

float g_next_check = 0.0f;

// How much a refill hands over: two clips where the weapon has one, and a small
// handful where it does not -- five rockets is the RPG's whole carry limit, so
// the clipless weapons are counted rather than measured.
constexpr int kClipsPerRefill = 2;
constexpr int kCliplessRefill = 5;

std::string AmmoOf(CBasePlayerItem* item) {
    const char* ammo = item->pszAmmo1();
    return ammo == nullptr ? std::string() : std::string(ammo);
}

int Carried(CBasePlayer* player, CBasePlayerItem* item) {
    const int index = item->PrimaryAmmoIndex();
    if (index < 0) {
        return -1;  // a crowbar: nothing to run out of
    }
    int total = player->m_rgAmmo[index];

    // The clip counts. A shotgun with four shells in it and nothing in reserve
    // is not a gun that needs rescuing, and announcing one would be noise every
    // time a player finished a fight.
    CBasePlayerItem* weapon = item->GetWeaponPtr();
    if (weapon != nullptr) {
        const int clip = ((CBasePlayerWeapon*)weapon)->m_iClip;
        if (clip > 0) {
            total += clip;
        }
    }
    return total;
}

void Refill(CBasePlayer* player, CBasePlayerItem* item, const std::string& ammo) {
    const int clip = item->iMaxClip();
    const int amount = clip > 0 ? clip * kClipsPerRefill : kCliplessRefill;
    player->GiveAmmo(amount, (char*)ammo.c_str(), item->iMaxAmmo1());

    const char* name = item->pszName();
    Notify(std::string("The suit synthesises ammunition for your ") +
           (name != nullptr ? name : ammo.c_str()) + ".");
}

}  // namespace

void ResetAmmoRelief() {
    // Rebuilt, never carried: the timers below are level time, which restarts
    // with the map, and what the level stocks is a different answer in every
    // map. This is the same rule the rest of the game side follows.
    g_available.clear();
    g_watch.clear();
    g_next_check = 0.0f;

    // One pass over the entity list, at map load, and never again. The
    // alternative -- asking during the check -- is a search of every entity in
    // the level once a second for as long as a gun is dry.
    for (int index = 1; index < gpGlobals->maxEntities; ++index) {
        edict_t* edict = INDEXENT(index);
        if (edict == nullptr || edict->free) {
            continue;
        }
        const char* classname = STRING(edict->v.classname);
        if (classname == nullptr || classname[0] == '\0') {
            continue;
        }
        for (const AmmoSource& source : kAmmoSources) {
            if (std::string(classname) == source.classname) {
                g_available.insert(source.ammo);
            }
        }
    }
}

void RunAmmoRelief() {
    if (gpGlobals->time < g_next_check) {
        return;
    }
    g_next_check = gpGlobals->time + kAmmoReliefCheckSeconds;

    // Off unless the seed asked for it, and the seed says so in the snapshot --
    // never from a cached flag of our own. A client that has not connected yet
    // has the option off, which is the safe way round: nothing is granted.
    if (!State().ammo_relief) {
        if (!g_watch.empty()) {
            g_watch.clear();
        }
        return;
    }
    if (!Live()) {
        return;
    }

    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }
    // Handing ammo over writes a user message, so it waits on the same thing
    // the loadout waits on. See `ClientReady`.
    if (!ClientReady()) {
        return;
    }

    for (int slot = 0; slot < MAX_ITEM_TYPES; ++slot) {
        for (CBasePlayerItem* item = player->m_rgpPlayerItems[slot];
             item != nullptr; item = item->m_pNext) {
            const std::string ammo = AmmoOf(item);
            if (ammo.empty() || ammo == kSelfFeedingAmmo) {
                continue;
            }
            // The level stocks it. Finding it is the game's problem, which is
            // what this option is deliberately not about.
            if (g_available.find(ammo) != g_available.end()) {
                continue;
            }

            const int carried = Carried(player, item);
            if (carried < 0) {
                continue;
            }

            Watch& watch = g_watch[ammo];
            if (carried > 0) {
                // Ammo again, from a body or from the multiworld. The countdown
                // is not paused, it is over: the next time this runs dry starts
                // a fresh one.
                watch.due = 0.0f;
                continue;
            }

            // Empty again inside the grace window. This is the case the window
            // exists for: the refill arrived, the player died to whatever
            // emptied the gun, and the save they reloaded is from before it.
            if (watch.grace_until > gpGlobals->time) {
                watch.grace_until = 0.0f;
                watch.due = 0.0f;
                Refill(player, item, ammo);
                watch.grace_until = gpGlobals->time + kAmmoReliefGraceSeconds;
                continue;
            }

            if (watch.due <= 0.0f) {
                watch.due = gpGlobals->time + kAmmoReliefDelaySeconds;
                const char* name = item->pszName();
                char line[128];
                std::snprintf(line, sizeof(line),
                              "Your %s is empty and this level carries no %s. "
                              "The suit will synthesise more in %d minutes.",
                              name != nullptr ? name : ammo.c_str(), ammo.c_str(),
                              static_cast<int>(kAmmoReliefDelaySeconds / 60.0f));
                Notify(line);
                continue;
            }

            if (gpGlobals->time >= watch.due) {
                watch.due = 0.0f;
                Refill(player, item, ammo);
                watch.grace_until = gpGlobals->time + kAmmoReliefGraceSeconds;
            }
        }
    }
}

}  // namespace ap
