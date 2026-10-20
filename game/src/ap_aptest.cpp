#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_aptest.h"

#include <cstring>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_text.h"
#include "ap_transitions.h"
#include "ap_warpsave.h"

extern int gmsgAPLabel;  // player.cpp

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
    // Placed crouched: the spot is in a vent a standing player does not fit.
    bool crouch = false;
    // Only `tp` goes to the spot; arriving leaves the player at spawn, for a
    // spot that would kill them.
    bool manual = false;
    // The way the player faces when placed.
    bool has_yaw = false;
    float yaw = 0.0f;
    // Label every transition of whatever map the player is on, `T<n> > <to>`,
    // n by id number. `entry` is the one the scenario came in through.
    bool transition_labels = false;
    std::string entry;
    // Text drawn at points in the scenario's map.
    struct Label {
        float position[3];
        std::string text;
    };
    std::vector<Label> labels;
    // `pair=<id> <id>`: the transition pairs the scenario plays with.
    std::vector<std::pair<std::string, std::string>> pairs;
    // `save=<name>`: the game is saved under this name on `!pass` or `!fail`,
    // for a later scenario to carry on from.
    std::string save_as;
    // `load=<name>`: the scenario starts by loading this save, wherever it was
    // taken, instead of loading `map` fresh.
    std::string load;
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
// The map and life the point labels were last sent for. A level change or a
// death reloads the client's level, and it forgets them with it.
std::string g_labels_map;
float g_labels_since = -1.0f;
bool g_labels_sent = false;
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
        } else if (key == "crouch") {
            out.crouch = value == "1";
        } else if (key == "manual") {
            out.manual = value == "1";
        } else if (key == "pair") {
            std::istringstream fields(value);
            std::string a, b;
            if (fields >> a >> b) {
                out.pairs.push_back({a, b});
            }
        } else if (key == "save") {
            out.save_as = value;
        } else if (key == "load") {
            out.load = value;
        } else if (key == "transitions") {
            out.transition_labels = value == "1";
        } else if (key == "entry") {
            out.entry = value;
        } else if (key == "yaw") {
            out.has_yaw = true;
            out.yaw = static_cast<float>(std::atof(value.c_str()));
        } else if (key == "label") {
            // `x y z text`
            std::istringstream fields(value);
            Destination::Label label;
            if (fields >> label.position[0] >> label.position[1] >> label.position[2]) {
                std::getline(fields, label.text);
                label.text = Trim(label.text);
                if (!label.text.empty()) {
                    out.labels.push_back(label);
                }
            }
        }
    }
    return !out.map.empty() || !out.load.empty();
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
    if (!g_destination.load.empty()) {
        if (!WarpSaveExists(g_destination.load)) {
            g_arriving = false;
            Notify("[aptest] No save '" + g_destination.load + "' yet: !pass or !fail the "
                   "scenario before this one first, then !redo.");
            return;
        }
        RequestLoad(g_destination.load, "");
        return;
    }
    RequestMap(g_destination.map);
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
    if (g_destination.crouch) {
        // Ducked as the movement code would leave it: crouched size and view,
        // and it stays that way while there is no room to stand up.
        if (!FindStandSpot(player, target, spot, head_hull)) {
            spot = target;
            Notify("[aptest] No room to crouch near the spot; placed on it anyway.");
        }
        player->pev->flags |= FL_DUCKING;
        player->pev->view_ofs = VEC_DUCK_VIEW;
        UTIL_SetSize(player->pev, VEC_DUCK_HULL_MIN, VEC_DUCK_HULL_MAX);
    } else if (!FindStandSpot(player, target, spot)) {
        spot = target;
        Notify("[aptest] No room to stand near the spot; placed on it anyway.");
    }
    if (!g_destination.entry.empty()) {
        // A spot by a transition, which can hang in the air (c1a0e's teleport):
        // on the ground below it, as an arrival would be.
        TraceResult tr;
        UTIL_TraceHull(spot, spot - Vector(0, 0, 4096), ignore_monsters,
                       g_destination.crouch ? head_hull : human_hull, player->edict(), &tr);
        if (!tr.fStartSolid && tr.flFraction < 1.0f) {
            spot = tr.vecEndPos;
        }
    }
    UTIL_SetOrigin(player->pev, spot);
    player->pev->velocity = g_vecZero;
    if (g_destination.has_yaw) {
        player->pev->angles = player->pev->v_angle = Vector(0, g_destination.yaw, 0);
        player->pev->fixangle = 1;
    }
}

// The scenario's labels, as points: a negative index tells the client the
// label is a position, not an entity.
void SendPointLabel(CBasePlayer* player, int index, const float at[3],
                    const std::string& text) {
    MESSAGE_BEGIN(MSG_ONE, gmsgAPLabel, nullptr, player->pev);
    WRITE_SHORT(-index);
    WRITE_COORD(at[0]);
    WRITE_COORD(at[1]);
    WRITE_COORD(at[2]);
    WRITE_STRING(text.c_str());
    MESSAGE_END();
}

long TransitionNumber(const Transition& t) {
    return ParseLong(t.id.substr(t.id.rfind(':') + 1));
}

