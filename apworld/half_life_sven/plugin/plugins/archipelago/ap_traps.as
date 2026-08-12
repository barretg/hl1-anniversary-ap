/*
* Traps.
*
* All three are nuisances, never punishments. A trap that can cost a run turns
* every unopened location into a reason not to play, so nothing here kills, takes
* progress away, or removes anything permanently -- Butterfingers is the closest,
* and the suit hands the weapon back half a minute later.
*
* Delivered as one-shot `TRAP` events, so they fire once and never replay on a
* map load or a reconnect. Because they only ever fire once, a trap that arrives
* while there is nobody to spring it on is simply gone -- which is what the queue
* below exists to prevent.
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

// How long before the dropped weapon can be picked back up. Without this the
// player is standing on it and collects it again the same tick, and the trap is
// a flicker of the HUD.
const float BUTTERFINGERS_GRACE = 2.0f;

// How hard it is thrown, and how much of that is upward. Enough to land a stride
// or two away rather than at the player's feet.
const float BUTTERFINGERS_THROW = 250.0f;
const float BUTTERFINGERS_LIFT = 150.0f;

// "<player entindex>|<classname>" -> g_Engine.time it hit the floor. Two windows
// hang off it: the grace period, and the far longer one during which the loadout
// sweep must leave the weapon where it landed.
dictionary g_flWeaponDroppedAt;

string DroppedKey( CBasePlayer@ pPlayer, const string& in szClassname )
{
	return "" + pPlayer.entindex() + "|" + szClassname;
}

float SecondsSinceDropped( CBasePlayer@ pPlayer, const string& in szClassname )
{
	float flWhen = 0.0f;
	if( !g_flWeaponDroppedAt.get( DroppedKey( pPlayer, szClassname ), flWhen ) )
		return -1.0f;

	return g_Engine.time - flWhen;
}

/* Is this weapon on the floor because a trap put it there? */
bool WeaponWithheld( CBasePlayer@ pPlayer, const string& in szClassname )
{
	float flAge = SecondsSinceDropped( pPlayer, szClassname );

	if( flAge < 0.0f )
		return false;

	if( flAge >= BUTTERFINGERS_SECONDS )
	{
		g_flWeaponDroppedAt.delete( DroppedKey( pPlayer, szClassname ) );
		return false;
	}

	return true;
}

/* Too soon to pick it straight back up? */
bool WeaponJustDropped( CBasePlayer@ pPlayer, const string& in szClassname )
{
	float flAge = SecondsSinceDropped( pPlayer, szClassname );
	return flAge >= 0.0f && flAge < BUTTERFINGERS_GRACE;
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
	g_flWeaponDroppedAt.deleteAll();
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
	array<string>@ keys = g_flWeaponDroppedAt.getKeys();

	for( uint i = 0; i < keys.length(); ++i )
	{
		if( keys[i].SubString( 0, szPrefix.Length() ) == szPrefix )
			g_flWeaponDroppedAt.delete( keys[i] );
	}
}

/*
* How long a map has to have been settled before the queue drains onto it.
*
* Counted from the moment there is somewhere for a trap to land, not from the
* map load: arriving is not the same as being on your feet in the level, and a
* trap sprung during the loading screen is a trap nobody sees.
*/
const float TRAP_QUEUE_DELAY = 5.0f;

// A ceiling on how much can pile up. Each spawn trap puts four monsters around
// every player, so an unbounded queue draining at once is a server hitch at
// best. Reaching this means several traps arrived during one loading screen,
// which the delay alone should already have made unlikely.
const uint TRAP_QUEUE_MAX = 12;

// Traps that arrived with nowhere to land, oldest first. Deliberately a plain
// global: it survives a map change, which is the entire point -- a trap received
// on the way out of one level springs on the next one.
array<string> g_QueuedTraps;

// g_Engine.time at which this map became somewhere a trap could land, or 0 if it
// is not somewhere right now. Reset on every map load, because g_Engine.time
// restarts there and a stamp from the last map means nothing on this one.
float g_flTrapGroundSince = 0.0f;

