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

// Player-facing lines waiting for a frame safe enough to send them in.
std::vector<std::string> g_notices;

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

const char* Intern(const std::string& text) {
    // A set, because it never invalidates a reference to an element it already
    // holds. The pointer handed out here has to stay good for as long as an
    // entity might carry it, which is the life of the process; a vector would
    // reallocate and take every previous classname with it.
    //
    // It never shrinks, and that is the point. There are two dozen weapon
    // classnames in the game.
    static std::set<std::string> pool;
    return pool.insert(text).first->c_str();
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

void Notify(const std::string& text) {
    // Queued, never sent from here. A notification is a user message, and the
    // hooks that raise one run at moments the engine cannot take a message:
    // `CBasePlayer::Killed`, `Spawn` before the client is fully in the server,
    // the middle of a level load. Writing one there is
    // `SZ_GetSpace: Tried to write to an uninitialized sizebuf_t`, which takes
    // the game down.
    //
    // The same rule as the deferred level change, for the same reason: a hook
    // decides *what* happens, and StartFrame is where it actually happens.
    g_notices.push_back(text);
}

void FlushNotices() {
    if (g_notices.empty()) {
        return;
    }

    CBasePlayer* player = Player();
    const bool can_message =
        player != nullptr && (player->pev->flags & FL_CLIENT) != 0;

    for (const std::string& text : g_notices) {
        // The server console always gets it, so nothing is lost when there is
        // nobody to tell.
        ALERT(at_console, "[AP] %s\n", text.c_str());
        if (!can_message) {
            continue;
        }

        const std::string line = "[AP] " + text + "\n";
        CLIENT_PRINTF(player->edict(), print_console, line.c_str());

        // HUD_PRINTTALK: the message area chat uses, bottom left, a few lines
        // deep and gone after a few seconds. The client runs this through
        // titles.txt first, so a leading '#' would be read as a lookup key and
        // a '%' as a substitution. Neither belongs in a location name, but
        // neither is impossible, and a name that silently vanished would be
        // worse than an ugly one.
        std::string hud = line;
        for (char& c : hud) {
            if (c == '%') {
                c = ' ';
            }
        }
        if (hud[0] == '#') {
            hud.insert(hud.begin(), ' ');
        }
        ClientPrint(player->pev, HUD_PRINTTALK, hud.c_str());
    }

    g_notices.clear();
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
            Notify("This mod's checkdata.txt and the apworld that made your seed are "
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
    // A weapon Butterfingers threw on the floor went with the old level.
    ClearWithheld();

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
    // on the poll clock, the armour clamp has to be tighter than 0.2s or a
    // charge panel would visibly fill the bar before we emptied it, and
    // anything a hook wanted to tell the player is sent from here rather than
    // from the hook.
    FlushNotices();
    RunLoadout();
    RunDeferred();
    ClampArmour();

    if (gpGlobals->time < g_next_poll) {
        return;
    }
    g_next_poll = gpGlobals->time + kPollIntervalSeconds;

    // What the player held before this poll, so the snapshot can be diffed for
    // things worth announcing. Weapons and mission unlocks arrive in the
    // snapshot rather than as events -- the snapshot is idempotent and events
    // are one-shot -- so without this they arrive in total silence.
    const std::set<std::string> had_items = State().held_items;
    const std::set<std::string> had_chapters = State().open_chapters;
    const bool had_goal = State().goal_open;
    const std::string had_session = State().session;

    std::vector<PendingEvent> events;
    if (g_bridge.Poll(State(), events)) {
        AnnounceArrivals(had_session, had_items, had_chapters, had_goal);

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

void AnnounceArrivals(const std::string& had_session,
                      const std::set<std::string>& had_items,
                      const std::set<std::string>& had_chapters,
                      bool had_goal) {
    const Snapshot& now = State();

    // The first snapshot of a session is everything at once: every item the
    // player has been sent all run, every mission opened so far. Announcing that
    // would be a wall of text on every connect and every map load, saying
    // nothing that `ap` does not say better.
    if (had_session.empty() || had_session != now.session) {
        return;
    }

    for (const std::string& item : now.held_items) {
        if (had_items.find(item) == had_items.end()) {
            Notify("Received: " + item);
        }
    }

    for (const std::string& key : now.open_chapters) {
        if (had_chapters.find(key) == had_chapters.end()) {
            const Chapter* chapter = Data().ChapterByKey(key);
            Notify(std::string(chapter ? chapter->name : key) +
                   " unlocked. ap_warp to travel there.");
        }
    }

    if (now.goal_open && !had_goal) {
        const Chapter* goal = Data().ChapterByKey(Data().goal_chapter);
        Notify(std::string(goal ? goal->name : "The finale") +
               " is open. Finish it to win.");
    }
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
        Notify(event.payload);
    }
    // An unknown kind is a delivery from a newer client. ACKed anyway by the
    // caller: holding it would stall the client's whole event window.
}

}  // namespace ap
