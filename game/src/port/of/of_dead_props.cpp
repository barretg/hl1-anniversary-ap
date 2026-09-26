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
//=========================================================
// Opposing Force's dead houndeye and alien slave props, which it added to
// houndeye.cpp and islave.cpp. Self-contained, so kept out of those files.
//=========================================================

#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "monsters.h"
#include "port_compat.h"

//=========================================================
// DEAD HOUNDEYE PROP
//=========================================================
class CDeadHoundeye : public CBaseMonster
{
public:
	void Spawn() override;
	int Classify() override { return CLASS_ALIEN_PASSIVE; }

	void KeyValue(KeyValueData* pkvd) override;

	int m_iPose; // which sequence to display	-- temporary, don't need to save
	static char* m_szPoses[3];
};

char* CDeadHoundeye::m_szPoses[] = {"dead"};

void CDeadHoundeye::KeyValue(KeyValueData* pkvd)
{
	if (FStrEq(pkvd->szKeyName, "pose"))
	{
		m_iPose = atoi(pkvd->szValue);
		{ pkvd->fHandled = TRUE; return; }
	}

	{ CBaseMonster::KeyValue(pkvd); return; }
}

LINK_ENTITY_TO_CLASS(monster_houndeye_dead, CDeadHoundeye);

//=========================================================
// ********** DeadHoundeye SPAWN **********
//=========================================================
void CDeadHoundeye::Spawn()
{
	PRECACHE_MODEL("models/houndeye_dead.mdl");
	SET_MODEL(ENT(pev), "models/houndeye_dead.mdl");

	pev->effects = 0;
	pev->yaw_speed = 8;
	pev->sequence = 0;
	m_bloodColor = BLOOD_COLOR_GREEN;

	pev->sequence = LookupSequence(m_szPoses[m_iPose]);

	if (pev->sequence == -1)
	{
		ALERT(at_console, "Dead houndeye with bad pose\n");
	}

	// Corpses have less health
	pev->health = 8;

	MonsterInitDead();
}

//=========================================================
// DEAD ALIEN SLAVE PROP
//
// Designer selects a pose in worldcraft, 0 through num_poses-1
// this value is added to what is selected as the 'first dead pose'
// among the monster's normal animations. All dead poses must
// appear sequentially in the model file. Be sure and set
// the m_iFirstPose properly!
//
//=========================================================
class CDeadISlave : public CBaseMonster
{
public:
	void Spawn() override;
	int Classify() override { return CLASS_ALIEN_PASSIVE; }

	void KeyValue(KeyValueData* pkvd) override;

	int m_iPose; // which sequence to display	-- temporary, don't need to save
	static char* m_szPoses[1];
};

char* CDeadISlave::m_szPoses[] = {"dead_on_stomach"};

void CDeadISlave::KeyValue(KeyValueData* pkvd)
{
	if (FStrEq(pkvd->szKeyName, "pose"))
	{
		m_iPose = atoi(pkvd->szValue);
		{ pkvd->fHandled = TRUE; return; }
	}

	{ CBaseMonster::KeyValue(pkvd); return; }
}

LINK_ENTITY_TO_CLASS(monster_alien_slave_dead, CDeadISlave);

//=========================================================
// ********** DeadISlave SPAWN **********
//=========================================================
void CDeadISlave::Spawn()
{
	PRECACHE_MODEL("models/islave.mdl");
	SET_MODEL(ENT(pev), "models/islave.mdl");

	pev->effects = 0;
	pev->sequence = 0;
	m_bloodColor = BLOOD_COLOR_GREEN;

	pev->sequence = LookupSequence(m_szPoses[m_iPose]);
	if (pev->sequence == -1)
	{
		ALERT(at_console, "Dead slave with bad pose\n");
	}
	// Corpses have less health
	pev->health = 8; //gSkillData.slaveHealth;

	MonsterInitDead();
}
