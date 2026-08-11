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
from dataclasses import dataclass, field
from pathlib import Path

CHECKDATA_NAME = "checkdata.txt"
IN_NAME = "ap_in.txt"
OUT_NAME = "ap_out.txt"


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
        self._pending: dict[int, PendingEvent] = {}
        self._last_snapshot = ""
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
        self._seq += 1
        event = PendingEvent(self._seq, kind, payload)
        self._pending[event.seq] = event
        return event

    def acknowledge(self, seq: int) -> None:
        self._pending.pop(seq, None)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def write_snapshot(
        self,
        *,
        connected: bool,
        chapters: list[str],
        items: list[str],
        goal_open: bool,
        death_link: bool,
        force: bool = False,
    ) -> bool:
        """Rewrite ap_in.txt. Returns True if anything was written.

        Unchanged snapshots are skipped so the plugin's size-based early-out
        stays effective -- but only when nothing is pending, since a pending
        event needs its timestamp refreshed until it is acknowledged.
        """
        lines = [
            "# Written by the Half-Life (Sven Co-op) Archipelago client.",
            f"session={self.session}",
            f"connected={1 if connected else 0}",
            f"goal_open={1 if goal_open else 0}",
            f"death_link={1 if death_link else 0}",
            "chapters=" + ",".join(sorted(chapters)),
            "items=" + ";".join(sorted(items)),
        ]
        body = "\n".join(lines)

        if body == self._last_snapshot and not self._pending and not force:
            return False
        self._last_snapshot = body

        full = [body, f"now={time.time():.0f}"]
        full += [event.render() for event in sorted(self._pending.values(), key=lambda e: e.seq)]

        self.dir.mkdir(parents=True, exist_ok=True)
        # Written via a temp file and replaced, so the plugin never reads a
        # half-written snapshot and mistakes it for a shorter one.
        temp = self.in_path.with_suffix(".tmp")
        temp.write_text("\n".join(full) + "\n", encoding="utf-8")
        os.replace(temp, self.in_path)
        return True

    def clear_log(self) -> None:
        """Truncate ap_out.txt, e.g. when starting a fresh session."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text("", encoding="utf-8")
        self._cursor = 0


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
