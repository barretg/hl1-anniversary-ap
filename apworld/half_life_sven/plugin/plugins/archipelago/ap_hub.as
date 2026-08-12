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
	// One call per line. The engine's client print buffer is 128 bytes, so the
	// whole list in a single call came out cut off partway through the third
	// command and the rest was simply lost.
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK, "[AP] Commands:\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"  !ap  list missions and what is unlocked\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"  !tracker [text]  locations found and missing, to console\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"  !find [text]  point at the nearest check, or one you name\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"  !warp <number>  travel to an unlocked mission\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"  !hub  return to the campaign portal\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"  !help  this list\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"Or press a mission console's button in the hub.\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"In console (mind the dot): .ap  .ap_tracker  .ap_find  .ap_warp\n" );
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

	// One line per call: the print buffer is 128 bytes and silently truncates.
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"Type !warp <number> to travel to an unlocked mission.\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
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

/*
* Is this location part of the seed, and has it been found?
*
* Anything the client has listed in neither set is not in this seed at all.
*/
bool LocationInSeed( APLocation@ pLocation )
{
	string szId = "" + pLocation.id;
	return g_CheckedLocations.exists( szId ) || g_MissingLocations.exists( szId );
}

bool LocationFound( APLocation@ pLocation )
{
	return g_CheckedLocations.exists( "" + pLocation.id );
}

/*
* Which way is it, in words, from where the player is standing and facing.
*
* Deliberately a compass rather than a route: the direction is the straight line
* to the thing, so in a corridor it can point through a wall. Run it again after
* moving and it updates, which is what makes it work in practice -- hot and cold
* rather than turn by turn. Anything better would want a navigation graph, which
* AngelScript cannot reach and half these maps do not have.
*
* Left and right come from the player's own facing rather than north, because
* nobody knows which way north is in Black Mesa. Dot products against forward
* and right do it without any trigonometry.
*/
string BearingTo( CBasePlayer@ pPlayer, const Vector& in vecTarget )
{
	Vector vecFrom = pPlayer.pev.origin;
	Vector vecDelta = vecTarget - vecFrom;

	// Flat plane only: height is reported separately, and letting it into the
	// bearing makes something directly overhead read as "far ahead".
	Vector vecFlat( vecDelta.x, vecDelta.y, 0.0f );
	float flFlat = vecFlat.Length();

	if( flFlat < 64 )
		return "right about where you are standing";

	Math.MakeVectors( pPlayer.pev.v_angle );
	Vector vecForward = g_Engine.v_forward;
	Vector vecRight = g_Engine.v_right;

	// By hand: Vector's `*` is component-wise, not a dot product.
	float flForward = ( vecFlat.x * vecForward.x + vecFlat.y * vecForward.y ) / flFlat;
	float flRight = ( vecFlat.x * vecRight.x + vecFlat.y * vecRight.y ) / flFlat;

	string szSide = flRight >= 0 ? "right" : "left";

	if( flForward > 0.85f )
		return "straight ahead";
	if( flForward > 0.35f )
		return "ahead and to your " + szSide;
	if( flForward > -0.35f )
		return "to your " + szSide;
	if( flForward > -0.85f )
		return "behind you, to your " + szSide;

	return "directly behind you";
}

/*
* How far away something *really* is, for choosing the nearest one.
*
* Straight-line distance is a bad judge of that indoors. Height is the expensive
* axis: 800 units across a floor is a walk, 800 units up is a hunt for the stairs
* and usually a good deal of level in between. Ranking by the straight line put
* Office Complex's shotgun -- 677 out but nearly 800 above -- ahead of two
* chargers sitting on the player's own floor.
*
* So the flat distance, plus the height difference several times over. This is
* only ever used to rank candidates; the distance reported to the player stays
* the honest straight line.
*/
const float FIND_VERTICAL_PENALTY = 3.0f;

float TravelScore( CBasePlayer@ pPlayer, const Vector& in vecTarget )
{
	Vector vecDelta = vecTarget - pPlayer.pev.origin;
	Vector vecFlat( vecDelta.x, vecDelta.y, 0.0f );

	float flRise = vecDelta.z;
	if( flRise < 0 )
		flRise = -flRise;

	return vecFlat.Length() + FIND_VERTICAL_PENALTY * flRise;
}

