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

// The authored lobby: one room, a labelled panel per mission, and a pit.
//
// It replaces `stalkyard`, which was a stock deathmatch map picked against three
// criteria a hub can fail on -- no `trigger_changelevel` out of it, nothing that
// hurts you while you stand still, and small enough to reload after every
// mission. This map is ours, so the first holds by construction and the third by
// authoring. The second it breaks on purpose, and that is fine: the pit is a
// joke, and the player has to walk into it.
//
// `HUB_MAP` in tools/campaign_layout.py and `startmap` in liblist.gam are the
// same name; tests/test_mod_install.py fails if they drift apart.
const char* const kHubMap = "ap_lobby_alpha";

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

// Has this mission's own completion check been sent?
//
// The completion is a location like any other, so it can arrive from the server
// without the game having played a second of the mission: released, collected,
// or sent by hand from the console. It is also the location the finale's seal
// counts, so this list has to agree with what that seal is waiting on.
//
// Found by the mission key the record carries rather than by map: a completion
// names both, but the key is what says which mission it completes.
bool CompletionFound(const Chapter& chapter) {
    const Snapshot& state = State();
    for (const Location& location : Data().locations) {
        if (location.type != TriggerType::ChapterComplete) continue;
        if (location.chapter != chapter.key) continue;
        return state.checked.find(location.id) != state.checked.end();
    }
    return false;
}

// Is there anything left to find in this mission?
//
// Only what this seed actually contains is counted. Chargesanity off leaves
// every charger id in `checkdata.txt` unclaimed for the whole run, and counting
// those would mean no mission was ever finished.
bool AllFound(const Chapter& chapter) {
    const Snapshot& state = State();
    size_t in_seed = 0;

    for (const Location& location : Data().locations) {
        const Chapter* owner = Data().ChapterOfMap(location.map);
        if (owner == nullptr || owner->key != chapter.key) continue;
        if (!state.InSeed(location.id)) continue;

        ++in_seed;
        if (state.checked.find(location.id) == state.checked.end()) {
            return false;
        }
    }

    // Before the first snapshot everything reads as in-seed and nothing as
    // checked, so this is only ever true once the client has actually spoken.
    return in_seed > 0;
}

// Either answer alone is incomplete. A mission can be emptied of everything the
// seed put in it without its completion ever being sent, when `missions_required`
// is low enough that nothing was waiting on it, and a completion can arrive from
// the server with every charger in the mission still unfound.
bool Finished(const Chapter& chapter) {
    return CompletionFound(chapter) || AllFound(chapter);
}

// Where a refusal goes. Somebody who typed `ap_warp` is reading the console, and
// `Say` is the answer to a command. Somebody who pressed a panel is looking at
// the room, and a console-only refusal is indistinguishable from a dead button.
void Refuse(bool on_screen, const std::string& text) {
    if (on_screen) {
        Notify(text);
    } else {
        Say(text);
    }
}

// May the player enter this mission at all? Says why not on their behalf.
//
// The one set of rules, asked in one place, so a lobby panel can never become a
// way past a gate `ap_warp` refuses. Everything here is the client's answer
// rather than anything counted locally: deciding "is this open" from a cached
// count is how the two halves drift apart.
bool MissionOpen(const Chapter& chapter, bool on_screen) {
    const Snapshot& state = State();

    if (state.ChapterExcluded(chapter.key)) {
        Refuse(on_screen, chapter.name + " is not in this seed.");
        return false;
    }

    // Not connected means we do not know what is open, and "do not know" has to
    // refuse rather than allow. Warping freely while disconnected and connecting
    // afterwards would put a player inside a mission the seed had locked, with
    // every check in it live the moment the client came up -- which is a way
    // around every gate in the game, reachable by closing one window.
    //
    // `ap_hub` is deliberately still allowed: going home is never a way in.
    if (!state.connected) {
        Refuse(on_screen,
               "The Archipelago client is not connected, so no mission is open "
               "yet. Start it, connect to your room, and try again.");
        return false;
    }

    const bool open = chapter.is_goal ? state.goal_open
                                      : state.ChapterOpen(chapter.key);
    if (!open) {
        Refuse(on_screen,
               chapter.name +
                   (chapter.is_goal
                        ? " is still sealed. Finish more missions."
                        : " is locked. Its unlock item has not arrived."));
        return false;
    }

    return true;
}

