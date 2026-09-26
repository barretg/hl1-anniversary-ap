// Opposing Force and Blue Shift content, seen through one mod folder.
//
// `/install` links each owned game's models, sounds and maps into
// `hlap_downloads` (and `hlap_hd`), which the engine searches above `valve`. A
// file whose path Half-Life (or the other game) also ships would shadow it, so
// the installer puts that one under a campaign directory instead --
// `models/ap_of/scientist.mdl` -- and lists it in `archipelago/content.txt`:
//
//   V|1                                  format
//   C|<campaign>|<game dir>|<prefix>     a mounted campaign
//   M|<campaign>|<map>                   a map that belongs to it
//   R|<campaign>|<path>                  a relocated file, e.g. models/scientist.mdl
//   T|<campaign>|<key>|<new key>         a titles.txt message it defines differently
//   S|<campaign>|<name>|<new name>       likewise a sentence; no new name: silenced
//
// titles.txt and sentences.txt are one file for the whole mod, holding
// Half-Life's text under its own keys and each game's differing text under the
// new ones. On the game's maps, `env_message` keys and played sentences are
// swapped for the game's copy: its credits, and no HEV voice in Blue Shift.
//
// While a map of that campaign is loaded, every model and sound the game asks
// the engine for is looked up here and redirected to the campaign's copy. The
// redirect sits on the engine function table itself, so map-placed entities,
// the SDK's monsters and our own code all go through it without a line of the
// SDK changed. On a Half-Life map, and with no content.txt at all, nothing is
// redirected.

#pragma once

#include <string>

namespace ap {

// Once, from GameDLLInit: wrap the engine's model and sound functions.
void InstallContentHooks();

// From CWorld::Precache, before anything on the map precaches: which campaign
// this map belongs to, and so which copies to use.
void BeginMapContent();

// The campaign of the map being loaded, or "half_life".
const std::string& CurrentCampaign();

// Whether the loaded map belongs to one of these games, for the entity behaviour
// they changed from Half-Life's. False on every Half-Life map.
bool OnOpposingForce();
bool OnBlueShift();

// Whether a map's campaign is mounted, i.e. installed and linked in.
bool IsMountedMap(const std::string& map);

// Whether a campaign ("opposing_force") is mounted. Half-Life always is.
bool IsMountedCampaign(const std::string& campaign);

}  // namespace ap