string HeightTo( CBasePlayer@ pPlayer, const Vector& in vecTarget )
{
	float flRise = vecTarget.z - pPlayer.pev.origin.z;

	if( flRise > 128 )
		return ", well above you";
	if( flRise > 48 )
		return ", a little above you";
	if( flRise < -128 )
		return ", well below you";
	if( flRise < -48 )
		return ", a little below you";

	return "";
}

/*
* The tracer: is there anything solid between the player and the thing?
*
* One TraceLine, only when the player asks. Turns "somewhere over there" into
* "you can see it from here" or "there is a wall in the way, find the door".
*/
string SightTo( CBasePlayer@ pPlayer, const Vector& in vecTarget )
{
	TraceResult tr;
	g_Utility.TraceLine( pPlayer.GetGunPosition(), vecTarget,
	                     ignore_monsters, pPlayer.edict(), tr );

	if( tr.flFraction >= 1.0f )
		return "You have a clear line to it.";

	return "Something solid is in the way.";
}

void DescribeLocation( CBasePlayer@ pPlayer, APLocation@ pLocation )
{
	string szPrefix = LocationFound( pLocation ) ? "[found] " : "";

	// A line at a time. The engine's print buffer is 128 bytes and truncates
	// without saying so, and a location name plus a bearing is well past it.
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] " + szPrefix + pLocation.name + "\n" );

	// Somewhere else entirely: say where, and how to get there.
	if( pLocation.map != g_szCurrentMap )
	{
		APChapter@ pChapter = ChapterForMap( pLocation.map );
		if( pChapter is null )
		{
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
				"[AP] It is on " + pLocation.map + ".\n" );
			return;
		}

		// Name the part, and hand over the exact command that goes there. On a
		// mission you have already been through that is a warp straight to the
		// part, not back to its beginning.
		string szPart = PartLabel( pChapter, pLocation.map );

		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] In " + pChapter.name
			+ ( szPart.Length() > 0 ? ", " + szPart : "" )
			+ " (" + pLocation.map + ").\n" );

		if( szPart.Length() > 0 && MapReached( pLocation.map ) )
		{
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
				"[AP] Get there with !warp " + pLocation.map + "\n" );
		}
		else
		{
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
				"[AP] Get there with !warp " + pChapter.index + "\n" );
		}
		return;
	}

	if( !pLocation.hasPosition )
	{
		// Either the check is the map itself, or it is a weapon somebody hands
		// over rather than one lying on the floor -- nothing to point at either
		// way, but they want different answers.
		if( pLocation.kind == TRIGGER_MAP_REACHED
		    || pLocation.kind == TRIGGER_CHAPTER_COMPLETE )
		{
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
				"[AP] That is this map itself -- keep going.\n" );
		}
		else
		{
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
				"[AP] Somewhere on this map; it is given to you, not left lying.\n" );
		}
		return;
	}

	int iDistance = int( ( pLocation.position - pPlayer.pev.origin ).Length() );

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] About " + iDistance + " units " + BearingTo( pPlayer, pLocation.position )
		+ HeightTo( pPlayer, pLocation.position ) + ".\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] " + SightTo( pPlayer, pLocation.position ) + "\n" );
}

