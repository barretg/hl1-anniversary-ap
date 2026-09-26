#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "monsters.h"
#include "player.h"
#include "saverestore.h"
#include "weapons.h"

#include "ap_bots.h"
#include "ap_content.h"

#include <cmath>
#include <vector>

#include "ap_main.h"
#include "ap_traps.h"

namespace {

// --- the brain's numbers, from fun-with-bots ------------------------------

// How far ahead the way is checked, how often the bot's own progress is sampled,
// and how far it has to have travelled in that time to count as moving. A
// single step is too small to tell from being stuck, which is why progress is
// sampled on an interval.
constexpr float kLookahead = 24.0f;
constexpr float kProgressInterval = 0.3f;
constexpr float kProgressDistance = 16.0f;

// The step the engine walks a monster up without being asked. A hull traced
// along the floor calls every staircase a wall, so the forward trace is retried
// from the top of a step before the way is believed shut.
constexpr float kStepHeight = 18.0f;

// A jump got somewhere if it ended this much higher, or this much further along
// the heading. One that has not landed by the timeout was a fall, and the bot
// goes back to walking.
constexpr float kJumpGainZ = 8.0f;
constexpr float kJumpGainForward = 16.0f;
constexpr float kJumpTimeout = 2.0f;

// The smallest turn taken when a heading is given up on. Anything less and the
// bot walks back into the same wall from very nearly the same angle.
constexpr float kTurnMin = 45.0f;

// How close something has to be to be swung at: a shade over two hulls apart,
// so the bot starts swinging as it bumps rather than after.
constexpr float kMeleeRange = 48.0f;
constexpr float kMeleeHeight = 72.0f;

// One swing is the player model's crowbar swing, 13 frames at 24fps; the hit
// lands partway through it, and there is a breath before the next.
constexpr float kSwingHitAt = 0.2f;
constexpr float kSwingTime = 0.55f;
constexpr float kRecoverTime = 0.2f;

// A bout is a few swings, not a stand-off: after 1 to 3 of them, rolled each
// bout, the bot turns its back and runs, and ignores everything in reach for a
// moment so that it actually gets somewhere before the next bump.
constexpr int kBoutSwingsMin = 1;
constexpr int kBoutSwingsMax = 3;
constexpr float kFleeMinSeconds = 1.0f;
constexpr float kFleeMaxSeconds = 2.0f;
// How far either side of straight-away the bot runs off on.
constexpr float kFleeSpread = 45.0f;

// --- the body ----------------------------------------------------------------

// A player's run speed and jump. The jump is the player's own: sqrt(2 * 800 *
// 45), 45 units at the default gravity, and the crouch tucks another 18 on top.
constexpr float kRunSpeed = 240.0f;
constexpr float kJumpSpeed = 268.0f;

// The player's own hulls, origin at the centre rather than at the feet as a
// monster's is. It has to be: the player model is drawn around its origin, and
// with a monster's feet-origin every bot stood waist-deep in the floor.
//
// The same geometry gives the crouch jump for free. Ducking on the ground drops
// the centre so the feet stay put; ducking in the air leaves the centre where
// it is, so the legs tuck up 18 units -- which is what makes a crouch jump clear
// more than a plain one.
constexpr float kStandHalf = 36.0f;
constexpr float kDuckHalf = 18.0f;

// How often the brain runs. Movement is scaled by the real interval, so this
// only sets how smooth it looks.
constexpr float kThinkInterval = 0.05f;

// How long a body lies there before fading.
constexpr float kCorpseSeconds = 5.0f;

// No more than this many quota bots however the cvar is set; each is an entity
// and a model, and the edict table is finite.
constexpr int kQuotaCeiling = 32;

cvar_t bot_quota = {(char*)"bot_quota", (char*)"0"};
cvar_t bot_autofill = {(char*)"bot_autofill", (char*)"0"};
cvar_t bot_zombie = {(char*)"bot_zombie", (char*)"0"};

// Every multiplayer skin Half-Life ships in valve/models/player. A bot wears
// one at random. Each costs a model precache slot on every map, and a missing
// file is a fatal precache error, so the list is only what retail installs:
// spelled as on disk, since several are capitalised and not every filesystem
// forgives that. All of them carry the player skeleton and sequences, so the
// crowbar and the animation names below fit any of them.
const char* const kBotModels[] = {
    "models/player/barney/barney.mdl",
    "models/player/bbbbarney/bbbbarney.mdl",
    "models/player/gina/Gina.mdl",
    "models/player/gman/Gman.mdl",
    "models/player/gordon/gordon.mdl",
    "models/player/helmet/Helmet.mdl",
    "models/player/hgrunt/Hgrunt.mdl",
    "models/player/ivan/ivan.mdl",
    "models/player/recon/recon.mdl",
    "models/player/robo/robo.mdl",
    "models/player/scientist/Scientist.mdl",
    "models/player/skeleton/skeleton.mdl",
    "models/player/tmcm/TMCM.mdl",
    "models/player/zombie/zombie.mdl",
};
constexpr int kBotModelCount = sizeof(kBotModels) / sizeof(kBotModels[0]);

// Opposing Force's multiplayer skins, which `/install` links in when OF is
// owned. All carry the same skeleton and sequences. Its zombie is left out:
// that path is Half-Life's zombie, and OF's copy is only visible on OF maps.
// Blue Shift's player models are byte for byte Half-Life's, so it adds none.
const char* const kOpForBotModels[] = {
    "models/player/beret/beret.mdl",
    "models/player/cl_suit/cl_suit.mdl",
    "models/player/ctf_barney/ctf_barney.mdl",
    "models/player/ctf_gina/ctf_gina.mdl",
    "models/player/ctf_gordon/ctf_gordon.mdl",
    "models/player/ctf_scientist/ctf_scientist.mdl",
    "models/player/drill/drill.mdl",
    "models/player/fassn/fassn.mdl",
    "models/player/grunt/grunt.mdl",
    "models/player/massn/massn.mdl",
    "models/player/otis/otis.mdl",
    "models/player/recruit/recruit.mdl",
    "models/player/shephard/shephard.mdl",
    "models/player/tower/tower.mdl",
};
constexpr int kOpForBotModelCount = sizeof(kOpForBotModels) / sizeof(kOpForBotModels[0]);

// Every skin is a model slot on every map, and OF's biggest maps already use
// most of the 512. So each map gets a few of OF's, picked by the map's name:
// the same few every time it loads, which a restored bot's model relies on.
constexpr int kOpForSkinsPerMap = 4;
const char* g_mapSkins[kOpForSkinsPerMap];
int g_mapSkinCount = 0;
const char* const kCrowbarModel = "models/p_crowbar.mdl";

enum MoveState { kMoveWander, kMoveJump };
enum MeleeState { kMeleeIdle, kMeleeSwing, kMeleeRecover };

}  // namespace

