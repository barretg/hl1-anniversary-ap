#include "extdll.h"
#include "util.h"
#include "cbase.h"

#include "ap_content.h"
#include "ap_main.h"

#include <cctype>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace ap {

namespace {

const char* const kHalfLife = "half_life";

struct Campaign {
    std::string prefix;              // "ap_of"
    std::set<std::string> relocated; // lowercase paths, "sound/..." for sounds
    // Keys this game defines differently from Half-Life, and the name its own
    // copy was merged in under. An empty sentence name means the game silenced it.
    std::unordered_map<std::string, std::string> titles;     // uppercase key
    std::unordered_map<std::string, std::string> sentences;  // uppercase name
    // Sentence redirects by engine index ("!12"), built on first use because
    // indices exist only once the dll has read sentences.txt. -1: silenced.
    std::unordered_map<std::string, std::string> by_index;
    bool indexed = false;
};

std::map<std::string, Campaign> g_campaigns;
std::unordered_map<std::string, std::string> g_map_campaign;
bool g_loaded = false;

std::string g_current = kHalfLife;
const Campaign* g_active = nullptr;  // null unless it relocated any file
Campaign* g_texts = nullptr;         // null unless it renamed any text

const char* const kSilence = "common/null.wav";

// Redirected names, kept for the life of the process. The engine stores the
// pointer it is given for a model name rather than copying it, so each one
// must outlive every map that uses it. Nodes of an unordered_map never move.
std::unordered_map<std::string, std::string> g_interned;

// The engine's own functions, called by the wrappers below.
enginefuncs_t g_real;

std::string Lower(const char* text) {
    std::string out = text ? text : "";
    for (char& c : out) {
        c = c == '\\' ? '/' : static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return out;
}

std::string Upper(const std::string& text) {
    std::string out = text;
    for (char& c : out) {
        c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }
    return out;
}

void Load() {
    if (g_loaded) {
        return;
    }
    g_loaded = true;
    std::ifstream in(StoreDir() + "/content.txt");
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (line.size() < 2 || line[1] != '|') {
            continue;  // comments, blanks, and record kinds newer than us
        }
        std::vector<std::string> f;
        size_t start = 0;
        for (size_t bar; (bar = line.find('|', start)) != std::string::npos; start = bar + 1) {
            f.push_back(line.substr(start, bar - start));
        }
        f.push_back(line.substr(start));
        if (f[0] == "C" && f.size() >= 4) {
            g_campaigns[f[1]].prefix = f[3];
        } else if (f[0] == "M" && f.size() >= 3) {
            g_map_campaign[Lower(f[2].c_str())] = f[1];
        } else if (f[0] == "R" && f.size() >= 3) {
            g_campaigns[f[1]].relocated.insert(Lower(f[2].c_str()));
        } else if (f[0] == "T" && f.size() >= 4) {
            g_campaigns[f[1]].titles[Upper(f[2])] = f[3];
        } else if (f[0] == "S" && f.size() >= 4) {
            g_campaigns[f[1]].sentences[Upper(f[2])] = f[3];
        }
    }
}

// `models/scientist.mdl` -> `models/ap_of/scientist.mdl` if this campaign moved
// it, else the name unchanged. `base` is the directory the engine prefixes
// itself ("sound/" for sounds), which the table includes and the name does not.
// "!HG_ALERT0" or its engine index "!12" -> this game's copy, or silence.
const char* RedirectSentence(const char* name) {
    if (!g_texts || !name || name[0] != '!') {
        return name;
    }
    if (!g_texts->indexed) {
        g_texts->indexed = true;
        for (const auto& [key, renamed] : g_texts->sentences) {
            char from[32], to[32];
            if (SENTENCEG_Lookup(("!" + key).c_str(), from) < 0) {
                continue;
            }
            if (renamed.empty()) {
                g_texts->by_index[from] = kSilence;
            } else if (SENTENCEG_Lookup(("!" + renamed).c_str(), to) >= 0) {
                g_texts->by_index[from] = to;
            }
        }
    }
    const auto indexed = g_texts->by_index.find(name);
    if (indexed != g_texts->by_index.end()) {
        return indexed->second.c_str();
    }
    const auto named = g_texts->sentences.find(Upper(name + 1));
    if (named == g_texts->sentences.end()) {
        return name;
    }
    return named->second.empty() ? kSilence : Intern("!" + named->second);
}

const char* Redirect(const char* name, const char* base) {
    if (!g_active || !name || !*name) {
        return name;
    }
    // A sentence is a name, not a file; a leading `*` marks a streamed sound
    // and is kept in front of the redirected path.
    const char* path = name;
    std::string lead;
    while (*path == '*' || *path == '#') {
        lead += *path++;
    }
    if (*path == '!') {
        return name;
    }
    const std::string key = std::string(base) + Lower(path);
    if (!g_active->relocated.count(key)) {
        return name;
    }
    std::string rel = Lower(path);
    const size_t slash = rel.rfind('/');
    rel.insert(slash == std::string::npos ? 0 : slash + 1, g_active->prefix + "/");
    const std::string redirected = lead + rel;
    auto it = g_interned.try_emplace(redirected, redirected).first;
    return it->second.c_str();
}

int PrecacheModel(char* s) {
    return g_real.pfnPrecacheModel(const_cast<char*>(Redirect(s, "")));
}

int PrecacheSound(char* s) {
    const char* redirected = Redirect(s, "sound/");
    if (redirected != s) {
        // The original too. The engine plays some sounds by name without ever
        // asking the dll -- the player's footsteps, from its own movement code
        // -- and one that was never precached is silent and spams the console.
        // Those fall back to Half-Life's copy, which is the same step.
        g_real.pfnPrecacheSound(s);
    }
    return g_real.pfnPrecacheSound(const_cast<char*>(redirected));
}

void SetModel(edict_t* e, const char* m) {
    g_real.pfnSetModel(e, Redirect(m, ""));
}

int ModelIndex(const char* m) {
    return g_real.pfnModelIndex(Redirect(m, ""));
}

void EmitSound(edict_t* e, int channel, const char* sample, float volume,
               float attenuation, int flags, int pitch) {
    g_real.pfnEmitSound(e, channel, Redirect(RedirectSentence(sample), "sound/"), volume,
                        attenuation, flags, pitch);
}

void EmitAmbientSound(edict_t* e, float* pos, const char* sample, float vol,
                      float attenuation, int flags, int pitch) {
    g_real.pfnEmitAmbientSound(e, pos, Redirect(RedirectSentence(sample), "sound/"), vol,
                               attenuation, flags, pitch);
}

}  // namespace

