// `!menu`: the warp and the tracker as the engine's own numbered menu, picked
// with the number keys, as the Sven plugin's `!menu` is.
//
// No engine work. The server already registers `ShowMenu`, the stock client
// draws it, and while one is up the number keys go to it and come back as
// `menuselect <n>`. Singleplayer's rules ignore that command, so sdk.patch hands
// it to `MenuSelect` first.
//
// Every choice that does something runs the matching chat command through
// `RunCommand`, so a menu warp is refused exactly where a typed one would be.

#pragma once

#include <string>

class CBasePlayer;

namespace ap {

// Open a page by its action: `main`, or any `verb|arg` the pages use.
void OpenMenu(const std::string& action);

// `menuselect <key>` from the client. True when a menu of ours was open and
// took the key; false leaves the command to whoever else reads it.
bool MenuSelect(CBasePlayer* player, int key);

// A chosen action, run from StartFrame rather than inside the command: it may
// change level or open the next page. See `MenuSelect`.
void RunMenu();

// A new level has no menu up: the client clears its copy on load.
void ResetMenu();

}  // namespace ap
