// Crowbar bots: the Bot Swarm Trap, and a free-roaming quota for testing.
//
// Ported from the fun-with-bots branch, where they were engine fake clients.
// A fake client needs a second client slot, which means maxplayers above 1, and
// GoldSrc will not save a game with more than one slot -- so no saves, no warp
// points and no reload on death, which is the whole of this mod's flow. Here the
// same brain drives an ordinary server-side entity, `ap_bot`, wearing the player
// model with a crowbar merged onto its hand.
//
// The brain is the branch's, unchanged in spirit: walk a heading; duck if that
// is what opens the way; otherwise crouch-jump it, and turn away if the landing
// got nowhere. Anything alive within reach -- the player, a monster, another
// bot -- is faced and hit with the crowbar until it is not in reach any more.
//
// Registered once, at GameDLLInit:
//   bot_quota <n>      keep n free-roaming bots on the map; 0 removes them
//   bot_autofill 0|1   1: a quota bot that dies is replaced. 0: the quota is
//                      spawned once per level and the dead stay dead
//   bot_zombie 0|1     1: every bot, trap or quota, stands still and swings at
//                      nothing
// All default to 0. Trap bots are not part of the quota and are never removed
// by it.

#pragma once

class CBaseEntity;
class Vector;

namespace ap {

// Called from `PrecacheTraps`, inside the map's precache window.
void PrecacheBots();

// The cvars above. Once, at GameDLLInit.
void RegisterBotCommands();

// Map start. The quota's "spawned once" count belongs to the level.
void ResetBots();

// Every frame: keeps the quota.
void RunBots();

// bot_zombie: every bot stands still.
bool BotZombie();

// One bot, feet at `origin`, running along `yaw`.
CBaseEntity* SpawnBot(const Vector& origin, float yaw, bool from_quota);

// How many bots the trap brings.
constexpr int kBotSwarmCount = 6;

// How hard a bot is to put down, and how hard it hits. Half a crowbar per swing:
// six of them round a player is a scramble, not an execution.
constexpr float kBotHealth = 30.0f;
constexpr float kBotCrowbarDamage = 5.0f;

}  // namespace ap
