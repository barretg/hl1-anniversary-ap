/*
* The hub, and enforcement of which missions may be entered.
*
* Sven Co-op already ships a hub: `-sp_campaign_portal`, the campaign portal map,
* with a physical console per Half-Life chapter. We use it as-is and gate it from
* the outside, so no map file is modified:
*
*   - MapChange is the choke point. Every route into a mission -- a portal
*     console, a console `changelevel`, the campaign's own end-of-map trigger --
*     goes through it, so one check covers them all.
*   - The portal map needs two players standing on a console to open a portal.
*     Chat commands (`!ap`, `!warp`) do the same job for a solo run.
*/

/*
* Printed to chat rather than console, since a player who needs the command list
* is unlikely to think to open the console to find it.
*/
void ShowHelp( CBasePlayer@ pPlayer )
{
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] Commands:\n"
		"  !ap            list missions and what is unlocked\n"
		"  !warp <number> travel to an unlocked mission\n"
		"  !hub           return to the campaign portal\n"
		"  !help          this list\n"
		"You can also press a mission console's button in the hub.\n" );
}

void ShowStatus( CBasePlayer@ pPlayer )
{
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"\n=== Archipelago: Half-Life (Sven Co-op) ===\n" );

	if( !g_State.connected )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"Not connected -- start the Half-Life (Sven Co-op) Client.\n" );
	}

	for( uint i = 0; i < g_Chapters.length(); ++i )
	{
		APChapter@ pChapter = g_Chapters[i];
		string szStatus;

		if( g_State.ChapterExcluded( pChapter.key ) )
			szStatus = "not in this seed";
		else if( pChapter.isGoal )
			szStatus = g_State.goalOpen ? "OPEN" : "sealed (finish more missions)";
		else
			szStatus = g_State.ChapterUnlocked( pChapter.key ) ? "unlocked" : "locked";

		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"  " + ( i < 10 ? " " : "" ) + i + ". " + pChapter.name + "  [" + szStatus + "]\n" );
	}

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"Type !warp <number> to travel to an unlocked mission.\n"
		"Mission 0 has no console in the portal room; !warp 0 is the only way there.\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] Mission list printed to your console (~).\n" );
}

void WarpToChapter( CBasePlayer@ pPlayer, int iIndex )
{
	if( iIndex < 0 || uint( iIndex ) >= g_Chapters.length() )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK, "[AP] No such mission.\n" );
		return;
	}

	APChapter@ pChapter = g_Chapters[iIndex];

	if( g_State.ChapterExcluded( pChapter.key ) )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] " + pChapter.name + " is not part of this seed.\n" );
		return;
	}

	if( !ChapterPlayable( pChapter ) )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] " + pChapter.name + " is still locked.\n" );
		return;
	}

	g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
		"[AP] Travelling to " + pChapter.name + "...\n" );
	ChangeLevel( pChapter.FirstMap() );
}

void ReturnToHub()
{
	ChangeLevel( HUB_MAP );
}

// The map we are about to travel to. Non-empty means a change is already
// queued, which is what stops two button presses, or a button press racing the
// portal map's own teleporter, from issuing two changelevels at once.
string g_szPendingLevel;

// Short, but long enough that the hook which asked for this has returned and the
// engine is back in its normal loop.
const float LEVEL_CHANGE_DELAY = 0.5f;

/*
* Ask for a level change.
*
* Never performed inline. Every caller is a hook -- PlayerUse, MapChange,
* MapStart -- and issuing a changelevel from inside one crashed the game on both
* mission completion and the hub buttons. Going through the scheduler means the
* engine is idle by the time the command runs.
*/
void ChangeLevel( const string& in szMap )
{
	if( g_szPendingLevel.Length() > 0 )
		return;

	g_szPendingLevel = szMap;
	g_Scheduler.SetTimeout( "PerformLevelChange", LEVEL_CHANGE_DELAY );
}

void PerformLevelChange()
{
	if( g_szPendingLevel.Length() == 0 )
		return;

	string szMap = g_szPendingLevel;
	g_szPendingLevel = "";
	// Survives until MapChange sees the transition, which is how a mission we
	// walked out of is told apart from one the campaign ended for us.
	g_bSelfChange = true;

	// Queued, not forced. ServerExecute would run this synchronously from inside
	// the scheduler tick instead of letting the engine drain it when ready.
	g_EngineFuncs.ServerCommand( "changelevel " + szMap + "\n" );
}

