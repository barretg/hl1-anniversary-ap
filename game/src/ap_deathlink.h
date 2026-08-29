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
//
// A death we inflict ourselves is not the player's death and is not reported or
// counted. Without that it is both an amnesty leak -- somebody else's mistake
// spending your allowance -- and a loop: the kill raises `Killed`, which reports
// a DEATH the client turns straight back into an outgoing DeathLink, which the
// other slot answers. Two slots with DeathLink on will do that to each other
// until one of them quits. See `kDeathLinkImmuneSeconds`.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

constexpr long kDeathLinkMaxAgeSeconds = 10;

// How long after a DeathLink kill a death still counts as ours rather than the
// player's. `TakeDamage` raises `Killed` inside the same call, so this only has
// to cover that; the margin is for a death that lands a frame or two later --
// gibs, a fall already in progress -- which is still not a death to report. The
// cost of being generous is one genuine death going unreported in the second
// after a DeathLink, which is the safer way to be wrong.
constexpr float kDeathLinkImmuneSeconds = 1.5f;

// How long after one `player_loadsaved` fade begins another is treated as the
// same event. The fade runs for seconds with the player alive inside it, and a
// map is free to fire the trigger every frame it is touched.
constexpr float kRevertQuietSeconds = 15.0f;

// From CBasePlayer::Killed. Reported whether or not DeathLink is on: the client
// decides what becomes of it, because deciding here from a cached flag means a
// stale snapshot silently swallows deaths.
void OnPlayerKilled(CBasePlayer* player, const std::string& cause);

// From `CRevertSaved::Use` (`player_loadsaved`), which is how Half-Life ends a
// run of events without killing the player: the screen fades, a message shows,
// and the engine reloads the last save. Falling into the void on Xen and letting
// a scientist die both end there, and neither ever reaches `Killed`, so neither
// was reported. It is a death by any measure the multiworld cares about.
//
// Ignored when the player is already dead, because `Killed` has then done the
// reporting and a revert on top of it would send the same death twice.
void OnRevertSaved();

// A DEATHLINK event from the client. `stamp` is the client's clock, compared
// against the `now` from the same snapshot rather than against ours.
void OnDeathLinkReceived(const std::string& source, const std::string& cause,
                         long stamp);

}  // namespace ap
