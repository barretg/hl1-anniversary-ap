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
// Opposing Force's gameplay cvars that its ported code reads. Not registered:
// each stays at its retail default, which is the value it is created with.

#include "extdll.h"
#include "util.h"

cvar_t oldgrapple = {"sv_oldgrapple", "0", FCVAR_SERVER};
