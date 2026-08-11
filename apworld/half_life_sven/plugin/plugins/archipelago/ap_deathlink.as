/*
* DeathLink.
*
* The rule is the same regardless of where the death came from: any death is
* everyone's death. A player dying locally gibs the rest of the lobby and sends
* one DeathLink out; a DeathLink arriving from the multiworld gibs the lobby.
*
* The only thing standing between that and an infinite cascade is
* g_flDeathLinkImmuneUntil, which is always set *before* the wipe runs.
*
* Amnesty (see ForgiveDeath) can hold a local death back from the multiworld. It
* never holds back the wipe.
*/

// Long enough to cover the gibs we cause and a co-op wipe from one explosion,
// short enough that a genuine second death seconds later still counts.
const float DEATHLINK_IMMUNITY = 2.0f;

// A DeathLink that arrived while a map was loading is stale by the time we can
// act on it; killing on arrival at the new map would be baffling.
const float DEATHLINK_MAX_AGE = 10.0f;

bool DeathLinkImmune()
{
	return g_Engine.time < g_flDeathLinkImmuneUntil;
}

/*
* DeathLink amnesty.
*
* Amnesty only ever applies to deaths leaving the lobby. Inside it the rule does
* not change: one death is still everyone's death, because a wipe that sometimes
* happens and sometimes does not is worse than either.
*
* The allowance is a countdown shared by the whole lobby, spent one per death,
* and refilled the moment a death gets through. It lives in a file because it has
* to outlive map changes, which wipe every global the plugin has.
*/
void LoadAmnesty()
{
	g_iAmnestyRemaining = -1;

	File@ pFile = g_FileSystem.OpenFile( AP_AMNESTY, OpenFile::READ );

	if( pFile is null || !pFile.IsOpen() )
		return;

	string szLine;
	if( !pFile.EOFReached() )
		pFile.ReadLine( szLine );
	pFile.Close();

	szLine = APTrim( szLine );
	if( szLine.Length() > 0 )
		g_iAmnestyRemaining = atoi( szLine );
}

void SaveAmnesty()
{
	File@ pFile = g_FileSystem.OpenFile( AP_AMNESTY, OpenFile::WRITE );

	if( pFile is null || !pFile.IsOpen() )
		return;

	pFile.Write( "" + g_iAmnestyRemaining + "\n" );
	pFile.Close();
}

/*
* Spend one death against the allowance.
*
* Returns true if it was forgiven, in which case nothing leaves the lobby.
* A stale remaining count (the setting was lowered mid-run, or the file predates
* it) is clamped rather than trusted.
*/
bool ForgiveDeath()
{
	int iAmnesty = g_State.deathLinkAmnesty;

	if( iAmnesty <= 0 )
		return false;

	// Nothing is leaving the lobby anyway, so there is nothing to forgive and no
	// allowance to spend. Reading a stale `false` here fails in the safe
	// direction: the death is reported and the client decides, as usual.
	if( !g_State.deathLink )
		return false;

	if( g_iAmnestyRemaining < 0 || g_iAmnestyRemaining > iAmnesty )
		g_iAmnestyRemaining = iAmnesty;

	if( g_iAmnestyRemaining > 0 )
	{
		--g_iAmnestyRemaining;
		SaveAmnesty();
		return true;
	}

	// Spent. This death goes out, and the allowance starts again.
	g_iAmnestyRemaining = iAmnesty;
	SaveAmnesty();
	return false;
}

/*
* Gib every living player except the one who is already dying.
*
* DMG_ALWAYSGIB is the point: a DeathLink should be unmistakable.
*/
void WipeLobby( CBasePlayer@ pExcept, const string& in szReason )
{
	g_flDeathLinkImmuneUntil = g_Engine.time + DEATHLINK_IMMUNITY;

	entvars_t@ pWorld = g_EntityFuncs.Instance( 0 ).pev;

	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );

		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;
		if( pPlayer.GetObserver().IsObserver() )
			continue;
		if( pExcept !is null && pPlayer.entindex() == pExcept.entindex() )
			continue;

		pPlayer.TakeDamage( pWorld, pWorld, 10000.0f, DMG_GENERIC | DMG_ALWAYSGIB );
	}

	g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] " + szReason + "\n" );
}

/* A player died for real. Report it once, and take the lobby with them. */
HookReturnCode PlayerKilled( CBasePlayer@ pPlayer, CBaseEntity@ pAttacker, int iGib )
{
	if( pPlayer is null )
		return HOOK_CONTINUE;

	// Either we caused this death, or another death is already being processed.
	if( DeathLinkImmune() )
		return HOOK_CONTINUE;

	string szName = APSanitise( string( pPlayer.pev.netname ) );
	string szCause = DeathCause( pAttacker );
	bool bForgiven = ForgiveDeath();

	// Reported unconditionally, forgiven or not. Whether it becomes a DeathLink
	// is the client's call, and the client is the only thing that actually knows
	// -- gating here on our cached copy of its flags means any staleness silently
	// swallows deaths, with nothing in either log to say why. The amnesty flag is
	// advice the client applies on top of that.
	BridgeSend( "DEATH|" + szName + "|" + szCause + "|" + ( bForgiven ? "1" : "0" ) );

	string szReason = szName + " died (" + szCause + ") and took everyone along.";
	if( bForgiven )
		szReason += " Amnesty remaining: " + g_iAmnestyRemaining;

	WipeLobby( pPlayer, szReason );

	return HOOK_CONTINUE;
}

/* A DeathLink arrived from another world. */
void ApplyIncomingDeathLink( const string& in szData, float flStamp )
{
	// szData is "<source>|<cause>", but HandleEvent already split on '|', so the
	// client joins those two with a '~' before sending.
	array<string>@ parts = szData.Split( "~" );
	string szSource = parts.length() > 0 ? parts[0] : "someone";
	string szCause = parts.length() > 1 ? parts[1] : "an unknown fate";

	// Both timestamps come from the client's clock -- the `now=` line written
	// into the same snapshot we are reading -- so this needs no engine time and
	// is immune to the map-load pause that g_Engine.time would hide.
	float flAge = g_flSnapshotNow - flStamp;
	if( flAge > DEATHLINK_MAX_AGE )
	{
		APLog( "ignoring stale DeathLink from " + szSource + " (" + int( flAge ) + "s old)" );
		return;
	}

	WipeLobby( null, szSource + " died (" + szCause + "). So did you." );
}

string DeathCause( CBaseEntity@ pAttacker )
{
	if( pAttacker is null )
		return "mysterious circumstances";

	string szClassname = pAttacker.GetClassname();

	if( szClassname == "worldspawn" )
		return "the scenery";
	if( szClassname == "player" )
		return "friendly fire";
	if( szClassname.SubString( 0, 8 ) == "monster_" )
		return szClassname.SubString( 8, szClassname.Length() - 8 );

	return szClassname;
}
