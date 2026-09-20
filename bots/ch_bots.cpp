#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"
#include "client.h"
#include "gamerules.h"
#include "ch_bots.h"

// A bot is nothing more than an engine fake client that the game DLL connects
// and spawns by hand: the engine hands back an edict, but it is up to us to run
// it through the same ClientConnect/ClientPutInServer path a real player takes.
// Bots send no usercmds, so BotThink() synthesises one for each of them every
// frame -- which is also the only reason gravity, touch and the rest of player
// physics run on them at all.
//
// The decisions in here are made from hull traces and from whether the bot
// actually moved, and from nothing else: there is no node graph, no navmesh and
// no knowledge of the map. That is deliberate. It means a bot can be dropped on
// any map, in any mod, and will get somewhere, which is what a bot used for
// filling out a round or for standing in front of a weapon has to do.

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Which HUD slot -- the 1-5 a player presses -- the bot's melee weapon is in,
// and what it goes back to afterwards.
//
//   MURDER 0: the crowbar is slot 1 and there is nothing to go back to, so the
//     bot draws it, swings, and leaves it out.
//   MURDER 1: the crowbar is in slot 2 and slot 1 holds whatever the bot would
//     rather be seen carrying, so a swing is draw slot 2, hit, back to slot 1.
#define MURDER 0

#if MURDER
#define BOT_MELEE_SLOT 2
#define BOT_STOW_SLOT 1
#else
#define BOT_MELEE_SLOT 1
#define BOT_STOW_SLOT 0 // 0: put nothing away when the swinging is done
#endif

// The slot a gun is looked for in when the crosshair crosses somebody. What is
// in it is only fired if it really is ranged -- if it has an ammo type -- so
// under MURDER 1, where this is the crowbar's slot, the check finds a melee
// weapon, fires nothing, and the melee behaviour above is all that happens.
#define BOT_RANGED_SLOT 2

// The engine's own ceiling on client slots. Not MAX_PLAYERS: that is a mod's
// constant and not every SDK has it, and this file is meant to drop into any of
// them.
constexpr int BOT_MAX_CLIENTS = 32;

// How far ahead the way is checked, how often the bot's own progress is
// sampled, and how far it has to have travelled in that time to count as
// moving. A single frame of movement is too small to tell from being stuck,
// which is why progress is sampled on an interval rather than per frame.
constexpr float BOT_LOOKAHEAD = 24.0f;
constexpr float BOT_PROGRESS_INTERVAL = 0.3f;
constexpr float BOT_PROGRESS_DISTANCE = 16.0f;

// The 18 units the engine walks a player up without being asked. A hull traced
// along the floor calls every staircase a wall, so the forward trace is retried
// from the top of a step before the way is believed shut.
constexpr float BOT_STEP_HEIGHT = 18.0f;

// Half the height of each hull, standing and ducked, measured from the feet.
constexpr float BOT_STAND_CENTRE = 36.0f;
constexpr float BOT_DUCK_CENTRE = 18.0f;

// UTIL_TraceHull's hull numbers. Spelled out rather than taken from util.h's
// enum, which not every SDK fork still has.
constexpr int BOT_HULL_STANDING = 1; // human_hull, 32x32x72
constexpr int BOT_HULL_DUCKING = 3;  // head_hull, 32x32x36

// A jump counts as having got somewhere if it ended this much higher than it
// started, or this much further along the heading.
constexpr float BOT_JUMP_GAIN_Z = 8.0f;
constexpr float BOT_JUMP_GAIN_FORWARD = 16.0f;

// A jump that has not landed by now is a fall, not a jump, and the bot stops
// holding its legs up and goes back to walking.
constexpr float BOT_JUMP_TIMEOUT = 2.0f;

// The smallest turn taken when a heading is given up on. Anything less and the
// bot walks back into the same wall from very nearly the same angle.
constexpr float BOT_TURN_MIN = 45.0f;

// How close another player has to be to be worth swinging at, measured between
// origins: a shade more than two player hulls, so the bot starts swinging as it
// bumps rather than after.
constexpr float BOT_MELEE_RANGE = 48.0f;
constexpr float BOT_MELEE_HEIGHT = 72.0f;

// How far a bot can see a target down its crosshair.
constexpr float BOT_SIGHT_RANGE = 2048.0f;