/*
* Remember that we owe the player a trip back to the hub.
*
* Written to disk because it has to outlive the map change it is queued behind:
* the plugin's globals do not survive one.
*/
void SetPendingHubReturn( bool bPending )
{
	File@ pFile = g_FileSystem.OpenFile( AP_PENDING, OpenFile::WRITE );

	if( pFile is null || !pFile.IsOpen() )
		return;

	pFile.Write( bPending ? "1\n" : "\n" );
	pFile.Close();
}

bool ConsumePendingHubReturn()
{
	File@ pFile = g_FileSystem.OpenFile( AP_PENDING, OpenFile::READ );

	if( pFile is null || !pFile.IsOpen() )
		return false;

	string szLine;
	if( !pFile.EOFReached() )
		pFile.ReadLine( szLine );
	pFile.Close();

	if( APTrim( szLine ) != "1" )
		return false;

	SetPendingHubReturn( false );
	return true;
}

/*
* Observe a map change. Never block one.
*
* Returning HOOK_HANDLED here to cancel a transition, and then issuing our own
* changelevel, crashed the game on mission completion. The engine is already
* committed by the time this runs, so the only safe thing to do is note what is
* happening and act once the next map has loaded (see MapStart in ap_main.as).
*
* Three cases matter:
*   - staying inside the current mission: nothing to do, and the destination map
*     fires its own "part reached" check.
*   - leaving the current mission from its last map: the mission is finished.
*     Send the completion and queue a return to the hub.
*   - entering a locked mission: let it load; MapStart bounces us back out.
*/
HookReturnCode MapChange( const string& in szNextMap )
{
	// `restart` and friends re-enter the map we are already on. That is not a
	// transition, and treating it as one both credited the mission and left us
	// fighting the engine over a changelevel it was already performing.
	if( szNextMap.Length() == 0 || szNextMap == g_szCurrentMap )
		return HOOK_CONTINUE;

	APChapter@ pNext = ChapterForMap( szNextMap );

	if( g_CurrentChapter !is null && g_CurrentChapter.HasMap( szNextMap ) )
		return HOOK_CONTINUE;  // same mission, next part

	if( g_CurrentChapter !is null )
	{
		// A mission is only finished if all three hold:
		//   - we are leaving from its *last* map. Walking out of the middle is
		//     not finishing it.
		//   - the transition is the campaign's, not ours. `!hub` and `!warp` out
		//     of a one-map mission are leaving, however far in you got.
		//   - we were actually playing it (g_bMissionActive): the engine can
		//     drop us on a locked mission's map and take us straight out again,
		//     and that must not read as a completion.
		if( g_szCurrentMap == g_CurrentChapter.LastMap()
		    && !g_bSelfChange && g_bMissionActive )
			CompleteChapter( g_CurrentChapter );

		// The campaign wants to run straight on into the next chapter. Let it
		// load, then bounce back to the hub from there.
		if( szNextMap != HUB_MAP )
			SetPendingHubReturn( true );
	}

	return HOOK_CONTINUE;
}

/*
* Rewiring the portal consoles.
*
* The stock portal needs exactly two players standing inside one console's
* game_zone_player before it will open, which makes a solo run impossible and a
* duo run fiddly. Rather than override the map script, we watch for the button
* press ourselves and run the same warp `!warp` would.
*
* The console entities are named regularly -- `hl_ch<N>but1` / `hl_ch<N>but2`,
* with `hl_ch<N>change` pointing at `hl_c<NN>` -- and portal N lines up exactly
* with our chapter index N (hl_ch3 -> hl_c03 -> Office Complex). So the button's
* targetname alone identifies the mission; nothing has to be read out of the map.
*
* Note the portal map has no console for chapter 0 (Black Mesa Inbound); reach it
* with `!warp 0`.
*/

// Half-Life's use range is 64 units from the gun position; be a little generous.
// Also used for the charger checks, which trace the same way.
const float USE_TRACE_RANGE = 96.0f;

// One press should mean one warp, not one per think while +use is held.
const float PORTAL_USE_COOLDOWN = 2.0f;

dictionary g_flLastPortalUse;

/* Chapter index behind a console button's targetname, or -1 if it is not one. */
int PortalChapterIndex( const string& in szName )
{
	if( szName.Length() < 6 || szName.SubString( 0, 5 ) != "hl_ch" )
		return -1;

	int iBut = szName.Find( "but" );
	if( iBut <= 5 )
		return -1;

	int iIndex = atoi( szName.SubString( 5, iBut - 5 ) );
	if( iIndex < 0 || uint( iIndex ) >= g_Chapters.length() )
		return -1;

	// Guard against the naming assumption quietly drifting: portal N must point
	// at the mission whose first map is hl_c<NN>.
	string szExpected = "hl_c" + ( iIndex < 10 ? "0" : "" ) + iIndex;
	if( g_Chapters[iIndex].FirstMap().SubString( 0, szExpected.Length() ) != szExpected )
	{
		APLog( "portal " + iIndex + " does not match chapter " + g_Chapters[iIndex].key );
		return -1;
	}

	return iIndex;
}

