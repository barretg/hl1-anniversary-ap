#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_hub.h"

#include <cstdio>
#include <string>

#include "ap_bridge.h"
#include "ap_checkdata.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

namespace ap {

// Chosen against the map files rather than by taste, and the three tests it had
// to pass are the three ways a hub can go wrong:
//
//   - No `trigger_changelevel`. `lambda_bunker` has one straight into `c3a1b`,
//     which would let a player walk out of the hub into the middle of Forget
//     About Freeman -- and the interception in this file would not stop it,
//     since that only takes over transitions *leaving* a mission.
//   - Nothing that can hurt you while you stand still. `pool_party` has a
//     `trigger_hurt` with `dmg 200` in it.
//   - Small, because it is reloaded after every mission. This is 683 KB against
//     `pool_party`'s 4.2 MB.
//
// `frenzy` passes the same three and is the obvious swap if this one palls.
const char* const kHubMap = "stalkyard";

namespace {

std::string g_pending_map;

std::string ArgumentTail(int from) {
    std::string text;
    for (int i = from; i < CMD_ARGC(); ++i) {
        if (!text.empty()) {
            text += " ";
        }
        text += CMD_ARGV(i);
    }
    return Trim(text);
}

const char* StatusOf(const Chapter& chapter) {
    const Snapshot& state = State();
    if (state.ChapterExcluded(chapter.key)) {
        return "not in this seed";
    }
    if (chapter.is_goal) {
        return state.goal_open ? "OPEN" : "sealed";
    }
    return state.ChapterOpen(chapter.key) ? "unlocked" : "locked";
}

void ListMissions() {
    if (!Data().Loaded()) {
        Say("No checkdata.txt. This is running as ordinary Half-Life.");
        return;
    }
    if (!State().connected) {
        Say("The Archipelago client is not connected yet.");
    }

    for (const Chapter& chapter : Data().chapters) {
        char line[160];
        std::snprintf(line, sizeof(line), "  %2d. %-26s [%s]", chapter.index,
                      chapter.name.c_str(), StatusOf(chapter));
        Say(line);
    }
    Say("ap_warp <number or name> to travel. ap_hub to come back.");
}

void Help() {
    Say("ap                       every mission and its unlock status");
    Say("ap_warp <number or name> travel to an unlocked mission");
    Say("ap_hub                   return to the hub");
    Say("ap_tracker [map]         locations found and still out there");
    Say("ap_find [text]           point at the nearest unfound check");
}

void Warp() {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is nowhere to warp to.");
        return;
    }
    const std::string argument = ArgumentTail(1);
    if (argument.empty()) {
        Say("Usage: ap_warp <number or name>. ap lists them.");
        return;
    }

    const Chapter* chapter = nullptr;
    const long index = ParseLong(argument, -1);
    if (index >= 0 && argument.find_first_not_of("0123456789") == std::string::npos) {
        chapter = Data().ChapterByIndex(static_cast<int>(index));
    }
    if (chapter == nullptr) {
        chapter = Data().ChapterByName(argument);
    }
    if (chapter == nullptr) {
        Say("No mission by that number or name.");
        return;
    }

    const Snapshot& state = State();
    if (state.ChapterExcluded(chapter->key)) {
        Say(chapter->name + " is not in this seed.");
        return;
    }

    // Not connected means we do not know what is open, and "do not know" has to
    // refuse rather than allow. Warping freely while disconnected and connecting
    // afterwards would put a player inside a mission the seed had locked, with
    // every check in it live the moment the client came up -- which is a way
    // around every gate in the game, reachable by closing one window.
    //
    // `ap_hub` is deliberately still allowed: going home is never a way in.
    if (!state.connected) {
        Say("The Archipelago client is not connected, so no mission is open yet. "
            "Start it, connect to your room, and try again.");
        return;
    }

    // The client owns the answer to "is this open", including the finale's seal.
    // Deciding it here from a cached count is how the two halves drift apart.
    const bool open = chapter->is_goal ? state.goal_open
                                       : state.ChapterOpen(chapter->key);
    if (!open) {
        Say(chapter->name +
            (chapter->is_goal ? " is still sealed. Finish more missions."
                              : " is locked. Its unlock item has not arrived."));
        return;
    }

    Notify(std::string("Warping to ") + chapter->name + ".");
    RequestMap(chapter->maps.front());
}

void ToHub() {
    Notify("Returning to the hub.");
    RequestMap(kHubMap);
}

void Cmd_Ap() { ListMissions(); }
void Cmd_ApHelp() { Help(); }
void Cmd_ApWarp() { Warp(); }
void Cmd_ApHub() { ToHub(); }
void Cmd_ApFind() { Find(ArgumentTail(1)); }
void Cmd_ApTracker() { Tracker(ArgumentTail(1)); }

}  // namespace

void RegisterCommands() {
    static bool registered = false;
    if (registered) {
        return;  // the engine keeps them for the life of the process
    }
    registered = true;

    // The first of our code the engine ever reaches, so the trace starts here.
    TraceReset();
    Trace("GameDLLInit: ap::RegisterCommands");

    // pfnAddServerCommand directly: the SDK has no macro for it, and it takes a
    // non-const name, so the casts are the engine's ABI rather than sloppiness.
    g_engfuncs.pfnAddServerCommand((char*)"ap", Cmd_Ap);
    g_engfuncs.pfnAddServerCommand((char*)"ap_help", Cmd_ApHelp);
    g_engfuncs.pfnAddServerCommand((char*)"ap_warp", Cmd_ApWarp);
    g_engfuncs.pfnAddServerCommand((char*)"ap_hub", Cmd_ApHub);
    g_engfuncs.pfnAddServerCommand((char*)"ap_find", Cmd_ApFind);
    g_engfuncs.pfnAddServerCommand((char*)"ap_tracker", Cmd_ApTracker);
    Trace("  commands registered");
}

bool InHub() {
    return Data().ChapterOfMap(CurrentMap()) == nullptr;
}

void RequestMap(const std::string& map_name) {
    if (map_name.empty()) {
        return;
    }
    // Deferred, always. Even from a console command, which looks safe: the
    // engine is midway through its own command dispatch and a level change from
    // inside it is the same crash class as one from inside a level change.
    g_pending_map = map_name;
}

bool InterceptChangeLevel(const std::string& from_map, const std::string& to_map) {
    if (!Data().Loaded()) {
        return false;  // ordinary Half-Life; leave every transition alone
    }

    const Chapter* from = Data().ChapterOfMap(from_map);
    const Chapter* to = Data().ChapterOfMap(to_map);

    if (from == nullptr) {
        // Leaving the hub or the hazard course by the game's own route. Not a
        // mission boundary, and not ours to take over.
        return false;
    }
    if (to != nullptr && to->key == from->key) {
        return false;  // inside a mission: retail's own transition, untouched
    }

    // A mission boundary. The arrival check for the mission's last map has
    // already fired; this is the moment the mission is over.
    Wire().Send("COMPLETE", from->key);
    if (from->is_goal) {
        Wire().Send("GOAL", from->key);
    }

    Notify(from->name + " complete. Returning to the hub.");
    RequestMap(kHubMap);
    return true;
}

void RunDeferred() {
    if (g_pending_map.empty()) {
        return;
    }
    const std::string map_name = g_pending_map;
    g_pending_map.clear();

    char command[80];
    std::snprintf(command, sizeof(command), "map %s\n", map_name.c_str());
    SERVER_COMMAND(command);
    SERVER_EXECUTE();
}

}  // namespace ap