class CApBot : public CBaseMonster {
public:
    void Spawn() override;
    int Classify() override { return CLASS_PLAYER_ALLY; }
    void Killed(entvars_t* pevAttacker, int iGib) override;

    int Save(CSave& save) override;
    int Restore(CRestore& restore) override;
    static TYPEDESCRIPTION m_SaveData[];

    void EXPORT BotThink();

    // Takes the crowbar with it.
    void Remove();

    bool FromQuota() const { return m_fromQuota != FALSE; }
    void SetFromQuota(bool from_quota) { m_fromQuota = from_quota ? TRUE : FALSE; }

private:
    bool Ducked() const { return pev->maxs.z < kStandHalf - 1.0f; }
    Vector Feet() const { return pev->origin + Vector(0.0f, 0.0f, pev->mins.z); }
    void SetDucked(bool ducked);
    bool CanStand();
    bool PathClear(const Vector& forward, bool duck);
    Vector Eyes() const;

    void EnsureCrowbar();
    void DropCrowbar();

    void SetSequenceNamed(const char* name, bool restart);
    void TurnAway();
    void SampleProgress();

    CBaseEntity* FindVictim();
    bool MeleeThink(float& yaw);
    void Swing(CBaseEntity* victim);
    void JumpThink(const Vector& forward);
    void MoveThink(float dt, float yaw, bool fighting);
    void Animate(bool moving);
    void DeadThink();

    // Saved: which crowbar is this bot's, so a restore does not make a second.
    EHANDLE m_crowbar;
    BOOL m_fromQuota = FALSE;

    // Not saved. A restored bot starts its brain over, which costs it nothing
    // worse than one misjudged step.
    float m_yaw = 0.0f;
    float m_lastThink = 0.0f;
    MoveState m_move = kMoveWander;
    Vector m_lastOrigin;
    float m_nextProgressCheck = 0.0f;
    Vector m_jumpStart;
    bool m_airborne = false;
    float m_jumpExpire = 0.0f;
    MeleeState m_melee = kMeleeIdle;
    float m_meleeNext = 0.0f;
    bool m_hitPending = false;
    int m_swingsLeft = 0;  // in this bout; 0 between bouts
    float m_diedAt = 0.0f;
};

