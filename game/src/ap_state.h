// What the client last told us, and nothing else.
//
// The game side is stateless across map loads and saves on purpose: everything
// here is rebuilt from the next snapshot, so a quickload cannot desync and a
// re-sent check is a no-op on the server.

#pragma once

#include <set>
#include <string>
#include <utility>
#include <vector>

namespace ap {

struct Snapshot {
    bool connected = false;
    std::string session;        // changes when the client restarts
    std::string data_version;   // ours must match, or ids mean different things

    // Which slot of which seed is being played, "<seed>:<slot>". This is what
    // says the run has changed underneath us, and it is a different question
    // from the session above: a client restarted onto the same slot is a blip
    // and must move nobody, while a different slot connected from the client
    // already running changes everything the run is about.
    //
    // Empty while the client is disconnected, which is no news rather than a
    // new slot, so the last one named stands.
    std::string slot;

    std::set<std::string> open_chapters;      // missions that may be entered
    std::set<std::string> excluded_chapters;  // not in this seed at all
    // Complete on the server but never finished on this machine for this slot:
    // collected, released, or played by someone else on it.
    std::set<std::string> remote_complete;
    std::set<std::string> held_items;         // item names the player has been sent
    std::set<std::string> ungated_classnames; // left entirely to the game
    std::vector<std::string> starting_weapons;

    bool goal_open = false;
    bool death_link = false;

    // The campaign key whose viewmodels every map uses (`viewmodel_style`), or
    // empty for each game's own hands.
    std::string viewmodel_hands;
    // An ally's drop counts as a weapon source. Off in every seed that does not
    // ask for it, and in snapshots from clients older than the option.
    bool ally_weapon_drops = false;
    // Butterfingers hands the weapon back after its timer. Off, only once the
    // player has no weapons left. On in snapshots from clients older than the
    // option, which is how those seeds played.
    bool butterfingers_reissue = true;
    // The sv_airaccelerate Progressive Air Acceleration has reached. -1 leaves
    // it to the game: seeds without the option, and older clients.
    int air_accelerate = -1;
    // Melee Throw is in this seed's pool, so a throw before it arrives says
    // why nothing happened. Off from older clients: mouse2 stays silent.
    bool melee_throw = false;
    int death_link_amnesty = 0;

    // Transitions mode (absent from a hub seed's snapshot). Directed entries
    // are (from, to); `transition_pairs` holds each non-vanilla pair once and
    // means both directions.
    bool transitions_mode = false;
    std::string map_shuffle;
    std::string start_map;
    std::string ending_map;
    std::string final_boss;
    bool transition_hub = false;
    std::set<std::string> transition_chapters;
    std::set<std::string> boss_maps;
    std::set<std::string> inert_transitions;
    std::vector<std::pair<std::string, std::string>> transition_pairs;
    std::vector<std::pair<std::string, std::string>> one_way_transitions;
    std::vector<std::pair<std::string, std::string>> backtrack_orbs;
    // Orbs placed in testing, each on its own map. `key` is the transition it
    // belongs to (by id), or `#name` for a pair inside the map. An orange
    // departure ("out") sends the player to its transition's partner in the
    // seed, onto that partner's green arrival ("in") when one is placed; a `#`
    // entrance sends to the exit of the same name on its map.
    struct WorkshopOrb {
        std::string map, key, label;
        std::string after;  // shown once this name has fired on its map
        bool departs = true;  // "out", orange; "in" is a green arrival
        float at[3] = {0, 0, 0};
        float yaw = 0.0f;
    };
    std::vector<WorkshopOrb> orbs;
    std::string orbs_raw;  // as sent, for telling one set from another
    // One-way doors opened from their far side: (map, `*N,x,y,z`), the door's
    // brush model and a spot on its far side. From the near side it opens only
    // once it has been opened in play.
    std::vector<std::pair<std::string, std::string>> door_openers;

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
    bool RemoteComplete(const std::string& key) const {
        return remote_complete.find(key) != remote_complete.end();
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
