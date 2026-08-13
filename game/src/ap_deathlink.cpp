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

int ReadAmnesty() {
    std::ifstream file(AmnestyPath().c_str());
    if (!file) {
        return -1;  // never written this run
    }
    std::string text;
    std::getline(file, text);
    const long value = ParseLong(text, -1);
    return static_cast<int>(value);
}

void WriteAmnesty(int remaining) {
    std::ofstream file(AmnestyPath().c_str(), std::ios::out | std::ios::trunc);
    if (file) {
        file << remaining << "\n";
    }
}

}  // namespace

void OnPlayerKilled(CBasePlayer* player, const std::string& cause) {
    if (player == nullptr || !Live()) {
        return;
    }

    // Reported unconditionally, whether or not DeathLink is on. The client
    // decides what becomes of it: deciding here from a cached flag means a stale
    // snapshot silently swallows deaths with nothing in either log to explain it.
    int remaining = ReadAmnesty();
    if (remaining < 0) {
        remaining = State().death_link_amnesty;
    }

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
        remaining = State().death_link_amnesty;
    }
    WriteAmnesty(remaining);

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
    player->TakeDamage(player->pev, player->pev, player->pev->health + 100.0f,
                       DMG_GENERIC | DMG_ALWAYSGIB);
}

}  // namespace ap
