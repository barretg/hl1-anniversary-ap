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
*   - Mission travel is driven by the multiworld: `!ap` lists what is unlocked
*     and `!warp` enters it. The portal consoles run the same code path.
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
		"  !tracker [map] locations found and still out there, to console\n"
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

	string szShown;
	bool bMultiCampaign = IncludedCampaignCount() > 1;

	for( uint i = 0; i < g_Chapters.length(); ++i )
	{
		APChapter@ pChapter = g_Chapters[i];
		string szStatus;

		if( g_State.ChapterExcluded( pChapter.key ) )
			szStatus = "not in this seed";
		else if( pChapter.isGoal )
			szStatus = g_State.GoalOpen( pChapter.key ) ? "OPEN" : "sealed (finish more missions)";
		else
			szStatus = g_State.ChapterUnlocked( pChapter.key ) ? "unlocked" : "locked";

		// A seed can hold several campaigns, so say which one a mission is from
		// as the list moves from one to the next. Skipped entirely on a
		// single-campaign seed, where the heading would just be noise.
		if( bMultiCampaign && pChapter.campaign != szShown
		    && !g_State.ChapterExcluded( pChapter.key ) )
		{
			szShown = pChapter.campaign;
			string szName;
			if( g_CampaignNames.get( szShown, szName ) )
				g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE, "-- " + szName + "\n" );
		}

		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"  " + ( i < 10 ? " " : "" ) + i + ". " + pChapter.name + "  [" + szStatus + "]\n" );
	}

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"Type !warp <number> to travel to an unlocked mission.\n"
		"Mission 0 has no console in the portal room; !warp 0 is the only way there.\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] Mission list printed to your console (~).\n" );
}

/*
* `!tracker` -- every location in the seed, by map, found or not.
*
* Printed to console rather than chat: it is a couple of hundred lines on a full
* seed, and chat holds five. A location the seed does not contain is skipped
* entirely, so chargesanity off means no charger lines rather than two hundred
* that can never be ticked.
*
* Optionally filtered: `!tracker hl_c03` for one map, `!tracker office` for
* anything whose mission or map name contains that.
*/
void ShowTracker( CBasePlayer@ pPlayer, const string& in szFilter )
{
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"\n=== Archipelago: location tracker ===\n" );

	if( g_CheckedLocations.getSize() == 0 && g_MissingLocations.getSize() == 0 )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"No location data yet -- is the client connected?\n" );
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] No location data yet; check the client.\n" );
		return;
	}

	string szWanted = szFilter;
	szWanted.ToLowercase();

	uint uiFound = 0;
	uint uiTotal = 0;
	uint uiShown = 0;

	for( uint iChapter = 0; iChapter < g_Chapters.length(); ++iChapter )
	{
		APChapter@ pChapter = g_Chapters[iChapter];
		if( g_State.ChapterExcluded( pChapter.key ) )
			continue;

		for( uint iMap = 0; iMap < pChapter.maps.length(); ++iMap )
		{
			string szMap = pChapter.maps[iMap];

			// Gather this map's locations first: a map with nothing in the seed
			// should not print a heading at all.
			array<APLocation@> onMap;
			for( uint i = 0; i < g_Locations.length(); ++i )
			{
				APLocation@ pLocation = g_Locations[i];
				if( pLocation.map != szMap )
					continue;

				string szId = "" + pLocation.id;
				if( !g_CheckedLocations.exists( szId ) && !g_MissingLocations.exists( szId ) )
					continue;  // not in this seed

				onMap.insertLast( pLocation );
			}

			if( onMap.length() == 0 )
				continue;

			uint uiMapFound = 0;
			for( uint i = 0; i < onMap.length(); ++i )
			{
				string szId = "" + onMap[i].id;
				if( g_CheckedLocations.exists( szId ) )
					++uiMapFound;
			}

			uiFound += uiMapFound;
			uiTotal += onMap.length();

			if( szWanted.Length() > 0 )
			{
				string szMapLower = szMap;
				szMapLower.ToLowercase();
				string szChapterLower = pChapter.name;
				szChapterLower.ToLowercase();
				// Find returns String::INVALID_INDEX rather than -1, and it is
				// unsigned -- so it is taken as an int the way the rest of this
				// file does, where a miss reads as negative.
				int iInMap = szMapLower.Find( szWanted );
				int iInChapter = szChapterLower.Find( szWanted );
				if( iInMap < 0 && iInChapter < 0 )
					continue;
			}

			++uiShown;
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
				"\n" + pChapter.name + " -- " + szMap
				+ "  (" + uiMapFound + "/" + onMap.length() + ")\n" );

			for( uint i = 0; i < onMap.length(); ++i )
			{
				string szId = "" + onMap[i].id;
				string szMark = g_CheckedLocations.exists( szId ) ? "[x] " : "[ ] ";
				g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
					"    " + szMark + onMap[i].name + "\n" );
			}
		}
	}

	if( uiShown == 0 && szWanted.Length() > 0 )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"Nothing matches \"" + szFilter + "\".\n" );
	}

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"\nFound " + uiFound + " of " + uiTotal + " locations in this seed.\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] Tracker printed to your console (~): "
		+ uiFound + "/" + uiTotal + " found.\n" );
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
* Which missions may be entered is the multiworld's decision, and the stock
* console knows nothing about it. Rather than override the map script, we watch
* for the button press ourselves and run the same warp `!warp` would, so there is
* one route into a mission and one place that decides whether it is allowed.
*
* Every console is a pair of buttons named `<console>but1` / `<console>but2`, so
* trimming the suffix off a targetname gives the console. Which mission that
* console opens comes from a generated table (the `P` records in checkdata.txt)
* rather than from arithmetic on the number in the name, because the hub numbers
* its consoles differently in every campaign it fronts: Half-Life's are unpadded
* and start at `hl_ch1`, Opposing Force's are zero padded and skip `of_ch06`
* altogether, Blue Shift uses `bs_ch01`-`bs_ch06` and They Hunger `th_ep01`-`03`.
* Deriving the mission from the digits was right for Half-Life alone and wrong
* for Opposing Force in a way that would silently warp a player to the mission
* after the one they pressed.
*
* Note the portal map has no console for Half-Life's mission 0 (Black Mesa
* Inbound); reach it with `!warp 0`.
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
	// `hl_ch3but1` -> `hl_ch3`. Anything without the suffix is some other button.
	int iBut = szName.Find( "but" );
	if( iBut <= 0 )
		return -1;

	string szConsole = szName.SubString( 0, iBut );
	string szChapter;
	if( !g_PortalConsoles.get( szConsole, szChapter ) )
		return -1;

	for( uint i = 0; i < g_Chapters.length(); ++i )
	{
		if( g_Chapters[i].key == szChapter )
			return int( i );
	}

	// The table named a mission this data file does not have, which means the two
	// were generated from different sources. Say so rather than warp anywhere.
	APLog( "console " + szConsole + " points at unknown chapter " + szChapter );
	return -1;
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
		// Held down, so this fires every tick of an HEV charge: the armour it
		// pours in is taken back as fast as the charger supplies it, rather than
		// climbing for a second and then dropping to zero.
		EnforceArmour( pPlayer );
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

	if( szCommand == "!tracker" )
	{
		pParams.ShouldHide = true;
		string szFilter;
		if( pArguments.ArgC() >= 2 )
			szFilter = pArguments[1];
		ShowTracker( pPlayer, szFilter );
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

	// ArgC() is signed and the index is not, which the compiler warns about on
	// every build unless the comparison is made explicit.
	for( uint i = 0; i < uint( pArguments.ArgC() ); ++i )
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
