#include "ap_bridge.h"

#include <fstream>
#include <sstream>

#include "ap_text.h"

namespace ap {
namespace {

void CollectStrings(const std::string& value, char delimiter,
                    std::set<std::string>& out) {
    out.clear();
    if (Trim(value).empty()) {
        return;
    }
    for (const std::string& part : Split(value, delimiter)) {
        const std::string item = Trim(part);
        if (!item.empty()) {
            out.insert(item);
        }
    }
}

void CollectIds(const std::string& value, std::set<long>& out) {
    out.clear();
    if (Trim(value).empty()) {
        return;
    }
    for (const std::string& part : Split(value, ',')) {
        const std::string id = Trim(part);
        if (!id.empty()) {
            out.insert(ParseLong(id));
        }
    }
}

void CollectList(const std::string& value, char delimiter,
                 std::vector<std::string>& out) {
    out.clear();
    if (Trim(value).empty()) {
        return;
    }
    for (const std::string& part : Split(value, delimiter)) {
        const std::string item = Trim(part);
        if (!item.empty()) {
            out.push_back(item);
        }
    }
}

// `a,b;c,d`, as the client writes transition pairs.
void CollectPairs(const std::string& value,
                  std::vector<std::pair<std::string, std::string>>& out) {
    out.clear();
    std::vector<std::string> entries;
    CollectList(value, ';', entries);
    for (const std::string& entry : entries) {
        const size_t comma = entry.find(',');
        if (comma == std::string::npos) {
            continue;
        }
        const std::string a = Trim(entry.substr(0, comma));
        const std::string b = Trim(entry.substr(comma + 1));
        if (!a.empty() && !b.empty()) {
            out.push_back({a, b});
        }
    }
}

}  // namespace

void Bridge::Open(const std::string& store) {
    store_ = store;
    in_path_ = store + "/ap_in.txt";
    out_path_ = store + "/ap_out.txt";
    last_text_.clear();
    // Not the session or the high-water mark: a map load is not a new client,
    // and forgetting what we had applied would replay every event in flight.
}

bool Bridge::Poll(Snapshot& out, std::vector<PendingEvent>& events) {
    events.clear();
    if (in_path_.empty()) {
        return false;
    }

    std::ifstream file(in_path_.c_str(), std::ios::in | std::ios::binary);
    if (!file) {
        return false;  // the client has not written one yet
    }

    std::ostringstream buffer;
    buffer << file.rdbuf();
    const std::string text = buffer.str();
    if (text.empty()) {
        return false;  // caught mid-write
    }
    if (text == last_text_) {
        return false;  // nothing has changed; do not reparse or re-ACK
    }

    Snapshot parsed;
    std::vector<PendingEvent> found;
    long now = now_;

    std::istringstream lines(text);
    std::string line;
    while (std::getline(lines, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == '#') {
            continue;
        }

        if (StartsWith(line, "event=")) {
            const std::vector<std::string> f = Split(line.substr(6), '|');
            if (f.size() >= 3) {
                PendingEvent event;
                event.seq = static_cast<int>(ParseLong(f[0]));
                event.kind = f[1];
                event.payload = f[2];
                event.stamp = f.size() >= 4 ? ParseLong(f[3]) : 0;
                found.push_back(event);
            }
            continue;
        }

        const size_t equals = line.find('=');
        if (equals == std::string::npos) {
            continue;
        }
        const std::string key = line.substr(0, equals);
        const std::string value = line.substr(equals + 1);

        if (key == "session") {
            parsed.session = Trim(value);
        } else if (key == "slot") {
            parsed.slot = Trim(value);
        } else if (key == "data_version") {
            parsed.data_version = Trim(value);
        } else if (key == "connected") {
            parsed.connected = ParseBool(value);
        } else if (key == "goal_open") {
            parsed.goal_open = ParseBool(value);
        } else if (key == "viewmodel_hands") {
            parsed.viewmodel_hands = Trim(value);
        } else if (key == "ally_weapon_drops") {
            parsed.ally_weapon_drops = ParseBool(value);
        } else if (key == "butterfingers_reissue") {
            parsed.butterfingers_reissue = ParseBool(value);
        } else if (key == "melee_throw") {
            parsed.melee_throw = ParseBool(value);
        } else if (key == "air_accelerate") {
            parsed.air_accelerate = static_cast<int>(ParseLong(value));
        } else if (key == "death_link") {
            parsed.death_link = ParseBool(value);
        } else if (key == "death_link_amnesty") {
            parsed.death_link_amnesty = static_cast<int>(ParseLong(value));
        } else if (key == "chapters") {
            CollectStrings(value, ',', parsed.open_chapters);
        } else if (key == "excluded") {
            CollectStrings(value, ',', parsed.excluded_chapters);
        } else if (key == "items") {
            CollectStrings(value, ';', parsed.held_items);
        } else if (key == "ungated") {
            CollectStrings(value, ';', parsed.ungated_classnames);
        } else if (key == "starting") {
            CollectList(value, ';', parsed.starting_weapons);
        } else if (key == "checked") {
            CollectIds(value, parsed.checked);
        } else if (key == "missing") {
            CollectIds(value, parsed.missing);
        } else if (key == "progression_mode") {
            parsed.transitions_mode = Trim(value) == "transitions";
        } else if (key == "map_shuffle") {
            parsed.map_shuffle = Trim(value);
        } else if (key == "start_map") {
            parsed.start_map = Trim(value);
        } else if (key == "ending_map") {
            parsed.ending_map = Trim(value);
        } else if (key == "final_boss") {
            parsed.final_boss = Trim(value);
        } else if (key == "transition_hub") {
            parsed.transition_hub = ParseBool(value);
        } else if (key == "transition_chapters") {
            CollectStrings(value, ',', parsed.transition_chapters);
        } else if (key == "boss_maps") {
            CollectStrings(value, ',', parsed.boss_maps);
        } else if (key == "inert_transitions") {
            CollectStrings(value, ';', parsed.inert_transitions);
        } else if (key == "transition_pairs") {
            CollectPairs(value, parsed.transition_pairs);
        } else if (key == "one_way_transitions") {
            CollectPairs(value, parsed.one_way_transitions);
        } else if (key == "backtrack_orbs") {
            CollectPairs(value, parsed.backtrack_orbs);
        } else if (key == "now") {
            now = ParseLong(value);
        }
        // An unknown key is a field from a newer client. Ignored, never refused.
    }

    // A snapshot with no session line is not one: most likely a torn read of a
    // file being replaced. Leave the last good state alone.
    if (parsed.session.empty()) {
        return false;
    }

    if (parsed.session != session_) {
        session_ = parsed.session;
        applied_ = 0;
    }

    // An empty slot is a disconnected client, not a new run, so the last one we
    // were told about stands. Carried into the snapshot rather than left blank
    // so that the poll can diff it the same way it diffs the session.
    if (parsed.slot.empty()) {
        parsed.slot = slot_;
    } else {
        slot_ = parsed.slot;
    }

    last_text_ = text;
    now_ = now;
    out = parsed;

    for (const PendingEvent& event : found) {
        if (event.seq > applied_) {
            events.push_back(event);
        }
    }
    for (const PendingEvent& event : events) {
        if (event.seq > applied_) {
            applied_ = event.seq;
        }
    }

    return true;
}

void Bridge::Send(const std::string& kind, const std::string& arg) {
    std::vector<std::string> args;
    args.push_back(arg);
    Send(kind, args);
}

void Bridge::Send(const std::string& kind, const std::vector<std::string>& args) {
    if (out_path_.empty()) {
        return;
    }
    std::ofstream file(out_path_.c_str(), std::ios::out | std::ios::app);
    if (!file) {
        return;  // the client reopens the log on its side; the next line will do
    }
    file << kind;
    for (const std::string& arg : args) {
        file << '|' << arg;
    }
    file << '\n';
}

void Bridge::Acknowledge(int seq) {
    std::ostringstream text;
    text << seq;
    Send("ACK", text.str());
}

}  // namespace ap