LINK_ENTITY_TO_CLASS(ap_bot, CApBot);

TYPEDESCRIPTION CApBot::m_SaveData[] = {
    DEFINE_FIELD(CApBot, m_crowbar, FIELD_EHANDLE),
    DEFINE_FIELD(CApBot, m_fromQuota, FIELD_BOOLEAN),
};
IMPLEMENT_SAVERESTORE(CApBot, CBaseMonster);

void CApBot::Spawn() {
    // A restore does not come through here: the saved model is kept.
    const int pick = RANDOM_LONG(0, kBotModelCount + g_mapSkinCount - 1);
    SET_MODEL(ENT(pev), pick < kBotModelCount ? kBotModels[pick]
                                               : g_mapSkins[pick - kBotModelCount]);
    // Shirt and trousers, as a player's topcolor and bottomcolor: a hue each,
    // low byte and high byte. The client remaps any studio model by it, and it
    // is saved with the rest of entvars.
    pev->colormap = RANDOM_LONG(0, 255) | (RANDOM_LONG(0, 255) << 8);
    // Handed the feet, like any spawn spot; the origin is the hull's centre.
    pev->origin.z += kStandHalf;
    UTIL_SetOrigin(pev, pev->origin);
    UTIL_SetSize(pev, VEC_HULL_MIN, VEC_HULL_MAX);

    // MOVETYPE_STEP is a monster's: `WALK_MOVE` steps it up stairs and along
    // floors, and when it is off the ground the engine flies it on its velocity
    // with gravity, which is all a jump needs.
    pev->solid = SOLID_SLIDEBOX;
    pev->movetype = MOVETYPE_STEP;
    pev->health = ap::kBotHealth;
    pev->max_health = ap::kBotHealth;
    pev->takedamage = DAMAGE_AIM;
    pev->deadflag = DEAD_NO;
    pev->view_ofs = VEC_VIEW;
    // FL_MONSTER so other monsters see it, and so the crowbar sound code calls
    // hitting one a body rather than a wall.
    pev->flags |= FL_MONSTER;
    m_bloodColor = BLOOD_COLOR_RED;

    m_yaw = pev->angles.y;
    SampleProgress();
    SetSequenceNamed("ref_aim_crowbar", true);

    // Staggered, so a swarm does not think in lockstep.
    SetThink(&CApBot::BotThink);
    pev->nextthink = gpGlobals->time + RANDOM_FLOAT(0.05f, 0.15f);
}

void CApBot::SetDucked(bool ducked) {
    if (ducked == Ducked()) {
        return;
    }
    const bool on_ground = (pev->flags & FL_ONGROUND) != 0;
    const Vector feet = Feet();
    UTIL_SetSize(pev, ducked ? VEC_DUCK_HULL_MIN : VEC_HULL_MIN,
                 ducked ? VEC_DUCK_HULL_MAX : VEC_HULL_MAX);
    // On the ground the feet stay on the floor; in the air the centre stays put
    // and the legs tuck up or drop down. See kStandHalf.
    if (on_ground) {
        UTIL_SetOrigin(pev, feet - Vector(0.0f, 0.0f, pev->mins.z));
    }
    pev->view_ofs = ducked ? VEC_DUCK_VIEW : VEC_VIEW;
}

bool CApBot::CanStand() {
    // The standing hull, where `SetDucked(false)` would put it: on the ground
    // the feet stay where they are, in the air the centre does.
    const Vector centre = (pev->flags & FL_ONGROUND) != 0
                              ? Feet() + Vector(0.0f, 0.0f, kStandHalf)
                              : pev->origin;
    TraceResult tr;
    UTIL_TraceHull(centre, centre, dont_ignore_monsters, human_hull, edict(),
                   &tr);
    return tr.fStartSolid == 0 && tr.fAllSolid == 0;
}