void InstallContentHooks() {
    static bool installed = false;
    if (installed) {
        return;
    }
    installed = true;
    g_real = g_engfuncs;
    g_engfuncs.pfnPrecacheModel = PrecacheModel;
    g_engfuncs.pfnPrecacheSound = PrecacheSound;
    g_engfuncs.pfnSetModel = SetModel;
    g_engfuncs.pfnModelIndex = ModelIndex;
    g_engfuncs.pfnEmitSound = EmitSound;
    g_engfuncs.pfnEmitAmbientSound = EmitAmbientSound;
}

void BeginMapContent() {
    Load();
    const auto found = g_map_campaign.find(Lower(STRING(gpGlobals->mapname)));
    g_current = found == g_map_campaign.end() ? kHalfLife : found->second;
    const auto campaign = g_campaigns.find(g_current);
    g_active = campaign == g_campaigns.end() || campaign->second.relocated.empty()
        ? nullptr : &campaign->second;
    g_texts = campaign == g_campaigns.end()
        || (campaign->second.titles.empty() && campaign->second.sentences.empty())
        ? nullptr : &campaign->second;
    if (g_texts) {
        g_real.pfnPrecacheSound(const_cast<char*>(kSilence));
    }
}

void RemapSpawn(entvars_t* pev) {
    // env_message shows a titles.txt message by key; the credits and chapter
    // lines are keys Half-Life uses for its own text. At spawn rather than as
    // the key is read, since maps often list `classname` after `message`.
    if (!g_texts || !pev || FStringNull(pev->message)
        || !FClassnameIs(pev, "env_message")) {
        return;
    }
    const auto found = g_texts->titles.find(Upper(STRING(pev->message)));
    if (found != g_texts->titles.end()) {
        pev->message = MAKE_STRING(Intern(found->second));
    }
}

const std::string& CurrentCampaign() {
    return g_current;
}

bool OnOpposingForce() {
    return g_current == "opposing_force";
}

bool OnBlueShift() {
    return g_current == "blue_shift";
}

bool IsMountedMap(const std::string& map) {
    Load();
    return g_map_campaign.count(Lower(map.c_str())) > 0;
}

}  // namespace ap
