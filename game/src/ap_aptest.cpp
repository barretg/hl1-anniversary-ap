#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_aptest.h"

#include <fstream>
#include <string>

#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_text.h"

namespace ap {

#ifdef HLAP_TEST_BUILD
namespace {

// The scenario `aptest.py` last started, read from `aptest_go.txt`.
struct Destination {
    std::string map;
    bool has_position = false;
    float position[3] = {0, 0, 0};
};

Destination g_destination;
// Set by `ap_test_go`, cleared once the player has been put in place.
bool g_arriving = false;
// When the player was first seen alive on the destination map.
float g_alive_since = -1.0f;

bool ReadDestination(Destination& out) {
    std::ifstream file((StoreDir() + "/aptest_go.txt").c_str());
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
        if (key == "map") {
            out.map = value;
        } else if (key == "pos") {
            out.has_position = ParseVector(value, out.position);
        }
    }
    return !out.map.empty();
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

void Cmd_TestGo() {
    if (!ReadDestination(g_destination)) {
        Notify("[aptest] No aptest_go.txt. Start a scenario in aptest.py first.");
        return;
    }
    // Each scenario expects its check afresh, even on a map already visited.
    ForgetSentChecks();
    g_arriving = true;
    g_alive_since = -1.0f;
    RequestMap(g_destination.map);
}

void Cmd_TestTeleport() {
    if (CurrentMap() != g_destination.map) {
        Notify("[aptest] Not on the scenario's map; use ap_test_go.");
        return;
    }
    Teleport();
}

}  // namespace
#endif

void RegisterTestCommands() {
#ifdef HLAP_TEST_BUILD
    g_engfuncs.pfnAddServerCommand((char*)"ap_test_go", Cmd_TestGo);
    g_engfuncs.pfnAddServerCommand((char*)"ap_test_tp", Cmd_TestTeleport);
#endif
}

void RunTestHarness() {
#ifdef HLAP_TEST_BUILD
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
    Notify("[aptest] In place. Steps are in the aptest.py window.");
#endif
}

}  // namespace ap
