/*
* Archipelago for Half-Life (Sven Co-op).
*
* Server plugin entry point. Register it in svencoop/default_plugins.txt:
*
*   "plugin"
*   {
*       "name"   "Archipelago"
*       "script" "archipelago/ap_main"
*   }
*
* See docs/setup_en.md for the full install, and docs/protocol.md for the file
* bridge this talks over.
*/

#include "ap_state"
#include "ap_bridge"
#include "ap_items"
#include "ap_locations"
#include "ap_deathlink"
#include "ap_hub"

// How often to look for a new snapshot from the client. Fast enough that an item
// arrives while it still feels connected to the check that earned it.
const float POLL_INTERVAL = 0.25f;

// The illegal-weapon sweep is a safety net behind CanCollect, not the primary
// mechanism, so it can afford to be slow.
const float SWEEP_INTERVAL = 1.0f;

void PluginInit()
{
	g_Module.ScriptInfo.SetAuthor( "hl1-sven-ap" );
	g_Module.ScriptInfo.SetContactInfo( "https://github.com/" );

	g_Hooks.RegisterHook( Hooks::Game::MapChange, @MapChange );
	g_Hooks.RegisterHook( Hooks::Player::ClientSay, @ClientSay );
	g_Hooks.RegisterHook( Hooks::Player::PlayerSpawn, @PlayerSpawn );
	g_Hooks.RegisterHook( Hooks::Player::PlayerKilled, @PlayerKilled );
	g_Hooks.RegisterHook( Hooks::Monster::MonsterKilled, @MonsterKilled );
	g_Hooks.RegisterHook( Hooks::PickupObject::CanCollect, @PickupCanCollect );
}

/*
* Runs on every map load. The plugin keeps no state across maps on purpose: the
* client is the source of truth, so we simply rebuild from checkdata.txt and the
* next snapshot.
*/
void MapInit()
{
	g_szCurrentMap = string( g_Engine.mapname );

	LoadCheckData();
	IndexCurrentMap();

	@g_CurrentChapter = ChapterForMap( g_szCurrentMap );

	// Sent checks are tracked per session by the client, which dedupes anyway;
	// clearing here just avoids the set growing across a long run.
	g_SentChecks.deleteAll();
	g_uiLastInputSize = 0;
	g_flDeathLinkImmuneUntil = 0.0f;

	g_Scheduler.SetInterval( "BridgePoll", POLL_INTERVAL, g_Scheduler.REPEAT_INFINITE_TIMES );
	g_Scheduler.SetInterval( "SweepIllegalWeapons", SWEEP_INTERVAL, g_Scheduler.REPEAT_INFINITE_TIMES );
}

void MapStart()
{
	BridgeHello();

	if( g_CurrentChapter !is null )
	{
		RegisterMapReached();

		// Someone got here by a route that bypassed MapChange (a direct
		// `map` command, or a listen server started straight into a chapter).
		if( !ChapterPlayable( g_CurrentChapter ) )
		{
			g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
				"[AP] " + g_CurrentChapter.name + " is locked. Returning to the hub.\n" );
			g_Scheduler.SetTimeout( "ReturnToHub", 3.0f );
		}
	}
}

HookReturnCode PlayerSpawn( CBasePlayer@ pPlayer )
{
	// The HL campaign .cfg files equip a full loadout on spawn, and that runs
	// after this hook -- so defer a tick and take it all back off again.
	g_Scheduler.SetTimeout( "ApplyLoadoutDeferred", 0.5f, EHandle( pPlayer ) );
	return HOOK_CONTINUE;
}

void ApplyLoadoutDeferred( EHandle hPlayer )
{
	CBasePlayer@ pPlayer = cast<CBasePlayer@>( hPlayer.GetEntity() );
	if( pPlayer is null )
		return;
	ApplyLoadout( pPlayer );
}
