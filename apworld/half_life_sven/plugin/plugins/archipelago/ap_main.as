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
#include "ap_traps"
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
	ClearWithheldWeapons();
	// Force a full reparse of the snapshot.
	g_szLastInput = "";
	g_flDeathLinkImmuneUntil = 0.0f;
	// Unlike everything else here, the amnesty countdown is deliberately carried
	// across the map change: it is spent over a whole run.
	LoadAmnesty();
	// Whatever level change was queued has happened; we are here.
	g_szPendingLevel = "";
	g_bSelfChange = false;
	// Earned back in MapStart, once we know this map is one we are meant to be
	// on. Until then nothing here counts as progress.
	g_bMissionActive = false;

	EnsureScheduled();
}

/*
* Register the polling timers, and make sure there is exactly one of each.
*
* Held as handles rather than guarded by a bool, because the bool only worked if
* a map load really does wipe the scheduler. If it does not, every map added
* another poller and another loadout sweep on top of the last, and a session
* spent hopping between missions would end up running the whole lot several times
* a second -- which looks exactly like the server grinding to a halt.
*
* Handles make that self-correcting either way. They live in globals alongside
* the timers themselves: if a map load wipes the scheduler it wipes these too and
* they come back null, so there is nothing to remove and nothing dangling to
* remove it from. If it does not, they still point at the old timers and we take
* them down before laying new ones.
*/
CScheduledFunction@ g_pBridgeTimer = null;
CScheduledFunction@ g_pSweepTimer = null;

void EnsureScheduled()
{
	if( g_pBridgeTimer !is null )
	{
		g_Scheduler.RemoveTimer( g_pBridgeTimer );
		@g_pBridgeTimer = null;
	}

	if( g_pSweepTimer !is null )
	{
		g_Scheduler.RemoveTimer( g_pSweepTimer );
		@g_pSweepTimer = null;
	}

	@g_pBridgeTimer = g_Scheduler.SetInterval(
		"BridgePoll", POLL_INTERVAL, g_Scheduler.REPEAT_INFINITE_TIMES );
	@g_pSweepTimer = g_Scheduler.SetInterval(
		"EnforceLoadouts", SWEEP_INTERVAL, g_Scheduler.REPEAT_INFINITE_TIMES );
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
	// EnsureScheduled takes down whatever it laid last time before laying it
	// again, so this is safe whether or not the map load wiped the scheduler.
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
		// Are we allowed to be here? Checked *before* anything is sent, not
		// after. The campaign runs one mission straight into the next, so the
		// engine will happily drop us on the first map of a mission we never
		// unlocked -- and sending its "reached" check on the way through, then
		// crediting its completion on the way back out, is exactly the run of
		// phantom checks that produced a finished Office Complex nobody played.
		//
		// The playable test is only trusted while the client is connected: with
		// no snapshot we do not know what is unlocked, and locking a player out
		// of their own game is worse than a stray check.
		if( g_State.connected && !ChapterPlayable( g_CurrentChapter ) )
		{
			g_PlayerFuncs.ClientPrintAll( HUD_PRINTTALK,
				"[AP] " + g_CurrentChapter.name + " is locked. Returning to the hub.\n" );
			g_Scheduler.SetTimeout( "ReturnToHub", 3.0f );
			return;
		}

		// From here on this is a mission we are genuinely playing, so leaving its
		// last map means we finished it.
		g_bMissionActive = true;

		RegisterMapReached();

		// A campaign's last map finishes with a game_end and never changes level
		// again (hl_c18 for Half-Life, and the same shape in the others) -- so
		// MapChange can never see it finish. Arriving on a finale's last map is
		// therefore what counts as finishing that campaign.
		if( g_CurrentChapter.isGoal && g_szCurrentMap == g_CurrentChapter.LastMap() )
			CompleteChapter( g_CurrentChapter );
	}
}

HookReturnCode PlayerSpawn( CBasePlayer@ pPlayer )
{
	// Whatever Butterfingers made them drop, the death already took.
	ClearWithheldWeapons( pPlayer );

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
