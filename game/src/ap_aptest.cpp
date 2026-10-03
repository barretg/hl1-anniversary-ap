#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_aptest.h"

#include <cmath>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_text.h"

namespace ap {

#ifdef HLAP_TEST_BUILD
namespace {

// How often the harness's files are looked at, in seconds.
constexpr float kPollInterval = 0.5f;

// The scenario `aptest.py` last started, read from `aptest_go.txt`.
struct Destination {
    long seq = -1;
    std::string map;
    bool has_position = false;
    float position[3] = {0, 0, 0};
};

Destination g_destination;
// Whether the harness's files have been looked at since the dll loaded. What
// `aptest_go.txt` holds at that first look is a scenario from before the game
// started, and is only adopted: loading a map the moment the game starts would
// be a surprise, so `!redo` does that. Anything the harness writes after it is
// loaded. Set on the first look whether or not the file is there yet, or the
// first scenario a fresh harness starts would be mistaken for an old one.
bool g_looked = false;
// Set when a scenario's map is requested, cleared once the player is placed.
bool g_arriving = false;
// When the player was first seen alive on the destination map.
float g_alive_since = -1.0f;
float g_next_poll = 0.0f;
// How far into `aptest_say.txt` has been shown. It starts at the end, so a
// previous session's lines are not replayed.
std::streamoff g_say_cursor = -1;

std::string GoPath() { return StoreDir() + "/aptest_go.txt"; }
std::string SayPath() { return StoreDir() + "/aptest_say.txt"; }

bool ReadDestination(Destination& out) {
    std::ifstream file(GoPath().c_str());
    if (!file) {
        return false;
    }
    out = Destination();
    std::string line;
    while (std::getline(file, line)) {
        line = Trim(line);
        const size_t eq = line.find('=');
        if (eq == std::string::npos) {
            continue;
        }
        const std::string key = line.substr(0, eq);
        const std::string value = Trim(line.substr(eq + 1));
        if (key == "seq") {
            out.seq = ParseLong(value);
        } else if (key == "map") {
            out.map = value;
        } else if (key == "pos") {
            out.has_position = ParseVector(value, out.position);
        }
    }
    return !out.map.empty();
}

// Lines the harness wants shown, `hud|text` on screen and in the console,
// `con|text` in the console only.
void ShowSaid() {
    std::ifstream file(SayPath().c_str(), std::ios::binary);
    if (!file) {
        return;
    }
    file.seekg(0, std::ios::end);
    const std::streamoff size = file.tellg();
    if (g_say_cursor < 0) {
        g_say_cursor = size;  // first look: skip what is already there
        return;
    }
    if (size < g_say_cursor) {
        g_say_cursor = 0;  // a new harness run truncated it
    }
    if (size == g_say_cursor) {
        return;
    }
    file.seekg(g_say_cursor);
    std::string chunk(static_cast<size_t>(size - g_say_cursor), '\0');
    file.read(&chunk[0], static_cast<std::streamsize>(chunk.size()));
    // Only whole lines; one being written is picked up next time.
    const size_t end = chunk.rfind('\n');
    if (end == std::string::npos) {
        return;
    }
    g_say_cursor += static_cast<std::streamoff>(end + 1);
    std::istringstream lines(chunk.substr(0, end + 1));
    std::string line;
    while (std::getline(lines, line)) {
        line = Trim(line);
        if (StartsWith(line, "hud|")) {
            Notify(line.substr(4));
        } else if (StartsWith(line, "con|")) {
            ALERT(at_console, "%s\n", line.substr(4).c_str());
        }
    }
}

void Load() {
    // Each scenario expects its check afresh, even on a map already visited.
    ForgetSentChecks();
    g_arriving = true;
    g_alive_since = -1.0f;
    RequestMap(g_destination.map);
}

// Somewhere a standing player fits, as near the point as possible. Item and
// monster origins sit in lockers, on shelves and against walls, and dropping a
// player on the exact spot puts them in the geometry. Rings outward and upward,
// each spot checked with the player hull, then settled onto the floor.
bool StandSpot(CBasePlayer* player, const Vector& target, Vector& out) {
    static const float kRadii[] = {0.0f, 24.0f, 48.0f, 80.0f, 128.0f};
    static const float kHeights[] = {36.0f, 72.0f, 0.0f, 128.0f};
    for (float height : kHeights) {
        for (float radius : kRadii) {
            const int steps = radius == 0.0f ? 1 : 8;
            for (int i = 0; i < steps; ++i) {
                const float angle = 6.2831853f * i / steps;
                const Vector spot = target + Vector(radius * std::cos(angle),
                                                    radius * std::sin(angle), height);
                TraceResult tr;
                UTIL_TraceHull(spot, spot, ignore_monsters, human_hull,
                               player->edict(), &tr);
                if (tr.fStartSolid || tr.fAllSolid) {
                    continue;
                }
                UTIL_TraceHull(spot, spot - Vector(0, 0, 256), ignore_monsters,
                               human_hull, player->edict(), &tr);
                out = tr.vecEndPos;
                return true;
            }
        }
    }
    return false;
}

void Teleport() {
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        return;
    }
    if (!g_destination.has_position) {
        Notify("[aptest] No spot for this scenario; starting from spawn.");
        return;
    }
    const Vector target(g_destination.position[0], g_destination.position[1],
                        g_destination.position[2]);
    Vector spot;
    if (!StandSpot(player, target, spot)) {
        spot = target;
        Notify("[aptest] No room to stand near the spot; placed on it anyway.");
    }
    UTIL_SetOrigin(player->pev, spot);
    player->pev->velocity = g_vecZero;
}

// Everything but `tp` is the harness's to answer.
const char* const kHarnessVerbs[] = {
    "pass", "fail", "note", "next", "prev", "redo", "go", "info", "status",
    "list", "give", "take", "item", "trap", "deathlink", "clear", "connect",
    "disconnect",
};

void Cmd_Test() {
    const std::string verb = Lower(CMD_ARGC() > 1 ? CMD_ARGV(1) : "");
    std::string rest;
    for (int i = 2; i < CMD_ARGC(); ++i) {
        rest += (rest.empty() ? "" : " ") + std::string(CMD_ARGV(i));
    }
    if (!TestDispatch(verb, rest)) {
        Notify("[aptest] testing_aptest pass|fail|note|next|prev|redo|go|info|status|"
               "list|clear|give|take|item|trap|deathlink|connect|disconnect|tp");
    }
}

}  // namespace
#endif

