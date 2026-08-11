"""The file bridge, with no Archipelago dependency.

Keeping this importable on its own is what lets `tests/test_bridge.py` exercise
the whole protocol with no game and no server running.

Directions:
    ap_out.txt  game -> here, append-only. We keep a byte cursor so a restart
                does not replay the log and a partially written final line is
                left for the next poll.
    ap_in.txt   here -> game, a full snapshot rewritten on every change. One-shot
                deliveries ride along as `event=` lines until the game ACKs them.
"""

from __future__ import annotations

import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

CHECKDATA_NAME = "checkdata.txt"
IN_NAME = "ap_in.txt"
OUT_NAME = "ap_out.txt"

# How many un-acked events may sit in the snapshot at once.
#
# Finishing a game releases every remaining item at once, which can be hundreds
# of filler grants. Writing them all into every snapshot means the plugin
# reparses and re-ACKs the whole backlog several times a second, which saturates
# the bridge and starves everything else going through it. The rest wait in a
# backlog and drain a window at a time.
MAX_PENDING_IN_SNAPSHOT = 16

# Kinds that bypass the window entirely. Both are time-sensitive and tiny: the
# plugin discards a DeathLink older than ten seconds, so one stuck behind a
# few hundred filler grants would simply never fire, and chat that arrives
# minutes late is worse than useless.
PRIORITY_KINDS = frozenset({"DEATHLINK", "CHAT"})

# How hard to try the atomic rename before writing in place instead.
REPLACE_ATTEMPTS = 5
REPLACE_RETRY_DELAY = 0.02


@dataclass
class GameEvent:
    """One line the plugin wrote to ap_out.txt."""

    kind: str
    args: list[str]

    @property
    def arg(self) -> str:
        return self.args[0] if self.args else ""


@dataclass
class PendingEvent:
    """A one-shot delivery, held in the snapshot until the game ACKs it."""

    seq: int
    kind: str
    payload: str
    stamp: float = field(default_factory=time.time)

    def render(self) -> str:
        return f"event={self.seq}|{self.kind}|{self.payload}|{self.stamp:.0f}"


