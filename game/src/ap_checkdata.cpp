#include "ap_checkdata.h"

#include <cmath>
#include <cstdlib>
#include <fstream>

#include "ap_text.h"

namespace ap {

bool Chapter::HasMap(const std::string& map) const {
    for (const std::string& name : maps) {
        if (name == map) {
            return true;
        }
    }
    return false;
}

bool Chapter::IsLastMap(const std::string& map) const {
    return !maps.empty() && maps.back() == map;
}

static TriggerType TriggerFromName(const std::string& name) {
    if (name == "map_reached") return TriggerType::MapReached;
    if (name == "chapter_complete") return TriggerType::ChapterComplete;
    if (name == "charger") return TriggerType::Charger;
    if (name == "weapon_pickup") return TriggerType::WeaponPickup;
    return TriggerType::Unknown;
}

// A charger's arg is `<classname>@<x y z>`.
static bool ParseChargerArg(const std::string& arg, Location& out) {
    const size_t at = arg.find('@');
    if (at == std::string::npos) {
        return false;
    }
    out.charger_classname = arg.substr(0, at);
    return ParseVector(arg.substr(at + 1), out.at);
}

bool CheckData::Load(const std::string& path) {
    chapters.clear();
    locations.clear();
    gated_classnames.clear();
    starting_weapons.clear();
    format_version = 0;
    data_version.clear();
    goal_chapter.clear();

    std::ifstream file(path.c_str());
    if (!file) {
        return false;
    }

    std::string line;
    while (std::getline(file, line)) {
        line = Trim(line);
        if (line.empty() || line[0] == '#') {
            continue;
        }

        const std::vector<std::string> f = Split(line, '|');
        const std::string& record = f[0];

        if (record == "V" && f.size() >= 2) {
            format_version = static_cast<int>(ParseLong(f[1]));
        } else if (record == "D" && f.size() >= 2) {
            data_version = f[1];
        } else if (record == "G" && f.size() >= 2) {
            goal_chapter = f[1];
        } else if (record == "C" && f.size() >= 6) {
            Chapter chapter;
            chapter.index = static_cast<int>(ParseLong(f[1]));
            chapter.key = f[2];
            chapter.name = f[3];
            chapter.maps = Split(f[4], ',');
            chapter.is_goal = ParseBool(f[5]);
            // Format 2. Absent in an older file, which reads as false and gives
            // the old behaviour of never completing on arrival.
            chapter.complete_on_arrival = f.size() >= 7 && ParseBool(f[6]);
            chapters.push_back(chapter);
        } else if (record == "L" && f.size() >= 6) {
            Location location;
            location.id = ParseLong(f[1]);
            location.map = f[2];
            location.type = TriggerFromName(f[3]);
            location.name = f[5];

            switch (location.type) {
                case TriggerType::ChapterComplete:
                    location.chapter = f[4];
                    break;
                case TriggerType::WeaponPickup:
                    location.classnames = Split(f[4], ',');
                    break;
                case TriggerType::Charger:
                    if (!ParseChargerArg(f[4], location)) {
                        // A charger we cannot place can never be matched, and
                        // pretending otherwise would hide the failure.
                        continue;
                    }
                    break;
                default:
                    break;
            }

            if (f.size() >= 7) {
                location.has_position = ParseVector(f[6], location.position);
            }
            locations.push_back(location);
        } else if (record == "K" && f.size() >= 3) {
            gated_classnames.push_back(std::make_pair(f[1], f[2]));
        } else if (record == "S" && f.size() >= 2) {
            starting_weapons.push_back(f[1]);
        } else if (record == "P" && f.size() >= 3) {
            hub_buttons.push_back(std::make_pair(f[1], f[2]));
        } else if (record == "M" && f.size() >= 8) {
            CarriedMonster monster;
            monster.map = f[1];
            monster.classname = f[2];
            monster.targetname = f[3];
            monster.netname = f[4];
            if (!ParseVector(f[5], monster.origin)) {
                // Nowhere to put it. Placing it at the world origin would be a
                // monster in a wall, so drop the record instead.
                continue;
            }
            monster.angle = static_cast<float>(atof(f[6].c_str()));
            monster.spawnflags = static_cast<int>(ParseLong(f[7]));
            carried_monsters.push_back(monster);
        }
        // Anything else is a record type from a newer generator. Ignored rather
        // than refused: the file is additive by design.
    }

    return Loaded();
}

const Chapter* CheckData::ChapterOfButton(const std::string& targetname) const {
    if (targetname.empty()) {
        return nullptr;  // most of the map: brushes with no name at all
    }
    for (size_t i = 0; i < hub_buttons.size(); ++i) {
        if (hub_buttons[i].first == targetname) {
            return ChapterByKey(hub_buttons[i].second);
        }
    }
    return nullptr;
}

const Chapter* CheckData::ChapterOfMap(const std::string& map) const {
    for (const Chapter& chapter : chapters) {
        if (chapter.HasMap(map)) {
            return &chapter;
        }
    }
    return nullptr;
}

const Chapter* CheckData::ChapterByKey(const std::string& key) const {
    for (const Chapter& chapter : chapters) {
        if (chapter.key == key) {
            return &chapter;
        }
    }
    return nullptr;
}

const Chapter* CheckData::ChapterByIndex(int index) const {
    for (const Chapter& chapter : chapters) {
        if (chapter.index == index) {
            return &chapter;
        }
    }
    return nullptr;
}

namespace {

// Letters and digits only, lowercased. A player typing a mission name is not
// transcribing it: `gonarchs lair` and `Gonarch's Lair` are the same request,
// and so are `weve got hostiles` and `"We've Got Hostiles"`.
std::string Simplify(const std::string& text) {
    std::string out;
    for (char c : text) {
        if (c >= 'A' && c <= 'Z') {
            out.push_back(static_cast<char>(c - 'A' + 'a'));
        } else if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
            out.push_back(c);
        }
    }
    return out;
}

}  // namespace

