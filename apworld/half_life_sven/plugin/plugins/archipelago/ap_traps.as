/*
* Traps.
*
* All three are nuisances, never punishments. A trap that can cost a run turns
* every unopened location into a reason not to play, so nothing here kills, takes
* progress away, or removes anything permanently -- Butterfingers is the closest,
* and the suit hands the weapon back half a minute later.
*
* Delivered as one-shot `TRAP` events, so they fire once and never replay on a
* map load or a reconnect.
*/

// Four of whatever is being spawned, arranged around each player.
const int TRAP_SPAWN_COUNT = 4;

// Far enough out not to telefrag anyone, close enough to be everyone's problem.
const float TRAP_SPAWN_RADIUS = 96.0f;

// The four scientist sub-models: Glasses, Einstein, Luther, Slick. One of each,
// in a random order, which is what makes it read as a crowd rather than a clone.
const int SCIENTIST_VARIANTS = 4;

// How long a dropped weapon stays dropped before the loadout sweep reissues it.
// Long enough to be a real inconvenience, short enough that a gun lost down a
// lift shaft is not a lost item.
const float BUTTERFINGERS_SECONDS = 30.0f;

// "<player entindex>|<classname>" -> g_Engine.time when the sweep may hand it
// back. Checked by ApplyLoadout, which would otherwise re-grant within a second
// and make the whole trap a flicker.
dictionary g_flWeaponWithheldUntil;

string WithheldKey( CBasePlayer@ pPlayer, const string& in szClassname )
{
	return "" + pPlayer.entindex() + "|" + szClassname;
}

/* Is this weapon currently on the floor because a trap put it there? */
bool WeaponWithheld( CBasePlayer@ pPlayer, const string& in szClassname )
{
	float flUntil = 0.0f;
	if( !g_flWeaponWithheldUntil.get( WithheldKey( pPlayer, szClassname ), flUntil ) )
		return false;

	if( g_Engine.time >= flUntil )
	{
		g_flWeaponWithheldUntil.delete( WithheldKey( pPlayer, szClassname ) );
		return false;
	}

	return true;
}

/*
* Forget every withheld weapon.
*
* Called on map load. The globals survive a map change but `g_Engine.time` does
* not, so a deadline recorded on the last map reads as far in the future on this
* one and would withhold the weapon indefinitely. A map change is a generous
* enough end to the trap anyway -- the dropped gun is on a level nobody is
* standing on any more.
*/
void ClearWithheldWeapons()
{
	g_flWeaponWithheldUntil.deleteAll();
}

/*
* Forget one player's withheld weapons.
*
* Dying already cost them everything they were carrying, and the loadout is
* rebuilt from scratch on respawn; making them wait out the rest of the timer on
* top of that is punishing a death twice.
*/
void ClearWithheldWeapons( CBasePlayer@ pPlayer )
{
	if( pPlayer is null )
		return;

	string szPrefix = "" + pPlayer.entindex() + "|";
	array<string>@ keys = g_flWeaponWithheldUntil.getKeys();

	for( uint i = 0; i < keys.length(); ++i )
	{
		if( keys[i].SubString( 0, szPrefix.Length() ) == szPrefix )
			g_flWeaponWithheldUntil.delete( keys[i] );
	}
}

void SpringTrap( const string& in szName )
{
	if( szName == "Scientist Trap" )
		SpawnTrap( "monster_scientist", "Someone called for a science team." );
	else if( szName == "Headcrab Trap" )
		SpawnTrap( "monster_headcrab", "Headcrabs. Of course it is headcrabs." );
	else if( szName == "Butterfingers Trap" )
		Butterfingers();
	else
		APLog( "unknown trap: " + szName );
}

/*
* Drop four of something around every living player.
*
* Like the rest of this plugin, a trap is the lobby's problem rather than one
* player's: a DeathLink takes everybody, so a headcrab delivery does too. Players
* standing together get one another's spawns on top of their own, which is the
* intended outcome and not worth deduplicating.
*/
void SpawnTrap( const string& in szClassname, const string& in szMessage )
{
	int iSpawned = 0;

	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );

		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;
		if( pPlayer.GetObserver().IsObserver() )
			continue;

		// Reshuffled per player, so two people do not get the same four
		// scientists standing in the same four places.
		array<int> variants = { 0, 1, 2, 3 };
		ShuffleVariants( variants );

		for( int j = 0; j < TRAP_SPAWN_COUNT; ++j )
		{
			if( SpawnOne( pPlayer, szClassname, ( 360.0f / TRAP_SPAWN_COUNT ) * j,
			              variants[j % SCIENTIST_VARIANTS] ) )
				++iSpawned;
		}
	}

	// Nobody alive, or nowhere to put them. The trap is simply spent.
	if( iSpawned > 0 )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] " + szMessage + "\n" );
	else
		APLog( "trap found nowhere to put " + szClassname );
}

/*
* Place one monster on a bearing from a player.
*
* The hull trace is what stops them arriving inside a wall: it stops at the first
* thing a human-sized body cannot pass, so the end position is somewhere one can
* actually stand. Pulled back a little from that so a monster hard against the
* wall is not wedged into it.
*/
bool SpawnOne( CBasePlayer@ pPlayer, const string& in szClassname, float flBearing,
               int iVariant )
{
	Vector vecAngles( 0.0f, pPlayer.pev.angles.y + flBearing, 0.0f );
	Math.MakeVectors( vecAngles );

	Vector vecStart = pPlayer.pev.origin;
	Vector vecEnd = vecStart + g_Engine.v_forward * TRAP_SPAWN_RADIUS;

	TraceResult tr;
	g_Utility.TraceHull( vecStart, vecEnd, ignore_monsters, human_hull,
	                     pPlayer.edict(), tr );

	// Solid the whole way: there is no room on this bearing at all.
	if( tr.flFraction < 0.25f )
		return false;

	Vector vecSpot = vecStart + g_Engine.v_forward
	                 * ( TRAP_SPAWN_RADIUS * tr.flFraction * 0.9f );

	dictionary keys;
	keys[ "origin" ] = "" + vecSpot.x + " " + vecSpot.y + " " + vecSpot.z;
	keys[ "angles" ] = "0 " + ( vecAngles.y + 180.0f ) + " 0";
	if( szClassname == "monster_scientist" )
		keys[ "body" ] = "" + iVariant;

	CBaseEntity@ pMonster = g_EntityFuncs.CreateEntity( szClassname, keys, true );
	return pMonster !is null;
}

/* Everyone drops what they are holding. */
void Butterfingers()
{
	int iDropped = 0;

	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );

		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;

		CBasePlayerItem@ pActive = cast<CBasePlayerItem@>(
			pPlayer.m_hActiveItem.GetEntity() );

		if( pActive is null )
			continue;

		string szClassname = pActive.GetClassname();

		// Booked before the drop: the loadout sweep runs every second and would
		// put it straight back in their hands.
		g_flWeaponWithheldUntil[ WithheldKey( pPlayer, szClassname ) ] =
			g_Engine.time + BUTTERFINGERS_SECONDS;

		pPlayer.DropPlayerItem( szClassname );
		++iDropped;
	}

	if( iDropped > 0 )
		g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
			"[AP] Butterfingers! Everyone dropped what they were holding.\n" );
}

void ShuffleVariants( array<int>@ values )
{
	for( uint i = values.length(); i > 1; --i )
	{
		uint j = uint( Math.RandomLong( 0, int( i ) - 1 ) );
		int swap = values[i - 1];
		values[i - 1] = values[j];
		values[j] = swap;
	}
}
