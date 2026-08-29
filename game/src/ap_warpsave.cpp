#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_warpsave.h"

#include <algorithm>
#include <cstdio>
#include <cstring>

#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

namespace ap {
namespace {

// Where GoldSrc keeps savegames: `<mod folder>/SAVE`, with the engine's working
// directory at the install root. The same reasoning as `StoreDir` in ap_main.cpp,
// and the same reason it is a relative path.
std::string SaveDir() {
    char game_dir[260] = {0};
    GET_GAME_DIR(game_dir);
    std::string dir(game_dir);
    if (dir.empty()) {
        dir = "hlap";
    }
    return dir + "/SAVE";
}

std::string SavePath(const std::string& save) {
    return SaveDir() + "/" + save + ".sav";
}

// A savegame's name is a filename and a console argument, so it may hold nothing
// that needs quoting and nothing a path can be built out of.
std::string Sanitise(const std::string& text, size_t limit) {
    std::string out;
    for (char c : Lower(Trim(text))) {
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
            out += c;
        }
        if (out.size() >= limit) {
            break;
        }
    }
    return out;
}

// FNV-1a, 32 bit. Any short stable hash would do; this one is four lines and
// `apworld/half_life/client/bridge.py` computes the same digits, which is what
// lets the client sweep the files the game wrote.
std::string Hash8(const std::string& text) {
    unsigned int hash = 2166136261u;
    for (unsigned char c : text) {
        hash ^= c;
        hash *= 16777619u;
    }
    char out[16];
    std::snprintf(out, sizeof(out), "%08x", hash);
    return out;
}

std::string Prefix() {
    const std::string key = WarpKey();
    return key.empty() ? std::string() : "ap" + key + "_";
}

// A save we owe, and when the level will have settled enough to take it. Not
// state about the run: it is cleared by the map load that would invalidate it,
// and nothing reads it after the save has been issued.
std::string g_pending_save;
float g_pending_at = 0.0f;

// The arrival this map load is owed a warp point for, if any.
std::string g_arrival_map;

void Issue(const std::string& save, float delay) {
    g_pending_save = save;
    g_pending_at = gpGlobals->time + delay;
}

// Can the engine take a save at all right now? It refuses on a dead player, with
// a console message the player will not connect to the command they typed.
bool CanSave(std::string& why) {
    CBasePlayer* player = Player();
    if (player == nullptr || !player->IsAlive()) {
        why = "Not while you are dead.";
        return false;
    }
    return true;
}

}  // namespace

std::string WarpKey() {
    const std::string slot = State().slot;
    if (slot.empty()) {
        return std::string();
    }
    return Hash8(slot);
}

std::string AutoWarpName(const std::string& map) {
    const std::string prefix = Prefix();
    const std::string clean = Sanitise(map, 16);
    if (prefix.empty() || clean.empty()) {
        return std::string();
    }
    return prefix + "m" + clean;
}

bool WarpSaveExists(const std::string& save) {
    if (save.empty()) {
        return false;
    }
    FILE* file = std::fopen(SavePath(save).c_str(), "rb");
    if (file == nullptr) {
        return false;
    }
    std::fclose(file);
    return true;
}

std::vector<WarpPoint> NamedWarps() {
    std::vector<WarpPoint> found;
    const std::string prefix = Prefix();
    if (prefix.empty()) {
        return found;
    }

#ifdef _WIN32
    const std::string pattern = SaveDir() + "/" + prefix + "u*.sav";
    WIN32_FIND_DATAA entry;
    HANDLE handle = FindFirstFileA(pattern.c_str(), &entry);
    if (handle == INVALID_HANDLE_VALUE) {
        return found;
    }
    do {
        std::string name(entry.cFileName);
        if (name.size() < prefix.size() + 6) {
            continue;
        }
        name.erase(name.size() - 4);  // ".sav"

        // `<prefix>u<label>_<map>`: the label holds no underscore, so the one
        // separator in what is left is the last one.
        const std::string tail = name.substr(prefix.size() + 1);
        const size_t split = tail.find_last_of('_');
        if (split == std::string::npos || split == 0 ||
            split + 1 >= tail.size()) {
            continue;
        }

        WarpPoint point;
        point.save = name;
        point.label = tail.substr(0, split);
        point.map = tail.substr(split + 1);
        found.push_back(point);
    } while (FindNextFileA(handle, &entry));
    FindClose(handle);
#endif

    std::sort(found.begin(), found.end(),
              [](const WarpPoint& a, const WarpPoint& b) {
                  return a.label < b.label;
              });
    return found;
}

bool FindNamedWarp(const std::string& label, WarpPoint& out) {
    const std::string wanted = Sanitise(label, 12);
    if (wanted.empty()) {
        return false;
    }
    for (const WarpPoint& point : NamedWarps()) {
        if (point.label == wanted) {
            out = point;
            return true;
        }
    }
    return false;
}