/*
* A trap has arrived. Hold it rather than spring it.
*
* Nothing is sprung from here even when the map is perfectly ready: the queue
* drains on the sweep, so a trap that lands mid-level still waits out a tick or
* two, and every trap goes through exactly one path.
*/
void SpringTrap( const string& in szName )
{
	if( !KnownTrap( szName ) )
	{
		// Not something we can ever spring, so queueing it would only leave it
		// sitting there being retried forever.
		APLog( "unknown trap: " + szName );
		return;
	}

	if( g_QueuedTraps.length() >= TRAP_QUEUE_MAX )
	{
		APLog( "trap queue full, dropping: " + szName );
		return;
	}

	g_QueuedTraps.insertLast( szName );
}

bool KnownTrap( const string& in szName )
{
	return szName == "Scientist Trap"
	    || szName == "Headcrab Trap"
	    || szName == "Butterfingers Trap";
}

/*
* Is there anywhere for a trap to land right now?
*
* Two ways for the answer to be no. Nobody alive and out of observer mode is the
* obvious one -- every trap here acts on living players, so with none the trap is
* spent on nothing. A queued level change is the subtle one: the map is loaded
* and people are standing on it, but they are about to be somewhere else, and
* spawning a crowd of headcrabs into a level that is one breath from unloading
* is the same waste as spawning them into a loading screen.
*/
bool TrapGroundReady()
{
	if( g_szPendingLevel.Length() > 0 )
		return false;

	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );

		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;
		if( pPlayer.GetObserver().IsObserver() )
			continue;

		return true;
	}

	return false;
}

/*
* Drain the queue if the level has been standing still long enough.
*
* Called from the once-a-second sweep, so the real wait is TRAP_QUEUE_DELAY plus
* up to a second. Anything that makes the ground unready -- a level change queued,
* the last player dying -- puts the clock back to zero, so the countdown restarts
* rather than resuming: five settled seconds, not five seconds in total.
*/
void ProcessTrapQueue()
{
	if( !TrapGroundReady() )
	{
		g_flTrapGroundSince = 0.0f;
		return;
	}

	if( g_flTrapGroundSince == 0.0f )
		g_flTrapGroundSince = g_Engine.time;

	if( g_QueuedTraps.length() == 0 )
		return;

	if( g_Engine.time - g_flTrapGroundSince < TRAP_QUEUE_DELAY )
		return;

	// Taken as a copy and cleared first: springing a trap can print, spawn and
	// schedule, and none of that should be able to see a half-drained queue.
	array<string> pending = g_QueuedTraps;
	g_QueuedTraps.resize( 0 );

	for( uint i = 0; i < pending.length(); ++i )
		SpringTrapNow( pending[i] );
}

/*
* Forget that this map was ever settled.
*
* Called on map load. Only the clock is reset -- the queue itself is what carries
* the held traps to the new map.
*/
void ResetTrapGround()
{
	g_flTrapGroundSince = 0.0f;
}

void SpringTrapNow( const string& in szName )
{
	if( szName == "Scientist Trap" )
		SpawnTrap( "monster_scientist", "Someone called for a science team." );
	else if( szName == "Headcrab Trap" )
		SpawnTrap( "monster_headcrab", "What remarkable specimen!" );
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
		g_flWeaponDroppedAt[ DroppedKey( pPlayer, szClassname ) ] = g_Engine.time;

		// DropItem with no position throws the held weapon the way the engine's
		// own drop does. It is `DropItem`, not `DropPlayerItem` -- the latter is
		// the C++ name and is not bound to script.
		CBaseEntity@ pDropped = pPlayer.DropItem( szClassname );

		if( pDropped is null )
		{
			// Some weapons refuse to be dropped. Do not leave a booking behind
			// that would stop the sweep reissuing something they still hold.
			g_flWeaponDroppedAt.delete( DroppedKey( pPlayer, szClassname ) );
			continue;
		}

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
