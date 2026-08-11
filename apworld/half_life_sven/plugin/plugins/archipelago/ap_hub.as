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
		// A mission is only finished if we are leaving from its *last* map. The
		// campaign's own changelevel there is the completion signal; walking out
		// of the middle with !hub is not.
		if( g_szCurrentMap == g_CurrentChapter.LastMap() )
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
const float PORTAL_USE_RANGE = 96.0f;

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
* are looking. This fires whether or not the button itself accepts the press,
* which is the point -- the stock two-player lock never gets a say.
*/
HookReturnCode PlayerUse( CBasePlayer@ pPlayer, uint& out uiFlags )
{
	uiFlags = 0;

	if( pPlayer is null || g_szCurrentMap != HUB_MAP )
		return HOOK_CONTINUE;

	Math.MakeVectors( pPlayer.pev.v_angle );
	Vector vecStart = pPlayer.GetGunPosition();
	Vector vecEnd = vecStart + g_Engine.v_forward * PORTAL_USE_RANGE;

	TraceResult tr;
	g_Utility.TraceLine( vecStart, vecEnd, dont_ignore_monsters, pPlayer.edict(), tr );

	if( tr.pHit is null )
		return HOOK_CONTINUE;

	CBaseEntity@ pHit = g_EntityFuncs.Instance( tr.pHit );
	if( pHit is null )
		return HOOK_CONTINUE;

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