/*
* `!find` -- point the player at a check.
*
* With no argument, the nearest one on this map they have not found yet, which
* is the question people actually have. With text, whatever matches by name.
*/
void FindLocation( CBasePlayer@ pPlayer, const string& in szQuery )
{
	if( g_CheckedLocations.getSize() == 0 && g_MissingLocations.getSize() == 0 )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] No location data yet; check the client.\n" );
		return;
	}

	if( szQuery.Length() == 0 )
	{
		APLocation@ pNearest = null;
		float flNearest = 0;

		for( uint i = 0; i < g_Locations.length(); ++i )
		{
			APLocation@ pLocation = g_Locations[i];
			if( pLocation.map != g_szCurrentMap || !pLocation.hasPosition )
				continue;
			if( !LocationInSeed( pLocation ) || LocationFound( pLocation ) )
				continue;

			float flScore = TravelScore( pPlayer, pLocation.position );
			if( pNearest is null || flScore < flNearest )
			{
				@pNearest = pLocation;
				flNearest = flScore;
			}
		}

		if( pNearest is null )
		{
			g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
				"[AP] Nothing left to find on this map.\n" );
			return;
		}

		DescribeLocation( pPlayer, pNearest );
		return;
	}

	string szWanted = szQuery;
	szWanted.ToLowercase();

	array<APLocation@> matches;
	for( uint i = 0; i < g_Locations.length(); ++i )
	{
		APLocation@ pLocation = g_Locations[i];
		if( !LocationInSeed( pLocation ) )
			continue;

		string szName = pLocation.name;
		szName.ToLowercase();
		// Find returns String::INVALID_INDEX rather than -1, and it is unsigned;
		// read as an int, a miss comes out negative.
		int iAt = szName.Find( szWanted );
		if( iAt >= 0 )
			matches.insertLast( pLocation );
	}

	if( matches.length() == 0 )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] Nothing in this seed matches \"" + szQuery + "\".\n" );
		return;
	}

	// A single hit gets directions. Several, and naming them is more use than
	// guessing which one was meant -- but prefer this map, since that is nearly
	// always what a player means.
	if( matches.length() == 1 )
	{
		DescribeLocation( pPlayer, matches[0] );
		return;
	}

	APLocation@ pHere = null;
	uint uiHere = 0;
	for( uint i = 0; i < matches.length(); ++i )
	{
		if( matches[i].map == g_szCurrentMap )
		{
			if( pHere is null )
				@pHere = matches[i];
			++uiHere;
		}
	}

	if( uiHere == 1 )
	{
		DescribeLocation( pPlayer, pHere );
		return;
	}

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] " + matches.length() + " matches; printed to your console (~).\n" );
	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
		"\n=== !find \"" + szQuery + "\" ===\n" );

	for( uint i = 0; i < matches.length(); ++i )
	{
		APLocation@ pLocation = matches[i];
		string szMark = LocationFound( pLocation ) ? "[x] " : "[ ] ";
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTCONSOLE,
			"    " + szMark + pLocation.name + "  (" + pLocation.map + ")\n" );
	}
}

/*
* `!warp office` as well as `!warp 3`.
*
* Numbers are exact and win outright. Text is matched against mission names the
* way `!tracker` matches, because remembering that Office Complex is 3 is a
* worse ask than typing "office" -- and with 40 missions across four campaigns,
* the numbers are no longer memorable at all.
*/
void WarpToQuery( CBasePlayer@ pPlayer, const string& in szQuery )
{
	if( szQuery.Length() == 0 )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] Usage: !warp <number or mission name>\n" );
		return;
	}

	// A plain number is an index and nothing else.
	bool bNumeric = true;
	for( uint i = 0; i < szQuery.Length(); ++i )
	{
		string szChar = szQuery.SubString( i, 1 );
		if( szChar < "0" || szChar > "9" )
		{
			bNumeric = false;
			break;
		}
	}

	if( bNumeric )
	{
		WarpToChapter( pPlayer, atoi( szQuery ) );
		return;
	}

	string szWanted = szQuery;
	szWanted.ToLowercase();

	// A map name outright: `!warp hl_c11_a3`.
	for( uint i = 0; i < g_Chapters.length(); ++i )
	{
		APChapter@ pChapter = g_Chapters[i];
		for( uint j = 0; j < pChapter.maps.length(); ++j )
		{
			string szMap = pChapter.maps[j];
			szMap.ToLowercase();
			if( szMap == szWanted )
			{
				WarpToMap( pPlayer, pChapter, pChapter.maps[j] );
				return;
			}
		}
	}

	// `!warp surface tension 3` -- a mission and a part of it. Split the trailing
	// number off and match the rest as a name.
	int iPart = 0;
	int iSplit = szWanted.RFind( " " );
	if( iSplit > 0 )
	{
		string szTail = szWanted.SubString( iSplit + 1, szWanted.Length() - iSplit - 1 );
		bool bTailNumeric = szTail.Length() > 0;
		for( uint i = 0; i < szTail.Length(); ++i )
		{
			string szChar = szTail.SubString( i, 1 );
			if( szChar < "0" || szChar > "9" )
			{
				bTailNumeric = false;
				break;
			}
		}

		if( bTailNumeric )
		{
			iPart = atoi( szTail );
			szWanted = szWanted.SubString( 0, iSplit );
		}
	}

	array<int> matches;
	for( uint i = 0; i < g_Chapters.length(); ++i )
	{
		string szName = g_Chapters[i].name;
		szName.ToLowercase();
		// Find returns String::INVALID_INDEX, unsigned; as an int a miss is
		// negative.
		int iAt = szName.Find( szWanted );
		if( iAt >= 0 )
			matches.insertLast( int( i ) );
	}

	if( matches.length() == 0 )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] No mission matches \"" + szQuery + "\".\n" );
		return;
	}

	if( matches.length() == 1 )
	{
		APChapter@ pChapter = g_Chapters[matches[0]];

		if( iPart > 0 )
		{
			if( uint( iPart ) > pChapter.maps.length() )
			{
				g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
					"[AP] " + pChapter.name + " has only "
					+ pChapter.maps.length() + " part(s).\n" );
				return;
			}

			WarpToMap( pPlayer, pChapter, pChapter.maps[iPart - 1] );
			return;
		}

		WarpToChapter( pPlayer, matches[0] );
		return;
	}

	g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
		"[AP] " + matches.length() + " missions match; be more specific:\n" );

	for( uint i = 0; i < matches.length() && i < 4; ++i )
	{
		APChapter@ pChapter = g_Chapters[matches[i]];
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP]   " + matches[i] + ". " + pChapter.name + "\n" );
	}
}