class Bridge:
    """Both halves of the file protocol."""

    def __init__(self, store_dir: str | os.PathLike[str]) -> None:
        self.dir = Path(store_dir)
        self.out_path = self.dir / OUT_NAME
        self.in_path = self.dir / IN_NAME

        self._cursor = 0
        self._seq = 0
        # Events currently visible to the game, and the queue waiting behind
        # them. Nothing is ever discarded: the backlog drains a window at a time
        # as the game acknowledges what it has already applied.
        self._pending: dict[int, PendingEvent] = {}
        self._backlog: deque[PendingEvent] = deque()
        self._last_snapshot = ""
        self._last_pending: tuple[int, ...] = ()
        # Identifies this run of the client. Our event sequence restarts from 1
        # on every launch, so the plugin needs to know when that has happened or
        # it would mistake fresh events for ones it had already applied.
        self.session = uuid.uuid4().hex[:8]

    # -- game -> client --------------------------------------------------

    def reset_cursor(self) -> None:
        """Skip whatever is already in the log.

        Called when a session starts so a previous run's events are not replayed
        as if they had just happened.
        """
        self._cursor = self.out_path.stat().st_size if self.out_path.exists() else 0

    def read_events(self) -> list[GameEvent]:
        """Consume new complete lines from ap_out.txt."""
        if not self.out_path.exists():
            return []

        size = self.out_path.stat().st_size
        if size < self._cursor:
            # The file was truncated -- a fresh game session. Start over.
            self._cursor = 0
        if size == self._cursor:
            return []

        with self.out_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._cursor)
            chunk = handle.read()
            # Only advance past data we actually consumed, so a line the plugin
            # is midway through writing is picked up whole on the next poll.
            consumed = chunk.rfind("\n")
            if consumed < 0:
                return []
            self._cursor += len(chunk[: consumed + 1].encode("utf-8"))
            chunk = chunk[: consumed + 1]

        events: list[GameEvent] = []
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            events.append(GameEvent(parts[0], parts[1:]))
        return events

    # -- client -> game --------------------------------------------------

    def queue_event(self, kind: str, payload: str) -> PendingEvent:
        """Queue a one-shot delivery. Never dropped, only metered."""
        self._seq += 1
        event = PendingEvent(self._seq, kind, payload)

        if kind in PRIORITY_KINDS:
            # Straight into the snapshot, over the cap if need be.
            self._pending[event.seq] = event
        else:
            self._backlog.append(event)
            self._fill_window()

        return event

    def acknowledge(self, seq: int) -> None:
        """The game has applied this event; make room for the next one."""
        if self._pending.pop(seq, None) is not None:
            self._fill_window()

    def _fill_window(self) -> None:
        """Promote backlog events into the snapshot, oldest first."""
        while self._backlog and len(self._pending) < MAX_PENDING_IN_SNAPSHOT:
            event = self._backlog.popleft()
            self._pending[event.seq] = event

    @property
    def pending_count(self) -> int:
        """Events visible to the game right now."""
        return len(self._pending)

    @property
    def queued_count(self) -> int:
        """Everything still owed to the game, in flight or waiting."""
        return len(self._pending) + len(self._backlog)

    def write_snapshot(
        self,
        *,
        connected: bool,
        chapters: list[str],
        items: list[str],
        goal_open: bool,
        death_link: bool,
        death_link_amnesty: int = 0,
        data_version: str = "",
        force: bool = False,
    ) -> bool:
        """Rewrite ap_in.txt. Returns True if anything was written.

        Only written when something the game cares about actually changed: the
        state itself, or which events are in flight. Rewriting on every poll
        because `now=` had moved on made the plugin reparse and re-ACK the whole
        pending set several times a second.
        """
        lines = [
            "# Written by the Half-Life (Sven Co-op) Archipelago client.",
            f"session={self.session}",
            # The plugin refuses to send checks if this disagrees with its own
            # copy, since the two would be numbering locations differently.
            f"data_version={data_version}",
            f"connected={1 if connected else 0}",
            f"goal_open={1 if goal_open else 0}",
            f"death_link={1 if death_link else 0}",
            # Counted down by the plugin, not here: the death message has to name
            # the remaining allowance at the moment of the death.
            f"death_link_amnesty={max(0, int(death_link_amnesty))}",
            "chapters=" + ",".join(sorted(chapters)),
            "items=" + ";".join(sorted(items)),
        ]
        body = "\n".join(lines)
        pending = tuple(sorted(self._pending))

        if body == self._last_snapshot and pending == self._last_pending and not force:
            return False

        self._last_snapshot = body
        self._last_pending = pending

        full = [body, f"now={time.time():.0f}"]
        full += [self._pending[seq].render() for seq in pending]

        self.dir.mkdir(parents=True, exist_ok=True)
        self._publish("\n".join(full) + "\n")
        return True

    def _publish(self, text: str) -> None:
        """Write the snapshot without ever leaving a half-written file visible.

        Normally a temp file and a rename. On Windows the rename fails outright
        if the destination is open in another process, and the plugin opens
        ap_in.txt several times a second, so a collision is a matter of when
        rather than if. Retry briefly, then fall back to writing in place: a torn
        read is transient and the plugin re-reads on the next poll, whereas a
        failed write freezes the bridge until the client is restarted.
        """
        temp = self.in_path.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")

        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(temp, self.in_path)
                return
            except PermissionError:
                if attempt < REPLACE_ATTEMPTS - 1:
                    time.sleep(REPLACE_RETRY_DELAY)

        self.in_path.write_text(text, encoding="utf-8")
        temp.unlink(missing_ok=True)

    def clear_log(self) -> None:
        """Truncate ap_out.txt, e.g. when starting a fresh session."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text("", encoding="utf-8")
        self._cursor = 0
        # A leftover .tmp means a previous session died mid-publish. It is not
        # read by anything, but it is the visible symptom of that failure and
        # should not be mistaken for a live file.
        self.in_path.with_suffix(".tmp").unlink(missing_ok=True)


def find_store_dir(game_dir: str | os.PathLike[str]) -> Path:
    """Resolve `<Sven Co-op>/svencoop/scripts/plugins/store/archipelago`.

    Accepts either the Sven Co-op install root or the `svencoop` directory
    itself, since both are reasonable things for someone to point at.
    """
    root = Path(game_dir)
    if (root / "svencoop").is_dir():
        root = root / "svencoop"
    return root / "scripts" / "plugins" / "store" / "archipelago"


def is_game_dir(path: str | os.PathLike[str]) -> bool:
    """Does this look like a Sven Co-op installation?

    Checked against the campaign maps rather than just the folder name, so
    pointing at an empty `Sven Co-op` folder is rejected rather than silently
    producing a bridge nothing will ever read.
    """
    if not path:
        return False
    try:
        root = Path(path)
    except (TypeError, ValueError):
        return False
    if root.name.lower() == "svencoop":
        candidates = [root]
    else:
        candidates = [root / "svencoop", root]
    return any((c / "maps" / "hl_c00.bsp").is_file() for c in candidates)
