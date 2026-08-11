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

// The loadout sweep is a safety net behind CanCollect and the spawn hook, not
// the primary mechanism, so it can afford to be slow.
const float SWEEP_INTERVAL = 1.0f;

void PluginInit()
{
	g_Module.ScriptInfo.SetAuthor( "hl1-sven-ap" );
	g_Module.ScriptInfo.SetContactInfo( "https://github.com/barretg" );

	g_Game.AlertMessage( at_console, "[AP] PluginInit reached!\n" );

	g_Hooks.RegisterHook( Hooks::Game::MapChange, @MapChange );
	g_Hooks.RegisterHook( Hooks::Player::ClientSay, @ClientSay );
	g_Hooks.RegisterHook( Hooks::Player::PlayerUse, @PlayerUse );
	g_Hooks.RegisterHook( Hooks::Player::PlayerSpawn, @PlayerSpawn );
	g_Hooks.RegisterHook( Hooks::Player::PlayerKilled, @PlayerKilled );
	g_Hooks.RegisterHook( Hooks::Monster::MonsterKilled, @MonsterKilled );
	g_Hooks.RegisterHook( Hooks::PickupObject::CanCollect, @PickupCanCollect );

	// `as_reloadplugins` runs PluginInit but not MapInit, so without this a
	// reloaded plugin would sit with no campaign data until the next map change,
	// stripping loadouts it had no rules for.
	Initialise();

	// Whoever is already alive lost their loadout to the reload; give it back.
	ApplyLoadoutToAll();
}

/*
* Everything needed to operate on the current map. Safe to run more than once,
* which is what lets both map load and plugin load share it.
*/
void Initialise()
{
	g_szCurrentMap = string( g_Engine.mapname );

	ForceSurvivalOff();
	LoadCheckData();
	IndexCurrentMap();

	@g_CurrentChapter = ChapterForMap( g_szCurrentMap );

	// Sent checks are tracked per session by the client, which dedupes anyway;
	// clearing here just avoids the set growing across a long run.
	g_SentChecks.deleteAll();
	g_flLastPortalUse.deleteAll();
	// Force a full reparse of the snapshot.
	g_szLastInput = "";
	g_flDeathLinkImmuneUntil = 0.0f;
	// Unlike everything else here, the amnesty countdown is deliberately carried
	// across the map change: it is spent over a whole run.
	LoadAmnesty();
	// Whatever level change was queued has happened; we are here.
	g_szPendingLevel = "";

	EnsureScheduled();
}

/*
* Register the polling timers once per module.
*
* A map load wipes the scheduler, so MapInit clears the flag first and we
* re-register. A plugin reload gets a fresh module with the flag already false.
* Either way there is exactly one of each timer.
*/
bool g_bScheduled = false;

void EnsureScheduled()
{
	if( g_bScheduled )
		return;
	g_bScheduled = true;

	g_Scheduler.SetInterval( "BridgePoll", POLL_INTERVAL, g_Scheduler.REPEAT_INFINITE_TIMES );
	g_Scheduler.SetInterval( "EnforceLoadouts", SWEEP_INTERVAL, g_Scheduler.REPEAT_INFINITE_TIMES );
}

/*
* Survival mode is one life per round with no respawning, which fights
* everything this plugin does: a DeathLink wipe would end the round outright,
* and mission progress would hinge on a round timer rather than on the
* multiworld. The HL campaign turns it on for itself (`mp_survival_supported 1`
* in maps/hl_c*.cfg, and HLSP.as is explicitly the survival-mode script), so it
* has to be forced back off on every map.
*
* Called twice: once in MapInit before the map script gets a chance to enable
* map support, and again in MapStart to undo it if it did.
*/
void ForceSurvivalOff()
{
	g_EngineFuncs.CVarSetFloat( "mp_survival_supported", 0 );

	g_SurvivalMode.SetStartOn( false );

	if( g_SurvivalMode.IsEnabled() )
	{
		g_SurvivalMode.Disable();
		APLog( "survival mode forced off" );
	}
}

/*
* Runs on every map load. The plugin keeps no state across maps on purpose: the
* client is the source of truth, so we simply rebuild from checkdata.txt and the
* next snapshot.
*/
void MapInit()
{
	// The map load wiped the scheduler, so the timers must be registered again.
	g_bScheduled = false;
	Initialise();
}

void MapStart()
{
	// The map script has run by now; take survival back off if it enabled it.
	ForceSurvivalOff();

	BridgeHello();

	// A mission finished on the way here and the campaign carried us into the
	// next one. Nothing on this map counts; go back to the hub.
	if( ConsumePendingHubReturn() )
	{
		if( g_szCurrentMap != HUB_MAP )
		{
			g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK, "[AP] Returning to the hub...\n" );
			g_Scheduler.SetTimeout( "ReturnToHub", 3.0f );
		}
		return;
	}

	if( g_CurrentChapter !is null )
	{
		RegisterMapReached();

		// The final mission ends on hl_c18, which finishes with a game_end and
		// never changes level again -- so MapChange can never see it finish.
		// Arriving on the goal mission's last map means Nihilanth is dead.
		if( g_CurrentChapter.isGoal && g_szCurrentMap == g_CurrentChapter.LastMap() )
		{
			CompleteChapter( g_CurrentChapter );
			return;
		}

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