const Chapter* CheckData::ChapterByName(const std::string& text) const {
    const std::string wanted = Simplify(text);
    if (wanted.empty()) {
        return nullptr;
    }

    // An exact name first, so `Xen` does not resolve to whichever mission merely
    // contains those letters.
    for (const Chapter& chapter : chapters) {
        if (Simplify(chapter.name) == wanted) {
            return &chapter;
        }
    }

    // Then a chapter key or one of its map names, which is what someone reading
    // the console output or the data files will reach for: `c1a0c`, `c2a5`.
    for (const Chapter& chapter : chapters) {
        if (Simplify(chapter.key) == wanted) {
            return &chapter;
        }
        for (const std::string& map : chapter.maps) {
            if (Simplify(map) == wanted) {
                return &chapter;
            }
        }
    }

    // Finally anything containing what was typed, so `surface` and `gonarch`
    // work. First match in campaign order wins.
    for (const Chapter& chapter : chapters) {
        if (Simplify(chapter.name).find(wanted) != std::string::npos) {
            return &chapter;
        }
    }
    return nullptr;
}

const Location* CheckData::LocationById(long id) const {
    for (const Location& location : locations) {
        if (location.id == id) {
            return &location;
        }
    }
    return nullptr;
}

const Location* CheckData::ChargerAt(const std::string& map,
                                     const std::string& classname,
                                     const float at[3]) const {
    const Location* best = nullptr;
    float best_distance = kChargerMatchRadius;

    for (const Location& location : locations) {
        if (location.type != TriggerType::Charger) continue;
        if (location.map != map) continue;
        if (location.charger_classname != classname) continue;

        const float dx = location.at[0] - at[0];
        const float dy = location.at[1] - at[1];
        const float dz = location.at[2] - at[2];
        const float distance = std::sqrt(dx * dx + dy * dy + dz * dz);
        if (distance <= best_distance) {
            best_distance = distance;
            best = &location;
        }
    }

    return best;
}

const Location* CheckData::WeaponPickupFor(const std::string& classname,
                                           const std::string& map) const {
    // The map only has to be *a* campaign map, not the one the location is
    // anchored to.
    //
    // "First Shotgun" is one check for the first shotgun of the run, and the
    // generator anchors it to the earliest map that contains one so the apworld
    // has somewhere to put it in the region graph. Requiring the player to pick
    // up that particular copy is a different and much stricter thing: Office
    // Complex alone has five shotguns across four of its maps, and taking any of
    // the other four meant the check never fired at all. The one in the anchor
    // map is not even the one most players walk into first.
    //
    // Widening this cannot make a check available earlier than the anchor,
    // because the anchor *is* the earliest map in campaign order that has one --
    // so nothing comes into reach that logic did not already allow.
    if (ChapterOfMap(map) == nullptr) {
        return nullptr;  // the hub or the hazard course: finding one here is not
                         // finding it in the campaign
    }

    for (const Location& location : locations) {
        if (location.type != TriggerType::WeaponPickup) continue;
        for (const std::string& name : location.classnames) {
            if (name == classname) {
                return &location;
            }
        }
    }
    return nullptr;
}

std::string CheckData::ItemGating(const std::string& classname) const {
    for (const auto& entry : gated_classnames) {
        if (entry.first == classname) {
            return entry.second;
        }
    }
    return std::string();
}

std::vector<std::string> CheckData::ClassnamesFor(const std::string& item_name) const {
    std::vector<std::string> found;
    for (const auto& entry : gated_classnames) {
        if (entry.second == item_name) {
            found.push_back(entry.first);
        }
    }
    return found;
}

}  // namespace ap
