/*
* Weapon gating and item delivery.
*
* Three things have to line up for the crowbar-only start to hold:
*   1. The HL campaign .cfg files equip a full loadout on spawn (see the
*      `weapon_*` lines in maps/hl_c*.cfg), so we strip and re-grant on spawn.
*   2. Weapons lying in the world must refuse to be picked up -- that is the
*      PickupObject::CanCollect hook.
*   3. Anything that slips through either of those (scripted_sequence gifts,
*      game_player_equip, monster drops) is caught by a periodic sweep.
*/

/* Is this classname allowed in a player's hands right now? */
bool ClassnameAllowed( const string& in szClassname )
{
	for( uint i = 0; i < g_StartingWeapons.length(); ++i )
	{
		if( g_StartingWeapons[i] == szClassname )
			return true;
	}

	string szItem;
	if( !g_LockedClassnames.get( szClassname, szItem ) )
		return true;  // not something we gate (ammo, health, unknown weapons)

	return g_State.ItemUnlocked( szItem );
}

/* Every classname the player is currently entitled to hold. */
array<string> AllowedClassnames()
{
	array<string> allowed = g_StartingWeapons;
	array<string>@ keys = g_LockedClassnames.getKeys();

	for( uint i = 0; i < keys.length(); ++i )
	{
		string szItem;
		if( g_LockedClassnames.get( keys[i], szItem ) && g_State.ItemUnlocked( szItem ) )
		{
			allowed.insertLast( keys[i] );
		}
	}

	return allowed;
}

// Handing this out with GiveNamedItem fires the suit's pickup sequence, which
// wipes the inventory we are in the middle of rebuilding. So the suit is never
// granted here: it is kept or taken instead, and the player earns it by walking
// over the pickup in Anomalous Materials once the item has arrived.
const string SUIT_CLASSNAME = "item_suit";

// Long enough for the suit's pickup sequence to have done its inventory wipe
// before we put the weapons back.
const float SUIT_PICKUP_RESTORE_DELAY = 1.5f;

// The long jump module does not live in the inventory either, so we cannot tell
// whether a player already has it by looking. It is granted only on the paths
// that run once, never on the repeating one.
const string LONGJUMP_CLASSNAME = "item_longjump";

/* Is the player already carrying this weapon? */
bool HasItem( CBasePlayer@ pPlayer, const string& in szClassname )
{
	for( size_t iSlot = 0; iSlot < MAX_ITEM_TYPES; ++iSlot )
	{
		CBasePlayerItem@ pItem = pPlayer.m_rgpPlayerItems( iSlot );

		while( pItem !is null )
		{
			if( pItem.GetClassname() == szClassname )
				return true;
			@pItem = cast<CBasePlayerItem@>( pItem.m_hNextItem.GetEntity() );
		}
	}

	return false;
}

/* Take away anything the multiworld has not granted, and nothing else. */
void StripDisallowed( CBasePlayer@ pPlayer )
{
	// m_rgpPlayerItems takes a size_t; using int here warns on every build.
	for( size_t iSlot = 0; iSlot < MAX_ITEM_TYPES; ++iSlot )
	{
		CBasePlayerItem@ pItem = pPlayer.m_rgpPlayerItems( iSlot );

		while( pItem !is null )
		{
			// Grab the next link first: removing an item unlinks it.
			CBasePlayerItem@ pNext = cast<CBasePlayerItem@>( pItem.m_hNextItem.GetEntity() );

			if( !ClassnameAllowed( pItem.GetClassname() ) )
			{
				pPlayer.RemovePlayerItem( pItem );
				g_EntityFuncs.Remove( pItem );
			}

			@pItem = pNext;
		}
	}
}

/*
* Bring a player's inventory in line with what the multiworld has granted.
*
* Deliberately additive: disallowed weapons are removed one at a time and
* missing ones are handed over, so nothing that is legitimately held is ever
* taken away first. The previous version wiped the inventory and rebuilt it,
* which meant any grant that failed to land left the player with nothing.
*
* Ammo is never touched. Ammo pickups stay useful, and finding a stash before
* the gun is a normal part of a run rather than a loss.
*
* `bFull` covers the things that cannot be detected on the player and so must
* not run on a repeating timer: the suit and the long jump module.
*/
void ApplyLoadout( CBasePlayer@ pPlayer, bool bFull = true )
{
	if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
		return;

	// Never strip on incomplete data. If checkdata.txt has not loaded we do not
	// know what is allowed, and taking everything away would leave the player
	// with no crowbar and no explanation.
	if( !CheckDataLoaded() )
	{
		APLog( "loadout skipped: checkdata.txt is not loaded" );
		return;
	}

	// Removing the suit is all-or-nothing in the API, so it is the one case that
	// still costs a full wipe. It only happens when the suit is shuffled and not
	// yet received, and the grant loop below puts the weapons straight back.
	if( bFull && !ClassnameAllowed( SUIT_CLASSNAME ) )
		pPlayer.RemoveAllItems( true, false );
	else
		StripDisallowed( pPlayer );

	array<string> allowed = AllowedClassnames();
	for( uint i = 0; i < allowed.length(); ++i )
	{
		string szClassname = allowed[i];

		// Never granted: doing so runs the suit's pickup sequence, which wipes
		// the inventory we are rebuilding.
		if( szClassname == SUIT_CLASSNAME )
			continue;

		if( szClassname == LONGJUMP_CLASSNAME )
		{
			if( bFull )
				pPlayer.GiveNamedItem( szClassname );
			continue;
		}

		if( !HasItem( pPlayer, szClassname ) )
			pPlayer.GiveNamedItem( szClassname );
	}
}

