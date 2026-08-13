// What the client last told us, and nothing else.
//
// The game side is stateless across map loads and saves on purpose: everything
// here is rebuilt from the next snapshot, so a quickload cannot desync and a
// re-sent check is a no-op on the server.

#pragma once

#include <set>
#include <string>

namespace ap {

struct Snapshot {
    bool connected = false;
    std::string session;        // changes when the client restarts
    std::string data_version;   // ours must match, or ids mean different things

    std::set<std::string> open_chapters;      // missions that may be entered
    std::set<std::string> excluded_chapters;  // not in this seed at all
    std::set<std::string> held_items;         // item names the player has been sent
    std::set<std::string> ungated_classnames; // left entirely to the game
    std::vector<std::string> starting_weapons;

    bool goal_open = false;
    bool death_link = false;
    int death_link_amnesty = 0;

    std::set<long> checked;   // for ap_tracker
    std::set<long> missing;   // ids in neither set are not in this seed

    bool Has(const std::string& item) const;
    bool ChapterOpen(const std::string& key) const;
};

// The live one. Replaced wholesale by each poll rather than merged: a partial
// update is how the two halves come to disagree.
Snapshot& State();

}  // namespace ap
