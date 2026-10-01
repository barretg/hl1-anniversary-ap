#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_menu.h"

#include <algorithm>
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

// Keys 1-7 are the page's items, as Sven's `CTextMenu` pages them.
const size_t kItemsPerPage = 7;

// The client keeps at most 512 characters of a menu (`MAX_MENU_STRING`), and a
// user message holds under 192 bytes, so the page goes in pieces of this size.
const size_t kMenuTextMax = 511;
const size_t kChunk = 175;

// A label longer than this is cut, so seven of them and a title fit the 512.
const size_t kLabelMax = 56;

struct Item {
    std::string label;
    std::string action;
    bool done = false;  // drawn grey
};

// The one player's open menu. Closed when `open` is false.
struct Menu {
    bool open = false;
    std::string title;
    std::vector<Item> items;
    size_t page = 0;
};

Menu g_menu;

// A choice waiting for the next frame. See `RunMenu`.
std::string g_pending;

std::string Cut(const std::string& text) {
    return text.size() <= kLabelMax ? text : text.substr(0, kLabelMax - 3) + "...";
}

// `Office Complex: Health Charger 1` reads as `Health Charger 1` under a title
// that already names the mission, as the Sven menu's labels do.
std::string WithoutPrefix(const std::string& name, const std::string& prefix) {
    if (name.size() > prefix.size() && name.compare(0, prefix.size(), prefix) == 0) {
        return name.substr(prefix.size());
    }
    return name;
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

// Draw the current page. Keys: 1-7 its items, 8 back a page, 9 the next, 0 exit
// (sent as `menuselect 10`, which is bit 9).
void Show() {
    const size_t first = g_menu.page * kItemsPerPage;
    const size_t last = std::min(first + kItemsPerPage, g_menu.items.size());
    const bool back = g_menu.page > 0;
    const bool more = last < g_menu.items.size();

    std::string text = "\\y" + g_menu.title + "\\w\n\n";
    int bits = 1 << 9;
    for (size_t i = first; i < last; ++i) {
        const Item& item = g_menu.items[i];
        const int key = static_cast<int>(i - first) + 1;
        bits |= 1 << (key - 1);
        text += (item.done ? "\\d" : "") + std::to_string(key) + ". " + Cut(item.label) +
                (item.done ? "\\w" : "") + "\n";
    }
    text += "\n";
    if (back) {
        bits |= 1 << 7;
        text += "8. Back\n";
    }
    if (more) {
        bits |= 1 << 8;
        text += "9. More\n";
    }
    text += "0. Exit";
    if (text.size() > kMenuTextMax) {
        text.resize(kMenuTextMax);
    }
    Send(bits, text);
}

void Open(const std::string& title, std::vector<Item> items) {
    g_menu = Menu();
    g_menu.open = true;
    g_menu.title = title;
    g_menu.items = std::move(items);
    Show();
}

// The games this seed has a mission in, in data order.
std::vector<std::string> SeedGames() {
    std::vector<std::string> games;
    for (const Chapter& chapter : Data().chapters) {
        if (State().ChapterExcluded(chapter.key)) {
            continue;
        }
        bool seen = false;
        for (const std::string& game : games) {
            seen = seen || game == chapter.campaign;
        }
        if (!seen) {
            games.push_back(chapter.campaign);
        }
    }
    return games;
}

// `!ap`'s status, in the menu's word for it.
std::string MenuStatus(const Chapter& chapter) {
    const std::string status = MissionStatus(chapter);
    if (status == "complete") return "done";
    if (status == "unlocked" || status == "OPEN") return "open";
    return status;
}

// A mission's checks, by map like `!tracker`; a game's weapon checks.
std::vector<const Location*> ChecksOf(const Chapter& chapter) {
    std::vector<const Location*> checks;
    for (const Location& location : Data().locations) {
        const Chapter* owner = Data().ChapterOfMap(location.map);
        if (owner == nullptr || owner->key != chapter.key || IsWeaponCheck(location) ||
            !State().InSeed(location.id)) {
            continue;
        }
        checks.push_back(&location);
    }
    return checks;
}

std::vector<const Location*> WeaponsOf(const std::string& game) {
    std::vector<const Location*> checks;
    for (const Location& location : Data().locations) {
        if (!IsWeaponCheck(location) || !State().InSeed(location.id)) {
            continue;
        }
        const Chapter* chapter = Data().ChapterByKey(location.chapter);
        if (chapter != nullptr && chapter->campaign == game) {
            checks.push_back(&location);
        }
    }
    return checks;
}

int FoundOf(const std::vector<const Location*>& checks) {
    int found = 0;
    for (const Location* location : checks) {
        found += Collected(*location) ? 1 : 0;
    }
    return found;
}

std::string Count(int found, size_t total) {
    return "  " + std::to_string(found) + "/" + std::to_string(total);
}

// Unfound first, then the found ones grey and marked: picking any points at it.
void OpenChecks(const std::string& title, const std::vector<const Location*>& checks,
                const std::string& prefix) {
    std::vector<Item> items;
    for (int pass = 0; pass < 2; ++pass) {
        for (const Location* location : checks) {
            const bool done = Collected(*location);
            if (done != (pass == 1)) {
                continue;
            }
            items.push_back({(done ? "[done] " : "") + WithoutPrefix(location->name, prefix),
                             "find|" + std::to_string(location->id), done});
        }
    }
    Open(title + ": " + std::to_string(FoundOf(checks)) + "/" +
             std::to_string(checks.size()) + " found",
         std::move(items));
}

bool TrackerReady() {
    if (!State().checked.empty() || !State().missing.empty()) {
        return true;
    }
    Notify("No location data yet; check the client.");
    return false;
}

void Main() {
    std::vector<Item> items = {{"Warp to a mission", "warp"},
                               {"Tracker", "track"},
                               {"Nearest check here", "near"}};
    if (!NamedWarps().empty()) {
        items.push_back({"Warp points", "points"});
    }
    items.push_back({"Return to the hub", "hub"});
    Open("Archipelago", std::move(items));
}

void WarpMissions(const std::string& game) {
    std::vector<Item> items;
    for (const Chapter& chapter : Data().chapters) {
        if (chapter.campaign != game || State().ChapterExcluded(chapter.key)) {
            continue;
        }
        items.push_back({std::to_string(MissionNumberInGame(chapter)) + ". " + chapter.name +
                             " [" + MenuStatus(chapter) + "]",
                         "warpm|" + std::to_string(chapter.index)});
    }
    Open("Warp: " + GameName(game), std::move(items));
}

void WarpGames() {
    const std::vector<std::string> games = SeedGames();
    if (games.size() == 1) {
        WarpMissions(games.front());  // one choice is a key press for nothing
        return;
    }
    std::vector<Item> items;
    for (const std::string& game : games) {
        items.push_back({GameName(game), "warpc|" + game});
    }
    Open("Warp: which game?", std::move(items));
}

// A mission: its start, or a part already reached. With nothing but its start
// reached, or the mission shut, that is the warp and no menu.
void WarpParts(int index) {
    const Chapter* chapter = Data().ChapterByIndex(index);
    if (chapter == nullptr) {
        return;
    }
    std::vector<Item> items;
    for (size_t i = 1; i < chapter->maps.size(); ++i) {
        if (Visited(chapter->maps[i])) {
            items.push_back({"Part " + std::to_string(i + 1) + " (" + chapter->maps[i] + ")",
                             "gopart|" + std::to_string(index) + " " +
                                 std::to_string(i + 1)});
        }
    }
    if (items.empty() || !ChapterIsOpen(*chapter)) {
        RunCommand("warp", std::to_string(index));
        return;
    }
    items.insert(items.begin(), {"Start (" + chapter->maps.front() + ")",
                                 "go|" + std::to_string(index)});
    Open(chapter->name, std::move(items));
}

void Points() {
    std::vector<Item> items;
    for (const WarpPoint& point : NamedWarps()) {
        items.push_back({point.label + " (" + point.map + ")", "point|" + point.label});
    }
    if (items.empty()) {
        Notify("No warp points yet. !setwarp <name> makes one where you stand.");
        return;
    }
    Open("Warp points", std::move(items));
}

void TrackMissions(const std::string& game) {
    std::vector<Item> items;
    const std::vector<const Location*> weapons = WeaponsOf(game);
    if (!weapons.empty()) {
        const int found = FoundOf(weapons);
        items.push_back({"Weapons" + Count(found, weapons.size()) +
                             (found == static_cast<int>(weapons.size()) ? " (done)" : ""),
                         "trackw|" + game});
    }
    for (const Chapter& chapter : Data().chapters) {
        if (chapter.campaign != game || State().ChapterExcluded(chapter.key)) {
            continue;
        }
        const std::vector<const Location*> checks = ChecksOf(chapter);
        if (checks.empty()) {
            continue;
        }
        const int found = FoundOf(checks);
        items.push_back({chapter.name + Count(found, checks.size()) +
                             (found == static_cast<int>(checks.size()) ? " (done)" : ""),
                         "trackm|" + std::to_string(chapter.index)});
    }
    Open("Tracker: " + GameName(game), std::move(items));
}

void TrackGames() {
    if (!TrackerReady()) {
        return;
    }
    const std::vector<std::string> games = SeedGames();
    if (games.size() == 1) {
        TrackMissions(games.front());
        return;
    }
    std::vector<Item> items;
    for (const std::string& game : games) {
        int found = 0;
        size_t total = 0;
        for (const Chapter& chapter : Data().chapters) {
            if (chapter.campaign != game || State().ChapterExcluded(chapter.key)) {
                continue;
            }
            const std::vector<const Location*> checks = ChecksOf(chapter);
            found += FoundOf(checks);
            total += checks.size();
        }
        const std::vector<const Location*> weapons = WeaponsOf(game);
        found += FoundOf(weapons);
        total += weapons.size();
        items.push_back({GameName(game) + Count(found, total), "trackc|" + game});
    }
    Open("Tracker: which game?", std::move(items));
}

void TrackMission(int index) {
    const Chapter* chapter = Data().ChapterByIndex(index);
    if (chapter == nullptr) {
        return;
    }
    const std::vector<const Location*> checks = ChecksOf(*chapter);
    if (checks.empty()) {
        Notify("No checks in " + chapter->name + ".");
        return;
    }
    OpenChecks(chapter->name, checks, chapter->name + ": ");
}

void TrackWeapons(const std::string& game) {
    const std::vector<const Location*> checks = WeaponsOf(game);
    if (checks.empty()) {
        Notify("No weapon checks in " + GameName(game) + ".");
        return;
    }
    OpenChecks(GameName(game) + " weapons", checks, GameName(game) + ": ");
}

// Actions are `verb|argument`, as the Sven plugin's `RunMenuAction`.
void Run(const std::string& action) {
    const size_t bar = action.find('|');
    const std::string verb = action.substr(0, bar);
    const std::string arg = bar == std::string::npos ? "" : action.substr(bar + 1);
    const int number = static_cast<int>(ParseLong(arg, -1));

    if (verb == "main") {
        Main();
    } else if (verb == "warp") {
        WarpGames();
    } else if (verb == "warpc") {
        WarpMissions(arg);
    } else if (verb == "warpm") {
        WarpParts(number);
    } else if (verb == "go" || verb == "gopart") {
        RunCommand("warp", arg);  // `<index>` or `<index> <part>`
    } else if (verb == "points") {
        Points();
    } else if (verb == "point") {
        if (!WarpToPoint(arg)) {
            Notify("That warp point is gone.");
        }
    } else if (verb == "track") {
        TrackGames();
    } else if (verb == "trackc") {
        TrackMissions(arg);
    } else if (verb == "trackm") {
        TrackMission(number);
    } else if (verb == "trackw") {
        TrackWeapons(arg);
    } else if (verb == "find") {
        FindById(ParseLong(arg, -1));
    } else if (verb == "near") {
        RunCommand("find", "");
    } else if (verb == "hub") {
        RunCommand("hub", "");
    }
}

}  // namespace

