// In-game half of the scenario harness, `tests/aptest/aptest.py`.
//
// The Python script stands in for the client: it writes the snapshot, watches
// the checks the game sends and records verdicts. It runs untouched in a
// terminal; the player drives it from here, in chat or the console:
//
//   !pass [note]  !fail <note>  !note <text>   record a verdict, next scenario
//   !next  !prev  !redo  !go <n>               move between scenarios
//   !info  !status  !list [text]               what the harness knows
//   !give <item>  !take <item>                 change what the snapshot holds
//   !tp                                        back to the scenario's spot
//
// (`testing_aptest <verb> ...` in the console.) Every verb but `tp` goes to the
// harness as an `APTEST` line in `ap_out.txt`. The harness answers in
// `aptest_say.txt`, which is shown here, and starts a scenario by rewriting
// `aptest_go.txt`, which loads its map and puts the player at its spot.
//
// Test builds only (`HLAP_TEST_BUILD`); a release dll registers nothing and
// `TestDispatch` declines everything.

#pragma once

#include <string>

namespace ap {

// Once, at GameDLLInit.
void RegisterTestCommands();

// A harness verb typed in chat (`!pass`). False if it is not one, or in a
// release build.
bool TestDispatch(const std::string& name, const std::string& rest);

// Every frame: shows what the harness said, loads a scenario it started, and
// places the player once they have spawned.
void RunTestHarness();

}  // namespace ap
