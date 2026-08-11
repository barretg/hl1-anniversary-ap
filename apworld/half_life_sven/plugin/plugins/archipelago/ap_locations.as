/*
* Turning things that happen in the map into Archipelago checks.
*
* Every location was generated from an entity that provably exists in the BSP
* (see tools/build_campaign_data.py), so there are no coordinate guesses here --
* a check fires off a classname, a kill, or a map transition.
*/

/* A weapon or item was collected: fire the matching pickup check, if any. */
void RegisterPickupCheck( const string& in szClassname )
{
	for( uint i = 0; i < g_MapPickups.length(); ++i )
	{
		APLocation@ pLocation = g_MapPickups[i];

		for( uint j = 0; j < pLocation.args.length(); ++j )
		{
			if( pLocation.args[j] == szClassname )
			{
				SendCheck( pLocation );
				return;
			}
		}
	}
}

/*
* Something died. Two kinds of check care: the first kill of a notable monster
* in this map, and cumulative kill-count milestones (which is how the sparse Xen
* maps still get checks).
*/
HookReturnCode MonsterKilled( CBaseMonster@ pMonster, CBaseEntity@ pAttacker, int iGib )
{
	if( pMonster is null )
		return HOOK_CONTINUE;

	string szClassname = pMonster.GetClassname();

	for( uint i = 0; i < g_MapKills.length(); ++i )
	{
		if( g_MapKills[i].arg == szClassname )
		{
			SendCheck( g_MapKills[i] );
			break;
		}
	}

	++g_iMapKills;
	for( uint i = 0; i < g_MapKillCounts.length(); ++i )
	{
		if( g_iMapKills >= atoi( g_MapKillCounts[i].arg ) )
			SendCheck( g_MapKillCounts[i] );
	}

	return HOOK_CONTINUE;
}

/*
* Fire the "reached this part" check for the map we just loaded into.
*
* Called from MapInit rather than on a trigger: by the time the plugin is
* running on hl_c11_a3, the player demonstrably got there.
*/
void RegisterMapReached()
{
	for( uint i = 0; i < g_Locations.length(); ++i )
	{
		APLocation@ pLocation = g_Locations[i];
		if( pLocation.kind == TRIGGER_MAP_REACHED && pLocation.map == g_szCurrentMap )
			SendCheck( pLocation );
	}
}

/*
* The mission is over. Sends the completion check and tells the client, which is
* what advances the `missions_required` count that opens Nihilanth.
*/
void CompleteChapter( APChapter@ pChapter )
{
	if( pChapter is null )
		return;

	for( uint i = 0; i < g_Locations.length(); ++i )
	{
		APLocation@ pLocation = g_Locations[i];
		if( pLocation.kind == TRIGGER_CHAPTER_COMPLETE && pLocation.arg == pChapter.key )
			SendCheck( pLocation );
	}

	BridgeSend( "COMPLETE|" + pChapter.key );

	if( pChapter.isGoal )
	{
		BridgeSend( "GOAL|" + pChapter.key );
		g_PlayerFuncs.ClientPrintAll(
			HUD_PRINTTALK, "[AP] Nihilanth is dead. Goal complete!\n" );
	}
	else
	{
		g_PlayerFuncs.ClientPrintAll(
			HUD_PRINTTALK, "[AP] Mission complete: " + pChapter.name + "\n" );
	}
}