// Is there room to go kLookahead units along `forward`, standing or ducked?
// A hull rather than a line, because what matters is whether the bot fits, and
// the whole point of the ducked answer is that the standing one does not.
bool CApBot::PathClear(const Vector& forward, bool duck) {
    const int hull = duck ? head_hull : human_hull;
    const float centre = duck ? kDuckHalf : kStandHalf;

    // Flat along the floor first; if that is shut, the same trace from the top
    // of a step asks whether the thing in the way is something the engine walks
    // the bot up anyway. Only asked once the flat one failed, so a low ceiling
    // never reaches it on its own.
    for (int pass = 0; pass < 2; ++pass) {
        const Vector start =
            Feet() + Vector(0.0f, 0.0f, centre + (pass ? kStepHeight : 0.0f));
        TraceResult tr;
        UTIL_TraceHull(start, start + forward * kLookahead, dont_ignore_monsters,
                       hull, edict(), &tr);
        if (tr.fAllSolid == 0 && tr.fStartSolid == 0 && tr.flFraction == 1.0f) {
            return true;
        }
    }
    return false;
}

Vector CApBot::Eyes() const { return pev->origin + pev->view_ofs; }

// The crowbar is its own entity: a non-player is drawn without its weaponmodel.
// MOVETYPE_FOLLOW with the bot as its aiment is the renderer's other way of
// putting a p_ model in someone's hand -- it copies the bones of whatever it
// follows by name, which is what a p_ model is built for.
void CApBot::EnsureCrowbar() {
    if (m_crowbar != nullptr) {
        return;
    }
    edict_t* pent = CREATE_NAMED_ENTITY(MAKE_STRING("info_target"));
    if (FNullEnt(pent)) {
        return;
    }
    DispatchSpawn(pent);
    SET_MODEL(pent, kCrowbarModel);
    pent->v.movetype = MOVETYPE_FOLLOW;
    pent->v.aiment = edict();
    pent->v.solid = SOLID_NOT;
    UTIL_SetOrigin(&pent->v, pev->origin);
    m_crowbar = CBaseEntity::Instance(pent);
}

void CApBot::DropCrowbar() {
    CBaseEntity* crowbar = m_crowbar;
    if (crowbar != nullptr) {
        UTIL_Remove(crowbar);
    }
    m_crowbar = nullptr;
}

void CApBot::Remove() {
    DropCrowbar();
    UTIL_Remove(this);
}

void CApBot::SetSequenceNamed(const char* name, bool restart) {
    const int sequence = LookupSequence(name);
    if (sequence < 0) {
        return;
    }
    if (!restart && sequence == pev->sequence) {
        return;
    }
    pev->sequence = sequence;
    pev->frame = 0;
    ResetSequenceInfo();
    // The aim sequences blend on pitch; straight ahead is the middle.
    SetBlending(0, 0.0f);
}

void CApBot::SampleProgress() {
    m_lastOrigin = pev->origin;
    m_nextProgressCheck = gpGlobals->time + kProgressInterval;
}

void CApBot::TurnAway() {
    const float turn = RANDOM_FLOAT(kTurnMin, 180.0f);
    m_yaw = UTIL_AngleMod(m_yaw + (RANDOM_LONG(0, 1) ? turn : -turn));
    SampleProgress();
}

// Whatever this bot has run into. Anything alive in reach -- the player, a
// monster, another bot -- and failing that, whatever is straight ahead and can
// be hurt, which is how a crate in the way gets hit too.
CBaseEntity* CApBot::FindVictim() {
    const Vector eyes = Eyes();
    CBaseEntity* nearest = nullptr;
    float nearest_distance = kMeleeRange;

    CBaseEntity* other = nullptr;
    while ((other = UTIL_FindEntityInSphere(other, pev->origin,
                                            kMeleeRange + kMeleeHeight)) !=
           nullptr) {
        if (other == this || other->pev->takedamage == DAMAGE_NO ||
            !other->IsAlive() || other->IsBSPModel()) {
            continue;
        }
        if ((other->pev->flags & (FL_CLIENT | FL_MONSTER)) == 0 ||
            (other->pev->flags & FL_NOTARGET) != 0) {
            continue;
        }
        const Vector delta = other->pev->origin - pev->origin;
        if (std::fabs(delta.z) > kMeleeHeight) {
            continue;
        }
        const float distance = delta.Length2D();
        if (distance > nearest_distance) {
            continue;
        }
        // Not through a wall.
        TraceResult tr;
        UTIL_TraceLine(eyes, other->Center(), ignore_monsters, edict(), &tr);
        if (tr.flFraction < 1.0f) {
            continue;
        }
        nearest_distance = distance;
        nearest = other;
    }
    if (nearest != nullptr) {
        return nearest;
    }

    UTIL_MakeVectors(Vector(0.0f, m_yaw, 0.0f));
    TraceResult tr;
    UTIL_TraceLine(eyes, eyes + gpGlobals->v_forward * kMeleeRange,
                   dont_ignore_monsters, edict(), &tr);
    if (tr.flFraction < 1.0f && !FNullEnt(tr.pHit)) {
        CBaseEntity* hit = CBaseEntity::Instance(tr.pHit);
        // The world has no takedamage, so this is only ever something that can
        // break or bleed.
        if (hit != nullptr && hit != this && hit->pev->takedamage != DAMAGE_NO) {
            return hit;
        }
    }
    return nullptr;
}

