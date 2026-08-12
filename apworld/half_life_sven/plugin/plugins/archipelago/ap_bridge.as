/*
* Archipelago file bridge.
*
* AngelScript has no sockets, but plugins may read and write inside
* scripts/plugins/store/. The Python client owns the connection to the
* Archipelago server and talks to us through two files:
*
*   ap_in.txt   client -> game, a full snapshot, rewritten whenever it changes.
*   ap_out.txt  game -> client, append-only event log.
*
* The snapshot is replayed in full on every map load, which is what makes the
* plugin stateless. Anything that must happen exactly once (an item grant, an
* incoming DeathLink) is carried as a sequenced `event=` line instead; we act on
* it, write back `ACK <seq>`, and the client drops it from the next snapshot.
*/

// The last snapshot text we parsed, so a poll that finds no change can bail out
// without reparsing. Compared in full rather than by size: `connected=1` and
// `connected=0` are the same length, and a size check would silently freeze the
// plugin on a stale snapshot forever.
string g_szLastInput;

// The client stamps each session with an id. When it changes, the client has
// restarted and its event sequence numbers have restarted with it.
string g_szSession;

// The client's wall-clock time when it last wrote the snapshot. Event freshness
// is judged against this, so the two sides never have to agree on a clock.
float g_flSnapshotNow = 0.0f;

/*
* Append one line to the outgoing log.
*
* Opened and closed per write: writes are rare (a handful per minute) and this
* means a crash mid-session never leaves a half-written file behind.
*/
void BridgeSend( const string& in szLine )
{
	File@ pFile = g_FileSystem.OpenFile( AP_OUT, OpenFile::APPEND );

	if( pFile is null || !pFile.IsOpen() )
	{
		APLog( "could not append to " + AP_OUT );
		return;
	}

	pFile.Write( szLine + "\n" );
	pFile.Close();
}

/*
* Refuse to work if our location ids do not mean the same thing as the seed's.
*
* This is the failure that looks like the plugin sending random checks: reaching
* a map fires the right id, but an older seed resolves that id to whatever
* location used to hold it.
*/
void CheckDataVersion( const string& in szClientVersion )
{
	if( szClientVersion.Length() == 0 || g_szDataVersion.Length() == 0 )
		return;

	bool bMismatch = szClientVersion != g_szDataVersion;
	if( bMismatch == g_bDataMismatch )
		return;

	g_bDataMismatch = bMismatch;

	if( bMismatch )
	{
		APLog( "DATA MISMATCH: plugin " + g_szDataVersion + ", client " + szClientVersion );
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
			"[AP] Plugin and apworld versions do not match. Checks are paused.\n"
			"[AP] Reinstall the plugin with /install, or regenerate your seed.\n" );
	}
	else
	{
		APLog( "data version matches the client" );
	}
}

void SendCheck( APLocation@ pLocation )
{
	// Sending here would report a location the seed does not agree with.
	if( g_bDataMismatch )
		return;

	string szKey = "" + pLocation.id;
	if( g_SentChecks.exists( szKey ) )
		return;

	g_SentChecks[ szKey ] = true;
	BridgeSend( "CHECK|" + pLocation.id );
	g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] " + pLocation.name + "\n" );
}

void SendAck( int iSeq )
{
	BridgeSend( "ACK|" + iSeq );
}

