#pragma once

// Fake-client bots that walk a map on their own and hit whatever they bump
// into. Self-contained: nothing here knows about any particular mod, and the
// only Half-Life SDK things it touches are the ones every SDK-derived game dll
// already has.
//
// What a bot does, once per frame, in this order:
//
//   - walks forward until the way ahead is shut;
//   - if crouching would open it, crouches and carries on;
//   - otherwise crouch-jumps forward at full height, and if it landed
//     somewhere new, carries on from there;
//   - otherwise turns at least BOT_TURN_MIN degrees off its current heading
//     and starts the loop again.
//
//   - if it is touching another player and has a melee weapon, it draws it,
//     swings while the player is still there, and puts it away afterwards --
//     see the MURDER switch at the top of ch_bots.cpp;
//   - if its crosshair happens to cross another player and the slot a gun is
//     expected in really does hold one, it draws that and fires.
//
// Console interface, all server-side:
//
//   sp_bot 3          adds three bots now. The cvar is a request, not a
//                     setting: it goes back to 0 once they are in, so setting
//                     it again adds more.
//   sp_bot_quota 4    holds the bot count at four, topping up as they are
//                     kicked. 0 means "don't manage it" until the first time
//                     the quota is set to something, after which 0 empties.
//   sp_bot_kickall    removes every bot.
//
// Dropping this into a mod means calling three functions from the game dll:
//
//   BotInit()                 from GameDLLInit(), in dlls/game.cpp
//   BotThink()                from StartFrame(), in dlls/client.cpp
//   BotClientDisconnected()   from ClientDisconnect(), in dlls/client.cpp
//
// and adding ch_bots.cpp to the build. Nothing else in the dll has to change.

// Registers the bot cvars and the sp_bot_kickall command. Once, at DLL init.
void BotInit();

// Runs every bot's decisions and physics. Once per server frame.
void BotThink();

// Forgets a bot's slot. Called for every client that leaves, bot or not.
void BotClientDisconnected(edict_t* pEntity);
