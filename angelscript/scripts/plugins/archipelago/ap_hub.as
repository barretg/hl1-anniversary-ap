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

		if( pChapter.isGoal )
			szStatus = g_State.goalOpen ? "OPEN" : "sealed (finish more missions)";
		else
			szStatus = g_State.ChapterUnlocked( pChapter.key ) ? "unlocked" : "locked";

		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"  " + ( i < 10 ? " " : "" ) + i + ". " + pChapter.name + "  [" + szStatus + "]\n" );
	}

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"Type !warp <number> to travel to an unlocked mission.\n" );
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

void ChangeLevel( const string& in szMap )
{
	g_EngineFuncs.ServerCommand( "changelevel " + szMap + "\n" );
	g_EngineFuncs.ServerExecute();
}

/*
* Decide what a pending map change means and whether to allow it.
*
* Three cases matter:
*   - staying inside the current mission: allow it, and let the destination map
*     fire its own "part reached" check.
*   - leaving the current mission: the mission is finished. Send the completion,
*     then send everyone back to the hub instead of on to the next chapter.
*   - entering a locked mission: refuse and stay put.
*/
HookReturnCode MapChange( const string& in szNextMap )
{
	APChapter@ pNext = ChapterForMap( szNextMap );

	if( g_CurrentChapter !is null && g_CurrentChapter.HasMap( szNextMap ) )
		return HOOK_CONTINUE;  // same mission, next part

	if( g_CurrentChapter !is null )
	{
		// The campaign's own changelevel at the end of a mission points at the
		// next chapter; that transition *is* the completion signal.
		CompleteChapter( g_CurrentChapter );

		if( szNextMap != HUB_MAP )
		{
			g_Scheduler.SetTimeout( "ReturnToHub", 2.0f );
			return HOOK_HANDLED;
		}
		return HOOK_CONTINUE;
	}

	// Leaving the hub for a mission.
	if( pNext !is null && !ChapterPlayable( pNext ) )
	{
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
			"[AP] " + pNext.name + " is locked -- you have not received its unlock yet.\n" );
		return HOOK_HANDLED;
	}

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

	return HOOK_CONTINUE;
}
