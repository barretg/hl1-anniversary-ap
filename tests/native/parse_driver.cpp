// Host build of the engine-free parsers, driven by tests/test_native_parsers.py.
//
//   parse_driver bridge <store dir>      the snapshot's transitions section
//   parse_driver checkdata <file> <id>   the E record count and one record

#include <cstdio>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_checkdata.h"

namespace {

void PrintPairs(const char* key, const std::vector<std::pair<std::string, std::string>>& v) {
    std::printf("%s=", key);
    for (const auto& pair : v) {
        std::printf("%s>%s;", pair.first.c_str(), pair.second.c_str());
    }
    std::printf("\n");
}

}  // namespace

int main(int argc, char** argv) {
    if (argc >= 3 && std::string(argv[1]) == "bridge") {
        ap::Bridge bridge;
        bridge.Open(argv[2]);
        ap::Snapshot s;
        std::vector<ap::PendingEvent> events;
        if (!bridge.Poll(s, events)) {
            std::printf("no snapshot\n");
            return 1;
        }
        std::printf("transitions_mode=%d\n", s.transitions_mode ? 1 : 0);
        std::printf("map_shuffle=%s\nstart_map=%s\nending_map=%s\nfinal_boss=%s\n",
                    s.map_shuffle.c_str(), s.start_map.c_str(), s.ending_map.c_str(),
                    s.final_boss.c_str());
        std::printf("transition_hub=%d\n", s.transition_hub ? 1 : 0);
        std::printf("transition_chapters=%zu\nboss_maps=%zu\ninert=%zu\n",
                    s.transition_chapters.size(), s.boss_maps.size(),
                    s.inert_transitions.size());
        PrintPairs("pairs", s.transition_pairs);
        PrintPairs("one_way", s.one_way_transitions);
        PrintPairs("orbs", s.backtrack_orbs);
        std::printf("chapters=%zu\n", s.open_chapters.size());
        return 0;
    }
    if (argc >= 4 && std::string(argv[1]) == "checkdata") {
        ap::CheckData data;
        if (!data.Load(argv[2])) {
            std::printf("load failed\n");
            return 1;
        }
        std::printf("transitions=%zu\n", data.transitions.size());
        const ap::Transition* t = data.TransitionById(argv[3]);
        if (t == nullptr) {
            std::printf("missing\n");
            return 1;
        }
        std::printf("%s|%s|%s|%s|%s|%s|%d|%.1f|%d\n", t->id.c_str(), t->map.c_str(),
                    t->to.c_str(), t->landmark.c_str(), t->kind.c_str(), t->partner.c_str(),
                    t->two_way ? 1 : 0, t->yaw, t->use_only ? 1 : 0);
        return 0;
    }
    std::fprintf(stderr, "usage: parse_driver bridge <dir> | checkdata <file> <id>\n");
    return 2;
}