void SetWarp(const std::string& label) {
    if (WarpKey().empty()) {
        Say("No slot is connected, so there is nothing to key a warp point to.");
        return;
    }
    std::string why;
    if (!CanSave(why)) {
        Say(why);
        return;
    }

    const std::string map = CurrentMap();
    const Chapter* chapter = Data().ChapterOfMap(map);

    if (label.empty()) {
        if (chapter == nullptr) {
            Say("You are not in a mission, and !hub already comes back here.");
            return;
        }
        const std::string save = AutoWarpName(map);
        if (save.empty()) {
            return;
        }
        Issue(save, 0.0f);

        const int part = PartOf(*chapter, map);
        char line[160];
        if (part > 0) {
            std::snprintf(line, sizeof(line),
                          "Warp point for %s part %d set to where you stand.",
                          chapter->name.c_str(), part);
        } else {
            std::snprintf(line, sizeof(line),
                          "Warp point for %s set to where you stand.",
                          chapter->name.c_str());
        }
        Notify(line);
        return;
    }

    const std::string clean = Sanitise(label, 12);
    if (clean.empty()) {
        Say("A warp name needs letters or numbers: !setwarp lab");
        return;
    }

    // The same label somewhere else is the same warp point moved, so the old
    // file goes: two saves under one name is a warp with two destinations.
    WarpPoint existing;
    if (FindNamedWarp(clean, existing) && existing.map != map) {
        std::remove(SavePath(existing.save).c_str());
    }

    const std::string save = Prefix() + "u" + clean + "_" + Sanitise(map, 16);
    Issue(save, 0.0f);
    Notify("Warp point '" + clean + "' set. Come back with !warp " + clean + ".");
}

void ListWarps() {
    if (WarpKey().empty()) {
        Say("No slot is connected, so no warp points are loaded.");
        return;
    }

    const std::vector<WarpPoint> named = NamedWarps();
    if (named.empty()) {
        Say("No warp points of your own. !setwarp <name> makes one here.");
    } else {
        Say("Your warp points:");
        for (const WarpPoint& point : named) {
            const Chapter* chapter = Data().ChapterOfMap(point.map);
            char line[192];
            std::snprintf(line, sizeof(line), "  !warp %s    %s (%s)",
                          point.label.c_str(),
                          chapter ? chapter->name.c_str() : "outside a mission",
                          point.map.c_str());
            Say(line);
        }
    }

    // The automatic ones are not listed one by one -- there is one per part of
    // every mission walked through, and `ap` already lists the missions.
    Say("Parts you have walked into: !warp <mission> <part>.");
}

void NoteArrival(const std::string& previous, const std::string& map,
                 bool requested) {
    g_pending_save.clear();
    g_arrival_map.clear();

    if (requested) {
        // We asked to be here: either a cold `map` warp, whose state is exactly
        // what a warp point should not preserve, or a `load` of the warp point
        // itself.
        return;
    }
    if (previous.empty() || previous == map) {
        // The first map of the session, or a quickload back into this one.
        return;
    }

    const Chapter* chapter = Data().ChapterOfMap(map);
    const Chapter* before = Data().ChapterOfMap(previous);
    if (chapter == nullptr || before == nullptr || chapter->key != before->key) {
        // Only a transition from another part of this mission. Crossing a
        // mission boundary is intercepted and never lands anywhere, and arriving
        // from the hub is a warp, which is handled above.
        return;
    }

    // Forwards only. Half-Life's transitions are two-way, and walking back into
    // part 2 from part 3 arrives at the far end of part 2, which is not where
    // part 2 begins. The warp point wanted here is the one the player first
    // walked into, and `RunWarpSave` keeps that one by refusing to overwrite;
    // this keeps the wrong door from being the one that writes it in the first
    // place. `!setwarp` is how a deliberate one is moved.
    if (PartOf(*chapter, map) <= PartOf(*before, previous)) {
        return;
    }

    g_arrival_map = map;
}

void RunWarpSave() {
    if (!g_pending_save.empty()) {
        if (gpGlobals->time < g_pending_at || !ClientReady()) {
            return;
        }
        const std::string save = g_pending_save;
        g_pending_save.clear();

        std::string why;
        if (!CanSave(why)) {
            Trace(("  warp save refused: " + save).c_str());
            return;
        }

        char command[96];
        std::snprintf(command, sizeof(command), "save %s\n", save.c_str());
        SERVER_COMMAND(command);
        SERVER_EXECUTE();
        Trace(("  warp save " + save).c_str());
        return;
    }

    if (g_arrival_map.empty()) {
        return;
    }
    // The key comes from the snapshot, so this waits for the client to speak.
    // Nothing is lost by waiting: the player is standing in the seam room.
    const std::string save = AutoWarpName(g_arrival_map);
    if (save.empty()) {
        return;
    }
    const std::string map = g_arrival_map;
    g_arrival_map.clear();

    if (WarpSaveExists(save)) {
        return;  // the first arrival is the one worth keeping
    }
    if (map != CurrentMap()) {
        return;
    }
    // A second of play, so the transition has finished and the player has landed
    // rather than being caught mid-teleport.
    Issue(save, 1.0f);
}

}  // namespace ap
