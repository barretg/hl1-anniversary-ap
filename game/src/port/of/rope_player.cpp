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
// Opposing Force's rope handling from CBasePlayer::PreThink, split out so the
// SDK's player.cpp only gains the call. Only env_rope sets PFLAG_ONROPE.

#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"
#include "CRope.h"

bool CBasePlayer::RopeThink()
{
	if ((m_afPhysicsFlags & PFLAG_ONROPE) == 0 || !m_pRope)
		return false;

	pev->velocity = g_vecZero;

	const Vector vecAttachPos = m_pRope->GetAttachedObjectsPosition();

	pev->origin = vecAttachPos;

	Vector vecForce;

	if ((pev->button & IN_MOVERIGHT) != 0)
	{
		vecForce.x = gpGlobals->v_right.x;
		vecForce.y = gpGlobals->v_right.y;
		vecForce.z = 0;

		m_pRope->ApplyForceFromPlayer(vecForce);
	}

	if ((pev->button & IN_MOVELEFT) != 0)
	{
		vecForce.x = -gpGlobals->v_right.x;
		vecForce.y = -gpGlobals->v_right.y;
		vecForce.z = 0;
		m_pRope->ApplyForceFromPlayer(vecForce);
	}

	//Determine if any force should be applied to the rope, or if we should move around. - Solokiller
	if ((pev->button & (IN_BACK | IN_FORWARD)) != 0)
	{
		if ((gpGlobals->v_forward.x * gpGlobals->v_forward.x +
				gpGlobals->v_forward.y * gpGlobals->v_forward.y -
				gpGlobals->v_forward.z * gpGlobals->v_forward.z) <= 0)
		{
			if (m_bIsClimbing)
			{
				const float flDelta = gpGlobals->time - m_flLastClimbTime;
				m_flLastClimbTime = gpGlobals->time;

				if ((pev->button & IN_FORWARD) != 0)
				{
					if (gpGlobals->v_forward.z < 0.0)
					{
						if (!m_pRope->MoveDown(flDelta))
						{
							//Let go of the rope, detach. - Solokiller
							pev->movetype = MOVETYPE_WALK;
							pev->solid = SOLID_SLIDEBOX;

							m_afPhysicsFlags &= ~PFLAG_ONROPE;
							m_pRope->DetachObject();
							m_pRope = nullptr;
							m_bIsClimbing = false;
						}
					}
					else
					{
						m_pRope->MoveUp(flDelta);
					}
				}
				if ((pev->button & IN_BACK) != 0)
				{
					if (gpGlobals->v_forward.z < 0.0)
					{
						m_pRope->MoveUp(flDelta);
					}
					else if (!m_pRope->MoveDown(flDelta))
					{
						//Let go of the rope, detach. - Solokiller
						pev->movetype = MOVETYPE_WALK;
						pev->solid = SOLID_SLIDEBOX;
						m_afPhysicsFlags &= ~PFLAG_ONROPE;
						m_pRope->DetachObject();
						m_pRope = nullptr;
						m_bIsClimbing = false;
					}
				}
			}
			else
			{
				m_bIsClimbing = true;
				m_flLastClimbTime = gpGlobals->time;
			}
		}
		else
		{
			vecForce.x = gpGlobals->v_forward.x;
			vecForce.y = gpGlobals->v_forward.y;
			vecForce.z = 0.0;
			if ((pev->button & IN_BACK) != 0)
			{
				vecForce.x = -gpGlobals->v_forward.x;
				vecForce.y = -gpGlobals->v_forward.y;
				vecForce.z = 0;
			}
			m_pRope->ApplyForceFromPlayer(vecForce);
			m_bIsClimbing = false;
		}
	}
	else
	{
		m_bIsClimbing = false;
	}

	if ((m_afButtonPressed & IN_JUMP) != 0)
	{
		//We've jumped off the rope, give us some momentum - Solokiller
		pev->movetype = MOVETYPE_WALK;
		pev->solid = SOLID_SLIDEBOX;
		m_afPhysicsFlags &= ~PFLAG_ONROPE;

		Vector vecDir = gpGlobals->v_up * 165.0 + gpGlobals->v_forward * 150.0;

		Vector vecVelocity = m_pRope->GetAttachedObjectsVelocity() * 2;

		vecVelocity = vecVelocity.Normalize();

		vecVelocity = vecVelocity * 200;

		pev->velocity = vecVelocity + vecDir;

		m_pRope->DetachObject();
		m_pRope = nullptr;
		m_bIsClimbing = false;
	}

	return true;
}
