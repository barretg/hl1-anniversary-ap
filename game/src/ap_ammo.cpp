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

#include "ap_checkdata.h"
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

// The map the source list was built from, and the level time last seen.
//
// Both exist because level time is the only clock here and it is not monotonic:
// it restarts near zero with a map and jumps *backwards* whenever a savegame is
// restored, which is a quickload, a death, or a warp. Everything below is a
// deadline in that clock, so a jump back leaves every one of them in a future
// that will not arrive for as long as the jump was -- including the throttle,
// which is how the whole watcher switched itself off for the rest of a map after
// one quickload.
//
// A restore also hands back whatever ammo the save was holding, so the honest
// answer to "time went backwards" is that this map's watch means nothing any
// more. It is thrown away and rebuilt, which is the same rule the rest of the
// game side follows.
std::string g_scanned_map;
float g_last_seen_time = 0.0f;

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
    Trace(("  ammo refilled: " + ammo).c_str());
}

// Are these two maps parts of the same mission?
//
// Which is the question that decides whether a countdown survives a map change.
// Walking through a seam in the middle of Surface Tension does not solve the
// player's problem -- it is the same crossbow and the next map has no bolts
// either -- so the wait carries. Leaving for the hub, or for another mission, is
// a different situation entirely and starts again.
bool SameMission(const std::string& before, const std::string& now) {
    if (before.empty() || before == now) {
        return before == now;
    }
    const Chapter* was = Data().ChapterOfMap(before);
    const Chapter* is = Data().ChapterOfMap(now);
    return was != nullptr && is != nullptr && was->key == is->key;
}

// Rebuild the source list for the map we are standing in.
//
// `keep_timers` carries the countdowns across, re-based onto the new level's
// clock -- which has to be done by hand, because level time restarts near zero
// with every map and an absolute deadline from the last one means nothing here.
// A countdown for ammo the new map *does* stock is dropped rather than carried:
// the problem it was waiting out is over.
void Rebuild(bool keep_timers) {
    const float previous_now = g_last_seen_time;

    g_available.clear();
    g_next_check = 0.0f;
    g_last_seen_time = gpGlobals->time;
    g_scanned_map = std::string(STRING(gpGlobals->mapname));

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

    char line[96];
    std::snprintf(line, sizeof(line), "  ammo sources in %s: %d",
                  g_scanned_map.c_str(), static_cast<int>(g_available.size()));
    Trace(line);

    if (!keep_timers) {
        g_watch.clear();
        return;
    }

    std::map<std::string, Watch> carried;
    for (const std::pair<const std::string, Watch>& entry : g_watch) {
        if (entry.second.due <= 0.0f) {
            continue;  // nothing was owed
        }
        if (g_available.find(entry.first) != g_available.end()) {
            continue;  // this map stocks it; the wait is over
        }
        // What was left of the wait, measured against the clock it was set on,
        // and set again against the one running now. The grace window is not
        // carried: it exists for a save reloaded seconds after a refill, which a
        // map change is not.
        const float remaining = entry.second.due - previous_now;
        Watch fresh;
        fresh.due = gpGlobals->time + (remaining > 0.0f ? remaining : 0.0f);
        carried[entry.first] = fresh;
    }
    g_watch.swap(carried);
    if (!g_watch.empty()) {
        Trace("  ammo countdowns carried across the transition");
    }
}

}  // namespace

void ResetAmmoRelief() {
    // Called on every map load. A transition inside a mission keeps whatever
    // the player was already waiting out; the hub, or another mission, does
    // not -- that is a different situation and it starts again.
    Rebuild(SameMission(g_scanned_map,
                        std::string(STRING(gpGlobals->mapname))));
}

void RunAmmoRelief() {
    // Before the throttle, because the throttle is itself a deadline in the
    // clock this is checking. Level time moves backwards when a savegame is
    // restored, and every deadline held in it -- this throttle included -- then
    // sits in a future that will not arrive for as long as the jump was.
    //
    // Cleared rather than carried, unlike a transition: a restore hands the
    // player back whatever ammo the save was holding, so what the old watch was
    // waiting out may not be true any more. If the gun really is still empty the
    // next second starts a fresh wait and says so.
    if (gpGlobals->time < g_last_seen_time) {
        Trace("ap::RunAmmoRelief: the clock moved back; rebuilding");
        Rebuild(false);
    }
    g_last_seen_time = gpGlobals->time;

    if (gpGlobals->time < g_next_check) {
        return;
    }
    g_next_check = gpGlobals->time + kAmmoReliefCheckSeconds;

    // Belt and braces, and deliberately down here where it costs one string
    // comparison a second rather than one a frame: a map this list was not built
    // from means the source scan belongs to somewhere else entirely.
    if (g_scanned_map != std::string(STRING(gpGlobals->mapname))) {
        Trace("ap::RunAmmoRelief: a map we never scanned; rebuilding");
        ResetAmmoRelief();
    }

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
                Trace(("  ammo watch started: " + ammo).c_str());
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
