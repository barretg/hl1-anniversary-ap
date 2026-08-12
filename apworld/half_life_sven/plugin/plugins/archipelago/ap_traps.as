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

// The band each spawn lands in: far enough out not to telefrag anyone, close
// enough to be everyone's problem. Rolled per monster, so four of them arrive at
// four different distances rather than on the rim of a circle.
const float TRAP_SPAWN_MIN_RADIUS = 72.0f;
const float TRAP_SPAWN_MAX_RADIUS = 160.0f;

// How many bearings to try before giving up on one monster. A random bearing
// indoors is very often pointing at a wall, and one roll would mean a trap in a
// corridor spawning one scientist instead of four.
const int TRAP_PLACE_ATTEMPTS = 10;

// How far apart two of this trap's spawns have to be. Enough that they read as
// scattered rather than stacked, and that they are not born pushing each other.
const float TRAP_MIN_SEPARATION = 40.0f;

// Backed off whatever the outward trace hit, so nobody arrives wedged in a wall.
const float TRAP_WALL_MARGIN = 16.0f;

// How far a chosen spot may fall before it stops counting as the same room. A
// short drop is a step or a kerb; a long one is the monster leaving down a shaft
// the moment it arrives.
const float TRAP_DROP_HEIGHT = 128.0f;

// Half the height of the engine's standing hulls, which is the distance between
// the point a hull trace works with (the centre of the box) and a monster's own
// origin (its feet). Hull 1 is 32x32x72 and hull 3 is 32x32x36.
const float HUMAN_HULL_HALF = 36.0f;
const float HEAD_HULL_HALF = 18.0f;

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
* Whether this map's precache table has the trap monsters in it.
*
* GoldSrc will only accept a precache while the map is spawning, and killed the
* server outright the first time a trap tried to create a scientist on a map
* that had none of its own:
*
*   Host_Error: PF_precache_model: 'models/scientist.mdl' Precache can only be
*   done in spawn functions
*
* So the models are booked in MapInit instead, and this records that it happened.
* Cleared in Initialise, which runs on plugin load as well as on map load -- a
* plugin reloaded mid-map missed its chance to precache anything, and must not
* spawn a monster until the next map has booked them properly.
*/
bool g_bTrapMonstersPrecached = false;

