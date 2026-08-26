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
const char* const kLongJumpItem = "Long Jump Module";

// Equipment is applied to the player directly, never by spawning its pickup.
//
// `GiveNamedItem` works by creating the entity and touching the player with it,
// and `CItem::ItemTouch` only removes that entity when `MyTouch` returns true --
// which for both of these means "you did not already have it". The second grant
// onwards therefore leaves a real, uncollectable pickup lying on the floor, and
// since neither is a weapon, `HasNamedPlayerItem` cannot see them to stop it:
// one more every time the loadout runs, which is every check the player sends.
//
// True when this actually changed something, for the caller's "did anything
// happen" flag.
bool GrantLongJump(CBasePlayer* player) {
    if (player->m_fLongJump) {
        return false;
    }
    player->m_fLongJump = TRUE;
    // The client's movement code reads this, not the flag above: without it the
    // player has a long jump module that does not long jump.
    g_engfuncs.pfnSetPhysicsKeyValue(player->edict(), "slj", "1");
    return true;
}

struct Granting {
    Granting() { g_granting = true; }
    ~Granting() { g_granting = false; }
};

// What the player is actually holding, by the name the inventory knows it under,
// with its ammo. Written to ap_boot.txt.
//
// This exists because "the weapon is in my inventory but I cannot select it" has
// two completely different causes and they cannot be told apart from outside.
// Selecting a weapon in the HUD sends the name the *engine* registered for it
// -- `weapon_9mmhandgun`, whatever the map or the grant called it -- and
// `CBasePlayer::SelectItem` matches that against the classname of the instance
// being carried. A mismatch there is silent. `lastinv` works either way, because
// it follows a pointer and never looks at a name.
//
// So: the name we granted, the name in the inventory, and the ammo, all in one
// line. Whichever of them is wrong, the line says so.
void TraceInventory(CBasePlayer* player, const char* when) {
    if (!kTraceLoad || player == nullptr) {
        return;
    }

    std::string line = std::string("  inventory ") + when + ":";
    for (int slot = 0; slot < MAX_ITEM_TYPES; ++slot) {
        for (CBasePlayerItem* item = player->m_rgpPlayerItems[slot];
             item != nullptr; item = item->m_pNext) {
            line += " ";
            line += STRING(item->pev->classname);

            const int ammo_type = item->PrimaryAmmoIndex();
            if (ammo_type >= 0 && ammo_type < MAX_AMMO_SLOTS) {
                char count[24];
                std::snprintf(count, sizeof(count), "(ammo %d)",
                              player->m_rgAmmo[ammo_type]);
                line += count;
            }
        }
    }

    if (player->m_pActiveItem != nullptr) {
        line += " | active ";
        line += STRING(player->m_pActiveItem->pev->classname);
    }
    Trace(line.c_str());
}

// How much ammo a granted weapon arrives with, as a share of what the player is
// allowed to carry of it.
//
// `GiveNamedItem` hands over the weapon's `m_iDefaultAmmo`, which is what the
// pickup lying in a level would have given -- and that number assumes the level
// around it is stocked with more of the same. Received from the multiworld it is
// not: the RPG arrives with a single rocket, and Nihilanth is not a one-rocket
// fight.
//
// Half the carry limit, rounded up. Enough to use the weapon it came with,
// short of the cap the game itself sets, and still finite: three rockets, 125
// rounds of 9mm, five grenades. Applied when the weapon is granted, which is
// once per mission entry, since a warp reloads the map and the loadout is
// reapplied from scratch.
constexpr float kGrantedAmmoShare = 0.5f;

CBasePlayerItem* FindItem(CBasePlayer* player, const std::string& classname) {
    for (int slot = 0; slot < MAX_ITEM_TYPES; ++slot) {
        for (CBasePlayerItem* item = player->m_rgpPlayerItems[slot];
             item != nullptr; item = item->m_pNext) {
            if (classname == STRING(item->pev->classname)) {
                return item;
            }
        }
    }
    return nullptr;
}

// Top a just-granted weapon up to `kGrantedAmmoShare` of its carry limit.
// Only ever called on a real grant: doing it whenever the loadout runs would be
// an ammo tap that refills on every check the player sends.
void StockAmmo(CBasePlayer* player, const std::string& classname) {
    CBasePlayerItem* item = FindItem(player, classname);
    if (item == nullptr || item->pszAmmo1() == nullptr) {
        return;  // the crowbar, and anything else that does not take ammo
    }

    const int limit = item->iMaxAmmo1();
    if (limit <= 0) {
        return;
    }

    int wanted = static_cast<int>(limit * kGrantedAmmoShare + 0.5f);
    if (wanted < 1) {
        wanted = 1;
    }

    const int index = player->GetAmmoIndex(item->pszAmmo1());
    const int held = (index >= 0 && index < MAX_AMMO_SLOTS)
                         ? player->m_rgAmmo[index]
                         : 0;
    if (held >= wanted) {
        return;  // already carrying more than the grant would have given
    }

    player->GiveAmmo(wanted - held, (char*)item->pszAmmo1(), limit);
}

