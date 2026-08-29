// Wiring. The only header the SDK's own sources need to include.
//
// Every hook below is a call added to a Valve source file rather than a
// subclass, because the SDK is compiled whole and its classes are not designed
// to be extended from outside. Each is one line. `game/sdk.patch` applies them
// all, and `game/README.md` explains what each is for.
//
//   dlls/game.cpp        GameDLLInit                  -> ap::RegisterCommands
//   dlls/client.cpp      ServerActivate               -> ap::Startup
//   dlls/client.cpp      StartFrame                   -> ap::RunFrame
//   dlls/client.cpp      ClientPrecache               -> ap::PrecacheTraps
//   dlls/player.cpp      CBasePlayer::Spawn           -> ap::ApplyLoadout
//   dlls/player.cpp      CBasePlayer::Killed          -> ap::OnPlayerKilled
//   dlls/player.cpp      CRevertSaved::Use            -> ap::OnRevertSaved
//   dlls/player.cpp      CBasePlayer::PlayerUse       -> ap::OnPlayerUse
//   dlls/gamerules.cpp   CGameRules::CanHavePlayerItem-> ap::CanCollect
//   dlls/singleplay_gamerules.cpp CHalfLifeRules::CanHaveItem -> ap::CanCollect
//   dlls/triggers.cpp    CChangeLevel::ChangeLevelNow -> ap::InterceptChangeLevel
//   dlls/triggers.cpp    CTriggerHurt::HurtTouch      -> ap::OnHealingTouch

#pragma once

#include <set>
#include <string>

class CBaseEntity;
class CBasePlayer;

