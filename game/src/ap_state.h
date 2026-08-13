// What the client last told us, and nothing else.
//
// The game side is stateless across map loads and saves on purpose: everything
// here is rebuilt from the next snapshot, so a quickload cannot desync and a
// re-sent check is a no-op on the server.

#pragma once

#include <set>
#include <string>
#include <vector>

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

    bool Has(const std::string& item) const {
        return held_items.find(item) != held_items.end();
    }
    bool ChapterOpen(const std::string& key) const {
        return open_chapters.find(key) != open_chapters.end();
    }
    bool ChapterExcluded(const std::string& key) const {
        return excluded_chapters.find(key) != excluded_chapters.end();
    }
    bool Ungated(const std::string& classname) const {
        return ungated_classnames.find(classname) != ungated_classnames.end();
    }
    // A location the seed does not contain at all: dropped by chargesanity or by
    // an excluded mission. Before the first snapshot both sets are empty, which
    // is not the same answer, so that reads as "in the seed" rather than as
    // "nothing is".
    bool InSeed(long id) const {
        if (checked.empty() && missing.empty()) {
            return true;
        }
        return checked.find(id) != checked.end() || missing.find(id) != missing.end();
    }
};

// The live one. Replaced wholesale by each poll rather than merged: a partial
// update is how the two halves come to disagree.
Snapshot& State();

}  // namespace ap