bool TestDispatch(const std::string& name, const std::string& rest) {
#ifdef HLAP_TEST_BUILD
    if (name == "tp") {
        if (CurrentMap() != g_destination.map) {
            Notify("[aptest] Not on the scenario's map; !redo loads it.");
        } else {
            Teleport();
        }
        return true;
    }
    for (const char* verb : kHarnessVerbs) {
        if (name == verb) {
            Wire().Send("APTEST", std::vector<std::string>{name, Sanitise(rest)});
            return true;
        }
    }
#else
    (void)name;
    (void)rest;
#endif
    return false;
}

void RegisterTestCommands() {
#ifdef HLAP_TEST_BUILD
    g_engfuncs.pfnAddServerCommand((char*)"testing_aptest", Cmd_Test);
#endif
}

void RunTestHarness() {
#ifdef HLAP_TEST_BUILD
    if (gpGlobals->time >= g_next_poll || gpGlobals->time + 1.0f < g_next_poll) {
        g_next_poll = gpGlobals->time + kPollInterval;
        Destination next;
        const bool first = !g_looked;
        g_looked = true;
        if (ReadDestination(next) && next.seq != g_destination.seq) {
            g_destination = next;
            if (!first) {
                Load();
            }
        }
        // Held while a scenario's map loads: the load clears the chat area,
        // and the steps shown before it would be gone before they were read.
        // They are shown once the player is placed.
        if (!g_arriving) {
            ShowSaid();
        }
    }

    if (!g_arriving || CurrentMap() != g_destination.map) {
        return;
    }
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        g_alive_since = -1.0f;
        return;
    }
    // A second after spawning, once the loadout and the level's own spawn
    // logic have run.
    if (g_alive_since < 0.0f) {
        g_alive_since = gpGlobals->time;
        return;
    }
    if (gpGlobals->time - g_alive_since < 1.0f) {
        return;
    }
    g_arriving = false;
    Teleport();
    ShowSaid();
#endif
}

}  // namespace ap