/*
* Read the whole snapshot and rebuild g_State from it.
*
* Recognised keys:
*   chapters=<key>,<key>,...      missions whose unlock item we hold
*   excluded=<key>,<key>,...      missions this seed left out entirely
*   items=<name>;<name>;...       AP item names we hold (weapons, equipment)
*   goal_open=0|1                 enough missions done to enter the goal mission
*   death_link=0|1
*   death_link_amnesty=<n>        deaths forgiven before one is reported out
*   connected=0|1
*   event=<seq>|<kind>|<payload>|<unixtime>
*/
void BridgePoll()
{
	File@ pFile = g_FileSystem.OpenFile( AP_IN, OpenFile::READ );

	if( pFile is null || !pFile.IsOpen() )
		return;

	// Read the whole file first, then decide whether it is worth parsing. The
	// snapshot is a couple of hundred bytes, so this is cheaper than being
	// clever and cannot go stale the way a size comparison can.
	string szInput;
	while( !pFile.EOFReached() )
	{
		string szRaw;
		pFile.ReadLine( szRaw );
		szInput += szRaw + "\n";
	}
	pFile.Close();

	if( szInput == g_szLastInput )
		return;
	g_szLastInput = szInput;

	array<string>@ inputLines = szInput.Split( "\n" );

	dictionary chapters;
	dictionary excluded;
	dictionary items;
	dictionary ungated;
	dictionary goalsOpen;
	bool bGoalOpen = false;
	bool bConnected = false;
	bool bDeathLink = false;
	int iAmnesty = 0;
	array<string> events;

	string szSession;

	for( uint iLine = 0; iLine < inputLines.length(); ++iLine )
	{
		string szLine = APTrim( inputLines[iLine] );
		if( szLine.Length() == 0 || szLine.SubString( 0, 1 ) == "#" )
			continue;

		int iSplit = szLine.Find( "=" );
		if( iSplit < 0 )
			continue;

		string szKey = szLine.SubString( 0, iSplit );
		string szValue = szLine.SubString( iSplit + 1, szLine.Length() - iSplit - 1 );

		if( szKey == "chapters" )
		{
			array<string>@ keys = szValue.Split( "," );
			for( uint i = 0; i < keys.length(); ++i )
			{
				string szChapter = APTrim( keys[i] );
				if( szChapter.Length() > 0 )
					chapters[ szChapter ] = true;
			}
		}
		else if( szKey == "goals_open" )
		{
			// One entry per campaign whose finale is unsealed. `goal_open` below
			// is the same thing collapsed to a bool for an older plugin.
			array<string>@ keys = szValue.Split( "," );
			for( uint i = 0; i < keys.length(); ++i )
			{
				string szChapter = APTrim( keys[i] );
				if( szChapter.Length() > 0 )
					goalsOpen[ szChapter ] = true;
			}
		}
		else if( szKey == "excluded" )
		{
			array<string>@ keys = szValue.Split( "," );
			for( uint i = 0; i < keys.length(); ++i )
			{
				string szChapter = APTrim( keys[i] );
				if( szChapter.Length() > 0 )
					excluded[ szChapter ] = true;
			}
		}
		else if( szKey == "items" )
		{
			// Item names contain commas ("Weapon, Mk II" style is possible), so
			// this list is semicolon separated.
			array<string>@ names = szValue.Split( ";" );
			for( uint i = 0; i < names.length(); ++i )
			{
				string szItem = APTrim( names[i] );
				if( szItem.Length() > 0 )
					items[ szItem ] = true;
			}
		}
		else if( szKey == "ungated" )
		{
			// Classnames, so semicolon separated for the same reason `items` is.
			array<string>@ names = szValue.Split( ";" );
			for( uint i = 0; i < names.length(); ++i )
			{
				string szClassname = APTrim( names[i] );
				if( szClassname.Length() > 0 )
					ungated[ szClassname ] = true;
			}
		}
		else if( szKey == "now" )
			g_flSnapshotNow = atof( szValue );
		else if( szKey == "session" )
			szSession = szValue;
		else if( szKey == "data_version" )
			CheckDataVersion( szValue );
		else if( szKey == "goal_open" )
			bGoalOpen = szValue == "1";
		else if( szKey == "connected" )
			bConnected = szValue == "1";
		else if( szKey == "death_link" )
			bDeathLink = szValue == "1";
		else if( szKey == "death_link_amnesty" )
			iAmnesty = atoi( szValue );
		else if( szKey == "event" )
			events.insertLast( szValue );
	}

	// A restarted client numbers its events from 1 again. Without this, every
	// new event would look like one we had already applied and be ACKed away.
	if( szSession != g_szSession )
	{
		if( g_szSession.Length() > 0 )
			APLog( "client session changed; resetting event sequence" );
		g_szSession = szSession;
		g_State.lastEventSeq = 0;
	}

	bool bWasConnected = g_State.connected;

	g_State.unlockedChapters = chapters;
	g_State.excludedChapters = excluded;
	g_State.unlockedItems = items;
	g_UngatedClassnames = ungated;
	g_State.goalsOpen = goalsOpen;
	g_State.goalOpen = bGoalOpen;
	g_State.connected = bConnected;
	g_State.deathLink = bDeathLink;
	g_State.deathLinkAmnesty = iAmnesty;

	if( bConnected && !bWasConnected )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
			"[AP] Connected to the multiworld. Type !help for commands.\n" );
	else if( !bConnected && bWasConnected )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] Lost the multiworld connection.\n" );

	// The one item whose arrival is otherwise invisible: the suit is never taken
	// away, so nothing on screen changes except that armour starts working.
	int iSuitNow = ClassnameAllowed( SUIT_CLASSNAME ) ? 1 : 0;
	if( iSuitNow == 1 && g_iSuitOwned == 0 )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
			"[AP] HEV suit power restored. Armour works from here on.\n" );
	g_iSuitOwned = iSuitNow;

	// Applying the snapshot may have unlocked a weapon, so refresh loadouts
	// before handling events (an incoming DeathLink should not race a grant).
	ApplyLoadoutToAll();

	for( uint i = 0; i < events.length(); ++i )
		HandleEvent( events[i] );
}

/*
* One `event=` payload: <seq>|<kind>|<data>|<unixtime>
*
* Anything at or below lastEventSeq has already been applied in this session.
* We still ACK it, because the client only drops a line once we say we have it.
*/
void HandleEvent( const string& in szPayload )
{
	array<string>@ parts = szPayload.Split( "|" );
	if( parts.length() < 4 )
		return;

	int iSeq = atoi( parts[0] );
	string szKind = parts[1];
	string szData = parts[2];
	float flStamp = atof( parts[3] );

	if( iSeq <= g_State.lastEventSeq )
	{
		SendAck( iSeq );
		return;
	}
	g_State.lastEventSeq = iSeq;

	if( szKind == "DEATHLINK" )
		ApplyIncomingDeathLink( szData, flStamp );
	else if( szKind == "ITEM" )
		GrantFillerItem( szData );
	else if( szKind == "TRAP" )
		SpringTrap( szData );
	else if( szKind == "CHAT" )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, szData + "\n" );

	SendAck( iSeq );
}

/*
* Announce ourselves. The client uses HELLO to learn which map we are on and to
* re-send the snapshot, which is how a client started after the game catches up.
*/
void BridgeHello()
{
	BridgeSend( "HELLO|" + g_szCurrentMap );
}