/*
* Has anyone reached this map yet?
*
* Answered by the map's own "reached" check, which the client tells us about in
* the same breath as everything else `!tracker` needs. It is a better question
* than "is the mission unlocked", because it is the one that makes travelling
* back safe: a part you have stood in is a part you got to legitimately.
*/
bool MapReached( const string& in szMap )
{
	for( uint i = 0; i < g_Locations.length(); ++i )
	{
		APLocation@ pLocation = g_Locations[i];
		if( pLocation.kind == TRIGGER_MAP_REACHED && pLocation.map == szMap )
			return g_CheckedLocations.exists( "" + pLocation.id );
	}

	// No "reached" check for it at all, so nothing to go on; let the mission's
	// own lock be the only gate.
	return true;
}

/* `Part 3`, or "" for a mission that is one map. */
string PartLabel( APChapter@ pChapter, const string& in szMap )
{
	if( pChapter is null || pChapter.maps.length() < 2 )
		return "";

	for( uint i = 0; i < pChapter.maps.length(); ++i )
	{
		if( pChapter.maps[i] == szMap )
			return "Part " + ( i + 1 );
	}

	return "";
}

/*
* Travel to one map of a mission rather than its start.
*
* Only somewhere already reached. The point is going back for checks missed on
* the way through, not skipping the parts between -- so the mission has to be
* unlocked *and* the part has to be one you have already stood in.
*/
void WarpToMap( CBasePlayer@ pPlayer, APChapter@ pChapter, const string& in szMap )
{
	if( pChapter is null )
		return;

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

	// The first map of a mission is always fair game: that is what the console
	// and `!warp <mission>` do, and you cannot have reached anything else first.
	if( szMap != pChapter.FirstMap() && !MapReached( szMap ) )
	{
		g_PlayerFuncs.ClientPrint( pPlayer, HUD_PRINTTALK,
			"[AP] You have not reached that part yet. Play there first.\n" );
		return;
	}

	string szPart = PartLabel( pChapter, szMap );
	g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
		"[AP] Travelling to " + pChapter.name
		+ ( szPart.Length() > 0 ? ", " + szPart : "" ) + "...\n" );
	ChangeLevel( szMap );
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
/*
* The same commands from the console as from chat.
*
* Chat is where they were born, but typing `!find` means opening chat, losing
* mouse look and pushing five lines of scrollback up the screen, which is a lot
* of ceremony to ask where a charger is. These are the console spellings.
*
* Registered as file-scope globals, which is how Sven Co-op's own plugins do it
* (`scripts/plugins/Yell.as`): the object's construction is the registration, so
* it happens once when the module loads and never repeats on a map change.
*
* Prefixed `ap` throughout, because `find` and `help` are words the console
* already has opinions about.
*/
string ConsoleArgs( const CCommand@ pArgs )
{
	string szQuery;

	for( int i = 1; i < pArgs.ArgC(); ++i )
	{
		if( szQuery.Length() > 0 )
			szQuery += " ";
		szQuery += pArgs[i];
	}

	return szQuery;
}

