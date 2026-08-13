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

// What `ap_warp` was asked for: a mission, and optionally which part of it.
//
// `unforeseen 6` is the mission named `unforeseen`, part 6. The part is only
// ever a trailing number with something in front of it, so `ap_warp 5` stays
// mission 5 rather than becoming a part of nothing, and `ap_warp 5 3` is
// mission 5 part 3.
struct WarpRequest {
    std::string where;
    int part = 0;  // 1-based; 0 means "the start of the mission"
};

bool IsNumber(const std::string& text) {
    return !text.empty() &&
           text.find_first_not_of("0123456789") == std::string::npos;
}

WarpRequest ParseWarp(const std::string& text) {
    WarpRequest request;
    request.where = text;

    const size_t space = text.find_last_of(" \t");
    if (space == std::string::npos) {
        return request;  // one word: all of it is the mission
    }

    const std::string tail = Trim(text.substr(space + 1));
    const std::string head = Trim(text.substr(0, space));
    if (head.empty() || !IsNumber(tail)) {
        return request;
    }

    request.where = head;
    request.part = static_cast<int>(ParseLong(tail, 0));
    return request;
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
    Say("ap_warp <number or name> to travel, plus a part number to return to "
        "somewhere you have been. ap_hub to come back.");
}

void Help() {
    Say("ap                            every mission and its unlock status");
    Say("ap_warp <number or name>      travel to an unlocked mission");
    Say("ap_warp <mission> <part>      to a part of it you have already reached");
    Say("ap_hub                        return to the hub");
    Say("ap_tracker [map]              locations found and still out there");
    Say("ap_find [text]                point at the nearest unfound check");
    Say("Names ignore case and punctuation: 'gonarch', 'c4a2', 'Gonarch's Lair'.");
}

void Warp() {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is nowhere to warp to.");
        return;
    }
    const std::string argument = ArgumentTail(1);
    if (argument.empty()) {
        Say("Usage: ap_warp <number or name> [part]. ap lists them.");
        return;
    }

    const WarpRequest request = ParseWarp(argument);

    const Chapter* chapter = nullptr;
    if (IsNumber(request.where)) {
        chapter = Data().ChapterByIndex(
            static_cast<int>(ParseLong(request.where, -1)));
    }
    if (chapter == nullptr) {
        chapter = Data().ChapterByName(request.where);
    }
    // A trailing number that turned out not to be a part -- `ap_warp c2a5 3`
    // where `c2a5 3` is nothing but `c2a5` is something -- has already been
    // handled, but the reverse needs a second look: `ap_warp 1 4` with no
    // mission 1 should not silently become a search for "1 4".
    if (chapter == nullptr && request.part > 0) {
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

    if (request.part <= 1) {
        Notify(std::string("Warping to ") + chapter->name + ".");
        RequestMap(chapter->maps.front());
        return;
    }

    // --- a part of a mission --------------------------------------------

    const int parts = static_cast<int>(chapter->maps.size());
    if (parts == 1) {
        Say(chapter->name + " is one map; there are no parts to warp to.");
        return;
    }
    if (request.part > parts) {
        char line[128];
        std::snprintf(line, sizeof(line), "%s has %d parts.",
                      chapter->name.c_str(), parts);
        Say(line);
        return;
    }

    const std::string& map_name = chapter->maps[request.part - 1];

    // Only somewhere already walked to. A partial warp is a way *back* -- after
    // a death, a reload, or an errand in the hub -- and never a way past the
    // half of a mission you have not played: the checks in a part you skipped to
    // would be free, and the fastest route through a mission would be to warp to
    // its last part.
    if (!Visited(map_name)) {
        char line[160];
        std::snprintf(line, sizeof(line),
                      "You have not reached %s part %d yet. Warp to the mission "
                      "and walk there.",
                      chapter->name.c_str(), request.part);
        Say(line);
        return;
    }

    char line[128];
    std::snprintf(line, sizeof(line), "Warping to %s, part %d.",
                  chapter->name.c_str(), request.part);
    Notify(line);
    RequestMap(map_name);
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

    // Leaving the mission. Whether that means *finishing* it depends on which
    // way the player walked: Half-Life's transitions are two-way, and walking
    // back through the door you came in lands you in the previous mission. That
    // has to be caught -- its checks would fire in a mission that may not even
    // be unlocked -- but it is not an achievement.
    const bool forwards = to != nullptr && to->index > from->index;

    if (forwards) {
        SendChapterComplete(*from);
        Notify(from->name + " complete. Returning to the hub.");
    } else {
        Notify(std::string("That way leads out of ") + from->name +
               ". Returning to the hub.");
    }

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
