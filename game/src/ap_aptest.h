// In-game half of the scenario harness, `tests/aptest/aptest.py`.
//
// The Python script stands in for the client: it writes the snapshot, watches
// the checks the game sends and records verdicts. What it cannot do from
// outside is move the player, so it leaves the scenario's destination in
// `archipelago/aptest_go.txt` and these commands act on it:
//
//   ap_test_go    load the scenario's map and, once the player is in, put
//                 them at its spot
//   ap_test_tp    back to the scenario's spot on this map
//
// Test builds only (`HLAP_TEST_BUILD`); a release dll registers nothing.

#pragma once

namespace ap {

// Once, at GameDLLInit.
void RegisterTestCommands();

// Every frame: finishes a pending `ap_test_go` once the player has spawned.
void RunTestHarness();

}  // namespace ap