void ConsoleStatus( const CCommand@ pArgs )
{
	CBasePlayer@ pPlayer = g_ConCommandSystem.GetCurrentPlayer();
	if( pPlayer !is null )
		ShowStatus( pPlayer );
}

void ConsoleTracker( const CCommand@ pArgs )
{
	CBasePlayer@ pPlayer = g_ConCommandSystem.GetCurrentPlayer();
	if( pPlayer !is null )
		ShowTracker( pPlayer, ConsoleArgs( pArgs ) );
}

void ConsoleFind( const CCommand@ pArgs )
{
	CBasePlayer@ pPlayer = g_ConCommandSystem.GetCurrentPlayer();
	if( pPlayer !is null )
		FindLocation( pPlayer, ConsoleArgs( pArgs ) );
}

void ConsoleWarp( const CCommand@ pArgs )
{
	CBasePlayer@ pPlayer = g_ConCommandSystem.GetCurrentPlayer();
	if( pPlayer is null )
		return;

	WarpToQuery( pPlayer, ConsoleArgs( pArgs ) );
}

void ConsoleHub( const CCommand@ pArgs )
{
	CBasePlayer@ pPlayer = g_ConCommandSystem.GetCurrentPlayer();
	if( pPlayer is null )
		return;

	g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] Returning to the hub...\n" );
	ReturnToHub();
}

void ConsoleHelp( const CCommand@ pArgs )
{
	CBasePlayer@ pPlayer = g_ConCommandSystem.GetCurrentPlayer();
	if( pPlayer !is null )
		ShowHelp( pPlayer );
}

CClientCommand g_CmdStatus( "ap", "List missions and what is unlocked", @ConsoleStatus );
CClientCommand g_CmdTracker( "ap_tracker", "Locations found and still missing", @ConsoleTracker );
CClientCommand g_CmdFind( "ap_find", "Point at the nearest check, or one you name", @ConsoleFind );
CClientCommand g_CmdWarp( "ap_warp", "Travel to an unlocked mission", @ConsoleWarp );
CClientCommand g_CmdHub( "ap_hub", "Return to the campaign portal", @ConsoleHub );
CClientCommand g_CmdHelp( "ap_help", "List the Archipelago commands", @ConsoleHelp );

/*
* Say out loud whether the console commands took.
*
* Registration happens when the module loads, which is server start or
* `as_reloadplugins` -- copying new script files over a running server changes
* nothing until then. Without this line the only symptom is a command that does
* not exist, which looks identical to a command that was never written.
*/
void ReportClientCommands()
{
	string szNames;
	uint uiAdded = 0;

	array<CClientCommand@> commands = {
		@g_CmdStatus, @g_CmdTracker, @g_CmdFind,
		@g_CmdWarp, @g_CmdHub, @g_CmdHelp
	};

	for( uint i = 0; i < commands.length(); ++i )
	{
		if( commands[i] is null )
			continue;

		if( commands[i].HasBeenAdded() )
		{
			++uiAdded;
			if( szNames.Length() > 0 )
				szNames += ", ";
			// The *qualified* name, which is what a player actually types. Sven
			// namespaces a plugin's console commands using `concommandns` from
			// default_plugins.txt, and with none set the separator dot is still
			// there -- so these are `.ap`, not `ap`. Logging GetName() instead
			// printed a list of commands that do not exist.
			szNames += commands[i].GetFullyQualifiedName();
		}
		else
		{
			APLog( "console command " + commands[i].GetName() + " was refused; "
			       + "something else on this server already owns that name" );
		}
	}

	APLog( "console commands ready (" + uiAdded + "): " + szNames );
}

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

	if( szCommand == "!find" )
	{
		pParams.ShouldHide = true;
		// Everything after the command, so `!find health charger` works.
		string szQuery;
		for( int i = 1; i < pArguments.ArgC(); ++i )
		{
			if( szQuery.Length() > 0 )
				szQuery += " ";
			szQuery += pArguments[i];
		}
		FindLocation( pPlayer, szQuery );
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
		string szWarp;
		for( int i = 1; i < pArguments.ArgC(); ++i )
		{
			if( szWarp.Length() > 0 )
				szWarp += " ";
			szWarp += pArguments[i];
		}
		WarpToQuery( pPlayer, szWarp );
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
