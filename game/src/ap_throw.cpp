#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"
#include "gamerules.h"
#include "skill.h"
#include "saverestore.h"

#include "ap_throw.h"

#include <cmath>
#include <set>

#include "ap_checkdata.h"
#include "ap_items.h"
#include "ap_main.h"
#include "ap_state.h"

namespace ap {
namespace {

const char* const kThrowItem = "Melee Throw";

constexpr float kThrowSpeed = 1100.0f;
constexpr float kThrowLift = 100.0f;
constexpr float kThrowGravity = 0.6f;
constexpr float kThrowSpin = -1500.0f;
// Back in the player's hands after this long wherever it went, so a throw off
// a ledge or into slime does not leave them unarmed for the rest of the level.
constexpr float kReturnSeconds = 10.0f;

// A short ribbon behind it in flight, the RPG rocket's smoke, in tenths of a
// second.
constexpr int kTrailLife = 6;
constexpr int kTrailWidth = 3;
constexpr int kTrailBrightness = 200;

// The bar flies as an 8-unit cube but lands in the 32x32x16 pickup box, which
// stopped flush against a wall is buried in it and drags itself out a few units
// per frame. Stepping back along the surface normal first drops it into open
// space instead.
constexpr float kLandClearance = 2.0f;
constexpr float kLandProbe = 32.0f;
constexpr float kLandBackoff = 8.0f;

struct Throwable {
    const char* classname;
    const char* model;
    const char* hit_wall;
    const char* hit_body;
    float (*damage)();
};

float CrowbarDamage() { return gSkillData.plrDmgCrowbar; }
float KnifeDamage() { return gSkillData.plrDmgKnife; }

const Throwable kThrowables[] = {
    {"weapon_crowbar", "models/w_crowbar.mdl", "weapons/cbar_hit1.wav",
     "weapons/cbar_hitbod1.wav", CrowbarDamage},
    {"weapon_knife", "models/w_knife.mdl", "weapons/knife_hit_wall1.wav",
     "weapons/knife_hit_flesh1.wav", KnifeDamage},
};

const Throwable* ThrowableFor(const char* classname) {
    for (const Throwable& entry : kThrowables) {
        if (FStrEq(entry.classname, classname)) {
            return &entry;
        }
    }
    return nullptr;
}

// Classnames in flight or on the floor, and the weapon each throw leaves to be
// taken out of the inventory on the next frame.
std::set<std::string> g_thrown;
EHANDLE g_pending_removal;

int g_trail = 0;

}  // namespace
}  // namespace ap

using ap::kLandBackoff;
using ap::kLandClearance;
using ap::kLandProbe;
using ap::kThrowGravity;
using ap::Throwable;
using ap::ThrowableFor;

class CApThrownMelee : public CBaseAnimating {
public:
    void Spawn() override;

    int Save(CSave& save) override;
    int Restore(CRestore& restore) override;
    static TYPEDESCRIPTION m_SaveData[];

    void EXPORT FlyTouch(CBaseEntity* other);
    void EXPORT PickupTouch(CBaseEntity* other);
    void EXPORT ReturnThink();

    const Throwable* Kind() const { return ThrowableFor(STRING(m_weapon)); }

    string_t m_weapon;

private:
    void Land();
    Vector LandClearance(const Vector& mins, const Vector& maxs) const;
    // Hands the weapon back and removes this. False when the player cannot
    // take it (dead, gone), leaving it where it is.
    bool GiveBack();
    void Remove();
};

LINK_ENTITY_TO_CLASS(ap_thrown_melee, CApThrownMelee);

TYPEDESCRIPTION CApThrownMelee::m_SaveData[] = {
    DEFINE_FIELD(CApThrownMelee, m_weapon, FIELD_STRING),
};
IMPLEMENT_SAVERESTORE(CApThrownMelee, CBaseAnimating);

void CApThrownMelee::Spawn() {
    pev->movetype = MOVETYPE_TOSS;
    pev->solid = SOLID_BBOX;
    pev->gravity = kThrowGravity;
    pev->friction = 0.8f;
    const Throwable* kind = Kind();
    SET_MODEL(ENT(pev), kind != nullptr ? kind->model : "models/w_crowbar.mdl");
    UTIL_SetSize(pev, Vector(-4, -4, -4), Vector(4, 4, 4));
    UTIL_SetOrigin(pev, pev->origin);
    SetTouch(&CApThrownMelee::FlyTouch);
}