void OpenMenu(const std::string& action) {
    if (!Data().Loaded()) {
        Say("No checkdata.txt, so there is no menu.");
        return;
    }
    Run(action);
}

bool MenuSelect(CBasePlayer* player, int key) {
    if (player == nullptr || !g_menu.open) {
        return false;
    }
    // The client took its menu down when the key was pressed; paging puts the
    // next one up, anything else closes ours to match.
    if (key == 8 && g_menu.page > 0) {
        --g_menu.page;
        Show();
        return true;
    }
    if (key == 9 && (g_menu.page + 1) * kItemsPerPage < g_menu.items.size()) {
        ++g_menu.page;
        Show();
        return true;
    }
    const size_t index = g_menu.page * kItemsPerPage + static_cast<size_t>(key - 1);
    const bool item = key >= 1 && key <= static_cast<int>(kItemsPerPage) &&
                      index < g_menu.items.size();
    // Not run here: inside a client command a level change or the next page's
    // message is the same trouble the Sven plugin deferred its choices for.
    g_pending = item ? g_menu.items[index].action : "";
    g_menu = Menu();
    return true;
}

void RunMenu() {
    if (g_pending.empty()) {
        return;
    }
    const std::string action = g_pending;
    g_pending.clear();
    Run(action);
}

void ResetMenu() {
    g_menu = Menu();
    g_pending.clear();
}

}  // namespace ap
