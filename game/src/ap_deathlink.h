// DeathLink, both directions.
//
// Out: every death is reported to the client, with a flag saying whether the
// amnesty allowance absorbed it. The countdown lives here rather than in the
// client because the death message has to name the remaining allowance at the
// moment of the death -- and it lives in a file rather than in memory because it
// has to survive a map change and a quickload, which is one of exactly two
// things on this side that does.
//
// In: a DEATHLINK delivery kills the player. One older than ten seconds is
// dropped -- it belongs to a moment that has passed, and arriving late is worse
// than not arriving.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

constexpr long kDeathLinkMaxAgeSeconds = 10;

// From CBasePlayer::Killed. Reported whether or not DeathLink is on: the client
// decides what becomes of it, because deciding here from a cached flag means a
// stale snapshot silently swallows deaths.
void OnPlayerKilled(CBasePlayer* player, const std::string& cause);

// A DEATHLINK event from the client. `stamp` is the client's clock, compared
// against the `now` from the same snapshot rather than against ours.
void OnDeathLinkReceived(const std::string& source, const std::string& cause,
                         long stamp);

}  // namespace ap