// The crowbar's own swing, from a bot rather than a player: a short line
// towards the victim, and a head-sized hull if the line slipped past.
void CApBot::Swing(CBaseEntity* victim) {
    const Vector eyes = Eyes();
    Vector direction;
    if (victim != nullptr) {
        direction = (victim->Center() - eyes).Normalize();
    } else {
        UTIL_MakeVectors(Vector(0.0f, m_yaw, 0.0f));
        direction = gpGlobals->v_forward;
    }
    const Vector end = eyes + direction * (kMeleeRange + 16.0f);

    TraceResult tr;
    UTIL_TraceLine(eyes, end, dont_ignore_monsters, edict(), &tr);
    if (tr.flFraction >= 1.0f) {
        UTIL_TraceHull(eyes, end, dont_ignore_monsters, head_hull, edict(), &tr);
    }

    CBaseEntity* hit =
        tr.flFraction < 1.0f && !FNullEnt(tr.pHit) ? CBaseEntity::Instance(tr.pHit)
                                                   : nullptr;
    if (hit == nullptr) {
        EMIT_SOUND_DYN(edict(), CHAN_WEAPON, "weapons/cbar_miss1.wav", 1,
                       ATTN_NORM, 0, 94 + RANDOM_LONG(0, 0xF));
        return;
    }

    ClearMultiDamage();
    hit->TraceAttack(pev, ap::kBotCrowbarDamage, direction, &tr, DMG_CLUB);
    ApplyMultiDamage(pev, pev);

    if (hit->Classify() != CLASS_NONE && hit->Classify() != CLASS_MACHINE) {
        static const char* const kBody[] = {"weapons/cbar_hitbod1.wav",
                                            "weapons/cbar_hitbod2.wav",
                                            "weapons/cbar_hitbod3.wav"};
        EMIT_SOUND(edict(), CHAN_WEAPON, kBody[RANDOM_LONG(0, 2)], 1, ATTN_NORM);
    } else {
        EMIT_SOUND_DYN(edict(), CHAN_WEAPON,
                       RANDOM_LONG(0, 1) ? "weapons/cbar_hit1.wav"
                                         : "weapons/cbar_hit2.wav",
                       1, ATTN_NORM, 0, 98 + RANDOM_LONG(0, 3));
    }
}

// True while a swing is in progress, which tells the rest of the think that the
// view belongs to the fight, and that standing still to hit someone is not
// being stuck. `yaw` is turned to face the victim; the heading itself is left
// alone, so the bot carries on its way when the fight is over.
bool CApBot::MeleeThink(float& yaw) {
    CBaseEntity* victim = FindVictim();

    if (m_melee == kMeleeIdle) {
        if (victim == nullptr || gpGlobals->time < m_meleeNext) {
            return false;
        }
        if (m_swingsLeft <= 0) {
            m_swingsLeft = RANDOM_LONG(kBoutSwingsMin, kBoutSwingsMax);
        }
        m_melee = kMeleeSwing;
        m_meleeNext = gpGlobals->time + kSwingTime;
        m_hitPending = true;
        SetSequenceNamed(Ducked() ? "crouch_shoot_crowbar" : "ref_shoot_crowbar",
                         true);
    }

    if (victim != nullptr) {
        yaw = UTIL_VecToYaw(victim->pev->origin - pev->origin);
    }

    switch (m_melee) {
        case kMeleeSwing:
            if (m_hitPending &&
                gpGlobals->time >= m_meleeNext - kSwingTime + kSwingHitAt) {
                m_hitPending = false;
                pev->angles.y = yaw;
                Swing(victim);
                --m_swingsLeft;
            }
            if (gpGlobals->time >= m_meleeNext) {
                m_melee = kMeleeRecover;
                m_meleeNext = gpGlobals->time + kRecoverTime;
            }
            break;
        case kMeleeRecover:
            if (gpGlobals->time >= m_meleeNext) {
                m_melee = kMeleeIdle;
                m_meleeNext = gpGlobals->time;
                if (victim == nullptr) {
                    // It left first. The next bump is a new bout.
                    m_swingsLeft = 0;
                    return false;
                }
                if (m_swingsLeft > 0) {
                    return true;  // straight into the next swing
                }
                // Bout over: turn tail and run, and leave everything alone
                // until well clear.
                m_swingsLeft = 0;
                m_yaw = UTIL_AngleMod(
                    UTIL_VecToYaw(pev->origin - victim->pev->origin) +
                    RANDOM_FLOAT(-kFleeSpread, kFleeSpread));
                m_meleeNext = gpGlobals->time +
                              RANDOM_FLOAT(kFleeMinSeconds, kFleeMaxSeconds);
                SampleProgress();
                return false;
            }
            break;
        default:
            break;
    }
    return m_melee != kMeleeIdle;
}