// Drawing a weapon takes the weapon's own deploy time, and a button pressed
// before that has run out is thrown away. This is comfortably longer than the
// half second every stock weapon's DefaultDeploy asks for.
constexpr float BOT_DRAW_TIME = 0.6f;

// How long the attack button is held for one swing, and how long it is let go
// of afterwards. The crowbar will swing again on a held button, but letting go
// keeps a swing a swing and gives the bot a frame to notice its victim left.
constexpr float BOT_SWING_TIME = 0.3f;
constexpr float BOT_RECOVER_TIME = 0.2f;

// A crosshair leaves a moving target for a frame at a time without the bot
// having lost it, and how long a failed weapon draw is waited out before it is
// tried again.
constexpr float BOT_TARGET_GRACE = 0.4f;
constexpr float BOT_DRAW_RETRY = 0.5f;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

enum BotMoveState
{
	MOVE_WANDER, // walking, ducking under things, turning
	MOVE_JUMP,   // committed to a crouch jump and seeing where it lands
};

enum BotMeleeState
{
	MELEE_IDLE,    // nothing in reach, nothing drawn on its account
	MELEE_DRAW,    // switched to the melee weapon, waiting for the deploy
	MELEE_SWING,   // attack held
	MELEE_RECOVER, // attack released, deciding whether to swing again
};

enum BotRangedState
{
	RANGED_IDLE,
	RANGED_DRAW,
	RANGED_FIRE,
};

struct bot_t
{
	// Whether this slot holds a bot is tracked here rather than read back off
	// pev->flags, because a disconnected player's edict is deliberately left
	// allocated (see ClientDisconnect) with its flags intact: a kicked bot
	// still looks like a live FL_FAKECLIENT for the rest of the map, and
	// calling pfnRunPlayerMove on a slot the engine no longer has a client in
	// crashes the server.
	bool bInUse;

	// The name the bot was created with. pev->netname cannot be trusted to
	// answer that question -- a mod that disguises or renames players writes
	// over both it and the userinfo name key, and then the next bot picks a
	// name that is already taken.
	char szName[32];

	float flYaw; // the heading being walked, and the whole of the bot's plan

	BotMoveState move;
	Vector vecLastOrigin;
	float flNextProgressCheck;

	Vector vecJumpStart;
	bool bAirborne; // left the floor, so it is time to tuck the legs up
	float flJumpExpire;

	BotMeleeState melee;
	float flMeleeNext;

	BotRangedState ranged;
	float flRangedNext;
	float flTargetLost; // 0 while the crosshair is still on somebody
};

static bot_t g_bots[BOT_MAX_CLIENTS + 1] = {};

static float g_flLastBotMoveTime = 0;

static cvar_t sp_bot = {"sp_bot", "0"};
static cvar_t sp_bot_quota = {"sp_bot_quota", "0"};

// Whether sp_bot_quota has ever been set to something. Until it has, a quota of
// zero means "not managed" rather than "kick everything", so the default value
// of a cvar nobody has touched does not throw out bots added with sp_bot.
static bool g_bQuotaTouched = false;