void SendPointLabels(CBasePlayer* player) {
    const std::string map = CurrentMap();
    int index = 0;
    if (map == g_destination.map) {
        for (const Destination::Label& label : g_destination.labels) {
            SendPointLabel(player, ++index, label.position, label.text);
        }
    }
    if (!g_destination.transition_labels) {
        return;
    }
    std::vector<const Transition*> here;
    for (const Transition& t : Data().transitions) {
        if (t.map == map) {
            here.push_back(&t);
        }
    }
    std::sort(here.begin(), here.end(), [](const Transition* a, const Transition* b) {
        return TransitionNumber(*a) < TransitionNumber(*b);
    });
    for (size_t n = 0; n < here.size(); ++n) {
        std::string text = "T" + std::to_string(n + 1);
        if (OutsideSeed(*here[n])) {
            text += " (not in seed)";
        } else if (Inert(here[n]->id)) {
            text += " (inert)";
        } else {
            text += " > " + LeadsTo(*here[n]);
        }
        if (here[n]->id == g_destination.entry) {
            text += " (entry)";
        }
        SendPointLabel(player, ++index, here[n]->at, text);
    }
}

// Once per map and life, a second in, when the client is in the level, and
// not while a scenario is still placing the player.
void RunPointLabels() {
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive() || g_destination.seq < 0) {
        g_labels_since = -1.0f;
        return;
    }
    if (g_labels_since < 0.0f || CurrentMap() != g_labels_map ||
        gpGlobals->time < g_labels_since) {
        g_labels_map = CurrentMap();
        g_labels_since = gpGlobals->time;
        g_labels_sent = false;
        return;
    }
    if (g_labels_sent || g_arriving || gpGlobals->time - g_labels_since < 1.0f) {
        return;
    }
    SendPointLabels(player);
    g_labels_sent = true;
}

// Everything but `tp` is the harness's to answer.
const char* const kHarnessVerbs[] = {
    "pass", "fail", "note", "next", "prev", "redo", "go", "info", "status",
    "list", "give", "take", "item", "trap", "deathlink", "clear", "connect",
    "disconnect", "chat", "orb", "door",
};

// The door the player is looking at, as `<model> <classname> <targetname>`,
// or empty: for `!door`, which the harness records as an opener.
std::string AimedDoor(CBasePlayer* player) {
    UTIL_MakeVectors(player->pev->v_angle);
    const Vector eye = player->pev->origin + player->pev->view_ofs;
    TraceResult tr;
    UTIL_TraceLine(eye, eye + gpGlobals->v_forward * 192.0f, dont_ignore_monsters,
                   player->edict(), &tr);
    CBaseEntity* hit = tr.pHit != nullptr ? CBaseEntity::Instance(tr.pHit) : nullptr;
    if (hit == nullptr || std::strncmp(STRING(hit->pev->classname), "func_door", 9) != 0) {
        return "";
    }
    return std::string(STRING(hit->pev->model)) + " " + STRING(hit->pev->classname) + " " +
           (FStringNull(hit->pev->targetname) ? "-" : STRING(hit->pev->targetname));
}

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

void RemapTestSpawn(entvars_t* pev) {
#ifdef HLAP_TEST_BUILD
    if (pev == nullptr || !g_arriving || g_destination.manual || !g_destination.load.empty() ||
        !g_destination.has_position || !FClassnameIs(pev, "info_player_start") ||
        g_destination.map != STRING(gpGlobals->mapname)) {
        return;
    }
    pev->origin = Vector(g_destination.position[0], g_destination.position[1],
                         g_destination.position[2]);
    if (g_destination.has_yaw) {
        pev->angles = Vector(0, g_destination.yaw, 0);
    }
#else
    (void)pev;
#endif
}

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
            // Where the player stands and faces, for a note that records a spot.
            std::string where;
            CBasePlayer* player = Player();
            if (player != nullptr) {
                char text[160];
                snprintf(text, sizeof(text), "%.0f %.0f %.0f %.0f %s", player->pev->origin.x,
                         player->pev->origin.y, player->pev->origin.z,
                         player->pev->v_angle.y, CurrentMap().c_str());
                where = text;
            }
            // The state this scenario ends in, for the one that carries on.
            if ((name == "pass" || name == "fail") && !g_destination.save_as.empty() &&
                player != nullptr && player->IsAlive()) {
                const std::string command = "save " + g_destination.save_as + "\n";
                SERVER_COMMAND(const_cast<char*>(command.c_str()));
                Notify("[aptest] Saved as " + g_destination.save_as + ".");
            }
            std::string text = rest;
            if (name == "door" && player != nullptr) {
                const std::string door = AimedDoor(player);
                if (door.empty() && Trim(rest).empty()) {
                    Notify("[aptest] !door: look at the door, within a few steps.");
                    return true;
                }
                text = door.empty() ? rest : door + (rest.empty() ? "" : " " + rest);
            }
            Wire().Send("APTEST", std::vector<std::string>{name, Sanitise(text), where});
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
            // The scenario's probes, before its map spawns and is tagged.
            ReloadData();
            // And its pairs, before its triggers spawn and are rewritten. A
            // seed in the snapshot has the say over a scenario's own.
            if (TransitionsMode()) {
                ApplySeedTransitions(State(), true);
            } else {
                SetTransitionPairs(g_destination.pairs);
            }
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

    RunPointLabels();
    // A loaded save lands wherever it was taken.
    const bool loaded = !g_destination.load.empty();
    if (!g_arriving || (!loaded && CurrentMap() != g_destination.map)) {
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
        // Off the map's spawn at once as well, before a trigger there is
        // touched; placed again below once the level has settled.
        if (!g_destination.manual && !loaded) {
            Teleport();
        }
        return;
    }
    if (gpGlobals->time - g_alive_since < 1.0f) {
        return;
    }
    g_arriving = false;
    if (!g_destination.manual && !loaded) {
        Teleport();
    }
    // Placed: the labels go out afresh, after the move.
    g_labels_since = -1.0f;
    ShowSaid();
#endif
}

}  // namespace ap