namespace ap {

class Bridge;
class CheckData;
struct PendingEvent;

// --- what the patched SDK files call -------------------------------------
//
// Redeclared here, rather than asking Valve's sources to include five of our
// headers, so that `game/sdk.patch` adds exactly one include per file. Each is
// defined in the module that owns it.

void RegisterCommands();                                    // ap_hub
void PrecacheTraps();                                       // ap_traps
void RequestLoadout();                                      // ap_items
bool CanCollect(CBasePlayer* player, CBaseEntity* pickup);  // ap_items
void OnPlayerUse(CBasePlayer* player, CBaseEntity* target); // ap_locations
void OnPlayerKilled(CBasePlayer* player, const std::string& cause);  // ap_deathlink
void OnRevertSaved();                                       // ap_deathlink
void OnHealingTouch(CBaseEntity* player, CBaseEntity* pool);// ap_locations
bool HandleChat(CBasePlayer* player, const std::string& said);       // ap_hub
bool InterceptChangeLevel(const std::string& from_map,
                          const std::string& to_map);       // ap_hub

// Once per map load: find the mod folder, read checkdata.txt, open the bridge,
// and announce ourselves with HELLO so the client sends a full snapshot.
void Startup();

// Every server frame. Polls the bridge on its own clock, applies whatever the
// client sent, and runs the deferred work nothing else may run inline.
void RunFrame();

// Apply one delivery from the client. The caller ACKs it either way, including
// a kind we do not recognise: holding one would stall the client's whole window.
void ApplyEvent(const PendingEvent& event);

// Tell the player what the newest snapshot brought. Weapons and mission unlocks
// live in the snapshot rather than in events, so a diff against what was held
// before the poll is the only place they can be noticed.
void AnnounceArrivals(const std::string& had_session,
                      const std::set<std::string>& had_items,
                      const std::set<std::string>& had_chapters,
                      bool had_goal);

// The single player. Null between map load and ClientPutInServer, which is most
// of what can go wrong in here, so every caller checks.
CBasePlayer* Player();

// The map the server is running, from gpGlobals.
std::string CurrentMap();

// A copy of this string that lives for the rest of the process, as a plain
// `const char*`.
//
// Required by any SDK call that turns a name into an entity: `GiveNamedItem` and
// `CBaseEntity::Create` both store the name with `MAKE_STRING`, which does not
// copy it -- it records the *offset of the caller's pointer* from the engine's
// string base, and `pev->classname` then points at whatever that address holds
// later. Every caller in Valve's own code passes a string literal, which lives
// in the data segment forever, so this never troubles them.
//
// Pass the `c_str()` of a temporary and the entity's classname turns to freed
// heap as soon as the caller returns: `HasNamedPlayerItem` stops matching it, so
// the loadout grants it again and again, and `SelectItem` cannot find it, so the
// HUD's slot keys silently fail while `lastinv` -- which follows a pointer --
// still works.
const char* Intern(const std::string& text);

// Loaded once per map load. Empty when checkdata.txt could not be read, in which
// case every check is silently inert -- see `Live`.
CheckData& Data();

// Read checkdata.txt if it has not been read yet. `Startup` calls this at
// ServerActivate, which is where it belongs; the precache hooks call it too,
// because precaching runs *before* ServerActivate and on the very first map of a
// session there would otherwise be nothing loaded to precache against.
void EnsureData();
Bridge& Wire();

// Is it safe to send checks? False when checkdata.txt is missing, when the
// client has not connected, or when the two halves disagree about the id map.
// That last one matters most: a mismatched pair numbers locations differently,
// so every check would land on the wrong location, which is worse than sending
// none.
bool Live();

// Does this game gate anything? True as soon as `checkdata.txt` is present,
// which is the moment the mod folder says "this is an Archipelago game".
//
// Deliberately not `Live`. Gating must not wait on the client, or closing the
// client would be a way around every lock in the game: collect what you like
// while disconnected, connect, keep it. It fails closed instead -- with no
// client you get your starting weapons and nothing else, which is the correct
// amount of Half-Life to be able to play without a multiworld.
bool Gated();

// Can the client take a user message yet?
//
// This is the question behind every crash of the form
// `SZ_GetSpace: Tried to write to an uninitialized sizebuf_t`, and `FL_CLIENT`
// is not the answer to it: that is set from the moment the engine begins
// restoring a player, several frames before there is anywhere for a message to
// go.
//
// The answer is frames run on this map, counted here, and nothing the engine
// offers. `m_fGameHUDInitialized` was tried and is a trap: it is not a saved
// field, so a `changelevel` leaves it FALSE, and the thing that would set it
// again is guarded by `m_fInitHUD`, which *is* saved and restores as FALSE. It
// therefore stays FALSE for the rest of the run, and every write to the client
// stops after the first transition.
//
// Anything that writes to the client waits on this: `FlushNotices`, and the
// loadout -- which writes two of them without looking like it, through
// `AddToPlayer`'s `WeapPickup` and `ForceClientDllUpdate`'s `ResetHUD`.
bool ClientReady();

// Console text: the answer to a command the player typed. Lists go here and
// nowhere else -- `ap` is eighteen lines and would bury the screen.
//
// Queued like `Notify` and for the same reasons, and never written with
// `ALERT`: the engine drops `ALERT(at_console)` unless `developer` is set, so
// it reaches nobody in a normal game.
void Say(const std::string& text);

// Something happened: a check was found, an item arrived, a pickup was refused.
// Goes to the HUD's message area, where it is readable without opening the
// console, and to the console as well so there is a log of it afterwards.
//
// Queued rather than sent. A user message written from inside `Killed`, from
// `Spawn` before the client is in the server, or mid-level-load is
// `SZ_GetSpace: Tried to write to an uninitialized sizebuf_t` and a dead game.
// Hooks decide what to say; `FlushNotices` says it.
void Notify(const std::string& text);

// Send everything `Notify` has queued. StartFrame only.
void FlushNotices();

// Collect the answer to one command instead of sending it line by line.
//
// A reply of a few lines is worth putting on the HUD, where it can be read
// without leaving the game -- which matters more than it sounds, because opening
// the console pauses single-player and a paused server runs no frames, so
// nothing deferred happens until it is closed again. A listing is not: it would
// bury the screen and overrun the message channel. The length decides, and the
// length is only known once the command has finished talking.
//
// Every `Say` and `Notify` between the two lands in the reply. A reply too long
// for the HUD still leaves one line there naming the command and saying where
// the rest went, so a key press is never answered with nothing at all -- which,
// with the console shut, is indistinguishable from a bind that did not work.
//
// `label` is the command as the player would say it: `!tracker`, `ap_tracker`.
void BeginReply(const std::string& label);
void EndReply();

// The longest reply that still goes to the HUD as well as the console.
constexpr size_t kReplyHudMaxLines = 9;

// A breadcrumb in `hlap/archipelago/ap_boot.txt`, flushed as it is written.
//
// This exists because of how this project fails: a mistake in a hook crashes the
// engine during map load, and everything that would tell you where -- the
// console, the last frame of gameplay -- is gone with it. The file survives, so
// the last line in it is the last hook that ran. Cheap enough to leave on: a
// dozen lines per map load.
void Trace(const char* where);
void TraceReset();
constexpr bool kTraceLoad = true;

// The poll clock. The bridge is checked this often rather than every frame; file
// I/O on a 60Hz tick is a waste and the client publishes far slower.
constexpr float kPollIntervalSeconds = 0.2f;

// Where the bridge and checkdata live, relative to the mod folder.
extern const char* const kStoreSubdir;  // "archipelago"

}  // namespace ap
