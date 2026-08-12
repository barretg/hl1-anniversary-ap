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

/*
* Has this seed left this classname to the game entirely?
*
* Checked ahead of everything else, because it is the one answer that means "do
* nothing" rather than "do something": no grant, no strip, no refusal at the
* pickup. Whatever Half-Life does with it is what happens.
*/
bool ClassnameUngated( const string& in szClassname )
{
	return g_UngatedClassnames.exists( szClassname );
}

/*
* Can this classname be handed over on the map we are on?
*
* False only for a weapon another campaign's map script owns. They Hunger's
* arsenal is custom entities registered by `scripts/maps/hunger/weapons/`, so
* asking for a tommy gun in Black Mesa asks the engine to build an entity that
* does not exist there. The item is not lost: the loadout is reapplied on every
* spawn and every map change, so it lands the moment the player is somewhere the
* weapon is real.
*/
bool ClassnameGrantableHere( const string& in szClassname )
{
	string szCampaigns;
	if( !g_RestrictedClassnames.get( szClassname, szCampaigns ) )
		return true;  // travels anywhere

	if( g_CurrentChapter is null )
		return false;

	array<string>@ keys = szCampaigns.Split( "," );
	for( uint i = 0; i < keys.length(); ++i )
	{
		if( APTrim( keys[i] ) == g_CurrentChapter.campaign )
			return true;
	}

	return false;
}

