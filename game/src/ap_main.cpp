#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_main.h"

#include <fstream>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_checkdata.h"
#include "ap_deathlink.h"
#include "ap_hub.h"
#include "ap_items.h"
#include "ap_locations.h"
#include "ap_state.h"
#include "ap_traps.h"

namespace ap {

const char* const kStoreSubdir = "archipelago";

namespace {

Bridge g_bridge;
CheckData g_data;
float g_next_poll = 0.0f;
bool g_started = false;
bool g_warned_mismatch = false;

// `<game dir>/archipelago`. GET_GAME_DIR hands back the mod folder's name
// ("hlap") and the engine's working directory is the install root, so a relative
// path is both correct and the only thing that works on a client whose Half-Life
// lives somewhere with a space in the name.
std::string StoreDir() {
    char game_dir[260] = {0};
    GET_GAME_DIR(game_dir);
    std::string dir(game_dir);
    if (dir.empty()) {
        dir = "hlap";
    }
    return dir + "/" + kStoreSubdir;
}

}  // namespace

CheckData& Data() { return g_data; }
Bridge& Wire() { return g_bridge; }

CBasePlayer* Player() {
    edict_t* edict = INDEXENT(1);
    if (FNullEnt(edict) || edict->free || !edict->pvPrivateData) {
        return nullptr;
    }
    CBaseEntity* entity = CBaseEntity::Instance(edict);
    if (entity == nullptr || !entity->IsPlayer()) {
        return nullptr;
    }
    return static_cast<CBasePlayer*>(entity);
}

std::string CurrentMap() {
    return std::string(STRING(gpGlobals->mapname));
}

void Say(const std::string& text) {
    CBasePlayer* player = Player();
    if (player == nullptr) {
        ALERT(at_console, "[AP] %s\n", text.c_str());
        return;
    }
    const std::string line = "[AP] " + text + "\n";
    CLIENT_PRINTF(player->edict(), print_console, line.c_str());
}

void Trace(const char* where) {
    if (!kTraceLoad) {
        return;
    }
    // Opened and closed per line rather than held: the point of the file is to
    // be readable after a crash, and a stream buffered inside a process that has
    // just died tells you nothing.
    std::ofstream file((StoreDir() + "/ap_boot.txt").c_str(), std::ios::app);
    if (file) {
        file << where << "\n";
    }
}

void TraceReset() {
    if (!kTraceLoad) {
        return;
    }
    std::ofstream file((StoreDir() + "/ap_boot.txt").c_str(),
                       std::ios::out | std::ios::trunc);
}

bool Gated() { return g_data.Loaded(); }

bool Live() {
    if (!g_data.Loaded() || !g_bridge.IsOpen()) {
        return false;
    }
    const Snapshot& state = State();
    if (!state.connected) {
        return false;
    }
    if (!state.data_version.empty() && !g_data.data_version.empty() &&
        state.data_version != g_data.data_version) {
        if (!g_warned_mismatch) {
            g_warned_mismatch = true;
            Say("This mod's checkdata.txt and the apworld that made your seed are "
                "different builds, so checks are paused. Run /install in the "
                "client.");
        }
        return false;
    }
    g_warned_mismatch = false;
    return true;
}

void Startup() {
    Trace("ServerActivate: ap::Startup");
    const std::string store = StoreDir();

    // Once per process rather than once per map: rereading a file that cannot
    // have changed on every level transition is pure cost, and the whole point
    // of the design is that a map load is cheap.
    if (!g_data.Loaded()) {
        if (!g_data.Load(store + "/checkdata.txt")) {
            ALERT(at_console,
                  "[AP] no checkdata.txt in %s -- running as ordinary Half-Life\n",
                  store.c_str());
        }
    }
    Trace(g_data.Loaded() ? "  checkdata read" : "  no checkdata");

    g_bridge.Open(store);
    g_started = true;
    g_next_poll = 0.0f;

    // The client answers a HELLO with a forced snapshot, so this is what gets
    // our unlocks back after any map load.
    g_bridge.Send("HELLO", CurrentMap());
    Trace("  bridge open");

    OnMapStart(CurrentMap());
    Trace("  map start done");
}

void RunFrame() {
    if (!g_started) {
        return;
    }
    static bool first = true;
    if (first) {
        first = false;
        Trace("StartFrame: first frame");
    }

    // Deferred work first, and every frame. A queued level change must not wait
    // on the poll clock, and the armour clamp has to be tighter than 0.2s or a
    // charge panel would visibly fill the bar before we emptied it.
    RunDeferred();
    ClampArmour();

    if (gpGlobals->time < g_next_poll) {
        return;
    }
    g_next_poll = gpGlobals->time + kPollIntervalSeconds;

    std::vector<PendingEvent> events;
    if (g_bridge.Poll(State(), events)) {
        for (const PendingEvent& event : events) {
            ApplyEvent(event);
            g_bridge.Acknowledge(event.seq);
        }
        // A snapshot that changed may have brought a weapon we are holding back
        // or opened a mission, so the loadout is reapplied rather than waiting
        // for the next spawn.
        CBasePlayer* player = Player();
        if (player != nullptr) {
            ApplyLoadout(player);
        }
    }

    RunTrapTimers();
    // A weapon the player is already holding never fires a touch, so the crowbar
    // check would otherwise be unsendable. Cheap: it only looks at entities
    // within arm's reach.
    SweepNearbyPickups();
}

void ApplyEvent(const PendingEvent& event) {
    CBasePlayer* player = Player();

    if (event.kind == "ITEM") {
        if (player != nullptr) {
            GrantFiller(player, event.payload);
        }
    } else if (event.kind == "TRAP") {
        QueueTrap(event.payload);
    } else if (event.kind == "DEATHLINK") {
        // `<source>~<cause>`: the payload joins its fields with '~' because the
        // event line itself is split on '|'.
        const size_t split = event.payload.find('~');
        const std::string source =
            split == std::string::npos ? event.payload : event.payload.substr(0, split);
        const std::string cause =
            split == std::string::npos ? std::string("an unknown fate")
                                       : event.payload.substr(split + 1);
        OnDeathLinkReceived(source, cause, event.stamp);
    } else if (event.kind == "CHAT") {
        Say(event.payload);
    }
    // An unknown kind is a delivery from a newer client. ACKed anyway by the
    // caller: holding it would stall the client's whole event window.
}

}  // namespace ap
