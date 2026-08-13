// DeathLink, both directions.
//
// Out: every death is reported to the client, with a flag saying whether the
// amnesty allowance absorbed it. The countdown lives here rather than in the
// client because the death message has to name the remaining allowance at the
// moment of the death.
//
// In: a DEATHLINK delivery kills the player. One older than ten seconds is
// dropped -- it belongs to a session that has since moved on, and arriving late
// is worse than not arriving.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

constexpr long kDeathLinkMaxAgeSeconds = 10;

// From CBasePlayer::Killed.
void OnPlayerKilled(CBasePlayer* player, const std::string& cause);

// A DEATHLINK event from the client.
void OnDeathLinkReceived(const std::string& source, const std::string& cause,
                         long stamp);

}  // namespace ap