/* Is this classname allowed in a player's hands right now? */
bool ClassnameAllowed( const string& in szClassname )
{
	if( ClassnameUngated( szClassname ) )
		return true;

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

/*
* Every classname the player is currently entitled to be handed.
*
* Narrower than ClassnameAllowed on purpose: an ungated classname is allowed in
* the player's hands but must never be granted, or we would be handing out on
* spawn the very thing the campaign is supposed to hand out in its own time.
*/
array<string> AllowedClassnames()
{
	array<string> allowed = g_StartingWeapons;
	array<string>@ keys = g_LockedClassnames.getKeys();

	for( uint i = 0; i < keys.length(); ++i )
	{
		if( ClassnameUngated( keys[i] ) )
			continue;

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
// granted here; the player earns it by walking over the pickup in Anomalous
// Materials once the item has arrived.
//
// It is never taken away either, and that is deliberate. In GoldSrc the suit bit
// is what un-hides the weapon HUD, and the client's weapon-selection input is
// disabled behind the same flag -- so a player without the suit cannot switch
// weapons at all, which made an unsuited run close to unplayable. What the HEV
// Suit *item* controls is armour: see EnforceArmour.
const string SUIT_CLASSNAME = "item_suit";

// Long enough for the suit's pickup sequence to have done its inventory wipe
// before we put the weapons back.
const float SUIT_PICKUP_RESTORE_DELAY = 1.5f;

// The long jump module is never handed over with GiveNamedItem. That builds the
// pickup entity in the world and touches the player with it, so a grant the
// player did not need leaves a module lying on the floor -- and since the loadout
// is reapplied on every snapshot change, every item and every trap dropped
// another one. SetLongJump does what the pickup does, without the pickup.
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
* Safe to call as often as you like: everything it grants is checked against what
* the player already has first, so a run of it changes nothing.
*/
void ApplyLoadout( CBasePlayer@ pPlayer )
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

	EnsureSuit( pPlayer );
	StripDisallowed( pPlayer );
	EnforceArmour( pPlayer );

	// Left out of a seed that does not shuffle it: the campaign hands the module
	// over itself from Forget About Freeman onward, and switching it on here
	// would be doing that ten missions early.
	if( !ClassnameUngated( LONGJUMP_CLASSNAME ) )
		SetLongJump( pPlayer, ClassnameAllowed( LONGJUMP_CLASSNAME ) );

	array<string> allowed = AllowedClassnames();
	for( uint i = 0; i < allowed.length(); ++i )
	{
		string szClassname = allowed[i];

		// Never granted: doing so runs the suit's pickup sequence, which wipes
		// the inventory we are rebuilding.
		if( szClassname == SUIT_CLASSNAME )
			continue;

		// Not an inventory item; SetLongJump above has already dealt with it.
		if( szClassname == LONGJUMP_CLASSNAME )
			continue;

		// Owned, but not a thing this map knows how to build. See
		// ClassnameGrantableHere.
		if( !ClassnameGrantableHere( szClassname ) )
			continue;

		// Butterfingers put this on the floor on purpose. Handing it back one
		// second later would make the trap a flicker and nothing more.
		if( WeaponWithheld( pPlayer, szClassname ) )
			continue;

		if( !HasItem( pPlayer, szClassname ) )
			pPlayer.GiveNamedItem( szClassname );
	}
}

/*
* Turn the long jump module on or off, with nothing dropped in the world.
*
* This is precisely what CItemLongJump's pickup does: raise the flag on the
* player, and write "slj" into their physics key buffer, which is where the
* engine's movement code actually looks. Setting only the first leaves the flag
* true and the jump unchanged, which is a worse bug than the litter it replaced
* because nothing about it is visible.
*
* Also the only way to take the module away again -- it is not an inventory item,
* so StripDisallowed cannot see it, and a campaign .cfg that hands one out would
* otherwise stick for the rest of the run.
*
* Both halves are checked before either is skipped, because they do not live for
* the same length of time. m_fLongJump belongs to the player entity and is gone
* the moment a map changes; the physics key buffer belongs to the client
* connection and survives it. So after every level change the two disagree --
* flag false, "slj" still 1 -- and a guard that trusted the flag alone concluded
* there was nothing to do while the player carried on long jumping for the rest
* of the run.
*/
void SetLongJump( CBasePlayer@ pPlayer, bool bEnabled )
{
	string szWanted = bEnabled ? "1" : "0";

	KeyValueBuffer@ pPhysics = g_EngineFuncs.GetPhysicsKeyBuffer( pPlayer.edict() );
	bool bPhysicsAgrees = pPhysics is null || pPhysics.GetValue( "slj" ) == szWanted;

	if( pPlayer.m_fLongJump == bEnabled && bPhysicsAgrees )
		return;

	pPlayer.m_fLongJump = bEnabled;

	if( pPhysics !is null )
		pPhysics.SetValue( "slj", szWanted );
}

/*
* Make sure the player is wearing a suit, whatever the map thinks.
*
* In GoldSrc the suit bit is what draws the weapon HUD and what lets the client
* switch weapons at all, so a player without one cannot see or select anything
* they are carrying. Half-Life's maps hand it over themselves, which is why this
* was never needed; Opposing Force's do not, and Shephard turned up with no HUD
* and no way to change weapons.
*
* Safe everywhere, because in this world the suit is not what the HEV Suit item
* controls -- armour is, and EnforceArmour holds that at zero until the item
* arrives. Wearing the suit grants nothing on its own.
*/
void EnsureSuit( CBasePlayer@ pPlayer )
{
	if( !pPlayer.HasSuit() )
		pPlayer.SetHasSuit( true );
}

/*
* Armour is what the HEV Suit item actually grants.
*
* The suit itself is never removed -- without it there is no weapon HUD and no
* way to change weapons -- so the item has to mean something else, and armour is
* the honest answer: the HUD is the suit's interface, the armour is its function.
* Until the item arrives, armour is held at zero no matter where it came from:
* the campaign's own spawn loadout, a battery, a charge panel, or a filler grant.
*
* Applied from three places, in descending order of how quickly the player would
* otherwise see a number that is about to vanish: while they hold use on a
* charger, on spawn, and on the one-second sweep as the catch-all.
*/
void EnforceArmour( CBasePlayer@ pPlayer )
{
	if( pPlayer is null || !pPlayer.IsConnected() || !pPlayer.IsAlive() )
		return;

	// Not gated in this seed, or already earned.
	if( ClassnameAllowed( SUIT_CLASSNAME ) )
		return;

	if( pPlayer.pev.armorvalue > 0.0f )
		pPlayer.pev.armorvalue = 0.0f;
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
* The safety net, on a slow repeating timer.
*
* Catches weapons that arrived by a route CanCollect does not cover (most
* importantly the per-map `game_player_equip` entities the HL campaign uses),
* and equally puts back anything a grant failed to deliver. Because the work is
* now additive, a loadout that is already correct costs one inventory walk and
* changes nothing, so firing is never interrupted.
*
* This is what makes the loadout self-correcting: whatever goes wrong on spawn,
* it is right again within a second. That now includes the long jump module,
* which the sweep used to skip because it could not tell whether a player had one.
*/
void EnforceLoadouts()
{
	ApplyLoadoutToAll();

	// Shares the timer rather than adding another: both are "look at the world
	// once a second and fix what the hooks missed".
	SweepWeaponPickups();

	// Same bargain again: the trap queue is asking "is there anywhere to put one
	// yet", which is a question about the world once a second.
	ProcessTrapQueue();
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
			// Nothing to put it in yet. Granting it anyway would show a number
			// that the next sweep takes straight back off again.
			if( ClassnameAllowed( SUIT_CLASSNAME ) )
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

	// Butterfingers just threw this out of their hands and they are standing on
	// it. Without a moment's grace they collect it again the same tick.
	if( WeaponJustDropped( pPlayer, szClassname ) )
	{
		bResult = false;
		return HOOK_HANDLED;
	}

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
