// The file bridge, game side.
//
//   ap_in.txt   client -> here. A full snapshot, rewritten whenever it changes,
//               with one-shot deliveries riding along as `event=` lines until we
//               ACK them by sequence number.
//   ap_out.txt  here -> client. Append-only, one `KIND|arg|arg` line per event.
//
// Both files live in `<Half-Life>/hlap/archipelago/`. `docs/protocol.md` is the
// contract; this header is only the shape of our half of it.
//
// Nothing here touches the engine, which is deliberate: with `ap_checkdata` it
// is the part of the game side that can be tested without the game.

#pragma once

#include <string>
#include <vector>

namespace ap {

struct Snapshot;  // ap_state.h

// One `event=` line: a delivery the client is waiting for us to acknowledge.
struct PendingEvent {
    int seq = 0;
    std::string kind;     // ITEM, TRAP, DEATHLINK, CHAT
    std::string payload;
    long stamp = 0;       // unix seconds; DeathLink older than 10s is dropped
};

class Bridge {
public:
    // `store` is the archipelago directory inside the mod folder.
    void Open(const std::string& store);

    // Re-read ap_in.txt if it has changed. False if it was unreadable, which is
    // normal and transient: the client rewrites it several times a second and a
    // torn read is fixed by the next poll.
    bool Poll(Snapshot& out, std::vector<PendingEvent>& events);

    // Append one line to ap_out.txt. Never blocks the caller on failure: a
    // check that could not be written is retried on the next poll rather than
    // lost, because the alternative is a check the player made and never got.
    void Send(const std::string& kind, const std::string& arg);

    // Acknowledge a delivery so the client can send the next one in its window.
    void Acknowledge(int seq);

private:
    std::string store_;
    std::string session_;   // changes when the client restarts; resets seq state
    int last_applied_ = 0;
};

}  // namespace ap