/*
* Book the trap monsters into this map's precache table.
*
* MapInit only. Anywhere later is the crash above. The cost is paid on every map
* whether or not a trap ever arrives, which is the trade: a handful of models in
* the precache table against a server that dies when one does.
*
* PrecacheMonster builds the monster once and throws it away, so it pulls in the
* models, sounds and sentences its own Precache would -- including the scientist
* sub-models the spawner picks between.
*/
void PrecacheTrapMonsters()
{
	g_Game.PrecacheMonster( "monster_scientist", true );
	g_Game.PrecacheMonster( "monster_headcrab", false );

	g_bTrapMonstersPrecached = true;
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

	// Nothing can be spawned on this map, so hold everything -- including
	// Butterfingers, which needs no precache -- rather than draining half a queue
	// now and leaving the rest. The next map load books the models and releases
	// the lot.
	if( !g_bTrapMonstersPrecached )
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

	// Earned back by MapInit, which is the only place a precache is legal. Set
	// here rather than trusted from the last map: the precache table belongs to
	// the map, so it goes when the map does.
	g_bTrapMonstersPrecached = false;
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
*
* Four is the ambition, not a promise. Each one is placed independently and a
* cramped room may have room for fewer, which is better than four in the walls.
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

		// One of each sub-model rather than four of one, in an order nobody can
		// predict, so a science team looks like a crowd rather than a clone.
		array<int> variants = { 0, 1, 2, 3 };
		ShuffleVariants( variants );

		// Where this player's spawns have already gone, so the next one can be
		// told to stand somewhere else. Per player rather than shared: two players
		// on top of each other getting spawns in the same spot is the trap working.
		array<Vector> placed;

		for( int j = 0; j < TRAP_SPAWN_COUNT; ++j )
		{
			if( SpawnOne( pPlayer, szClassname, variants[j % SCIENTIST_VARIANTS],
			              placed ) )
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
* Place one monster somewhere around a player.
*
* Bearing and distance are both rolled, and rolled again from scratch on every
* attempt: a rejected spot means that direction was no good, so nudging it would
* mostly find the same wall. Several attempts, because a random bearing in a
* corridor is usually pointing into a wall and the trap should still land.
*/
bool SpawnOne( CBasePlayer@ pPlayer, const string& in szClassname, int iVariant,
               array<Vector>@ placed )
{
	HULL_NUMBER hull = human_hull;
	float flHalfHeight = HUMAN_HULL_HALF;

	// A headcrab is nothing like a person-shaped hole, and testing one against a
	// human hull turns down crawlspaces and vents it fits through easily.
	if( szClassname == "monster_headcrab" )
	{
		hull = head_hull;
		flHalfHeight = HEAD_HULL_HALF;
	}

	for( int attempt = 0; attempt < TRAP_PLACE_ATTEMPTS; ++attempt )
	{
		float flBearing = Math.RandomFloat( 0.0f, 360.0f );
		float flRange = Math.RandomFloat( TRAP_SPAWN_MIN_RADIUS,
		                                  TRAP_SPAWN_MAX_RADIUS );

		Vector vecSpot;
		if( !FindTrapSpot( pPlayer, hull, flHalfHeight, flBearing, flRange, vecSpot ) )
			continue;

		// Two monsters in the same doorway read as one lump and can shove each
		// other through it. Cheaper to roll again than to resolve it after.
		if( TooCloseToPlaced( vecSpot, placed ) )
			continue;

		dictionary keys;
		keys[ "origin" ] = "" + vecSpot.x + " " + vecSpot.y + " " + vecSpot.z;
		// Facing back down the bearing, so whatever arrives is looking at whoever
		// it arrived for.
		keys[ "angles" ] = "0 " + ( flBearing + 180.0f ) + " 0";
		if( szClassname == "monster_scientist" )
			keys[ "body" ] = "" + iVariant;

		CBaseEntity@ pMonster = g_EntityFuncs.CreateEntity( szClassname, keys, true );

		if( pMonster is null )
			return false;

		placed.insertLast( vecSpot );
		return true;
	}

	return false;
}

/*
* Find somewhere on this bearing a monster can actually stand.
*
* Three traces, each rejecting a different way of arriving somewhere useless:
*
*   Outward, at chest height, using the monster's own hull. This is what keeps
*   them out of walls and in front of them rather than behind: it stops at the
*   first thing that hull cannot pass, so anything it reaches is connected to the
*   player by a corridor that hull fits down. A spot beyond the wall is never
*   reached in the first place.
*
*   Downward, to find the floor. Without it a spot chosen at chest height over a
*   staircase or a railing leaves the monster hanging in the air, and a headcrab
*   dropped into a lift shaft is a trap nobody ever meets. Limited to a short
*   fall, so "the floor" means this room and not the bottom of the map.
*
*   In place, at the resting spot. The belt-and-braces one: the drop can end with
*   a hull technically overlapping geometry it slid along, and a monster that
*   spawns inside the world either sticks or gets pushed through it.
*/
bool FindTrapSpot( CBasePlayer@ pPlayer, HULL_NUMBER hull, float flHalfHeight,
                   float flBearing, float flRange, Vector& out vecSpot )
{
	Vector vecAngles( 0.0f, flBearing, 0.0f );
	Math.MakeVectors( vecAngles );
	Vector vecDir = g_Engine.v_forward;

	Vector vecStart = pPlayer.pev.origin;

	TraceResult tr;
	g_Utility.TraceHull( vecStart, vecStart + vecDir * flRange, ignore_monsters,
	                     hull, pPlayer.edict(), tr );

	// The player is inside something, so nothing measured from here means
	// anything. Rare, but a trace that starts solid reports a fraction of 0 and
	// would otherwise read as "a wall right here".
	if( tr.fStartSolid != 0 || tr.fAllSolid != 0 )
		return false;

	float flReach = flRange * tr.flFraction;

	// Backed off whatever it hit, so the monster is standing near the wall rather
	// than shoulder-deep in it.
	if( tr.flFraction < 1.0f )
		flReach -= TRAP_WALL_MARGIN;

	// The wall is close enough that anything placed short of it would be inside
	// the player. Another bearing will do better.
	if( flReach < TRAP_SPAWN_MIN_RADIUS )
		return false;

	Vector vecCentre = vecStart + vecDir * flReach;

	TraceResult trDrop;
	g_Utility.TraceHull( vecCentre, vecCentre - Vector( 0.0f, 0.0f, TRAP_DROP_HEIGHT ),
	                     ignore_monsters, hull, pPlayer.edict(), trDrop );

	if( trDrop.fStartSolid != 0 || trDrop.fAllSolid != 0 )
		return false;

	// Nothing within a short fall: a ledge, a pit, or open air.
	if( trDrop.flFraction >= 1.0f )
		return false;

	Vector vecRest = trDrop.vecEndPos;

	TraceResult trFit;
	g_Utility.TraceHull( vecRest, vecRest, ignore_monsters, hull, pPlayer.edict(),
	                     trFit );

	if( trFit.fStartSolid != 0 || trFit.fAllSolid != 0 )
		return false;

	// Every trace above works in hull space, where the point being traced is the
	// centre of the box. A monster's origin is at its feet, so the same position
	// handed straight to the entity would bury it to the waist.
	vecSpot = vecRest - Vector( 0.0f, 0.0f, flHalfHeight - 1.0f );
	return true;
}

/* Is this spot on top of one we already used? */
bool TooCloseToPlaced( const Vector& in vecSpot, array<Vector>@ placed )
{
	for( uint i = 0; i < placed.length(); ++i )
	{
		if( ( placed[i] - vecSpot ).Length() < TRAP_MIN_SEPARATION )
			return true;
	}

	return false;
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
