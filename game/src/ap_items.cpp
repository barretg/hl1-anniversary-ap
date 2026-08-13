#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"

#include "ap_items.h"

#include <string>
#include <vector>

#include "ap_checkdata.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_traps.h"

namespace ap {
namespace {

// True while we are handing something over ourselves. `GiveNamedItem` spawns the
// entity and touches the player with it, so it goes through the very gate we are
// about to apply -- without this, granting a weapon would be refused by the rule
// that exists to refuse the map's copy of it.
bool g_granting = false;

// A spawn asked for the loadout and StartFrame has not applied it yet.
bool g_loadout_wanted = false;

const char* const kSuitItem = "HEV Suit";

struct Granting {
    Granting() { g_granting = true; }
    ~Granting() { g_granting = false; }
};

void Give(CBasePlayer* player, const std::string& classname) {
    if (player->HasNamedPlayerItem(classname.c_str())) {
        return;
    }
    // Butterfingers threw this one on the floor and it is not owed back yet.
    // Without this the loadout would return it on the next snapshot change,
    // which is any check the player sends -- seconds, usually.
    if (Withheld(classname)) {
        return;
    }

    {
        Granting guard;
        player->GiveNamedItem(classname.c_str());
    }

    // `GiveNamedItem` cannot report failure, and a half-added weapon is not
    // obvious from the outside: `CBasePlayerWeapon::AddToPlayer` sets the HUD's
    // weapon bit before `AddPlayerItem` decides whether to keep the item, so a
    // failed grant looks like a weapon that is visible, unselectable, and gone
    // again once the HUD catches up. Worse, the next loadout pass would see no
    // item, grant again, and spawn another entity for the same weapon.
    if (!player->HasNamedPlayerItem(classname.c_str())) {
        Trace(("  grant failed: " + classname).c_str());
    }
}

bool IsStartingWeapon(const std::string& classname) {
    const Snapshot& state = State();
    // The seed's list wins; the file's `S` records are the default rather than
    // the truth. An empty list means the client has nothing to say, never
    // "start with nothing".
    const std::vector<std::string>& list = state.starting_weapons.empty()
                                               ? Data().starting_weapons
                                               : state.starting_weapons;
    for (const std::string& name : list) {
        if (name == classname) {
            return true;
        }
    }
    return false;
}

}  // namespace

bool ArmourAllowed() {
    if (!Gated()) {
        return true;  // no checkdata: this is ordinary Half-Life
    }
    return State().Has(kSuitItem);
}

void ClampArmour() {
    if (ArmourAllowed()) {
        return;
    }
    CBasePlayer* player = Player();
    if (player != nullptr && player->pev->armorvalue > 0) {
        player->pev->armorvalue = 0;
    }
}

bool CanCollect(CBasePlayer* player, const std::string& classname) {
    if (g_granting) {
        return true;
    }
    if (!Gated()) {
        return true;  // no checkdata: this is ordinary Half-Life
    }
    if (IsStartingWeapon(classname)) {
        return true;
    }
    if (State().Ungated(classname)) {
        // The seed does not shuffle this one, so the game keeps its own
        // schedule for it. Not the same as calling it owned, which would have
        // granted it from the first spawn of the run.
        return true;
    }

    const std::string item = Data().ItemGating(classname);
    if (item.empty()) {
        return true;  // ammo, health, a battery: never gated
    }
    return State().Has(item);
}

bool CanCollect(CBasePlayer* player, CBaseEntity* pickup) {
    if (pickup == nullptr) {
        return true;
    }
    const std::string classname(STRING(pickup->pev->classname));

    // Walking up to a weapon is the check whether or not the multiworld has sent
    // it. Refusing it and never reporting it is how a location becomes
    // unsendable.
    //
    // Unless we are the ones handing it over: `GiveNamedItem` spawns an entity
    // and touches the player with it, so a granted weapon arrives through this
    // same path. Counting that as finding one would fire a weapon's check the
    // moment the multiworld sent it, in whatever map the player happened to be.
    if (!g_granting) {
        OnWeaponCollected(player, classname);
    }

    const bool allowed = CanCollect(player, classname);
    if (!allowed) {
        // Said once per pickup rather than on every touch: the entity stays
        // where it is, so the player walks over it repeatedly.
        static float last_said = 0.0f;
        if (gpGlobals->time - last_said > 3.0f) {
            last_said = gpGlobals->time;
            const std::string item = Data().ItemGating(classname);
            Notify(item.empty()
                       ? std::string("You cannot take that yet.")
                       : std::string("You need the ") + item +
                             " from the multiworld before you can take that.");
        }
    }
    return allowed;
}

void RequestLoadout() {
    static bool first = true;
    if (first) {
        first = false;
        Trace("CBasePlayer::Spawn: ap::RequestLoadout");
    }
    g_loadout_wanted = true;
}

void RunLoadout() {
    if (!g_loadout_wanted) {
        return;
    }
    CBasePlayer* player = Player();
    // Wait for a player who can actually be sent a message. On the frame after
    // a respawn there may not be one yet, and the whole point of deferring is
    // not to write to the client before it can hear us.
    if (player == nullptr || (player->pev->flags & FL_CLIENT) == 0) {
        return;
    }
    g_loadout_wanted = false;
    ApplyLoadout(player);
}

void ApplyLoadout(CBasePlayer* player) {
    if (player == nullptr || !Data().Loaded()) {
        return;
    }

    // The suit first and always, whatever the seed says about armour. In GoldSrc
    // it draws the weapon HUD and owns weapon switching, so a player without one
    // cannot use what they are holding.
    player->pev->weapons |= (1 << WEAPON_SUIT);

    const Snapshot& state = State();

    const std::vector<std::string>& starting =
        state.starting_weapons.empty() ? Data().starting_weapons
                                       : state.starting_weapons;
    for (const std::string& classname : starting) {
        Give(player, classname);
    }

    // Everything the multiworld has sent. Idempotent: `Give` skips what the
    // player already holds, so this runs on every spawn and every snapshot
    // change without piling up duplicates.
    for (const std::string& item : state.held_items) {
        if (item == kSuitItem) {
            continue;  // the suit is not a classname to hand over; see above
        }
        for (const std::string& classname : Data().ClassnamesFor(item)) {
            // Both spellings of a weapon unlock together, and retail's maps use
            // both, but the player only needs one of them in hand.
            if (player->HasNamedPlayerItem(classname.c_str())) {
                break;
            }
            Give(player, classname);
        }
    }

    ClampArmour();
}

void GrantFiller(CBasePlayer* player, const std::string& item_name) {
    if (player == nullptr) {
        return;
    }

    if (item_name == "Medkit" || item_name == "Health Charge") {
        const float amount = item_name == "Medkit" ? 25.0f : 15.0f;
        player->TakeHealth(amount, DMG_GENERIC);
    } else if (item_name == "Armor Battery") {
        if (ArmourAllowed()) {
            float armour = player->pev->armorvalue + 15.0f;
            player->pev->armorvalue = armour > MAX_NORMAL_BATTERY
                                          ? static_cast<float>(MAX_NORMAL_BATTERY)
                                          : armour;
        }
    } else if (item_name == "Ammo Cache") {
        // Ammo for what the player is actually holding, rather than a fixed
        // type: a cache of 9mm means nothing to someone carrying a crossbow.
        CBasePlayerItem* held = player->m_pActiveItem;
        if (held != nullptr && held->pszAmmo1() != nullptr) {
            player->GiveAmmo(held->iMaxAmmo1() / 2, (char*)held->pszAmmo1(),
                             held->iMaxAmmo1());
        }
    }

    Notify(std::string("Received: ") + item_name);
}

}  // namespace ap
