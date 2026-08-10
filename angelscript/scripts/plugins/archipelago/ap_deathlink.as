/*
* DeathLink.
*
* The rule is the same regardless of where the death came from: any death is
* everyone's death. A player dying locally gibs the rest of the lobby and sends
* one DeathLink out; a DeathLink arriving from the multiworld gibs the lobby.
*
* The only thing standing between that and an infinite cascade is
* g_flDeathLinkImmuneUntil, which is always set *before* the wipe runs.
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

	string szName = string( pPlayer.pev.netname );
	string szCause = DeathCause( pAttacker );

	if( g_State.deathLink && g_State.connected )
		BridgeSend( "DEATH|" + szName + "|" + szCause );

	WipeLobby( pPlayer, szName + " died (" + szCause + ") and took everyone along." );

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
