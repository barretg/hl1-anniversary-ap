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
		if( g_StartingWeapons[i] == szClassname )
			return true;

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
			allowed.insertLast( keys[i] );
	}

	return allowed;
}

/*
* Rebuild a player's inventory to exactly what the multiworld has granted.
*
* Ammo is deliberately kept (RemoveAllItems' second argument is false): ammo
* pickups stay useful, and finding a stash before the gun is a normal part of
* the run rather than a loss.
*/
void ApplyLoadout( CBasePlayer@ pPlayer )
{
	if( pPlayer is null || !pPlayer.IsConnected() )
		return;

	bool bSuitAllowed = ClassnameAllowed( "item_suit" );
	pPlayer.RemoveAllItems( !bSuitAllowed, false );

	array<string> allowed = AllowedClassnames();
	for( uint i = 0; i < allowed.length(); ++i )
	{
		// The suit and long jump module are items, not weapons; giving them
		// when they are not owned is exactly what we are preventing.
		pPlayer.GiveNamedItem( allowed[i] );
	}
}

void ApplyLoadoutToAll()
{
	for( int i = 1; i <= g_Engine.maxClients; ++i )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( i );
		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;
		ApplyLoadout( pPlayer );
	}
}

/*
* Catch weapons that arrived by a route CanCollect does not cover -- most
* importantly the per-map `game_player_equip` entities the HL campaign uses.
*
* Runs on a slow timer rather than every think: it walks the inventory and only
* touches it when something is actually not allowed, so an untouched loadout
* costs nothing and firing is never interrupted.
*/
void SweepIllegalWeapons()
{
	for( int iClient = 1; iClient <= g_Engine.maxClients; ++iClient )
	{
		CBasePlayer@ pPlayer = g_PlayerFuncs.FindPlayerByIndex( iClient );
		if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
			continue;

		for( int iSlot = 0; iSlot < MAX_ITEM_TYPES; ++iSlot )
		{
			CBasePlayerItem@ pItem = pPlayer.m_rgpPlayerItems( iSlot );

			while( pItem !is null )
			{
				// Grab the next link first: removing an item unlinks it.
				CBasePlayerItem@ pNext = cast<CBasePlayerItem@>( pItem.m_pNext.GetEntity() );

				if( !ClassnameAllowed( pItem.GetClassname() ) )
				{
					pPlayer.RemovePlayerItem( pItem );
					g_EntityFuncs.Remove( pItem );
				}

				@pItem = pNext;
			}
		}
	}
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

		if( szItemName == "Medkit" || szItemName == "Health Charge" )
		{
			pPlayer.GiveHealth( 25.0f, DMG_GENERIC );
		}
		else if( szItemName == "Armor Battery" )
		{
			pPlayer.pev.armorvalue = Math.min( pPlayer.pev.armorvalue + 20.0f, MAX_NORMAL_BATTERY );
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
	for( int iSlot = 0; iSlot < MAX_ITEM_TYPES; ++iSlot )
	{
		CBasePlayerItem@ pItem = pPlayer.m_rgpPlayerItems( iSlot );

		while( pItem !is null )
		{
			CBasePlayerWeapon@ pWeapon = cast<CBasePlayerWeapon@>( pItem );
			if( pWeapon !is null )
			{
				string szAmmo = pWeapon.pszAmmo1();
				if( szAmmo.Length() > 0 )
					pPlayer.GiveAmmo( pWeapon.iMaxClip() > 0 ? pWeapon.iMaxClip() * 2 : 20,
					                  szAmmo, pWeapon.iMaxAmmo1() );
			}

			@pItem = cast<CBasePlayerItem@>( pItem.m_pNext.GetEntity() );
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
		return HOOK_CONTINUE;

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
