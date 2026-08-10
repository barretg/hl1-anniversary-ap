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

// ap_in.txt is rewritten by the client, not appended to, so tracking its size is
// enough to know whether anything changed since the last poll.
uint g_uiLastInputSize = 0;

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

void SendCheck( APLocation@ pLocation )
{
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
*   items=<name>;<name>;...       AP item names we hold (weapons, equipment)
*   goal_open=0|1                 enough missions done to enter the goal mission
*   death_link=0|1
*   connected=0|1
*   event=<seq>|<kind>|<payload>|<unixtime>
*/
void BridgePoll()
{
	File@ pFile = g_FileSystem.OpenFile( AP_IN, OpenFile::READ );

	if( pFile is null || !pFile.IsOpen() )
		return;

	uint uiSize = pFile.GetSize();
	// Cheap early-out: an unchanged snapshot is the common case, several times
	// a second, and reparsing it would be pure waste.
	if( uiSize == g_uiLastInputSize )
	{
		pFile.Close();
		return;
	}
	g_uiLastInputSize = uiSize;

	dictionary chapters;
	dictionary items;
	bool bGoalOpen = false;
	bool bConnected = false;
	bool bDeathLink = false;
	array<string> events;

	while( !pFile.EOFReached() )
	{
		string szRaw;
		pFile.ReadLine( szRaw );
		string szLine = APTrim( szRaw );
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
		else if( szKey == "now" )
			g_flSnapshotNow = atof( szValue );
		else if( szKey == "goal_open" )
			bGoalOpen = szValue == "1";
		else if( szKey == "connected" )
			bConnected = szValue == "1";
		else if( szKey == "death_link" )
			bDeathLink = szValue == "1";
		else if( szKey == "event" )
			events.insertLast( szValue );
	}

	pFile.Close();

	bool bWasConnected = g_State.connected;

	g_State.unlockedChapters = chapters;
	g_State.unlockedItems = items;
	g_State.goalOpen = bGoalOpen;
	g_State.connected = bConnected;
	g_State.deathLink = bDeathLink;

	if( bConnected && !bWasConnected )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] Connected to the multiworld.\n" );

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