void ApplyLoadoutToAll( bool bFull = true )
{
	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );
		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;
		ApplyLoadout( pPlayer, bFull );
	}
}

/*
* The safety net, on a slow repeating timer.
*
* Catches weapons that arrived by a route CanCollect does not cover (most
* importantly the per-map `game_player_equip` entities the HL campaign uses),
* and equally puts back anything a grant failed to deliver. Because the work is
* now additive, a loadout that is already correct costs one inventory walk and
* changes nothing, so firing is never interrupted.
*
* This is what makes the loadout self-correcting: whatever goes wrong on spawn,
* it is right again within a second.
*/
void EnforceLoadouts()
{
	ApplyLoadoutToAll( false );
}

/*
* Deliver a filler item. Filler is generous on purpose -- most of the 174
* locations hold filler, so it needs to feel like a reward rather than noise.
*/
void GrantFillerItem( const string& in szItemName )
{
	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );
		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;

		// TakeHealth/TakeArmor add when given a positive amount; they are the
		// API's grant path despite the names.
		if( szItemName == "Medkit" || szItemName == "Health Charge" )
		{
			pPlayer.TakeHealth( 25.0f, DMG_GENERIC );
		}
		else if( szItemName == "Armor Battery" )
		{
			pPlayer.TakeArmor( 20.0f, DMG_GENERIC, 100 );
		}
		else if( szItemName == "Ammo Cache" )
		{
			GiveAmmoForHeldWeapons( pPlayer );
		}
	}

	g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] Received " + szItemName + "\n" );
}

/*
* Top up ammo for whatever the player is actually carrying, so an Ammo Cache is
* never dead weight the way a fixed ammo type would be.
*/
void GiveAmmoForHeldWeapons( CBasePlayer@ pPlayer )
{
	for( size_t iSlot = 0; iSlot < MAX_ITEM_TYPES; ++iSlot )
	{
		CBasePlayerItem@ pItem = pPlayer.m_rgpPlayerItems( iSlot );

		while( pItem !is null )
		{
			// GetWeaponPtr is the API's own accessor; a raw cast is not reliable.
			CBasePlayerWeapon@ pWeapon = pItem.GetWeaponPtr();
			if( pWeapon !is null )
			{
				string szAmmo = pWeapon.pszAmmo1();
				if( szAmmo.Length() > 0 )
					pPlayer.GiveAmmo( pWeapon.iMaxClip() > 0 ? pWeapon.iMaxClip() * 2 : 20,
					                  szAmmo, pWeapon.iMaxAmmo1() );
			}

			@pItem = cast<CBasePlayerItem@>( pItem.m_hNextItem.GetEntity() );
		}
	}
}

/* Refuse to hand over a weapon the multiworld has not granted yet. */
HookReturnCode PickupCanCollect( CBaseEntity@ pPickup, CBaseEntity@ pOther, bool& out bResult )
{
	bResult = true;

	if( pPickup is null )
		return HOOK_CONTINUE;

	CBasePlayer@ pPlayer = cast<CBasePlayer@>( pOther );
	if( pPlayer is null )
		return HOOK_CONTINUE;

	string szClassname = pPickup.GetClassname();

	// Walking over the weapon is what sends the check, whether or not the player
	// is allowed to keep it -- that is the whole point of the randomiser.
	RegisterPickupCheck( szClassname );

	if( ClassnameAllowed( szClassname ) )
	{
		// Collecting the suit runs a sequence that empties the inventory, so
		// hand the unlocked weapons back once it has finished with them.
		if( szClassname == SUIT_CLASSNAME )
			g_Scheduler.SetTimeout( "ApplyLoadoutDeferred", SUIT_PICKUP_RESTORE_DELAY,
			                        EHandle( pPlayer ) );

		return HOOK_CONTINUE;
	}

	bResult = false;
	g_PlayerFuncs.ClientPrint(
		pPlayer, HUD_PRINTCENTER,
		"You have not found the " + LockedItemName( szClassname ) + " yet.\n" );
	return HOOK_HANDLED;
}

string LockedItemName( const string& in szClassname )
{
	string szItem;
	if( g_LockedClassnames.get( szClassname, szItem ) )
		return szItem;
	return szClassname;
}