const char* StatusOf(const Chapter& chapter) {
    const Snapshot& state = State();
    // Said instead of "unlocked", and instead of a finale's seal, rather than
    // alongside either: having got into a mission is implied by having emptied
    // it, and this list is read to find where there is still something left. A
    // mission with nothing left in it is done with whether or not its own door
    // is still open.
    if (Finished(chapter)) {
        return "complete";
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
        // A mission the seed left out is not listed at all. It used to print as
        // "not in this seed", which with `exclude_intro_missions` on meant the
        // list opened with lines about missions nobody can play. The numbering
        // is `chapter.index` rather than a running count, so skipping one does
        // not renumber the rest: `ap_warp 7` still means the same mission.
        if (State().ChapterExcluded(chapter.key)) {
            continue;
        }
        char line[160];
        std::snprintf(line, sizeof(line), "  %2d. %-26s [%s]", chapter.index,
                      chapter.name.c_str(), StatusOf(chapter));
        Say(line);
    }
    Say("Press a panel in the hub, or !warp <number or name>, plus a part number "
        "to return to somewhere you have been. !hub to come back. !help for the "
        "rest.");
}

void Help() {
    Say("In chat (Y), or in the console without the !:");
    Say("!ap                       every mission and its unlock status");
    Say("!warp <number or name>    travel to an unlocked mission");
    Say("!warp <mission> <part>    to a part of it you have already reached");
    Say("!hub                      return to the hub");
    Say("!tracker [map]            locations found and still out there");
    Say("!find [text]              point at the nearest unfound check");
    Say("Names ignore case and punctuation: 'gonarch', 'c4a2', 'Gonarch's Lair'.");
    Say("In the hub you can press a mission's panel instead of typing anything.");
}

void Warp(const std::string& argument) {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is nowhere to warp to.");
        return;
    }
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

    if (!MissionOpen(*chapter, false)) {
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
void Cmd_ApWarp() { Warp(ArgumentTail(1)); }
void Cmd_ApHub() { ToHub(); }
void Cmd_ApFind() { Find(ArgumentTail(1)); }
void Cmd_ApTracker() { Tracker(ArgumentTail(1)); }

// One place that knows what every command is, whether it arrived from the
// console or from chat. The console names are the long ones (`ap_warp`); chat
// takes the short ones too, because `!warp 3` is what a player will type.
bool Dispatch(const std::string& name, const std::string& rest) {
    if (name == "ap") {
        ListMissions();
    } else if (name == "help" || name == "ap_help") {
        Help();
    } else if (name == "warp" || name == "ap_warp") {
        Warp(rest);
    } else if (name == "hub" || name == "ap_hub") {
        ToHub();
    } else if (name == "find" || name == "ap_find") {
        Find(rest);
    } else if (name == "tracker" || name == "ap_tracker") {
        Tracker(rest);
    } else {
        return false;
    }
    return true;
}

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

bool HandleChat(CBasePlayer* player, const std::string& said) {
    // `say` hands the whole line over as one argument, usually quoted, so this
    // is the raw text the player typed rather than anything pre-split.
    std::string text = Trim(said);
    if (text.size() >= 2 && text.front() == '"' && text.back() == '"') {
        text = Trim(text.substr(1, text.size() - 2));
    }
    if (text.empty()) {
        return false;
    }

    // `!` is the prefix, and `/` is accepted because half of everyone types
    // that instead. A line starting with neither is chat, and stays chat.
    if (text[0] != '!' && text[0] != '/') {
        return false;
    }
    text.erase(text.begin());

    const size_t space = text.find_first_of(" \t");
    std::string name = Lower(space == std::string::npos ? text
                                                       : text.substr(0, space));
    const std::string rest =
        space == std::string::npos ? std::string() : Trim(text.substr(space + 1));

    if (!Dispatch(name, rest)) {
        // Ours to answer even when it is not a command we have: a player who
        // typed `!warpp` wants to be told, not to have it broadcast to a chat
        // nobody else is in.
        Say(std::string("No such command: !") + name + ". Try !help.");
    }
    return true;
}

bool PressHubButton(CBasePlayer* player, CBaseEntity* target) {
    if (player == nullptr || target == nullptr || !Data().Loaded()) {
        return false;
    }
    // STRING(0) is the empty string, which no `P` record answers to, so an
    // unnamed brush falls straight through without a special case.
    const Chapter* chapter =
        Data().ChapterOfButton(std::string(STRING(target->pev->targetname)));
    if (chapter == nullptr) {
        return false;
    }

    if (MissionOpen(*chapter, true)) {
        Notify(std::string("Entering ") + chapter->name + ".");
        RequestMap(chapter->maps.front());
    }
    // Ours either way: a refused panel has still been answered, and the refusal
    // is on screen. Returning false would let the press fall through to the
    // charger check below it, which is not what a lobby panel is.
    return true;
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
