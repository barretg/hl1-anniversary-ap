#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_deathlink.h"

#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

namespace ap {
namespace {

// How much amnesty is left, kept in a file because it has to survive a map
// change and a quickload. Everything else about the game side is stateless; this
// is one of the two exceptions, and it exists because the death message has to
// name the remaining allowance at the instant of the death.
const char* const kAmnestyFile = "/ap_amnesty.txt";

std::string AmnestyPath() {
    char game_dir[260] = {0};
    GET_GAME_DIR(game_dir);
    std::string dir(game_dir);
    if (dir.empty()) {
        dir = "hlap";
    }
    return dir + "/archipelago" + kAmnestyFile;
}

// The countdown, and the setting it was counting down from.
//
// Both, because the client may change the setting mid-run -- `/amnesty 0` is a
// player deciding their deaths should start counting -- and the file alone
// cannot tell "3 left of 4" from "3 left of 3". Without the second number the
// saved countdown simply won over the new setting and went on forgiving deaths
// the player had just asked to have reported.
struct Amnesty {
    int remaining = -1;   // -1: nothing written this run
    int configured = -1;  // -1: written before this field existed
};

Amnesty ReadAmnesty() {
    Amnesty saved;
    std::ifstream file(AmnestyPath().c_str());
    if (!file) {
        return saved;  // never written this run
    }
    std::string text;
    std::getline(file, text);

    const std::vector<std::string> parts = Split(Trim(text), ' ');
    if (!parts.empty()) {
        saved.remaining = static_cast<int>(ParseLong(parts[0], -1));
    }
    if (parts.size() > 1) {
        saved.configured = static_cast<int>(ParseLong(parts[1], -1));
    }
    return saved;
}

void WriteAmnesty(int remaining, int configured) {
    std::ofstream file(AmnestyPath().c_str(), std::ios::out | std::ios::trunc);
    if (file) {
        file << remaining << " " << configured << "\n";
    }
}

// When a death still belongs to a DeathLink we delivered rather than to the
// player. Always set *before* the damage is dealt, because `TakeDamage` raises
// `Killed` inside the same call and a window opened afterwards would open too
// late to matter.
//
// Deliberately in memory and not in the amnesty file: it is worth less than a
// frame of the run, and a map change or a quickload inside it is not a death we
// caused.
float g_immune_until = 0.0f;

bool DeathLinkImmune() {
    return gpGlobals->time < g_immune_until;
}

// When the last `player_loadsaved` fade began, in level time. A revert is one
// event even when the map fires the trigger more than once, and the fade lasts
// seconds during which the player is still alive and still touching whatever
// set it off.
//
// Not reset on a map change and it does not need to be: `gpGlobals->time`
// restarts with the level, so a value carried over from the previous map is
// larger than the new clock and the difference below goes negative, which is
// not inside the window.
float g_reverted_at = -1000.0f;

}  // namespace

void OnRevertSaved() {
    CBasePlayer* player = Player();
    if (player == nullptr || !Live()) {
        return;
    }
    // Already dead means `Killed` has been through here with the real cause.
    if (!player->IsAlive()) {
        return;
    }
    const float since = gpGlobals->time - g_reverted_at;
    if (since >= 0.0f && since < kRevertQuietSeconds) {
        return;
    }
    g_reverted_at = gpGlobals->time;

    // Deliberately vague, because the entity does not know either: the same
    // entity ends a fall into the void, a scientist dying and a hostage lost.
    // What the multiworld needs is that the run was cut short, not the reason.
    OnPlayerKilled(player, "a fatal mistake");
}

void OnPlayerKilled(CBasePlayer* player, const std::string& cause) {
    if (player == nullptr || !Live()) {
        return;
    }

    // A death we dealt out ourselves, delivering somebody else's DeathLink. It
    // is not the player's death: it must not spend their amnesty, and above all
    // it must not be reported, because the client turns a reported death into an
    // outgoing DeathLink and the slot that sent this one would answer it.
    if (DeathLinkImmune()) {
        return;
    }

    // Reported unconditionally, whether or not DeathLink is on. The client
    // decides what becomes of it: deciding here from a cached flag means a stale
    // snapshot silently swallows deaths with nothing in either log to explain it.
    const int configured = State().death_link_amnesty;
    const Amnesty saved = ReadAmnesty();

    // The client's setting is the authority on how large the allowance is, and a
    // change to it takes effect now rather than after the old countdown runs
    // out. `/amnesty 0` is a player asking for their deaths to start counting,
    // and honouring it a few deaths later is the same as ignoring it.
    int remaining = (saved.remaining < 0 || saved.configured != configured)
                        ? configured
                        : saved.remaining;

    bool forgiven = false;
    if (State().death_link && remaining > 0) {
        forgiven = true;
        --remaining;
        char line[96];
        std::snprintf(line, sizeof(line),
                      "Death forgiven. %d more before one goes out.", remaining);
        Notify(line);
    } else if (State().death_link) {
        // The allowance runs again from the top, so a run does not become one
        // long unbroken chain after the first death that gets through.
        remaining = configured;
    }
    WriteAmnesty(remaining, configured);

    std::vector<std::string> args;
    args.push_back("Freeman");
    args.push_back(Sanitise(cause.empty() ? std::string("an unknown fate") : cause));
    args.push_back(forgiven ? "1" : "0");
    Wire().Send("DEATH", args);
}

void OnDeathLinkReceived(const std::string& source, const std::string& cause,
                         long stamp) {
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }

    // Freshness is judged against the client's own clock from the same snapshot,
    // so the two sides never have to agree on a clock. A DeathLink that arrived
    // during a map load is stale and must not kill someone who has just spawned.
    const long now = Wire().Now();
    if (stamp > 0 && now > 0 && now - stamp > kDeathLinkMaxAgeSeconds) {
        return;
    }
    if (!State().death_link) {
        return;
    }
    if (!player->IsAlive()) {
        return;
    }

    Notify(source + " died to " + cause + ".");

    // Before the damage, never after: `TakeDamage` raises `CBasePlayer::Killed`
    // inside this call, so a window opened on the next line would open after the
    // thing it exists to catch had already happened.
    g_immune_until = gpGlobals->time + kDeathLinkImmuneSeconds;

    player->TakeDamage(player->pev, player->pev, player->pev->health + 100.0f,
                       DMG_GENERIC | DMG_ALWAYSGIB);
}

}  // namespace ap
