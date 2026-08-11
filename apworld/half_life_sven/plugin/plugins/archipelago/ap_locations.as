/*
* Turning things that happen in the map into Archipelago checks.
*
* Every location was generated from an entity that provably exists in the BSP
* (see tools/build_campaign_data.py), so there are no coordinate guesses here --
* a check fires off a classname, a kill, or a map transition.
*/

/*
* A weapon or item was walked over: fire the matching pickup check, if any.
*
* Both location kinds are scoped to this map. `weapon_pickup` is the one place
* Half-Life would first have handed you that weapon; `pickup` is the older
* per-copy variant, currently not generated.
*
* Called whether or not the player is allowed to keep the weapon: walking over it
* is the discovery, and being told "you have not found the Shotgun yet" while
* standing on a shotgun is the joke the randomiser is built on.
*/
void RegisterPickupCheck( const string& in szClassname )
{
	if( MatchPickup( g_WeaponPickups, szClassname ) )
		return;

	MatchPickup( g_MapPickups, szClassname );
}

bool MatchPickup( array<APLocation@>@ locations, const string& in szClassname )
{
	for( uint i = 0; i < locations.length(); ++i )
	{
		APLocation@ pLocation = locations[i];

		for( uint j = 0; j < pLocation.args.length(); ++j )
		{
			if( pLocation.args[j] == szClassname )
			{
				SendCheck( pLocation );
				return true;
			}
		}
	}

	return false;
}

// Roughly a player bounding box plus an item's. Generous on purpose: this is the
// safety net, and a check is not worth being precious about.
const float WEAPON_REACH = 72.0f;

/*
* The safety net behind the pickup hook.
*
* CanCollect only fires when the engine is deciding whether to hand something
* over, and it does not for a weapon you are already carrying. The crowbar is in
* everyone's starting inventory, so its check would otherwise be impossible to
* send -- and with `accessibility: full` an unsendable location is a seed that
* cannot be finished. Any weapon whose item has already arrived has the same
* problem, so this covers all of them: standing next to the pickup is enough.
*
* Runs on the existing one-second sweep, and only while this map still has an
* unsent weapon check on it, so the usual cost is one length check on an empty
* array.
*/
void SweepWeaponPickups()
{
	for( uint i = 0; i < g_WeaponPickups.length(); ++i )
	{
		APLocation@ pLocation = g_WeaponPickups[i];

		if( g_SentChecks.exists( "" + pLocation.id ) )
			continue;

		for( uint j = 0; j < pLocation.args.length(); ++j )
		{
			if( AnyPlayerNear( pLocation.args[j] ) )
			{
				SendCheck( pLocation );
				break;
			}
		}
	}
}

bool AnyPlayerNear( const string& in szClassname )
{
	CBaseEntity@ pEntity = null;

	while( ( @pEntity = g_EntityFuncs.FindEntityByClassname( pEntity, szClassname ) ) !is null )
	{
		for( int i = 1; i <= g_Engine.maxClients; ++i )
		{
			CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );

			if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
				continue;

			if( ( pPlayer.pev.origin - pEntity.pev.origin ).Length() <= WEAPON_REACH )
				return true;
		}
	}

	return false;
}

/*
* A player pressed +use on something. If it is one of this map's chargers, that
* is a check.
*
* Chargers are brush entities with no targetname, so the only identity the BSP
* and the running game agree on is the brush model index the compiler gave them
* ("*58"). checkdata.txt carries "<classname>:<model>" for exactly that reason.
*
* The check fires on the press, not on drinking the charger dry: an empty unit
* is still a unit you found, and a player who tops up two points of health has
* done the same amount of exploring as one who was nearly dead.
*/
void RegisterChargerCheck( CBaseEntity@ pEntity )
{
	if( pEntity is null || g_MapChargers.length() == 0 )
		return;

	string szKey = pEntity.GetClassname() + ":" + string( pEntity.pev.model );

	for( uint i = 0; i < g_MapChargers.length(); ++i )
	{
		if( g_MapChargers[i].arg == szKey )
		{
			SendCheck( g_MapChargers[i] );
			return;
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