void CApThrownMelee::FlyTouch(CBaseEntity* other) {
    if (other == nullptr || other->edict() == pev->owner) {
        return;
    }
    const Throwable* kind = Kind();
    if (kind != nullptr && other->pev->takedamage != DAMAGE_NO) {
        CBaseEntity* thrower = CBaseEntity::Instance(pev->owner);
        other->TakeDamage(pev, thrower != nullptr ? thrower->pev : pev, kind->damage(),
                          DMG_CLUB);
        const bool flesh = other->Classify() != CLASS_NONE &&
                           other->Classify() != CLASS_MACHINE;
        EMIT_SOUND(ENT(pev), CHAN_WEAPON, flesh ? kind->hit_body : kind->hit_wall, 1,
                   ATTN_NORM);
    } else if (kind != nullptr) {
        EMIT_SOUND_DYN(ENT(pev), CHAN_WEAPON, kind->hit_wall, 1, ATTN_NORM, 0,
                       98 + RANDOM_LONG(0, 3));
    }
    Land();
}

void CApThrownMelee::Land() {
    // A dropped weapon's physics: falls to the floor, then waits there as a
    // trigger to be walked over.
    const Vector mins(-16, -16, 0);
    const Vector maxs(16, 16, 16);
    // Measured first: it reads the incoming velocity, which the next lines clear.
    const Vector clearance = LandClearance(mins, maxs);

    pev->owner = nullptr;  // the thrower has to be able to touch it now
    pev->velocity = g_vecZero;
    pev->avelocity = g_vecZero;
    pev->angles.x = 0;
    pev->angles.z = 0;
    pev->movetype = MOVETYPE_TOSS;
    pev->solid = SOLID_TRIGGER;
    UTIL_SetSize(pev, mins, maxs);
    UTIL_SetOrigin(pev, pev->origin + clearance);
    SetTouch(&CApThrownMelee::PickupTouch);
}

// Only from Land, while pev->velocity still points at the surface it hit.
Vector CApThrownMelee::LandClearance(const Vector& mins, const Vector& maxs) const {
    if (pev->velocity.Length() < 1) {
        return g_vecZero;
    }
    const Vector dir = pev->velocity.Normalize();
    TraceResult tr;
    // From a few units back along the flight path, which is open space: a trace
    // starting exactly on the plane can come back start-solid with no normal.
    UTIL_TraceLine(pev->origin - dir * kLandBackoff, pev->origin + dir * kLandProbe,
                   ignore_monsters, ENT(pev), &tr);
    if (tr.fAllSolid || tr.flFraction == 1.0f) {
        return g_vecZero;
    }
    const Vector normal = tr.vecPlaneNormal;
    // How far the landed box reaches toward that plane, per axis because the
    // box is not centred on its origin in z.
    const float reach = std::fabs(normal.x) * (normal.x > 0 ? -mins.x : maxs.x) +
                        std::fabs(normal.y) * (normal.y > 0 ? -mins.y : maxs.y) +
                        std::fabs(normal.z) * (normal.z > 0 ? -mins.z : maxs.z);
    const float have = DotProduct(pev->origin - tr.vecEndPos, normal);
    const float push = reach + kLandClearance - have;
    return push <= 0 ? g_vecZero : normal * push;
}

void CApThrownMelee::PickupTouch(CBaseEntity* other) {
    if (other != nullptr && other->IsPlayer() && other->IsAlive()) {
        GiveBack();
    }
}

void CApThrownMelee::ReturnThink() {
    if (!GiveBack()) {
        // Nobody to give it to right now; try again shortly rather than lose it.
        pev->nextthink = gpGlobals->time + 1.0f;
    }
}

bool CApThrownMelee::GiveBack() {
    CBasePlayer* player = ap::Player();
    if (player == nullptr || !player->IsAlive()) {
        return false;
    }
    const std::string classname(STRING(m_weapon));
    ap::g_thrown.erase(classname);
    // Already holding one (a save restored with this in flight, and the loadout
    // got there first): the bar just goes.
    if (!player->HasNamedPlayerItem(classname.c_str())) {
        ap::ReturnWeapon(player, classname);
        EMIT_SOUND(ENT(player->pev), CHAN_ITEM, "items/gunpickup2.wav", 1, ATTN_NORM);
    }
    Remove();
    return true;
}