/*
* PlayerUse tells us who pressed but not what they pressed, so trace where they
* are looking. This fires whether or not the entity itself accepts the press,
* which is the point in the hub -- the stock two-player lock never gets a say.
*
* Two things care about the result: the hub's mission consoles, and the health
* and HEV chargers scattered through the campaign.
*/
HookReturnCode PlayerUse( CBasePlayer@ pPlayer, uint& out uiFlags )
{
	uiFlags = 0;

	if( pPlayer is null )
		return HOOK_CONTINUE;

	// Nothing on this map is worth a trace on every +use tick.
	if( g_szCurrentMap != HUB_MAP && g_MapChargers.length() == 0 )
		return HOOK_CONTINUE;

	Math.MakeVectors( pPlayer.pev.v_angle );
	Vector vecStart = pPlayer.GetGunPosition();
	Vector vecEnd = vecStart + g_Engine.v_forward * USE_TRACE_RANGE;

	TraceResult tr;
	g_Utility.TraceLine( vecStart, vecEnd, dont_ignore_monsters, pPlayer.edict(), tr );

	if( tr.pHit is null )
		return HOOK_CONTINUE;

	CBaseEntity@ pHit = g_EntityFuncs.Instance( tr.pHit );
	if( pHit is null )
		return HOOK_CONTINUE;

	if( g_szCurrentMap != HUB_MAP )
	{
		RegisterChargerCheck( pHit );
		return HOOK_CONTINUE;
	}

	int iIndex = PortalChapterIndex( pHit.GetTargetname() );
	if( iIndex < 0 )
		return HOOK_CONTINUE;

	string szKey = "" + pPlayer.entindex();
	float flLast = 0.0f;
	g_flLastPortalUse.get( szKey, flLast );
	if( g_Engine.time - flLast < PORTAL_USE_COOLDOWN )
		return HOOK_CONTINUE;
	g_flLastPortalUse[ szKey ] = g_Engine.time;

	WarpToChapter( pPlayer, iIndex );
	return HOOK_CONTINUE;
}

/* Chat commands. `!ap` lists missions, `!warp <n>` travels, `!hub` goes back. */
HookReturnCode ClientSay( SayParameters@ pParams )
{
	CBasePlayer@ pPlayer = pParams.GetPlayer();
	const CCommand@ pArguments = pParams.GetArguments();

	if( pArguments.ArgC() < 1 )
		return HOOK_CONTINUE;

	string szCommand = pArguments[0];

	if( szCommand == "!help" )
	{
		pParams.ShouldHide = true;
		ShowHelp( pPlayer );
		return HOOK_HANDLED;
	}

	if( szCommand == "!ap" )
	{
		pParams.ShouldHide = true;
		ShowStatus( pPlayer );
		return HOOK_HANDLED;
	}

	if( szCommand == "!hub" )
	{
		pParams.ShouldHide = true;
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] Returning to the hub...\n" );
		ReturnToHub();
		return HOOK_HANDLED;
	}

	if( szCommand == "!warp" )
	{
		pParams.ShouldHide = true;
		if( pArguments.ArgC() < 2 )
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK, "[AP] Usage: !warp <number>\n" );
		else
			WarpToChapter( pPlayer, atoi( pArguments[1] ) );
		return HOOK_HANDLED;
	}

	RelayChat( pPlayer, pArguments );
	return HOOK_CONTINUE;
}

/*
* Forward ordinary chat to the multiworld.
*
* Sent unconditionally: whether it reaches the server is the client's decision,
* and it is the only side that knows whether it is connected.
*/
void RelayChat( CBasePlayer@ pPlayer, const CCommand@ pArguments )
{
	string szMessage;

	for( uint i = 0; i < pArguments.ArgC(); ++i )
	{
		if( i > 0 )
			szMessage += " ";
		szMessage += pArguments[i];
	}

	szMessage = APTrim( szMessage );
	if( szMessage.Length() == 0 )
		return;

	// A message beginning with '!' is a command we did not recognise; relaying
	// it would put typos and other plugins' commands into multiworld chat.
	if( szMessage.SubString( 0, 1 ) == "!" )
		return;

	BridgeSend( "CHAT|" + APSanitise( string( pPlayer.pev.netname ) )
	            + "|" + APSanitise( szMessage ) );
}