// The move being assembled for one bot this frame. Movement and combat both
// write into it -- combat takes the view, movement takes the legs -- and it is
// handed to the engine once, at the end.
struct botmove_t
{
	float flYaw;
	float flForward;
	int buttons;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static bool BotIsBotSlot(int index)
{
	return index >= 1 && index <= BOT_MAX_CLIENTS && g_bots[index].bInUse;
}

static int BotCount()
{
	int count = 0;

	for (int i = 1; i <= gpGlobals->maxClients && i <= BOT_MAX_CLIENTS; ++i)
	{
		if (g_bots[i].bInUse)
			++count;
	}

	return count;
}

static float BotMaxSpeed(CBasePlayer* pPlayer)
{
	// Whatever is asked for above the player's own maximum is clipped by the
	// movement code anyway; this only avoids asking for zero on a mod that
	// leaves maxspeed unset.
	return pPlayer->pev->maxspeed > 0 ? pPlayer->pev->maxspeed : 240.0f;
}

static void BotSampleProgress(bot_t* pBot, CBasePlayer* pPlayer)
{
	pBot->vecLastOrigin = pPlayer->pev->origin;
	pBot->flNextProgressCheck = gpGlobals->time + BOT_PROGRESS_INTERVAL;
}

// Gives up on the current heading for one at least BOT_TURN_MIN degrees off it,
// to either side.
static void BotTurnAway(bot_t* pBot, CBasePlayer* pPlayer)
{
	const float flTurn = RANDOM_FLOAT(BOT_TURN_MIN, 180.0f);

	pBot->flYaw = UTIL_AngleMod(pBot->flYaw + (RANDOM_LONG(0, 1) ? flTurn : -flTurn));
	BotSampleProgress(pBot, pPlayer);
}

// Is there room to walk BOT_LOOKAHEAD units along vecForward, standing or
// ducked? Traced as a hull rather than a line, because what matters is whether
// the player fits, and the whole point of the ducked answer is that the
// standing one does not fit.
static bool BotPathClear(CBasePlayer* pPlayer, const Vector& vecForward, bool bDuck)
{
	Vector vecFeet = pPlayer->pev->origin;

	vecFeet.z += pPlayer->pev->mins.z; // the bottom of whichever hull it has now

	const int hull = bDuck ? BOT_HULL_DUCKING : BOT_HULL_STANDING;
	const float flCentre = bDuck ? BOT_DUCK_CENTRE : BOT_STAND_CENTRE;

	// Two traces, and the second is the interesting one. Flat along the floor
	// first: if that is clear the bot can simply walk. If it is not, the same
	// trace from the top of a step answers the different question of whether
	// the thing in the way is something the engine will walk the bot up --
	// a stair lip, a kerb, a doorway's threshold -- and raising the hull is
	// safe here precisely because it is only asked once the flat trace has
	// already failed, so a low ceiling never reaches this trace on its own.
	for (int pass = 0; pass < 2; ++pass)
	{
		Vector vecStart = vecFeet;

		vecStart.z += flCentre + (pass ? BOT_STEP_HEIGHT : 0.0f);

		TraceResult tr;
		UTIL_TraceHull(vecStart, vecStart + vecForward * BOT_LOOKAHEAD,
			dont_ignore_monsters, hull, pPlayer->edict(), &tr);

		if (!tr.fAllSolid && !tr.fStartSolid && tr.flFraction == 1.0f)
			return true;
	}

	return false;
}

// The weapon at the head of a HUD slot's list, or NULL if the slot is empty.
static CBasePlayerItem* BotSlotWeapon(CBasePlayer* pPlayer, int slot)
{
	if (slot < 1 || slot >= MAX_ITEM_TYPES)
		return NULL;

	return pPlayer->m_rgpPlayerItems[slot];
}

// A weapon is ranged if it has an ammo type, which is the crowbar's answer to
// being asked whether it is a gun: pszAmmo1() is NULL for everything melee.
static bool BotWeaponIsRanged(CBasePlayer* pPlayer, CBasePlayerItem* pItem)
{
	const char* pszAmmo = pItem->pszAmmo1();

	if (!pszAmmo)
		return false;

	const int iAmmo = CBasePlayer::GetAmmoIndex(pszAmmo);

	if (iAmmo < 0 || iAmmo >= MAX_AMMO_SLOTS)
		return false;

	// A clip weapon with rounds still in it can fire with no reserve left, and
	// a weapon with no clip at all reports -1 and lives off the reserve.
	CBasePlayerWeapon* pWeapon = static_cast<CBasePlayerWeapon*>(pItem);

	return pWeapon->m_iClip > 0 || pPlayer->m_rgAmmo[iAmmo] > 0;
}

// The first thing in the gun slot that is a gun and has something to fire.
static CBasePlayerItem* BotRangedWeapon(CBasePlayer* pPlayer)
{
	for (CBasePlayerItem* pItem = BotSlotWeapon(pPlayer, BOT_RANGED_SLOT); pItem; pItem = pItem->m_pNext)
	{
		if (BotWeaponIsRanged(pPlayer, pItem))
			return pItem;
	}

	return NULL;
}

static void BotSelect(CBasePlayer* pPlayer, CBasePlayerItem* pItem)
{
	pPlayer->SelectItem(STRING(pItem->pev->classname));
}

// The nearest other living player close enough to be called a collision.
static CBasePlayer* BotMeleeVictim(CBasePlayer* pSelf)
{
	CBasePlayer* pNearest = NULL;
	float flNearest = BOT_MELEE_RANGE;

	for (int i = 1; i <= gpGlobals->maxClients && i <= BOT_MAX_CLIENTS; ++i)
	{
		CBaseEntity* pEntity = UTIL_PlayerByIndex(i);

		if (!pEntity || pEntity == pSelf || !pEntity->IsAlive())
			continue;

		const Vector vecDelta = pEntity->pev->origin - pSelf->pev->origin;

		if (fabs(vecDelta.z) > BOT_MELEE_HEIGHT)
			continue;

		const float flDistance = vecDelta.Length2D();

		if (flDistance > flNearest)
			continue;

		flNearest = flDistance;
		pNearest = static_cast<CBasePlayer*>(pEntity);
	}

	return pNearest;
}

// Whoever the bot's crosshair is on, if it is on anybody. Traced from the gun
// down the view, which is exactly what "the crosshair crossed them" means --
// the bot does not aim, it notices.
static CBasePlayer* BotCrosshairPlayer(CBasePlayer* pSelf, const Vector& vecAngles)
{
	Vector vecForward, vecRight, vecUp;
	UTIL_MakeVectorsPrivate(vecAngles, vecForward, vecRight, vecUp);

	const Vector vecSrc = pSelf->GetGunPosition();

	TraceResult tr;
	UTIL_TraceLine(vecSrc, vecSrc + vecForward * BOT_SIGHT_RANGE,
		dont_ignore_monsters, pSelf->edict(), &tr);

	if (FNullEnt(tr.pHit))
		return NULL;

	CBaseEntity* pHit = CBaseEntity::Instance(tr.pHit);

	if (!pHit || !pHit->IsPlayer() || !pHit->IsAlive())
		return NULL;

	return static_cast<CBasePlayer*>(pHit);
}

// ---------------------------------------------------------------------------
// Combat
// ---------------------------------------------------------------------------

static void BotStowMelee(CBasePlayer* pPlayer)
{
	// Under MURDER 0 there is nothing to go back to and the melee weapon stays
	// out, which is the difference between the two settings.
	if (0 == BOT_STOW_SLOT)
		return;

	CBasePlayerItem* pStow = BotSlotWeapon(pPlayer, BOT_STOW_SLOT);

	if (pStow)
		BotSelect(pPlayer, pStow);
}

// Returns true while a swing is in progress, which is the signal to the rest of
// the frame that the view belongs to the fight and that a bot standing still to
// hit somebody has not stopped making progress.
static bool BotMeleeThink(bot_t* pBot, CBasePlayer* pPlayer, botmove_t& move)
{
	CBasePlayer* pVictim = BotMeleeVictim(pPlayer);

	if (MELEE_IDLE == pBot->melee)
	{
		CBasePlayerItem* pMelee = BotSlotWeapon(pPlayer, BOT_MELEE_SLOT);

		if (!pVictim || !pMelee || gpGlobals->time < pBot->flMeleeNext)
			return false;

		BotSelect(pPlayer, pMelee);

		pBot->melee = MELEE_DRAW;
		pBot->flMeleeNext = gpGlobals->time + BOT_DRAW_TIME;
	}

	// Face what is being hit. A swing is a short trace straight out of the
	// bot's own view, so a bot that keeps its wandering heading misses from
	// touching distance. The heading itself is left alone: when the fight is
	// over the bot carries on the way it was going.
	if (pVictim)
		move.flYaw = UTIL_VecToYaw(pVictim->pev->origin - pPlayer->pev->origin);

	switch (pBot->melee)
	{
	case MELEE_DRAW:
		if (gpGlobals->time >= pBot->flMeleeNext)
		{
			pBot->melee = MELEE_SWING;
			pBot->flMeleeNext = gpGlobals->time + BOT_SWING_TIME;
		}
		break;

	case MELEE_SWING:
		move.buttons |= IN_ATTACK;

		if (gpGlobals->time >= pBot->flMeleeNext)
		{
			pBot->melee = MELEE_RECOVER;
			pBot->flMeleeNext = gpGlobals->time + BOT_RECOVER_TIME;
		}
		break;

	case MELEE_RECOVER:
		if (gpGlobals->time >= pBot->flMeleeNext)
		{
			if (pVictim)
			{
				pBot->melee = MELEE_SWING;
				pBot->flMeleeNext = gpGlobals->time + BOT_SWING_TIME;
			}
			else
			{
				// Nothing left to hit: put it away, and do not draw it again
				// on the very next frame if the victim is merely out of reach
				// rather than gone.
				BotStowMelee(pPlayer);

				pBot->melee = MELEE_IDLE;
				pBot->flMeleeNext = gpGlobals->time + BOT_DRAW_RETRY;
			}
		}
		break;

	default:
		break;
	}

	return MELEE_IDLE != pBot->melee;
}

static void BotRangedThink(bot_t* pBot, CBasePlayer* pPlayer, botmove_t& move)
{
	CBasePlayerItem* pGun = BotRangedWeapon(pPlayer);
	CBasePlayer* pTarget = BotCrosshairPlayer(pPlayer, Vector(0, move.flYaw, 0));

	switch (pBot->ranged)
	{
	case RANGED_IDLE:
		if (!pTarget || !pGun || gpGlobals->time < pBot->flRangedNext)
			break;

		if (pPlayer->m_pActiveItem == pGun)
		{
			// Already holding it, so there is nothing to wait for.
			pBot->ranged = RANGED_FIRE;
		}
		else
		{
			BotSelect(pPlayer, pGun);

			pBot->ranged = RANGED_DRAW;
			pBot->flRangedNext = gpGlobals->time + BOT_DRAW_TIME;
		}

		pBot->flTargetLost = 0;
		break;

	case RANGED_DRAW:
		if (gpGlobals->time < pBot->flRangedNext)
			break;

		if (pPlayer->m_pActiveItem != pGun)
		{
			// The switch did not take -- something else is holding the
			// inventory. Wait before asking again rather than asking every
			// frame for the rest of the map.
			pBot->ranged = RANGED_IDLE;
			pBot->flRangedNext = gpGlobals->time + BOT_DRAW_RETRY;
			break;
		}

		pBot->ranged = RANGED_FIRE;
		break;

	case RANGED_FIRE:
		if (!pGun || pPlayer->m_pActiveItem != pGun)
		{
			// Out of ammo, or somebody took the gun off it.
			pBot->ranged = RANGED_IDLE;
			pBot->flRangedNext = gpGlobals->time + BOT_DRAW_RETRY;
			break;
		}

		if (pTarget)
		{
			move.buttons |= IN_ATTACK;
			pBot->flTargetLost = 0;
			break;
		}

		if (0 == pBot->flTargetLost)
			pBot->flTargetLost = gpGlobals->time;
		else if (gpGlobals->time - pBot->flTargetLost > BOT_TARGET_GRACE)
			pBot->ranged = RANGED_IDLE;
		break;
	}
}

// ---------------------------------------------------------------------------
// Movement
// ---------------------------------------------------------------------------

static void BotBeginJump(bot_t* pBot, CBasePlayer* pPlayer)
{
	pBot->move = MOVE_JUMP;
	pBot->vecJumpStart = pPlayer->pev->origin;
	pBot->bAirborne = false;
	pBot->flJumpExpire = gpGlobals->time + BOT_JUMP_TIMEOUT;
}

static void BotBeginWander(bot_t* pBot, CBasePlayer* pPlayer)
{
	pBot->move = MOVE_WANDER;
	pBot->bAirborne = false;
	BotSampleProgress(pBot, pPlayer);
}

static void BotJumpThink(bot_t* pBot, CBasePlayer* pPlayer, botmove_t& move, const Vector& vecForward)
{
	const bool bOnGround = FBitSet(pPlayer->pev->flags, FL_ONGROUND) != 0;

	// Forward the whole way through: the jump is there to get somewhere, and a
	// crouch jump on the spot clears the obstacle and lands back in front of
	// it.
	move.flForward = BotMaxSpeed(pPlayer);

	// Checked before anything else, and on the ground as well as in the air.
	// A jump that has not landed by now is a long fall -- but a bot that never
	// left the ground at all is somewhere a jump does not work, on a ladder or
	// in water or against a slope too steep to leave, and it would otherwise
	// hold the button down there for the rest of the map.
	if (gpGlobals->time >= pBot->flJumpExpire)
	{
		BotBeginWander(pBot, pPlayer);
		BotTurnAway(pBot, pPlayer);
		return;
	}

	if (!pBot->bAirborne)
	{
		// Jump first and duck second, never both at once. That order is the
		// whole trick: the jump gets its full height from a standing player,
		// and ducking afterwards tucks the legs up for the last 18 units of
		// clearance. Pressing duck first gets neither.
		if (bOnGround)
			move.buttons |= IN_JUMP;
		else
			pBot->bAirborne = true;

		return;
	}

	move.buttons |= IN_DUCK;

	if (bOnGround)
	{
		// Landed. It got somewhere if it came down higher than it went up, or
		// further along the heading than the wall it was standing against --
		// either way the obstacle is behind it now and the heading is worth
		// keeping. If not, the heading is what is wrong.
		const Vector vecTravel = pPlayer->pev->origin - pBot->vecJumpStart;
		const bool bGained = vecTravel.z > BOT_JUMP_GAIN_Z ||
							 DotProduct(vecTravel, vecForward) > BOT_JUMP_GAIN_FORWARD;

		BotBeginWander(pBot, pPlayer);

		if (!bGained)
			BotTurnAway(pBot, pPlayer);

		return;
	}
}

static void BotMoveThink(bot_t* pBot, CBasePlayer* pPlayer, botmove_t& move, bool bFighting)
{
	Vector vecForward, vecRight, vecUp;
	UTIL_MakeVectorsPrivate(Vector(0, pBot->flYaw, 0), vecForward, vecRight, vecUp);

	if (MOVE_JUMP == pBot->move)
	{
		BotJumpThink(pBot, pPlayer, move, vecForward);
		return;
	}

	if (bFighting)
	{
		// Walk into whoever is being hit -- move.flYaw is already pointed at
		// them -- and do not read anything into having stopped moving, which
		// is what hitting somebody looks like from here.
		move.flForward = BotMaxSpeed(pPlayer);
		BotSampleProgress(pBot, pPlayer);
		return;
	}

	// Two ways to find out the way ahead is shut. The trace sees a wall before
	// the bot is pressed against it; the progress sample catches everything the
	// trace is too coarse for -- a corner taken at a shallow angle, a door
	// pushing back, another player in the way, a slope too steep to climb.
	bool bStuck = false;

	if (gpGlobals->time >= pBot->flNextProgressCheck)
	{
		bStuck = (pPlayer->pev->origin - pBot->vecLastOrigin).Length2D() < BOT_PROGRESS_DISTANCE;
		BotSampleProgress(pBot, pPlayer);
	}

	// The loop, in order: walk; duck and carry on if ducking is what opens the
	// way; otherwise crouch-jump it, and let the landing decide whether the
	// heading survives.
	if (!bStuck && BotPathClear(pPlayer, vecForward, false))
	{
		// Nothing in the way standing up. Note that the standing trace answers
		// the headroom question too: its hull is the full 72 tall, so a bot
		// under a vent's ceiling finds it blocked and stays ducked.
	}
	else if (!bStuck && BotPathClear(pPlayer, vecForward, true))
	{
		move.buttons |= IN_DUCK;
	}
	else if (FBitSet(pPlayer->pev->flags, FL_ONGROUND))
	{
		BotBeginJump(pBot, pPlayer);
		move.buttons |= IN_JUMP;
	}

	move.flForward = BotMaxSpeed(pPlayer);
}

// ---------------------------------------------------------------------------
// Connecting and kicking
// ---------------------------------------------------------------------------

// Picks a name no connected player is already using, so the engine does not
// rename the fake client behind our back.
static void BotPickName(char* out, int outSize)
{
	for (int suffix = 1; suffix < 128; ++suffix)
	{
		char candidate[32];
		snprintf(candidate, sizeof(candidate), "Bot%d", suffix);

		bool taken = false;

		for (int i = 1; i <= gpGlobals->maxClients && i <= BOT_MAX_CLIENTS; ++i)
		{
			if (g_bots[i].bInUse && FStrEq(g_bots[i].szName, candidate))
			{
				taken = true;
				break;
			}

			CBaseEntity* pPlayer = UTIL_PlayerByIndex(i);

			if (pPlayer && FStrEq(STRING(pPlayer->pev->netname), candidate))
			{
				taken = true;
				break;
			}
		}

		if (!taken)
		{
			strncpy(out, candidate, outSize - 1);
			out[outSize - 1] = '\0';
			return;
		}
	}

	strncpy(out, "Bot", outSize - 1);
	out[outSize - 1] = '\0';
}

static bool BotAdd()
{
	if (!g_pGameRules)
	{
		ALERT(at_console, "Can't add a bot: no map loaded\n");
		return false;
	}

	char name[32];
	BotPickName(name, sizeof(name));

	edict_t* pEdict = g_engfuncs.pfnCreateFakeClient(name);

	if (FNullEnt(pEdict))
	{
		ALERT(at_console, "Can't add a bot: server is full\n");
		return false;
	}

	const int index = ENTINDEX(pEdict);

	if (index < 1 || index > BOT_MAX_CLIENTS)
	{
		ALERT(at_console, "Can't add a bot: bad client slot %d\n", index);
		return false;
	}

	char* infobuffer = g_engfuncs.pfnGetInfoKeyBuffer(pEdict);

	// The engine gives a fake client an empty userinfo; without a model and
	// colours other clients have nothing to draw it with.
	g_engfuncs.pfnSetClientKeyValue(index, infobuffer, "model", "gordon");
	g_engfuncs.pfnSetClientKeyValue(index, infobuffer, "topcolor", "30");
	g_engfuncs.pfnSetClientKeyValue(index, infobuffer, "bottomcolor", "6");

	char rejectReason[128] = "";

	if (0 == ClientConnect(pEdict, name, "127.0.0.1", rejectReason))
	{
		ALERT(at_console, "Can't add a bot: %s\n", rejectReason);
		SERVER_COMMAND(UTIL_VarArgs("kick # %d\n", GETPLAYERUSERID(pEdict)));
		return false;
	}

	ClientPutInServer(pEdict);

	// Spawn() keeps FL_FAKECLIENT (player.cpp masks the flags), but set it
	// anyway so nothing downstream can mistake a bot for a real client.
	pEdict->v.flags |= FL_FAKECLIENT;

	bot_t* pBot = &g_bots[index];

	*pBot = bot_t();

	pBot->bInUse = true;

	strncpy(pBot->szName, name, sizeof(pBot->szName) - 1);
	pBot->szName[sizeof(pBot->szName) - 1] = '\0';

	pBot->flYaw = RANDOM_FLOAT(-180, 180);
	pBot->move = MOVE_WANDER;
	pBot->melee = MELEE_IDLE;
	pBot->ranged = RANGED_IDLE;
	pBot->vecLastOrigin = pEdict->v.origin;
	pBot->flNextProgressCheck = gpGlobals->time + BOT_PROGRESS_INTERVAL;

	ALERT(at_console, "Added bot \"%s\"\n", name);
	return true;
}

// Drops one bot's slot and queues the kick. The slot is forgotten now rather
// than when the kick runs: kick is queued in the command buffer and happens
// after this frame, and nothing should synthesise a move for a bot on its way
// out.
static void BotKick(int index)
{
	g_bots[index].bInUse = false;
	g_bots[index].szName[0] = '\0';

	SERVER_COMMAND(UTIL_VarArgs("kick # %d\n", GETPLAYERUSERID(INDEXENT(index))));
}

static void BotKickAll()
{
	int kicked = 0;

	for (int i = 1; i <= gpGlobals->maxClients && i <= BOT_MAX_CLIENTS; ++i)
	{
		if (!g_bots[i].bInUse)
			continue;

		BotKick(i);
		++kicked;
	}

	// Whatever the quota was, it is not what the player just asked for.
	CVAR_SET_FLOAT("sp_bot_quota", 0);
	g_bQuotaTouched = false;

	ALERT(at_console, "Kicked %d bot%s\n", kicked, 1 == kicked ? "" : "s");
}

static void BotServiceCvars()
{
	// sp_bot is a request rather than a setting: it says "add this many", and
	// is put back to zero once they are in so that setting it again adds more.
	const int iRequest = static_cast<int>(sp_bot.value);

	if (iRequest > 0)
	{
		for (int i = 0; i < iRequest; ++i)
		{
			if (!BotAdd())
				break;
		}

		CVAR_SET_FLOAT("sp_bot", 0);
	}

	const int iQuota = static_cast<int>(sp_bot_quota.value);

	if (iQuota > 0)
		g_bQuotaTouched = true;

	if (!g_bQuotaTouched)
		return;

	// One per frame in either direction. Connecting is not free, and a kick
	// does not take effect until the command buffer runs, so counting again
	// next frame is the only honest way to know where we are.
	const int iCount = BotCount();

	if (iCount < iQuota)
	{
		BotAdd();
		return;
	}

	if (iCount > iQuota)
	{
		for (int i = gpGlobals->maxClients < BOT_MAX_CLIENTS ? gpGlobals->maxClients : BOT_MAX_CLIENTS; i >= 1; --i)
		{
			if (g_bots[i].bInUse)
			{
				BotKick(i);
				break;
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

void BotInit()
{
	CVAR_REGISTER(&sp_bot);
	CVAR_REGISTER(&sp_bot_quota);

	g_engfuncs.pfnAddServerCommand("sp_bot_kickall", &BotKickAll);
}

void BotClientDisconnected(edict_t* pEntity)
{
	const int index = ENTINDEX(pEntity);

	if (index >= 1 && index <= BOT_MAX_CLIENTS)
	{
		g_bots[index].bInUse = false;
		g_bots[index].szName[0] = '\0';
	}
}

void BotThink()
{
	BotServiceCvars();

	const float flDelta = gpGlobals->time - g_flLastBotMoveTime;

	g_flLastBotMoveTime = gpGlobals->time;

	// Guard against the first frame of a level, where the delta is meaningless.
	if (flDelta <= 0 || flDelta > 1.0f)
		return;

	const int iMsec = static_cast<int>(flDelta * 1000.0f);
	const byte msec = static_cast<byte>(iMsec < 1 ? 1 : (iMsec > 255 ? 255 : iMsec));

	for (int i = 1; i <= gpGlobals->maxClients && i <= BOT_MAX_CLIENTS; ++i)
	{
		if (!BotIsBotSlot(i))
			continue;

		CBaseEntity* pEntity = UTIL_PlayerByIndex(i);

		if (!pEntity || !FBitSet(pEntity->pev->flags, FL_FAKECLIENT))
			continue;

		CBasePlayer* pPlayer = static_cast<CBasePlayer*>(pEntity);
		bot_t* pBot = &g_bots[i];

		// A dead bot still gets a move, empty of everything: it exists purely
		// so the engine runs player physics on a client that never sends a
		// usercmd of its own.
		if (!pPlayer->IsAlive())
		{
			pBot->melee = MELEE_IDLE;
			pBot->ranged = RANGED_IDLE;
			pBot->move = MOVE_WANDER;

			g_engfuncs.pfnRunPlayerMove(pPlayer->edict(), pPlayer->pev->v_angle, 0, 0, 0, 0, 0, msec);
			continue;
		}

		botmove_t move;

		move.flYaw = pBot->flYaw;
		move.flForward = 0;
		move.buttons = 0;

		// Melee first, and it wins: something within crowbar reach outranks
		// something across the room, and while a swing is in progress the gun
		// stays holstered.
		const bool bFighting = BotMeleeThink(pBot, pPlayer, move);

		if (bFighting)
		{
			pBot->ranged = RANGED_IDLE;

			// Whatever the bot is jumping over matters less than the player
			// standing on top of it.
			pBot->move = MOVE_WANDER;
			pBot->bAirborne = false;
		}
		else
		{
			BotRangedThink(pBot, pPlayer, move);
		}

		BotMoveThink(pBot, pPlayer, move, bFighting);

		const Vector vecAngles(0, move.flYaw, 0);

		// Face where it is going, so other players see the bot turn. The
		// engine sets these from the move as well, but not before anything
		// else this frame reads them.
		pPlayer->pev->angles = vecAngles;
		pPlayer->pev->v_angle = vecAngles;

		g_engfuncs.pfnRunPlayerMove(pPlayer->edict(), vecAngles, move.flForward, 0, 0,
			static_cast<unsigned short>(move.buttons), 0, msec);
	}
}
