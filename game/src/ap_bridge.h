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
// is the part of the game side that can be built and tested without the game.

#pragma once

#include <string>
#include <vector>

#include "ap_state.h"

namespace ap {

// One `event=` line: a delivery the client is waiting for us to acknowledge.
struct PendingEvent {
    int seq = 0;
    std::string kind;     // ITEM, TRAP, DEATHLINK, CHAT
    std::string payload;
    long stamp = 0;       // client's clock; compare against `now` from the same
                          // snapshot rather than against ours
};

class Bridge {
public:
    // `store` is the archipelago directory inside the mod folder.
    void Open(const std::string& store);
    bool IsOpen() const { return !store_.empty(); }

    // Re-read ap_in.txt if it has changed, and return the events in it that we
    // have not applied yet. False when nothing was read: unchanged, missing, or
    // momentarily unreadable while the client rewrites it. All three are normal
    // and the next poll fixes them.
    //
    // `out` is only touched when the file parsed, so a failed read leaves the
    // last good snapshot standing rather than blanking the player's unlocks.
    bool Poll(Snapshot& out, std::vector<PendingEvent>& events);

    // Append one line. Fields are written in order, joined with '|'.
    void Send(const std::string& kind, const std::string& arg);
    void Send(const std::string& kind, const std::vector<std::string>& args);

    // Acknowledge a delivery so the client can send the next one in its window.
    void Acknowledge(int seq);

    // The client's clock at the last snapshot's write, for judging an event's
    // freshness without the two sides agreeing on a clock.
    long Now() const { return now_; }

private:
    std::string store_;
    std::string in_path_;
    std::string out_path_;

    // The snapshot as we last parsed it. Compared by content, never by length:
    // `connected=1` and `connected=0` are the same size, and a length check
    // would freeze us on a stale snapshot with no symptom but things quietly
    // not happening.
    std::string last_text_;

    // The client's event sequence restarts at 1 on every launch, so a change of
    // session resets this. Without that, every event from a restarted client
    // would look already-applied and be ACKed away without running.
    std::string session_;

    // The last slot the client actually named. A disconnected client sends an
    // empty one, which is no news rather than a new run, so it is carried
    // forward into the snapshot instead of blanking what we knew.
    std::string slot_;
    int applied_ = 0;
    long now_ = 0;
};

}  // namespace ap
