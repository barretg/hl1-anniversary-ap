#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_menu.h"

#include <algorithm>
#include <functional>
#include <string>
#include <vector>

#include "ap_checkdata.h"
#include "ap_hub.h"
#include "ap_locations.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"
#include "ap_warpsave.h"

// Registered in player.cpp and declared in no header.
extern int gmsgShowMenu;

namespace ap {
namespace {

// Keys 1-7 are the page's entries, 8 back, 9 more, 0 exit: the Half-Life 2
// game's `!menu`, page for page.
const int kItemsPerPage = 7;

// The client keeps at most 512 characters of a menu (`MAX_MENU_STRING`), and a
// user message holds under 192 bytes, so the page goes in pieces of this size.
const size_t kMenuTextMax = 511;
const size_t kChunk = 175;

// A label longer than this is cut, so seven of them and a title fit the 512.
const size_t kLabelMax = 56;

struct Entry {
    std::string label;
    std::function<void()> act;
    bool done = false;  // drawn grey
};

enum class Page {
    kNone, kMain,
    kWarpGames,       // which game, when the seed has more than one
    kWarpMissions,    // a game's open missions
    kParts,           // a mission's start and the parts reached
    kWarpPoints,
    kTracker,         // the tracked mission: its parts, its game's weapons
    kTrackGames,      // which game, to track a mission in it
    kTrackMissions,   // a game's missions, to track one
    kTrackChecks,     // one part's checks, or a game's weapons
};

Page g_page = Page::kNone;
int g_first = 0;              // index of the first entry shown
std::string g_game;           // the game kWarpMissions / kTrackMissions list
int g_parts_of = -1;          // the mission kParts lists, by index
// What kTrackChecks lists: a part of the tracked mission (1-based), or 0 for
// the weapons of its game.
int g_track_part = 0;
// The key of the mission the tracker shows; empty follows wherever the player
// is. A key, not a pointer, like the Half-Life 2 game's.
std::string g_tracked;

std::string g_header;
std::vector<Entry> g_entries;

// A key waiting for the next frame. See `MenuSelect`.
int g_selected = 0;

void Open(Page page, int first = 0);

std::string Cut(const std::string& text) {
    return text.size() <= kLabelMax ? text : text.substr(0, kLabelMax - 3) + "...";
}

// "Health Charger 1 (Part 2)" rather than "Office Complex: Health Charger 1
// (Part 2)": the page's title already names the mission or the game.
std::string ShortName(const std::string& name) {
    const size_t colon = name.find(": ");
    return colon == std::string::npos ? name : name.substr(colon + 2);
}

std::string GameName(const std::string& key) {
    const Campaign* campaign = Data().CampaignByKey(key);
    return campaign != nullptr ? campaign->name : key;
}

void Send(int bits, const std::string& text) {
    CBasePlayer* player = Player();
    if (player == nullptr || !ClientReady() || gmsgShowMenu == 0) {
        return;
    }
    size_t at = 0;
    do {
        const std::string chunk = text.substr(at, kChunk);
        at += chunk.size();
        MESSAGE_BEGIN(MSG_ONE, gmsgShowMenu, NULL, player->pev);
        WRITE_SHORT(bits);
        WRITE_CHAR(-1);  // up until something is chosen
        WRITE_BYTE(at < text.size() ? 1 : 0);
        WRITE_STRING(chunk.c_str());
        MESSAGE_END();
    } while (at < text.size());
}

void Show() {
    std::string text = "\\y" + g_header + "\\w\n\n";
    int bits = 1 << 9;  // 0, exit
    const int count = static_cast<int>(g_entries.size());
    for (int i = 0; i < kItemsPerPage && g_first + i < count; ++i) {
        const Entry& entry = g_entries[g_first + i];
        bits |= 1 << i;
        text += (entry.done ? "\\d" : "") + std::to_string(i + 1) + ". " + Cut(entry.label) +
                (entry.done ? "\\w" : "") + "\n";
    }
    text += "\n";
    if (g_first > 0 || g_page != Page::kMain) {
        bits |= 1 << 7;
        text += "8. Back\n";
    }
    if (g_first + kItemsPerPage < count) {
        bits |= 1 << 8;
        text += "9. More\n";
    }
    text += "0. Exit";
    if (text.size() > kMenuTextMax) {
        text.resize(kMenuTextMax);
    }
    Send(bits, text);
}

void Close() {
    g_page = Page::kNone;
    Send(0, "");
}

// The games this seed has a mission in, in data order.
std::vector<std::string> SeedGames() {
    std::vector<std::string> games;
    for (const Chapter& chapter : Data().chapters) {
        if (!State().ChapterExcluded(chapter.key) &&
            std::find(games.begin(), games.end(), chapter.campaign) == games.end()) {
            games.push_back(chapter.campaign);
        }
    }
    return games;
}

// One part's checks, weapons apart: they belong to the game, not the map.
std::vector<const Location*> PartChecks(const Chapter& chapter, int part) {
    std::vector<const Location*> checks;
    for (const Location& location : Data().locations) {
        if (location.map == chapter.maps[part - 1] && !IsWeaponCheck(location) &&
            State().InSeed(location.id)) {
            checks.push_back(&location);
        }
    }
    return checks;
}

std::vector<const Location*> MissionChecks(const Chapter& chapter) {
    std::vector<const Location*> checks;
    for (size_t part = 1; part <= chapter.maps.size(); ++part) {
        for (const Location* location : PartChecks(chapter, static_cast<int>(part))) {
            checks.push_back(location);
        }
    }
    return checks;
}

std::vector<const Location*> WeaponChecks(const std::string& game) {
    std::vector<const Location*> checks;
    for (const Location& location : Data().locations) {
        // By its map: a weapon check names no mission of its own.
        if (IsWeaponCheck(location) && State().InSeed(location.id) &&
            Data().CampaignOfMap(location.map).key == game) {
            checks.push_back(&location);
        }
    }
    return checks;
}

std::string Count(const std::vector<const Location*>& checks) {
    int found = 0;
    for (const Location* location : checks) {
        found += Collected(*location) ? 1 : 0;
    }
    return std::to_string(found) + "/" + std::to_string(checks.size());
}

bool TrackerReady() {
    if (!State().checked.empty() || !State().missing.empty()) {
        return true;
    }
    Notify("No location data yet; check the client.");
    return false;
}

const Chapter* TrackedChapter() {
    const Chapter* tracked = g_tracked.empty() ? nullptr : Data().ChapterByKey(g_tracked);
    return tracked != nullptr ? tracked : Data().ChapterOfMap(CurrentMap());
}

// Part 1 always; a later part once the run has walked into it.
bool PartReached(const Chapter& chapter, int part) {
    return part == 1 || Visited(chapter.maps[part - 1]);
}

void Build(Page page) {
    g_entries.clear();
    switch (page) {
        case Page::kMain:
            g_header = "Archipelago";
            g_entries.push_back({"Warp to a mission", [] {
                                     Open(SeedGames().size() > 1 ? Page::kWarpGames
                                                                 : Page::kWarpMissions);
                                 }});
            g_entries.push_back({"Warp points", [] { Open(Page::kWarpPoints); }});
            g_entries.push_back({"Tracker", [] {
                                     if (TrackerReady()) {
                                         Open(Page::kTracker);
                                     }
                                 }});
            g_entries.push_back({"Find the nearest check", [] { RunCommand("find", ""); }});
            g_entries.push_back({PathTraceActive() ? "Stop tracing" : "Trace to the nearest check",
                                 [] { RunCommand("trace", ""); }});
            g_entries.push_back({"Go to the hub", [] { RunCommand("hub", ""); }});
            g_entries.push_back({"Set this part's warp point", [] { RunCommand("setwarp", ""); }});
            break;
        case Page::kWarpGames:
        case Page::kTrackGames: {
            const bool warp = page == Page::kWarpGames;
            g_header = warp ? "Warp to a mission" : "Track a mission";
            for (const std::string& game : SeedGames()) {
                g_entries.push_back({GameName(game), [game, warp] {
                                         g_game = game;
                                         Open(warp ? Page::kWarpMissions : Page::kTrackMissions);
                                     }});
            }
            break;
        }
        case Page::kWarpMissions: {
            const std::vector<std::string> games = SeedGames();
            if (games.size() == 1) {
                g_game = games.front();
            }
            g_header = "Warp to a mission";
            if (games.size() > 1) {
                g_header += ": " + GameName(g_game);
            }
            for (const Chapter& chapter : Data().chapters) {
                if (chapter.campaign != g_game || State().ChapterExcluded(chapter.key) ||
                    !ChapterIsOpen(chapter)) {
                    continue;
                }
                const int index = chapter.index;
                g_entries.push_back({std::to_string(MissionNumberInGame(chapter)) + ". " +
                                         chapter.name + " [" + MissionStatus(chapter) + "]",
                                     [index] {
                                         const Chapter* c = Data().ChapterByIndex(index);
                                         int reached = 0;
                                         for (size_t p = 1; c != nullptr && p <= c->maps.size(); ++p) {
                                             reached += PartReached(*c, static_cast<int>(p)) ? 1 : 0;
                                         }
                                         if (reached <= 1) {
                                             RunCommand("warp", std::to_string(index));
                                         } else {
                                             g_parts_of = index;
                                             Open(Page::kParts);
                                         }
                                     }});
            }
            if (g_entries.empty()) {
                g_header += "\n(nothing open yet)";
            }
            break;
        }
        case Page::kParts: {
            const Chapter* c = Data().ChapterByIndex(g_parts_of);
            if (c == nullptr) {
                break;
            }
            const int index = c->index;
            g_header = c->name;
            g_entries.push_back({"From the start", [index] {
                                     RunCommand("warp", std::to_string(index));
                                 }});
            for (size_t p = 1; p <= c->maps.size(); ++p) {
                const int part = static_cast<int>(p);
                if (!PartReached(*c, part)) {
                    continue;
                }
                g_entries.push_back({"Part " + std::to_string(part) + " (" +
                                         Count(PartChecks(*c, part)) + " found)",
                                     [index, part] {
                                         RunCommand("warp", std::to_string(index) + " " +
                                                                std::to_string(part));
                                     }});
            }
            break;
        }
        case Page::kWarpPoints:
            g_header = "Warp points";
            for (const WarpPoint& point : NamedWarps()) {
                const Chapter* chapter = Data().ChapterOfMap(point.map);
                const std::string label = point.label;
                g_entries.push_back({label + " (" + (chapter ? chapter->name : std::string("Hub")) +
                                         ")",
                                     [label] {
                                         if (!WarpToPoint(label)) {
                                             Notify("That warp point is gone.");
                                         }
                                     }});
            }
            if (g_entries.empty()) {
                g_header += "\n(none yet: !setwarp <name>)";
            }
            break;
        case Page::kTracker: {
            const Chapter* chapter = TrackedChapter();
            if (chapter == nullptr) {
                // The hub: nothing to follow yet.
                Open(SeedGames().size() > 1 ? Page::kTrackGames : Page::kTrackMissions);
                return;
            }
            const std::string here = CurrentMap();
            g_header = "Tracker: " + chapter->name + " [" + MissionStatus(*chapter) + "]";
            for (size_t p = 1; p <= chapter->maps.size(); ++p) {
                const int part = static_cast<int>(p);
                const std::vector<const Location*> checks = PartChecks(*chapter, part);
                if (checks.empty()) {
                    continue;
                }
                g_entries.push_back({"Part " + std::to_string(part) + ": " + Count(checks) +
                                         (chapter->maps[p - 1] == here ? " (here)" : ""),
                                     [part] {
                                         g_track_part = part;
                                         Open(Page::kTrackChecks);
                                     }});
            }
            const std::vector<const Location*> weapons = WeaponChecks(chapter->campaign);
            if (!weapons.empty()) {
                g_entries.push_back({"Weapons: " + Count(weapons), [] {
                                         g_track_part = 0;
                                         Open(Page::kTrackChecks);
                                     }});
            }
            g_entries.push_back({"Track another mission", [] {
                                     Open(SeedGames().size() > 1 ? Page::kTrackGames
                                                                 : Page::kTrackMissions);
                                 }});
            break;
        }
        case Page::kTrackMissions: {
            const std::vector<std::string> games = SeedGames();
            if (games.size() == 1) {
                g_game = games.front();
            }
            g_header = "Track a mission";
            if (games.size() > 1) {
                g_header += ": " + GameName(g_game);
            }
            const Chapter* here = Data().ChapterOfMap(CurrentMap());
            for (const Chapter& chapter : Data().chapters) {
                if (chapter.campaign != g_game || State().ChapterExcluded(chapter.key)) {
                    continue;
                }
                const std::string key = chapter.key;
                g_entries.push_back({chapter.name + ": " + Count(MissionChecks(chapter)) +
                                         (&chapter == here ? " (here)" : ""),
                                     [key] {
                                         g_tracked = key;
                                         Open(Page::kTracker);
                                     }});
            }
            break;
        }
        case Page::kTrackChecks: {
            std::vector<const Location*> checks;
            const Chapter* chapter = TrackedChapter();
            if (g_track_part > 0 && chapter != nullptr) {
                checks = PartChecks(*chapter, g_track_part);
                g_header = chapter->maps.size() > 1
                               ? chapter->name + ", part " + std::to_string(g_track_part)
                               : chapter->name;
            } else {
                const std::string game = chapter != nullptr ? chapter->campaign : g_game;
                checks = WeaponChecks(game);
                g_header = GameName(game) + " weapons";
            }
            g_header += ": " + Count(checks) + " found";
            // Unfound first; each picked says where it is, and traces it here.
            for (int pass = 0; pass < 2; ++pass) {
                for (const Location* location : checks) {
                    const bool done = Collected(*location);
                    if (done != (pass == 1)) {
                        continue;
                    }
                    const long id = location->id;
                    g_entries.push_back({(done ? "[done] " : "") + ShortName(location->name),
                                         [id] { TraceById(id); }, done});
                }
            }
            if (checks.empty()) {
                g_header += "\n(nothing)";
            }
            break;
        }
        case Page::kNone:
            break;
    }
}

void Open(Page page, int first) {
    g_page = page;
    g_first = first;
    Build(page);
    if (g_page == page) {  // Build may have opened another page instead
        Show();
    }
}

void Back() {
    if (g_first > 0) {
        Open(g_page, (std::max)(g_first - kItemsPerPage, 0));
        return;
    }
    const bool several = SeedGames().size() > 1;
    switch (g_page) {
        case Page::kWarpMissions:
            Open(several ? Page::kWarpGames : Page::kMain);
            break;
        case Page::kParts:
            Open(Page::kWarpMissions);
            break;
        case Page::kTrackMissions:
            if (several) {
                Open(Page::kTrackGames);
                break;
            }
            // fall through: one game, so its missions are the first tracker page
        case Page::kTrackGames:
        case Page::kTrackChecks:
            if (TrackedChapter() != nullptr) {
                Open(Page::kTracker);
            } else {
                Open(Page::kMain);
            }
            break;
        case Page::kMain:
        case Page::kNone:
            Close();
            break;
        default:
            Open(Page::kMain);
            break;
    }
}

void Select(int key) {
    if (g_page == Page::kNone) {
        return;
    }
    if (key == 10 || key == 0) {
        Close();
        return;
    }
    if (key == 8) {
        Back();
        return;
    }
    if (key == 9) {
        if (g_first + kItemsPerPage < static_cast<int>(g_entries.size())) {
            Open(g_page, g_first + kItemsPerPage);
        } else {
            Show();
        }
        return;
    }
    const int index = g_first + key - 1;
    if (key < 1 || key > kItemsPerPage || index >= static_cast<int>(g_entries.size())) {
        Show();  // a key with nothing on it: the menu stays
        return;
    }
    std::function<void()> act = g_entries[index].act;
    g_page = Page::kNone;  // the client closed it; an action may open another
    act();
}

}  // namespace

void OpenMenu() {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is no menu.");
        return;
    }
    if (g_page != Page::kNone) {
        Close();  // the bound key toggles it
        return;
    }
    Open(Page::kMain);
}

void TrackMission(const std::string& text) {
    if (const Chapter* chapter = Trim(text).empty() ? nullptr : Data().ChapterByName(text)) {
        g_tracked = chapter->key;
    }
}

bool MenuSelect(CBasePlayer* player, int key) {
    if (player == nullptr || g_page == Page::kNone) {
        return false;
    }
    // Not run here: inside a client command a level change or the next page's
    // message is the same trouble the Sven plugin deferred its choices for.
    g_selected = key;
    return true;
}

void RunMenu() {
    if (g_selected == 0) {
        return;
    }
    const int key = g_selected;
    g_selected = 0;
    Select(key);
}

void ResetMenu() {
    g_page = Page::kNone;
    g_selected = 0;
}

}  // namespace ap