// True when something was actually handed over, so the caller knows whether the
// client needs telling about it.
bool Give(CBasePlayer* player, const std::string& classname) {
    // Weapons only. `item_suit` and `item_longjump` have their own handling in
    // `ApplyLoadout`, because spawning their pickups leaves uncollectable ones
    // on the floor; anything else beginning `item_` would do the same, so a data
    // change that adds one says so in the trace rather than littering the map.
    if (classname.rfind("item_", 0) == 0) {
        Trace(("  refused to spawn a pickup for " + classname).c_str());
        return false;
    }

    if (player->HasNamedPlayerItem(classname.c_str())) {
        return false;
    }
    // Butterfingers threw this one on the floor and it is not owed back yet.
    // Without this the loadout would return it on the next snapshot change,
    // which is any check the player sends -- seconds, usually.
    if (Withheld(classname)) {
        return false;
    }

    {
        Granting guard;
        // `Intern`, never `classname.c_str()`: the entity keeps the pointer, not
        // the characters. See the comment on `Intern` in ap_main.h.
        player->GiveNamedItem(Intern(classname));
    }

    // `GiveNamedItem` cannot report failure, and a half-added weapon is not
    // obvious from the outside: `CBasePlayerWeapon::AddToPlayer` sets the HUD's
    // weapon bit before `AddPlayerItem` decides whether to keep the item, so a
    // failed grant looks like a weapon that is visible, unselectable, and gone
    // again once the HUD catches up. Worse, the next loadout pass would see no
    // item, grant again, and spawn another entity for the same weapon.
    if (!player->HasNamedPlayerItem(classname.c_str())) {
        Trace(("  grant failed: " + classname).c_str());
        return false;
    }

    StockAmmo(player, classname);

    Trace(("  granted " + classname).c_str());
    TraceInventory(player, "after grant");
    return true;
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

void EnforceSuit() {
    if (!Data().Loaded()) {
        return;  // ordinary Half-Life: the suit is the game's to give
    }
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }
    if ((player->pev->weapons & (1 << WEAPON_SUIT)) != 0) {
        return;
    }

    // Every frame, not only on a spawn and a snapshot change.
    //
    // "Granted, never removed" is the rule, and in GoldSrc the bit does more
    // than mark the suit as owned: it draws the HUD. A player without it has no
    // health, no ammo and no message area, which reads as the game having gone
    // quiet -- commands still run and checks still send, and none of it can be
    // seen.
    //
    // It is cleared deliberately for exactly one call, in `CanCollect`, so that
    // `CItemSuit::MyTouch` performs the real pickup and fires the map logic that
    // hangs off it. That clear and the MyTouch that undoes it are both inside
    // one synchronous touch, so this never lands between them. What this covers
    // is the case where MyTouch does *not* run -- anything that asks
    // `CanHaveItem` about an `item_suit` without going on to collect it -- which
    // otherwise left the bit clear for the rest of the run. That is what
    // happened after the suit was picked up in Anomalous Materials.
    Trace("  suit bit was missing; restored");
    player->pev->weapons |= (1 << WEAPON_SUIT);
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

    // The HEV suit is never refused, and it is made to complete for real.
    //
    // Two things go wrong otherwise and between them they seal Anomalous
    // Materials shut. The suit bit is set on every spawn, because in GoldSrc it
    // is what draws the weapon HUD -- so `CItemSuit::MyTouch` sees a player who
    // already has one, returns FALSE, and `CItem::ItemTouch` never reaches
    // `SUB_UseTargets`. In `c1a0d` that target is the `hevmaster1` multisource,
    // and the `trigger_once` that sends Barney to open the airlock into the test
    // chamber is mastered on it. No pickup, no multisource, no airlock. That
    // happens in every seed, whether or not the item has arrived.
    //
    // Refusing the touch while the `HEV Suit` item is still out there does the
    // same damage one step earlier, so the pickup always goes through. What the
    // item gates is armour, which `ArmourAllowed` clamps every frame; it was
    // never meant to gate the suit itself, which the player cannot play without.
    //
    // Clearing the bit is what lets the game's own code do the work: MyTouch
    // then plays the HEV logon, sets the bit back and returns TRUE, so the
    // targets fire and the entity is removed exactly as in an unmodified game.
    // It is restored inside the same touch, and `ApplyLoadout` would put it back
    // on the next poll in any case.
    if (player != nullptr && classname == "item_suit") {
        player->pev->weapons &= ~(1 << WEAPON_SUIT);
        return true;
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
    if (player == nullptr) {
        return;
    }
    // Cleared before the call, not after: `ApplyLoadout` sets it again itself if
    // the client is not ready yet, and clearing afterwards would throw that away
    // and lose the loadout entirely.
    g_loadout_wanted = false;
    ApplyLoadout(player);
}

void ApplyLoadout(CBasePlayer* player) {
    if (player == nullptr || !Data().Loaded()) {
        return;
    }

    // Nothing below may run before the client can take a user message, and two
    // things here write one. Granting is not the quiet inventory change it looks
    // like: `CBasePlayerWeapon::AddToPlayer` writes `WeapPickup`, and the
    // `ForceClientDllUpdate` at the end writes `ResetHUD` through
    // `UpdateClientData`. This runs from `CBasePlayer::Spawn`, which on a
    // quickload is several frames before either is safe, and writing then is
    // `SZ_GetSpace: Tried to write to an uninitialized sizebuf_t` and a dead
    // engine.
    //
    // Asked for again rather than skipped, so the loadout lands on the first
    // frame it is safe to land on. `FL_CLIENT` is not enough to decide this: it
    // is set while the engine is still restoring the player. See `ClientReady`.
    if (!ClientReady()) {
        g_loadout_wanted = true;
        return;
    }

    // Nothing can be handed to a corpse. `GiveNamedItem` still builds the entity
    // and touches the player with it, `AddPlayerItem` refuses, and the loadout
    // logs a grant failure for every weapon in the list -- which is what filled
    // the boot trace with `grant failed` while the player was dead in
    // Questionable Ethics. Asked for again, and the respawn asks too.
    if (!player->IsAlive()) {
        g_loadout_wanted = true;
        return;
    }

    // The suit first and always, whatever the seed says about armour. In GoldSrc
    // it draws the weapon HUD and owns weapon switching, so a player without one
    // cannot use what they are holding.
    player->pev->weapons |= (1 << WEAPON_SUIT);

    const Snapshot& state = State();

    bool gave_something = false;

    const std::vector<std::string>& starting =
        state.starting_weapons.empty() ? Data().starting_weapons
                                       : state.starting_weapons;
    for (const std::string& classname : starting) {
        gave_something |= Give(player, classname);
    }

    // Everything the multiworld has sent. This runs on every spawn and every
    // snapshot change, so it has to be exactly idempotent.
    for (const std::string& item : state.held_items) {
        // Equipment, applied directly. Neither spawns a pickup: see the note on
        // `GrantLongJump`.
        if (item == kSuitItem) {
            continue;  // the suit bit is set above; this item only frees armour
        }
        if (item == kLongJumpItem) {
            gave_something |= GrantLongJump(player);
            continue;
        }

        const std::vector<std::string> classnames = Data().ClassnamesFor(item);
        if (classnames.empty()) {
            continue;
        }

        // Held under *any* of its names counts as held, and the whole list has
        // to be checked before granting any of it.
        //
        // Retail ships several weapons under two classnames -- `weapon_mp5` and
        // `weapon_9mmAR`, `weapon_glock` and `weapon_9mmhandgun`, `weapon_357`
        // and `weapon_python` -- and its maps place both. Checking them in order
        // and granting the first one not held meant that picking a `weapon_9mmAR`
        // off the floor earned a granted `weapon_mp5` on top of it. The SDK
        // recognises a duplicate by classname, so it does not see those as the
        // same gun: it adds a second one and `AddWeapon` pays out another full
        // load of ammo, on every snapshot change, forever.
        bool already_held = false;
        for (const std::string& classname : classnames) {
            if (player->HasNamedPlayerItem(classname.c_str())) {
                already_held = true;
                break;
            }
        }
        if (already_held) {
            continue;
        }

        gave_something |= Give(player, classnames.front());
    }

    // Tell the client what it now has: forget everything the client is believed
    // to know and send it again, which is what the `fullupdate` console command
    // does. Only after a real grant, since it costs a HUD reset.
    //
    if (gave_something) {
        // The ammo has to be invalidated by hand first, and this is not
        // optional. `ForceClientDllUpdate` sets `m_fInitHUD`, which sends
        // `ResetHUD`, and that wipes the ammo counts the client is holding --
        // but `SendAmmoUpdate` only sends a type whose count has *changed*
        // since it last sent one. `m_rgAmmoLast` still agrees with `m_rgAmmo`,
        // so it sends nothing, and every ammo type except the one that just
        // moved reads zero on a HUD that has just been cleared.
        for (int i = 0; i < MAX_AMMO_SLOTS; ++i) {
            player->m_rgAmmoLast[i] = -1;
        }
        player->ForceClientDllUpdate();
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
