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

// Opposing Force's skill settings, from halflife-op4-updated's game.cpp and
// gamerules.cpp. Registered alongside Half-Life's; the values come from
// skillopfor.cfg, which the content installer links in and GameDLLInit execs.

#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "skill.h"
#include "ap_main.h"

#define DECLARE_SKILL_CVARS(name) \
	cvar_t sk_##name##1 = {"sk_" #name "1", "0"}; \
	cvar_t sk_##name##2 = {"sk_" #name "2", "0"}; \
	cvar_t sk_##name##3 = {"sk_" #name "3", "0"}
#define REGISTER_SKILL_CVARS(name) \
	CVAR_REGISTER(&sk_##name##1); \
	CVAR_REGISTER(&sk_##name##2); \
	CVAR_REGISTER(&sk_##name##3)

DECLARE_SKILL_CVARS(otis_health);
DECLARE_SKILL_CVARS(pitdrone_health);
DECLARE_SKILL_CVARS(pitdrone_dmg_bite);
DECLARE_SKILL_CVARS(pitdrone_dmg_whip);
DECLARE_SKILL_CVARS(pitdrone_dmg_spit);
DECLARE_SKILL_CVARS(shockroach_health);
DECLARE_SKILL_CVARS(shockroach_dmg_bite);
DECLARE_SKILL_CVARS(shockroach_lifespan);
DECLARE_SKILL_CVARS(hgrunt_ally_health);
DECLARE_SKILL_CVARS(hgrunt_ally_kick);
DECLARE_SKILL_CVARS(hgrunt_ally_pellets);
DECLARE_SKILL_CVARS(hgrunt_ally_gspeed);
DECLARE_SKILL_CVARS(medic_ally_health);
DECLARE_SKILL_CVARS(medic_ally_kick);
DECLARE_SKILL_CVARS(medic_ally_pellets);
DECLARE_SKILL_CVARS(medic_ally_gspeed);
DECLARE_SKILL_CVARS(medic_ally_heal);
DECLARE_SKILL_CVARS(torch_ally_health);
DECLARE_SKILL_CVARS(torch_ally_kick);
DECLARE_SKILL_CVARS(torch_ally_pellets);
DECLARE_SKILL_CVARS(torch_ally_gspeed);
DECLARE_SKILL_CVARS(massassin_health);
DECLARE_SKILL_CVARS(massassin_kick);
DECLARE_SKILL_CVARS(massassin_pellets);
DECLARE_SKILL_CVARS(massassin_gspeed);
DECLARE_SKILL_CVARS(shocktrooper_health);
DECLARE_SKILL_CVARS(shocktrooper_kick);
DECLARE_SKILL_CVARS(shocktrooper_gspeed);
DECLARE_SKILL_CVARS(shocktrooper_maxcharge);
DECLARE_SKILL_CVARS(shocktrooper_rchgspeed);
DECLARE_SKILL_CVARS(cleansuit_scientist_health);
DECLARE_SKILL_CVARS(voltigore_health);
DECLARE_SKILL_CVARS(voltigore_dmg_punch);
DECLARE_SKILL_CVARS(voltigore_dmg_beam);
DECLARE_SKILL_CVARS(babyvoltigore_health);
DECLARE_SKILL_CVARS(babyvoltigore_dmg_punch);
DECLARE_SKILL_CVARS(pitworm_health);
DECLARE_SKILL_CVARS(pitworm_dmg_swipe);
DECLARE_SKILL_CVARS(pitworm_dmg_beam);
DECLARE_SKILL_CVARS(geneworm_health);
DECLARE_SKILL_CVARS(geneworm_dmg_spit);
DECLARE_SKILL_CVARS(geneworm_dmg_hit);
DECLARE_SKILL_CVARS(zombie_barney_health);
DECLARE_SKILL_CVARS(zombie_barney_dmg_one_slash);
DECLARE_SKILL_CVARS(zombie_barney_dmg_both_slash);
DECLARE_SKILL_CVARS(zombie_soldier_health);
DECLARE_SKILL_CVARS(zombie_soldier_dmg_one_slash);
DECLARE_SKILL_CVARS(zombie_soldier_dmg_both_slash);
DECLARE_SKILL_CVARS(gonome_dmg_guts);
DECLARE_SKILL_CVARS(gonome_health);
DECLARE_SKILL_CVARS(gonome_dmg_one_slash);
DECLARE_SKILL_CVARS(gonome_dmg_one_bite);
DECLARE_SKILL_CVARS(plr_pipewrench);
DECLARE_SKILL_CVARS(plr_knife);
DECLARE_SKILL_CVARS(plr_grapple);
DECLARE_SKILL_CVARS(plr_eagle);
DECLARE_SKILL_CVARS(plr_762_bullet);
DECLARE_SKILL_CVARS(plr_556_bullet);
DECLARE_SKILL_CVARS(plr_displacer_self);
DECLARE_SKILL_CVARS(plr_displacer_other);
DECLARE_SKILL_CVARS(plr_displacer_radius);
DECLARE_SKILL_CVARS(plr_shockroachs);
DECLARE_SKILL_CVARS(plr_shockroachm);
DECLARE_SKILL_CVARS(plr_spore);
DECLARE_SKILL_CVARS(cleansuit_scientist_heal);

namespace ap {

void RegisterOpposingForceSkill() {
	REGISTER_SKILL_CVARS(otis_health);
	REGISTER_SKILL_CVARS(pitdrone_health);
	REGISTER_SKILL_CVARS(pitdrone_dmg_bite);
	REGISTER_SKILL_CVARS(pitdrone_dmg_whip);
	REGISTER_SKILL_CVARS(pitdrone_dmg_spit);
	REGISTER_SKILL_CVARS(shockroach_health);
	REGISTER_SKILL_CVARS(shockroach_dmg_bite);
	REGISTER_SKILL_CVARS(shockroach_lifespan);
	REGISTER_SKILL_CVARS(hgrunt_ally_health);
	REGISTER_SKILL_CVARS(hgrunt_ally_kick);
	REGISTER_SKILL_CVARS(hgrunt_ally_pellets);
	REGISTER_SKILL_CVARS(hgrunt_ally_gspeed);
	REGISTER_SKILL_CVARS(medic_ally_health);
	REGISTER_SKILL_CVARS(medic_ally_kick);
	REGISTER_SKILL_CVARS(medic_ally_pellets);
	REGISTER_SKILL_CVARS(medic_ally_gspeed);
	REGISTER_SKILL_CVARS(medic_ally_heal);
	REGISTER_SKILL_CVARS(torch_ally_health);
	REGISTER_SKILL_CVARS(torch_ally_kick);
	REGISTER_SKILL_CVARS(torch_ally_pellets);
	REGISTER_SKILL_CVARS(torch_ally_gspeed);
	REGISTER_SKILL_CVARS(massassin_health);
	REGISTER_SKILL_CVARS(massassin_kick);
	REGISTER_SKILL_CVARS(massassin_pellets);
	REGISTER_SKILL_CVARS(massassin_gspeed);
	REGISTER_SKILL_CVARS(shocktrooper_health);
	REGISTER_SKILL_CVARS(shocktrooper_kick);
	REGISTER_SKILL_CVARS(shocktrooper_gspeed);
	REGISTER_SKILL_CVARS(shocktrooper_maxcharge);
	REGISTER_SKILL_CVARS(shocktrooper_rchgspeed);
	REGISTER_SKILL_CVARS(cleansuit_scientist_health);
	REGISTER_SKILL_CVARS(voltigore_health);
	REGISTER_SKILL_CVARS(voltigore_dmg_punch);
	REGISTER_SKILL_CVARS(voltigore_dmg_beam);
	REGISTER_SKILL_CVARS(babyvoltigore_health);
	REGISTER_SKILL_CVARS(babyvoltigore_dmg_punch);
	REGISTER_SKILL_CVARS(pitworm_health);
	REGISTER_SKILL_CVARS(pitworm_dmg_swipe);
	REGISTER_SKILL_CVARS(pitworm_dmg_beam);
	REGISTER_SKILL_CVARS(geneworm_health);
	REGISTER_SKILL_CVARS(geneworm_dmg_spit);
	REGISTER_SKILL_CVARS(geneworm_dmg_hit);
	REGISTER_SKILL_CVARS(zombie_barney_health);
	REGISTER_SKILL_CVARS(zombie_barney_dmg_one_slash);
	REGISTER_SKILL_CVARS(zombie_barney_dmg_both_slash);
	REGISTER_SKILL_CVARS(zombie_soldier_health);
	REGISTER_SKILL_CVARS(zombie_soldier_dmg_one_slash);
	REGISTER_SKILL_CVARS(zombie_soldier_dmg_both_slash);
	REGISTER_SKILL_CVARS(gonome_dmg_guts);
	REGISTER_SKILL_CVARS(gonome_health);
	REGISTER_SKILL_CVARS(gonome_dmg_one_slash);
	REGISTER_SKILL_CVARS(gonome_dmg_one_bite);
	REGISTER_SKILL_CVARS(plr_pipewrench);
	REGISTER_SKILL_CVARS(plr_knife);
	REGISTER_SKILL_CVARS(plr_grapple);
	REGISTER_SKILL_CVARS(plr_eagle);
	REGISTER_SKILL_CVARS(plr_762_bullet);
	REGISTER_SKILL_CVARS(plr_556_bullet);
	REGISTER_SKILL_CVARS(plr_displacer_self);
	REGISTER_SKILL_CVARS(plr_displacer_other);
	REGISTER_SKILL_CVARS(plr_displacer_radius);
	REGISTER_SKILL_CVARS(plr_shockroachs);
	REGISTER_SKILL_CVARS(plr_shockroachm);
	REGISTER_SKILL_CVARS(plr_spore);
	REGISTER_SKILL_CVARS(cleansuit_scientist_heal);
}

void RefreshOpposingForceSkill() {
	gSkillData.otisHealth = GetSkillCvar((char*)"sk_otis_health");
	gSkillData.pitdroneHealth = GetSkillCvar((char*)"sk_pitdrone_health");
	gSkillData.pitdroneDmgBite = GetSkillCvar((char*)"sk_pitdrone_dmg_bite");
	gSkillData.pitdroneDmgWhip = GetSkillCvar((char*)"sk_pitdrone_dmg_whip");
	gSkillData.pitdroneDmgSpit = GetSkillCvar((char*)"sk_pitdrone_dmg_spit");
	gSkillData.shockroachHealth = GetSkillCvar((char*)"sk_shockroach_health");
	gSkillData.shockroachDmgBite = GetSkillCvar((char*)"sk_shockroach_dmg_bite");
	gSkillData.shockroachLifespan = GetSkillCvar((char*)"sk_shockroach_lifespan");
	gSkillData.hgruntAllyHealth = GetSkillCvar((char*)"sk_hgrunt_ally_health");
	gSkillData.hgruntAllyDmgKick = GetSkillCvar((char*)"sk_hgrunt_ally_kick");
	gSkillData.hgruntAllyShotgunPellets = GetSkillCvar((char*)"sk_hgrunt_ally_pellets");
	gSkillData.hgruntAllyGrenadeSpeed = GetSkillCvar((char*)"sk_hgrunt_ally_gspeed");
	gSkillData.medicAllyHealth = GetSkillCvar((char*)"sk_medic_ally_health");
	gSkillData.medicAllyDmgKick = GetSkillCvar((char*)"sk_medic_ally_kick");
	gSkillData.medicAllyGrenadeSpeed = GetSkillCvar((char*)"sk_medic_ally_gspeed");
	gSkillData.medicAllyHeal = GetSkillCvar((char*)"sk_medic_ally_heal");
	gSkillData.torchAllyHealth = GetSkillCvar((char*)"sk_torch_ally_health");
	gSkillData.torchAllyDmgKick = GetSkillCvar((char*)"sk_torch_ally_kick");
	gSkillData.torchAllyGrenadeSpeed = GetSkillCvar((char*)"sk_torch_ally_gspeed");
	gSkillData.massassinHealth = GetSkillCvar((char*)"sk_massassin_health");
	gSkillData.massassinDmgKick = GetSkillCvar((char*)"sk_massassin_kick");
	gSkillData.massassinGrenadeSpeed = GetSkillCvar((char*)"sk_massassin_gspeed");
	gSkillData.shocktrooperHealth = GetSkillCvar((char*)"sk_shocktrooper_health");
	gSkillData.shocktrooperDmgKick = GetSkillCvar((char*)"sk_shocktrooper_kick");
	gSkillData.shocktrooperGrenadeSpeed = GetSkillCvar((char*)"sk_shocktrooper_gspeed");
	gSkillData.shocktrooperMaxCharge = GetSkillCvar((char*)"sk_shocktrooper_maxcharge");
	gSkillData.shocktrooperRechargeSpeed = GetSkillCvar((char*)"sk_shocktrooper_rchgspeed");
	gSkillData.cleansuitScientistHealth = GetSkillCvar((char*)"sk_cleansuit_scientist_health");
	gSkillData.voltigoreHealth = GetSkillCvar((char*)"sk_voltigore_health");
	gSkillData.voltigoreDmgPunch = GetSkillCvar((char*)"sk_voltigore_dmg_punch");
	gSkillData.voltigoreDmgBeam = GetSkillCvar((char*)"sk_voltigore_dmg_beam");
	gSkillData.babyvoltigoreHealth = GetSkillCvar((char*)"sk_babyvoltigore_health");
	gSkillData.babyvoltigoreDmgPunch = GetSkillCvar((char*)"sk_babyvoltigore_dmg_punch");
	gSkillData.pitWormHealth = GetSkillCvar((char*)"sk_pitworm_health");
	gSkillData.pitWormDmgSwipe = GetSkillCvar((char*)"sk_pitworm_dmg_swipe");
	gSkillData.pitWormDmgBeam = GetSkillCvar((char*)"sk_pitworm_dmg_beam");
	gSkillData.geneWormHealth = GetSkillCvar((char*)"sk_geneworm_health");
	gSkillData.geneWormDmgSpit = GetSkillCvar((char*)"sk_geneworm_dmg_spit");
	gSkillData.geneWormDmgHit = GetSkillCvar((char*)"sk_geneworm_dmg_hit");
	gSkillData.zombieBarneyHealth = GetSkillCvar((char*)"sk_zombie_barney_health");
	gSkillData.zombieBarneyDmgOneSlash = GetSkillCvar((char*)"sk_zombie_barney_dmg_one_slash");
	gSkillData.zombieBarneyDmgBothSlash = GetSkillCvar((char*)"sk_zombie_barney_dmg_both_slash");
	gSkillData.zombieSoldierHealth = GetSkillCvar((char*)"sk_zombie_soldier_health");
	gSkillData.zombieSoldierDmgOneSlash = GetSkillCvar((char*)"sk_zombie_soldier_dmg_one_slash");
	gSkillData.zombieSoldierDmgBothSlash = GetSkillCvar((char*)"sk_zombie_soldier_dmg_both_slash");
	gSkillData.gonomeDmgGuts = GetSkillCvar((char*)"sk_gonome_dmg_guts");
	gSkillData.gonomeHealth = GetSkillCvar((char*)"sk_gonome_health");
	gSkillData.gonomeDmgOneSlash = GetSkillCvar((char*)"sk_gonome_dmg_one_slash");
	gSkillData.gonomeDmgOneBite = GetSkillCvar((char*)"sk_gonome_dmg_one_bite");
	gSkillData.plrDmgPipewrench = GetSkillCvar((char*)"sk_plr_pipewrench");
	gSkillData.plrDmgKnife = GetSkillCvar((char*)"sk_plr_knife");
	gSkillData.plrDmgGrapple = GetSkillCvar((char*)"sk_plr_grapple");
	gSkillData.plrDmgEagle = GetSkillCvar((char*)"sk_plr_eagle");
	gSkillData.plrDmg762 = GetSkillCvar((char*)"sk_plr_762_bullet");
	gSkillData.plrDmg556 = GetSkillCvar((char*)"sk_plr_556_bullet");
	gSkillData.plrDmgDisplacerSelf = GetSkillCvar((char*)"sk_plr_displacer_self");
	gSkillData.plrDmgDisplacerOther = GetSkillCvar((char*)"sk_plr_displacer_other");
	gSkillData.plrRadiusDisplacer = GetSkillCvar((char*)"sk_plr_displacer_radius");
	gSkillData.plrDmgShockRoachS = GetSkillCvar((char*)"sk_plr_shockroachs");
	gSkillData.plrDmgShockRoachM = GetSkillCvar((char*)"sk_plr_shockroachm");
	gSkillData.plrDmgSpore = GetSkillCvar((char*)"sk_plr_spore");
	gSkillData.cleansuitScientistHeal = GetSkillCvar((char*)"sk_cleansuit_scientist_heal");
}

}  // namespace ap