void CApThrownMelee::Remove() {
    // The client keeps a followed beam bound to the entity index; detach it so
    // the next entity in this slot does not inherit the tail.
    MESSAGE_BEGIN(MSG_BROADCAST, SVC_TEMPENTITY);
    WRITE_BYTE(TE_KILLBEAM);
    WRITE_SHORT(entindex());
    MESSAGE_END();
    SetThink(NULL);
    SetTouch(NULL);
    UTIL_Remove(this);
}

namespace ap {

bool ThrowMelee(CBasePlayerWeapon* weapon) {
    if (weapon == nullptr || weapon->m_pPlayer == nullptr) {
        return false;
    }
    if (!Data().Loaded() || !State().Has(kThrowItem)) {
        return false;  // not in this seed, or not sent yet: mouse2 does nothing
    }
    const Throwable* kind = ThrowableFor(STRING(weapon->pev->classname));
    if (kind == nullptr || Thrown(kind->classname)) {
        return false;
    }
    CBasePlayer* player = weapon->m_pPlayer;

    UTIL_MakeVectors(player->pev->v_angle);
    const Vector origin = player->GetGunPosition() + gpGlobals->v_forward * 16;
    // pev->owner is the thrower, so the two do not collide while it leaves their
    // hands. Land() clears it.
    auto* thrown = GetClassPtr(static_cast<CApThrownMelee*>(nullptr));
    thrown->pev->classname = MAKE_STRING("ap_thrown_melee");
    thrown->m_weapon = MAKE_STRING(kind->classname);
    thrown->pev->origin = origin;
    thrown->pev->angles = player->pev->v_angle;
    thrown->pev->owner = player->edict();
    thrown->Spawn();
    thrown->pev->velocity = gpGlobals->v_forward * kThrowSpeed +
                            gpGlobals->v_up * kThrowLift + player->pev->velocity;
    thrown->pev->avelocity = Vector(kThrowSpin, 0, 0);  // end over end
    thrown->SetThink(&CApThrownMelee::ReturnThink);
    thrown->pev->nextthink = gpGlobals->time + kReturnSeconds;

    MESSAGE_BEGIN(MSG_BROADCAST, SVC_TEMPENTITY);
    WRITE_BYTE(TE_BEAMFOLLOW);
    WRITE_SHORT(thrown->entindex());
    WRITE_SHORT(g_trail);
    WRITE_BYTE(kTrailLife);
    WRITE_BYTE(kTrailWidth);
    WRITE_BYTE(224);
    WRITE_BYTE(224);
    WRITE_BYTE(224);
    WRITE_BYTE(kTrailBrightness);
    MESSAGE_END();

    player->SetAnimation(PLAYER_ATTACK1);
    EMIT_SOUND_DYN(ENT(player->pev), CHAN_WEAPON, "weapons/cbar_miss1.wav", 1,
                   ATTN_NORM, 0, 98 + RANDOM_LONG(0, 3));

    g_thrown.insert(kind->classname);
    g_pending_removal = weapon;
    return true;
}

void RunThrows() {
    CBaseEntity* entity = g_pending_removal;
    g_pending_removal = nullptr;
    auto* weapon = static_cast<CBasePlayerItem*>(entity);
    CBasePlayer* player = Player();
    if (weapon == nullptr || player == nullptr) {
        return;
    }
    // Switch away first, so the player is holding whatever is next best rather
    // than an empty hand with the thrown weapon's stance.
    if (player->m_pActiveItem == weapon) {
        g_pGameRules->GetNextBestWeapon(player, weapon);
    }
    player->RemovePlayerItem(weapon);
    player->pev->weapons &= ~(1 << weapon->m_iId);
    weapon->Kill();
}

bool Thrown(const std::string& classname) {
    return g_thrown.count(classname) > 0;
}

void ClearThrown() {
    g_pending_removal = nullptr;
    if (!g_thrown.empty()) {
        g_thrown.clear();
        RequestLoadout();
    }
}

void PrecacheThrow() {
    g_trail = PRECACHE_MODEL((char*)"sprites/smoke.spr");
    PRECACHE_MODEL((char*)"models/w_crowbar.mdl");
    PRECACHE_SOUND((char*)"weapons/cbar_hit1.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_hitbod1.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_miss1.wav");
    PRECACHE_SOUND((char*)"items/gunpickup2.wav");
}

}  // namespace ap