void CApBot::JumpThink(const Vector& forward) {
    const bool on_ground = (pev->flags & FL_ONGROUND) != 0;

    // Checked first, on the ground as well as in the air: a jump that never left
    // the ground is somewhere a jump does not work, and would otherwise be
    // retried there for the rest of the map.
    if (gpGlobals->time >= m_jumpExpire) {
        m_move = kMoveWander;
        m_airborne = false;
        if (CanStand()) {
            SetDucked(false);
        }
        TurnAway();
        return;
    }

    if (!m_airborne) {
        if (!on_ground) {
            // Off the floor: now tuck the legs up. Jump first and duck second,
            // never both at once -- the jump gets its full height from standing,
            // and the tuck adds the last 18 units of clearance. The ducked box
            // sits inside the standing one, so it always fits.
            m_airborne = true;
            SetDucked(true);
        }
        return;
    }

    if (on_ground) {
        // Landed. It got somewhere if it came down higher, or further along the
        // heading than the wall it was standing against.
        const Vector travel = Feet() - m_jumpStart;
        const bool gained = travel.z > kJumpGainZ ||
                            DotProduct(travel, forward) > kJumpGainForward;
        m_move = kMoveWander;
        m_airborne = false;
        if (CanStand()) {
            SetDucked(false);
        }
        SampleProgress();
        if (!gained) {
            TurnAway();
        }
    }
}

void CApBot::MoveThink(float dt, float yaw, bool fighting) {
    Vector forward, right, up;
    UTIL_MakeVectorsPrivate(Vector(0.0f, m_yaw, 0.0f), forward, right, up);

    if (m_move == kMoveJump) {
        JumpThink(forward);
        return;
    }

    const bool on_ground = (pev->flags & FL_ONGROUND) != 0;
    if (!on_ground) {
        return;  // falling; the engine has it
    }

    if (fighting) {
        // Walk into whoever is being hit, and read nothing into having stopped,
        // which is what hitting somebody looks like from here.
        WALK_MOVE(edict(), yaw, kRunSpeed * dt, WALKMOVE_NORMAL);
        SampleProgress();
        return;
    }

    // Two ways to learn the way ahead is shut. The trace sees a wall before the
    // bot is pressed against it; the progress sample catches what the trace is
    // too coarse for -- a shallow corner, a ledge the engine will not walk it
    // off, a door pushing back, someone standing in the way.
    bool stuck = false;
    if (gpGlobals->time >= m_nextProgressCheck) {
        stuck = (pev->origin - m_lastOrigin).Length2D() < kProgressDistance;
        SampleProgress();
    }

    // The loop, in order: walk; duck and carry on if ducking is what opens the
    // way; otherwise crouch-jump it, and let the landing judge the heading.
    if (!stuck && PathClear(forward, false)) {
        if (Ducked() && CanStand()) {
            SetDucked(false);
        }
    } else if (!stuck && PathClear(forward, true)) {
        SetDucked(true);
    } else {
        // Up from standing, for the full height of the jump.
        if (Ducked() && CanStand()) {
            SetDucked(false);
        }
        m_move = kMoveJump;
        m_jumpStart = Feet();
        m_airborne = false;
        m_jumpExpire = gpGlobals->time + kJumpTimeout;
        pev->velocity = forward * kRunSpeed + Vector(0.0f, 0.0f, kJumpSpeed);
        pev->flags &= ~FL_ONGROUND;
        // Off the floor, or the engine puts it straight back on it.
        UTIL_SetOrigin(pev, pev->origin + Vector(0.0f, 0.0f, 1.0f));
        return;
    }

    WALK_MOVE(edict(), m_yaw, kRunSpeed * dt, WALKMOVE_NORMAL);
}

