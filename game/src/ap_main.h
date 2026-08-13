// Wiring. The only file the SDK's own sources need to know about.
//
// Every hook below is a call added to a Valve source file rather than a
// subclass, because the SDK is compiled whole and its classes are not designed
// to be extended from outside. Keep the added lines to one call each: the less
// this project edits Valve's files, the less a future SDK update costs.
//
//   dlls/world.cpp        ServerActivate    -> ap::Startup / ap::OnMapStart
//   dlls/world.cpp        precache          -> ap::PrecacheTraps
//   dlls/game.cpp         StartFrame        -> ap::RunFrame
//   dlls/player.cpp       CBasePlayer::Spawn   -> ap::ApplyLoadout
//   dlls/player.cpp       CBasePlayer::Killed  -> ap::OnPlayerKilled
//   dlls/player.cpp       CBasePlayer::PlayerUse -> ap::OnPlayerUse
//   dlls/weapons.cpp      CBasePlayerItem::AddToPlayer -> ap::CanCollect
//   dlls/client.cpp       ClientCommand     -> ap::HandleCommand
//   dlls/triggers.cpp     CChangeLevel::ChangeLevelNow -> ap::InterceptChangeLevel

#pragma once

#include <string>

namespace ap {

// Once per map load: find the mod folder, read checkdata.txt, open the bridge,
// announce ourselves with HELLO so the client sends a full snapshot.
void Startup();

// The poll clock. The bridge is checked this often rather than every frame;
// file I/O on a 60Hz tick is a waste and the client publishes far slower.
constexpr float kPollIntervalSeconds = 0.2f;

// Where the bridge and checkdata live, relative to the game directory.
extern const char* const kStoreSubdir;  // "archipelago"

}  // namespace ap
