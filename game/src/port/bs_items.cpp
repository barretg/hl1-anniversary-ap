/***
*
*	Copyright (c) 1996-2001, Valve LLC. All rights reserved.
*
*	This product contains software technology licensed from Id
*	Software, Inc. ("Id Technology").  Id Technology (c) 1996 Id Software, Inc.
*	All Rights Reserved.
*
*   Use, distribution, and modification of this source code and/or resulting
*   object code is restricted to non-commercial enhancements to products from
*   Valve LLC.  All other use, distribution, or modification is prohibited
*   without written permission from Valve LLC.
*
****/
// Blue Shift's security armour and its player freeze trigger, ported from
// halflife-bs-updated (items.cpp, triggers.cpp) to this SDK's conventions.

#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "weapons.h"
#include "items.h"
#include "gamerules.h"

extern int gmsgItemPickup;

// A Barney pickup: armour by `amount`, like a battery, and reported the same way.
static BOOL GiveSecurityArmor( CBaseEntity *pItem, CBasePlayer *pPlayer, float amount )
{
	if ( pPlayer->pev->deadflag != DEAD_NO )
		return FALSE;

	if ( pPlayer->pev->armorvalue >= MAX_NORMAL_BATTERY || !( pPlayer->pev->weapons & ( 1 << WEAPON_SUIT ) ) )
		return FALSE;

	pPlayer->pev->armorvalue += amount;
	pPlayer->pev->armorvalue = min<float>( pPlayer->pev->armorvalue, MAX_NORMAL_BATTERY );

	EMIT_SOUND( pPlayer->edict(), CHAN_ITEM, "items/gunpickup2.wav", 1, ATTN_NORM );

	MESSAGE_BEGIN( MSG_ONE, gmsgItemPickup, NULL, pPlayer->pev );
		WRITE_STRING( STRING( pItem->pev->classname ) );
	MESSAGE_END();

	// Suit reports new power level
	int pct = (int)( (float)( pPlayer->pev->armorvalue * 100.0 ) * ( 1.0 / MAX_NORMAL_BATTERY ) + 0.5 );
	pct = ( pct / 5 );
	if ( pct > 0 )
		pct--;

	char szcharge[64];
	sprintf( szcharge, "!HEV_%1dP", pct );
	pPlayer->SetSuitUpdate( szcharge, FALSE, SUIT_NEXT_IN_30SEC );
	return TRUE;
}

class CItemHelmet : public CItem
{
	void Spawn( void )
	{
		Precache();
		SET_MODEL( ENT( pev ), "models/Barney_Helmet.mdl" );
		CItem::Spawn();
	}
	void Precache( void )
	{
		PRECACHE_MODEL( "models/Barney_Helmet.mdl" );
		PRECACHE_SOUND( "items/gunpickup2.wav" );
	}
	BOOL MyTouch( CBasePlayer *pPlayer )
	{
		return GiveSecurityArmor( this, pPlayer, 40 );
	}
};

LINK_ENTITY_TO_CLASS( item_helmet, CItemHelmet );

class CItemArmorVest : public CItem
{
	void Spawn( void )
	{
		Precache();
		SET_MODEL( ENT( pev ), "models/Barney_Vest.mdl" );
		CItem::Spawn();
	}
	void Precache( void )
	{
		PRECACHE_MODEL( "models/Barney_Vest.mdl" );
		PRECACHE_SOUND( "items/gunpickup2.wav" );
	}
	BOOL MyTouch( CBasePlayer *pPlayer )
	{
		return GiveSecurityArmor( this, pPlayer, 60 );
	}
};

LINK_ENTITY_TO_CLASS( item_armorvest, CItemArmorVest );

// Toggles the player's controls each time it is used; frozen state survives a save.
class CTriggerPlayerFreeze : public CBaseDelay
{
public:
	void Spawn( void );
	void Use( CBaseEntity *pActivator, CBaseEntity *pCaller, USE_TYPE useType, float value );
	void EXPORT PlayerFreezeDelay( void );

	virtual int Save( CSave &save );
	virtual int Restore( CRestore &restore );
	static TYPEDESCRIPTION m_SaveData[];

	BOOL m_bUnFrozen;
};

LINK_ENTITY_TO_CLASS( trigger_playerfreeze, CTriggerPlayerFreeze );

TYPEDESCRIPTION CTriggerPlayerFreeze::m_SaveData[] =
{
	DEFINE_FIELD( CTriggerPlayerFreeze, m_bUnFrozen, FIELD_BOOLEAN ),
};

int CTriggerPlayerFreeze::Save( CSave &save )
{
	if ( !CBaseDelay::Save( save ) )
		return 0;
	return save.WriteFields( "CTriggerPlayerFreeze", this, m_SaveData, ARRAYSIZE( m_SaveData ) );
}

int CTriggerPlayerFreeze::Restore( CRestore &restore )
{
	if ( !CBaseDelay::Restore( restore ) )
		return 0;
	if ( !restore.ReadFields( "CTriggerPlayerFreeze", this, m_SaveData, ARRAYSIZE( m_SaveData ) ) )
		return 0;

	// The engine does not keep FL_FROZEN across a load, so apply it again.
	if ( !m_bUnFrozen )
	{
		SetThink( &CTriggerPlayerFreeze::PlayerFreezeDelay );
		pev->nextthink = gpGlobals->time + 0.5;
	}
	return 1;
}

void CTriggerPlayerFreeze::Spawn( void )
{
	if ( g_pGameRules->IsDeathmatch() )
		REMOVE_ENTITY( edict() );
	else
		m_bUnFrozen = TRUE;
}

void CTriggerPlayerFreeze::Use( CBaseEntity *pActivator, CBaseEntity *pCaller, USE_TYPE useType, float value )
{
	m_bUnFrozen = !m_bUnFrozen;

	CBasePlayer *pPlayer = (CBasePlayer *)UTIL_PlayerByIndex( 1 );
	if ( pPlayer )
		pPlayer->EnableControl( m_bUnFrozen );
}

void CTriggerPlayerFreeze::PlayerFreezeDelay( void )
{
	CBasePlayer *pPlayer = (CBasePlayer *)UTIL_PlayerByIndex( 1 );
	if ( pPlayer )
		pPlayer->EnableControl( m_bUnFrozen );

	SetThink( NULL );
}