// One sequence for the whole body. A non-player gets no gait layer, so the legs
// and arms come from the same animation: the full-body run, the crouch walk,
// the jump, or the crowbar pose while standing still.
void CApBot::Animate(bool moving) {
    if (m_melee != kMeleeIdle) {
        return;  // the swing owns the animation until it is done
    }
    const bool on_ground = (pev->flags & FL_ONGROUND) != 0;
    const char* name;
    if (!on_ground || m_move == kMoveJump) {
        name = "jump";
    } else if (Ducked()) {
        name = moving ? "crawl" : "crouch_aim_crowbar";
    } else {
        name = moving ? "run2" : "ref_aim_crowbar";
    }
    SetSequenceNamed(name, false);
}

void CApBot::BotThink() {
    pev->nextthink = gpGlobals->time + kThinkInterval;

    if (pev->deadflag != DEAD_NO) {
        DeadThink();
        return;
    }

    // The real interval, clamped: the first think after a spawn or a restore
    // has no previous one to measure from.
    float dt = gpGlobals->time - m_lastThink;
    if (m_lastThink <= 0.0f || dt < 0.0f || dt > 0.2f) {
        dt = kThinkInterval;
    }
    m_lastThink = gpGlobals->time;

    EnsureCrowbar();
    StudioFrameAdvance();

    if (ap::BotZombie()) {
        m_melee = kMeleeIdle;
        m_move = kMoveWander;
        SampleProgress();
        Animate(false);
        return;
    }

    float yaw = m_yaw;
    const bool fighting = MeleeThink(yaw);
    if (fighting) {
        // Whatever it was jumping over matters less than the thing it is
        // hitting. Only abandoned on the ground; mid-air, the engine finishes it.
        if (m_move == kMoveJump && (pev->flags & FL_ONGROUND) != 0) {
            m_move = kMoveWander;
            m_airborne = false;
        }
    }

    MoveThink(dt, yaw, fighting);

    pev->angles.y = fighting ? yaw : m_yaw;
    pev->ideal_yaw = pev->angles.y;
    Animate(!fighting);
}

void CApBot::Killed(entvars_t* pevAttacker, int iGib) {
    DropCrowbar();

    if (ShouldGibMonster(iGib)) {
        // Sets EF_NODRAW and throws the gibs; the think removes what is left.
        CallGibMonster();
        pev->deadflag = DEAD_DEAD;
        m_diedAt = gpGlobals->time - kCorpseSeconds;
        return;
    }

    pev->deadflag = DEAD_DEAD;
    pev->takedamage = DAMAGE_NO;
    pev->solid = SOLID_NOT;
    pev->velocity.x = 0.0f;
    pev->velocity.y = 0.0f;
    m_melee = kMeleeIdle;
    m_diedAt = gpGlobals->time;
    static const char* const kDeaths[] = {"die_simple", "die_backwards",
                                          "die_forwards", "die_spin", "gutshot"};
    SetSequenceNamed(kDeaths[RANDOM_LONG(0, 4)], true);
    pev->nextthink = gpGlobals->time + kThinkInterval;
}

void CApBot::DeadThink() {
    StudioFrameAdvance();
    // A body restored from a save has no death time; count from now.
    if (m_diedAt <= 0.0f || m_diedAt > gpGlobals->time) {
        m_diedAt = gpGlobals->time;
    }
    if (gpGlobals->time - m_diedAt < kCorpseSeconds) {
        return;
    }
    DropCrowbar();
    if ((pev->effects & EF_NODRAW) != 0) {
        UTIL_Remove(this);
        return;
    }
    // Sets its own think, and removes the body once it is gone.
    SUB_StartFadeOut();
}

