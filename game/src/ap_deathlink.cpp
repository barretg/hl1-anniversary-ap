#include "extdll.h"
#include "util.h"
#include "cbase.h"
#include "player.h"

#include "ap_deathlink.h"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "ap_bridge.h"
#include "ap_checkdata.h"
#include "ap_main.h"
#include "ap_state.h"
#include "ap_text.h"

namespace ap {
namespace {

// How much amnesty is left, kept in a file because it has to survive a map
// change and a quickload. Everything else about the game side is stateless; this
// is one of the two exceptions, and it exists because the death message has to
// name the remaining allowance at the instant of the death.
const char* const kAmnestyFile = "/ap_amnesty.txt";

// Who a death is put down to: the protagonist of the game being played. The
// hub, in no game, is Half-Life's.
const char* ProtagonistOf(const std::string& campaign) {
    if (campaign == "opposing_force") {
        return "Shephard";
    }
    if (campaign == "blue_shift") {
        return "Barney";
    }
    return "Freeman";
}

std::string AmnestyPath() {
    char game_dir[260] = {0};
    GET_GAME_DIR(game_dir);
    std::string dir(game_dir);
    if (dir.empty()) {
        dir = "hlap";
    }
    return dir + "/archipelago" + kAmnestyFile;
}

// The countdown, and the setting it was counting down from.
//
// Both, because the client may change the setting mid-run -- `/amnesty 0` is a
// player deciding their deaths should start counting -- and the file alone
// cannot tell "3 left of 4" from "3 left of 3". Without the second number the
// saved countdown simply won over the new setting and went on forgiving deaths
// the player had just asked to have reported.
struct Amnesty {
    int remaining = -1;   // -1: nothing written this run
    int configured = -1;  // -1: written before this field existed
};

Amnesty ReadAmnesty() {
    Amnesty saved;
    std::ifstream file(AmnestyPath().c_str());
    if (!file) {
        return saved;  // never written this run
    }
    std::string text;
    std::getline(file, text);

    const std::vector<std::string> parts = Split(Trim(text), ' ');
    if (!parts.empty()) {
        saved.remaining = static_cast<int>(ParseLong(parts[0], -1));
    }
    if (parts.size() > 1) {
        saved.configured = static_cast<int>(ParseLong(parts[1], -1));
    }
    return saved;
}

void WriteAmnesty(int remaining, int configured) {
    std::ofstream file(AmnestyPath().c_str(), std::ios::out | std::ios::trunc);
    if (file) {
        file << remaining << " " << configured << "\n";
    }
}

// When a death still belongs to a DeathLink we delivered rather than to the
// player. Always set *before* the damage is dealt, because `TakeDamage` raises
// `Killed` inside the same call and a window opened afterwards would open too
// late to matter.
//
// Deliberately in memory and not in the amnesty file: it is worth less than a
// frame of the run, and a map change or a quickload inside it is not a death we
// caused.
float g_immune_until = 0.0f;

bool DeathLinkImmune() {
    return gpGlobals->time < g_immune_until;
}

// When the last `player_loadsaved` fade began, in level time. A revert is one
// event even when the map fires the trigger more than once, and the fade lasts
// seconds during which the player is still alive and still touching whatever
// set it off.
//
// Not reset on a map change and it does not need to be: `gpGlobals->time`
// restarts with the level, so a value carried over from the previous map is
// larger than the new clock and the difference below goes negative, which is
// not inside the window.
float g_reverted_at = -1000.0f;

void ReportDeath(CBasePlayer* player, const std::string& cause);

// What last hurt the player, kept until `Killed` asks. Ongoing damage --
// poison, radiation, a drowning player's air running out -- comes back as the
// player hurting themselves with DMG_GENERIC, and is not allowed to overwrite
// the thing that started it.
struct LastHurt {
    std::string inflictor;
    std::string attacker;
    int damage_type = 0;
    float when = -1000.0f;
};
LastHurt g_last_hurt;

// How long the last hurt still explains a death. Long enough for a poison tick
// to finish what a headcrab started; a map change resets the clock below it.
constexpr float kLastHurtSeconds = 30.0f;

// Classnames whose plain name reads badly or says nothing.
const char* NamedCause(const std::string& classname) {
    static const struct {
        const char* classname;
        const char* text;
    } kNames[] = {
        {"monster_tripmine", "a tripmine"},
        {"monster_satchel", "a satchel charge"},
        {"grenade", "a grenade"},
        {"rpg_rocket", "a rocket"},
        {"hvr_rocket", "a rocket"},
        {"monster_snark", "a snark"},
        {"hornet", "a hornet"},
        {"bolt", "a crossbow bolt"},
        {"garg_stomp", "a gargantua"},
        {"monster_mortar", "a mortar"},
        {"func_tank", "a mounted gun"},
        {"func_tanklaser", "a mounted laser"},
        {"func_tankrocket", "a mounted rocket launcher"},
        {"func_tankmortar", "a mounted mortar"},
    };
    for (const auto& name : kNames) {
        if (classname == name.classname) {
            return name.text;
        }
    }
    return nullptr;
}

// The level itself rather than anything in it: the damage type says more.
bool IsEnvironment(const std::string& classname) {
    return classname.empty() || classname == "player" ||
           classname == "worldspawn" || classname.rfind("trigger_", 0) == 0 ||
           classname.rfind("func_", 0) == 0 || classname.rfind("env_", 0) == 0;
}

const char* DamageTypeCause(int damage_type) {
    if (damage_type & DMG_FALL) return "a fall";
    if (damage_type & (DMG_BLAST | DMG_MORTAR)) return "an explosion";
    if (damage_type & DMG_CRUSH) return "being crushed";
    if (damage_type & DMG_DROWN) return "drowning";
    if (damage_type & DMG_RADIATION) return "radiation";
    if (damage_type & (DMG_ACID | DMG_POISON | DMG_NERVEGAS)) return "toxic waste";
    if (damage_type & (DMG_BURN | DMG_SLOWBURN)) return "fire";
    if (damage_type & (DMG_FREEZE | DMG_SLOWFREEZE)) return "freezing";
    if (damage_type & DMG_SHOCK) return "electricity";
    if (damage_type & DMG_ENERGYBEAM) return "a laser";
    if (damage_type & DMG_SONIC) return "a shockwave";
    if (damage_type & DMG_BULLET) return "gunfire";
    return nullptr;
}

// "monster_alien_grunt" -> "an alien grunt".
std::string PlainCause(const std::string& classname) {
    std::string name = classname;
    for (const char* prefix : {"monster_", "weapon_", "ammo_"}) {
        if (name.rfind(prefix, 0) == 0) {
            name = name.substr(std::strlen(prefix));
            break;
        }
    }
    for (char& c : name) {
        if (c == '_') {
            c = ' ';
        }
    }
    if (name.empty()) {
        return "an unknown fate";
    }
    const bool vowel = std::strchr("aeiou", name[0]) != nullptr;
    return (vowel ? "an " : "a ") + name;
}

// What a death is put down to. The inflictor first, because it is the thing
// that landed: the player's own tripmine is still a tripmine. Then whoever
// owned it, and failing both, what kind of damage it was.
std::string DescribeCause(const std::string& attacker_from_killed) {
    std::string inflictor;
    std::string attacker = attacker_from_killed;
    int damage_type = 0;
    const float since = gpGlobals->time - g_last_hurt.when;
    if (since >= 0.0f && since < kLastHurtSeconds) {
        inflictor = g_last_hurt.inflictor;
        attacker = g_last_hurt.attacker;
        damage_type = g_last_hurt.damage_type;
    }
    g_last_hurt = LastHurt();

    for (const std::string& who : {inflictor, attacker}) {
        if (const char* named = NamedCause(who)) {
            return named;
        }
        if (!IsEnvironment(who)) {
            return PlainCause(who);
        }
    }
    if (const char* typed = DamageTypeCause(damage_type)) {
        return typed;
    }
    return attacker == "player" ? "their own hand" : "the environment";
}

}  // namespace

void OnPlayerDamaged(CBasePlayer* player, entvars_t* inflictor,
                     entvars_t* attacker, int damage_type) {
    if (player == nullptr) {
        return;
    }
    const bool self_tick = damage_type == DMG_GENERIC &&
                           (inflictor == nullptr || inflictor == player->pev) &&
                           (attacker == nullptr || attacker == player->pev);
    const float since = gpGlobals->time - g_last_hurt.when;
    if (self_tick && since >= 0.0f && since < kLastHurtSeconds) {
        return;
    }
    g_last_hurt.inflictor = inflictor ? STRING(inflictor->classname) : "";
    g_last_hurt.attacker = attacker ? STRING(attacker->classname) : "";
    g_last_hurt.damage_type = damage_type;
    g_last_hurt.when = gpGlobals->time;
}

void OnRevertSaved() {
    // Traced, and traced in every branch, because this is the one hook whose
    // failure is invisible: the screen is fading, the engine is about to reload,
    // and nothing else survives to say whether the entity fired at all. A void
    // fall that reported nothing is either a `player_loadsaved` we never saw or
    // one we deliberately dropped, and the trace is what tells those apart.
    Trace("CRevertSaved::Use: ap::OnRevertSaved");

    CBasePlayer* player = Player();
    if (player == nullptr) {
        Trace("  no player");
        return;
    }
    if (!Live()) {
        Trace("  not live; nothing reported");
        return;
    }
    // Already dead means `Killed` has been through here with the real cause.
    if (!player->IsAlive()) {
        Trace("  already dead; Killed reported it");
        return;
    }
    const float since = gpGlobals->time - g_reverted_at;
    if (since >= 0.0f && since < kRevertQuietSeconds) {
        Trace("  same revert as the last one");
        return;
    }
    Trace("  reporting a death");
    g_reverted_at = gpGlobals->time;

    // Deliberately vague, because the entity does not know either: the same
    // entity ends a fall into the void, a scientist dying and a hostage lost.
    // What the multiworld needs is that the run was cut short, not the reason.
    g_last_hurt = LastHurt();
    ReportDeath(player, "a fatal mistake");
}

void OnPlayerKilled(CBasePlayer* player, const std::string& attacker) {
    ReportDeath(player, DescribeCause(attacker));
}

namespace {

void ReportDeath(CBasePlayer* player, const std::string& cause) {
    if (player == nullptr || !Live()) {
        return;
    }

    // A death we dealt out ourselves, delivering somebody else's DeathLink. It
    // is not the player's death: it must not spend their amnesty, and above all
    // it must not be reported, because the client turns a reported death into an
    // outgoing DeathLink and the slot that sent this one would answer it.
    if (DeathLinkImmune()) {
        return;
    }

    // Reported unconditionally, whether or not DeathLink is on. The client
    // decides what becomes of it: deciding here from a cached flag means a stale
    // snapshot silently swallows deaths with nothing in either log to explain it.
    const int configured = State().death_link_amnesty;
    const Amnesty saved = ReadAmnesty();

    // The client's setting is the authority on how large the allowance is, and a
    // change to it takes effect now rather than after the old countdown runs
    // out. `/amnesty 0` is a player asking for their deaths to start counting,
    // and honouring it a few deaths later is the same as ignoring it.
    int remaining = (saved.remaining < 0 || saved.configured != configured)
                        ? configured
                        : saved.remaining;

    bool forgiven = false;
    if (State().death_link && remaining > 0) {
        forgiven = true;
        --remaining;
        char line[96];
        std::snprintf(line, sizeof(line),
                      "Death forgiven. %d more before one goes out.", remaining);
        Notify(line);
    } else if (State().death_link) {
        // The allowance runs again from the top, so a run does not become one
        // long unbroken chain after the first death that gets through.
        remaining = configured;
    }
    WriteAmnesty(remaining, configured);

    // Same reason as the trace in `OnRevertSaved`: a death is followed by a
    // reload, and the console goes with it.
    Trace(forgiven ? "  death forgiven by amnesty" : "  death sent");

    std::vector<std::string> args;
    args.push_back(ProtagonistOf(Data().CampaignOfMap(CurrentMap()).key));
    args.push_back(Sanitise(cause));
    args.push_back(forgiven ? "1" : "0");
    Wire().Send("DEATH", args);
}

}  // namespace

void OnDeathLinkReceived(const std::string& source, const std::string& cause,
                         long stamp) {
    CBasePlayer* player = Player();
    if (player == nullptr) {
        return;
    }

    // Freshness is judged against the client's own clock from the same snapshot,
    // so the two sides never have to agree on a clock. A DeathLink that arrived
    // during a map load is stale and must not kill someone who has just spawned.
    const long now = Wire().Now();
    if (stamp > 0 && now > 0 && now - stamp > kDeathLinkMaxAgeSeconds) {
        return;
    }
    if (!State().death_link) {
        return;
    }
    if (!player->IsAlive()) {
        return;
    }

    // The cause is the sender's whole sentence, slot name included where their
    // game puts one; only a DeathLink without one needs the source spelled out.
    Notify(cause.empty() ? source + " died." : cause);

    // Before the damage, never after: `TakeDamage` raises `CBasePlayer::Killed`
    // inside this call, so a window opened on the next line would open after the
    // thing it exists to catch had already happened.
    g_immune_until = gpGlobals->time + kDeathLinkImmuneSeconds;

    player->TakeDamage(player->pev, player->pev, player->pev->health + 100.0f,
                       DMG_GENERIC | DMG_ALWAYSGIB);
}

}  // namespace ap
