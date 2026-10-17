// Randomized level transitions (see .claude/TRANSITION_RANDO.md, section 5).
//
// A seed pairs every transition with another. A pair that is not the vanilla
// one is rewritten when the trigger spawns: both ends lead to each other
// through a synthetic landmark, `aplm_<hash>`, placed at each end's frame
// origin, with a small `trigger_transition` of the same name so the engine
// carries the player and what stands right at the trigger. The engine's
// translation is then the difference of the two frames; the rotation between
// them is applied on the first frame after arrival, from a stash kept in the
// dll, which outlives the level.
//
// A pair whose two ends are in one map never changes level: touching one end
// moves the player to the other in place.

#pragma once

#include <string>
#include <utility>
#include <vector>

// Include after the SDK's extdll.h, util.h and cbase.h, which have no guards.

class CBaseEntity;
class CBasePlayer;

namespace ap {

struct Snapshot;
struct Transition;

// The pairing, both directions, plus one-way exits (exit, arrival). Replaces
// whatever was set before.
void SetTransitionPairs(
    const std::vector<std::pair<std::string, std::string>>& pairs,
    const std::vector<std::pair<std::string, std::string>>& one_way = {});
// A snapshot's transitions section, applied when it differs from the last.
// A hub seed's snapshot clears a seed's pairing (not a test pair).
// `force` reapplies an unchanged one (after a test pair replaced it).
void ApplySeedTransitions(const Snapshot& state, bool force = false);
// The seed being played is a transitions mode one.
bool TransitionsMode();
// Not part of the seed being played: on a map outside its chapters, or left
// vanilla but leading out of them. Such a trigger is inert.
bool OutsideSeed(const Transition& t);
// A trigger that does nothing in this seed: listed inert, or outside it.
bool Inert(const std::string& id);
// The map a transition leads to in this seed: its seed partner's, else its
// vanilla `to`. Empty for an inert one.
std::string LeadsTo(const Transition& t);
// Leaving through `t` finishes its chapter: the vanilla way forwards out of
// it, wherever it leads in this seed (7.5).
bool CompletesChapter(const Transition& t);
// Rewrite this level's changelevels to the current pairing. Idempotent.
void RewriteLevelTransitions();
// The transition `id` leads to in this seed, or null for none set.
const std::string* SeedPartner(const std::string& id);
// Whether `id` is paired with something other than its vanilla partner.
bool Randomized(const std::string& id);

// This map's transition record for a trigger_changelevel, by its brush centre.
const Transition* TransitionOfTrigger(CBaseEntity* trigger);

// The synthetic landmark both ends of a pair share. Fits the engine's 32.
std::string PairLandmark(const std::string& a, const std::string& b);

// The arrival, once the player is in the new level. StartFrame.
void RunTransitionArrival();
// Warns at the lip of a one-way the player could not come back over. StartFrame.
void RunOneWayLips();
// At ServerActivate: a stash for some other map is stale.
void OnTransitionLevelStart();

// Somewhere `hull` fits, as near `target` as possible: rings outward and
// upward, each spot checked, then settled onto the floor.
bool FindStandSpot(CBasePlayer* player, const Vector& target, Vector& out,
                   int hull = human_hull);

// `ap_transition_pair <a> <b>` / `ap_transition_pair clear`, test build only.
void RegisterTransitionCommands();

}  // namespace ap