namespace ap {
namespace {

// Quota bots spawned on this level since the quota last changed. Without
// autofill, the quota is met once from this and the dead are not replaced.
int g_quota_spawned = 0;
int g_last_quota = 0;
bool g_quota_counted = false;
float g_next_quota_spawn = 0.0f;

template <typename Fn>
void ForEachBot(Fn fn) {
    CBaseEntity* entity = nullptr;
    while ((entity = UTIL_FindEntityByClassname(entity, "ap_bot")) != nullptr) {
        fn(static_cast<CApBot*>(entity));
    }
}

int LiveQuotaBots() {
    int count = 0;
    ForEachBot([&count](CApBot* bot) {
        if (bot->FromQuota() && bot->IsAlive()) {
            ++count;
        }
    });
    return count;
}

int Quota() {
    int quota = static_cast<int>(bot_quota.value);
    if (quota < 0) {
        quota = 0;
    }
    return quota > kQuotaCeiling ? kQuotaCeiling : quota;
}

}  // namespace

bool BotZombie() { return bot_zombie.value != 0.0f; }

void PrecacheBots() {
    for (const char* model : kBotModels) {
        PRECACHE_MODEL((char*)model);
    }
    g_mapSkinCount = 0;
    if (IsMountedCampaign("opposing_force")) {
        // FNV-1a of the map name, then consecutive skins from there.
        unsigned int hash = 2166136261u;
        for (const char* c = STRING(gpGlobals->mapname); *c; ++c) {
            hash = (hash ^ static_cast<unsigned char>(*c)) * 16777619u;
        }
        for (int i = 0; i < kOpForSkinsPerMap; ++i) {
            g_mapSkins[i] = kOpForBotModels[(hash + i) % kOpForBotModelCount];
            PRECACHE_MODEL((char*)g_mapSkins[i]);
        }
        g_mapSkinCount = kOpForSkinsPerMap;
    }
    PRECACHE_MODEL((char*)kCrowbarModel);
    PRECACHE_SOUND((char*)"weapons/cbar_hit1.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_hit2.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_hitbod1.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_hitbod2.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_hitbod3.wav");
    PRECACHE_SOUND((char*)"weapons/cbar_miss1.wav");
}

void RegisterBotCommands() {
    CVAR_REGISTER(&bot_quota);
    CVAR_REGISTER(&bot_autofill);
    CVAR_REGISTER(&bot_zombie);
}

void ResetBots() {
    // Counted on the first frame instead of here: a save being restored brings
    // its quota bots with it, and they are not in the level yet at this point.
    g_quota_counted = false;
}

CBaseEntity* SpawnBot(const Vector& origin, float yaw, bool from_quota) {
    edict_t* pent = CREATE_NAMED_ENTITY(MAKE_STRING("ap_bot"));
    if (FNullEnt(pent)) {
        return nullptr;
    }
    CApBot* bot = static_cast<CApBot*>(CBaseEntity::Instance(pent));
    if (bot == nullptr) {
        REMOVE_ENTITY(pent);
        return nullptr;
    }
    bot->pev->origin = origin;
    bot->pev->angles = Vector(0.0f, UTIL_AngleMod(yaw), 0.0f);
    bot->SetFromQuota(from_quota);
    DispatchSpawn(pent);
    return bot;
}

void RunBots() {
    const int quota = Quota();
    const int live = LiveQuotaBots();

    if (!g_quota_counted) {
        g_quota_counted = true;
        g_quota_spawned = live;
        g_last_quota = quota;
        // Let the level settle before anything is placed in it.
        g_next_quota_spawn = gpGlobals->time + 1.0f;
    }
    if (gpGlobals->time + 5.0f < g_next_quota_spawn) {
        g_next_quota_spawn = gpGlobals->time;  // the clock went backwards
    }

    // A new quota is met afresh, whatever the old one spawned.
    if (quota != g_last_quota) {
        g_last_quota = quota;
        g_quota_spawned = live;
    }

    if (live > quota) {
        int excess = live - quota;
        ForEachBot([&excess](CApBot* bot) {
            if (excess > 0 && bot->FromQuota() && bot->IsAlive()) {
                bot->Remove();
                --excess;
            }
        });
        g_quota_spawned = quota;
        return;
    }

    if (live == quota || gpGlobals->time < g_next_quota_spawn) {
        return;
    }
    const bool autofill = bot_autofill.value != 0.0f;
    if (!autofill && g_quota_spawned >= quota) {
        return;
    }

    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }

    // One at a time, a moment apart, so a big quota does not arrive as one lump
    // and a spot that cannot be found is not retried every frame.
    std::vector<Vector> placed;
    Vector spot;
    float bearing = 0.0f;
    if (PlaceNearPlayer(player, human_hull, kHumanHullHalf, placed, spot,
                        bearing) &&
        SpawnBot(spot, RANDOM_FLOAT(0.0f, 360.0f), true) != nullptr) {
        ++g_quota_spawned;
        g_next_quota_spawn = gpGlobals->time + 0.25f;
    } else {
        g_next_quota_spawn = gpGlobals->time + 1.0f;
    }
}

}  // namespace ap
