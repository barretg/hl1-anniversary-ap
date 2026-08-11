"""Bridge protocol tests. These need neither Sven Co-op nor an Archipelago server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apworld" / "half_life_sven"))

from client.bridge import (  # noqa: E402
    MAX_PENDING_IN_SNAPSHOT,
    Bridge,
    find_store_dir,
    is_game_dir,
)


@pytest.fixture
def bridge(tmp_path: Path) -> Bridge:
    return Bridge(tmp_path)


def snapshot(bridge: Bridge, **overrides) -> bool:
    kwargs = dict(
        connected=True,
        chapters=["office_complex"],
        items=["Shotgun"],
        goal_open=False,
        death_link=False,
    )
    kwargs.update(overrides)
    return bridge.write_snapshot(**kwargs)


def test_reads_complete_lines_only(bridge: Bridge) -> None:
    bridge.out_path.write_text("CHECK|7720001\nCHECK|7720002\nCHECK|772", encoding="utf-8")

    events = bridge.read_events()

    assert [e.kind for e in events] == ["CHECK", "CHECK"]
    assert [e.arg for e in events] == ["7720001", "7720002"]

    # The truncated third line is picked up once the plugin finishes writing it.
    with bridge.out_path.open("a", encoding="utf-8") as handle:
        handle.write("0003\n")
    assert [e.arg for e in bridge.read_events()] == ["7720003"]


def test_cursor_survives_repeated_polls(bridge: Bridge) -> None:
    bridge.out_path.write_text("CHECK|1\n", encoding="utf-8")
    assert len(bridge.read_events()) == 1
    assert bridge.read_events() == []


def test_truncated_log_restarts_the_cursor(bridge: Bridge) -> None:
    """A fresh game session truncates ap_out.txt; we must not skip its events."""
    bridge.out_path.write_text("CHECK|1\nCHECK|2\nCHECK|3\n", encoding="utf-8")
    bridge.read_events()

    bridge.out_path.write_text("CHECK|9\n", encoding="utf-8")
    assert [e.arg for e in bridge.read_events()] == ["9"]


def test_reset_cursor_skips_existing_log(bridge: Bridge) -> None:
    bridge.out_path.write_text("CHECK|1\n", encoding="utf-8")
    bridge.reset_cursor()
    assert bridge.read_events() == []


def test_snapshot_is_skipped_when_unchanged(bridge: Bridge) -> None:
    assert snapshot(bridge) is True
    assert snapshot(bridge) is False
    assert snapshot(bridge, items=["Shotgun", "RPG"]) is True


def test_snapshot_contents(bridge: Bridge) -> None:
    snapshot(bridge, chapters=["blast_pit", "office_complex"], items=["RPG", "Shotgun"])
    text = bridge.in_path.read_text(encoding="utf-8")

    assert "connected=1" in text
    assert "goal_open=0" in text
    assert "chapters=blast_pit,office_complex" in text
    # Item names are semicolon separated because names may contain commas.
    assert "items=RPG;Shotgun" in text
    assert "now=" in text


def test_snapshot_carries_a_session_id(bridge: Bridge) -> None:
    snapshot(bridge)
    assert f"session={bridge.session}" in bridge.in_path.read_text(encoding="utf-8")


def test_sessions_differ_between_client_runs(tmp_path: Path) -> None:
    """The plugin keys its event high-water mark on this."""
    assert Bridge(tmp_path).session != Bridge(tmp_path).session


def test_equal_length_changes_are_still_written(bridge: Bridge) -> None:
    """A flag flip does not change the snapshot's length.

    The plugin used to compare file size and would freeze on a stale snapshot,
    so this asserts the two states are genuinely distinguishable by content.
    """
    snapshot(bridge, connected=True)
    first = bridge.in_path.read_text(encoding="utf-8")

    assert snapshot(bridge, connected=False) is True
    second = bridge.in_path.read_text(encoding="utf-8")

    assert "connected=1" in first
    assert "connected=0" in second
    assert first != second


def test_pending_event_survives_until_acknowledged(bridge: Bridge) -> None:
    event = bridge.queue_event("ITEM", "Ammo Cache")
    snapshot(bridge)

    assert f"event={event.seq}|ITEM|Ammo Cache|" in bridge.in_path.read_text(encoding="utf-8")

    # Still there while unacknowledged, even though nothing else changed.
    snapshot(bridge)
    assert "event=" in bridge.in_path.read_text(encoding="utf-8")

    bridge.acknowledge(event.seq)
    assert bridge.pending_count == 0
    snapshot(bridge, force=True)
    assert "event=" not in bridge.in_path.read_text(encoding="utf-8")


def pending_lines(bridge: Bridge) -> list[str]:
    return [
        line for line in bridge.in_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("event=")
    ]


def test_snapshot_is_not_rewritten_while_pending_is_unchanged(bridge: Bridge) -> None:
    """The write amplifier: rewriting every poll made the plugin re-ACK the lot."""
    bridge.queue_event("ITEM", "Ammo Cache")
    assert snapshot(bridge) is True
    assert snapshot(bridge) is False
    assert snapshot(bridge) is False


def test_snapshot_is_rewritten_when_pending_changes(bridge: Bridge) -> None:
    first = bridge.queue_event("ITEM", "Ammo Cache")
    snapshot(bridge)

    bridge.acknowledge(first.seq)
    assert snapshot(bridge) is True


def test_flood_is_windowed_not_dropped(bridge: Bridge) -> None:
    for index in range(300):
        bridge.queue_event("ITEM", f"Item {index}")

    assert bridge.queued_count == 300
    assert bridge.pending_count == MAX_PENDING_IN_SNAPSHOT

    snapshot(bridge)
    assert len(pending_lines(bridge)) == MAX_PENDING_IN_SNAPSHOT


def test_flood_drains_completely(bridge: Bridge) -> None:
    """Every queued item must eventually reach the game."""
    total = 300
    for index in range(total):
        bridge.queue_event("ITEM", f"Item {index}")

    delivered: list[int] = []
    for _ in range(total * 2):  # generous bound; must finish well inside it
        if bridge.queued_count == 0:
            break
        for seq in list(bridge._pending):
            delivered.append(seq)
            bridge.acknowledge(seq)

    assert bridge.queued_count == 0
    assert len(delivered) == total
    assert delivered == sorted(delivered)  # oldest first, in order


def test_acknowledging_refills_the_window(bridge: Bridge) -> None:
    for index in range(MAX_PENDING_IN_SNAPSHOT + 5):
        bridge.queue_event("ITEM", f"Item {index}")

    first = min(bridge._pending)
    bridge.acknowledge(first)

    assert bridge.pending_count == MAX_PENDING_IN_SNAPSHOT


def test_deathlink_skips_the_queue(bridge: Bridge) -> None:
    """A DeathLink stuck behind a flood would go stale and never fire."""
    for index in range(300):
        bridge.queue_event("ITEM", f"Item {index}")

    death = bridge.queue_event("DEATHLINK", "PlayerOne~a gargantua")
    snapshot(bridge)

    assert any(f"event={death.seq}|DEATHLINK" in line for line in pending_lines(bridge))


def test_chat_skips_the_queue(bridge: Bridge) -> None:
    for index in range(300):
        bridge.queue_event("ITEM", f"Item {index}")

    chat = bridge.queue_event("CHAT", "[AP] hello")
    snapshot(bridge)

    assert any(f"event={chat.seq}|CHAT" in line for line in pending_lines(bridge))


def test_event_sequence_numbers_are_monotonic(bridge: Bridge) -> None:
    first = bridge.queue_event("ITEM", "Medkit")
    second = bridge.queue_event("DEATHLINK", "someone~a headcrab")
    assert second.seq > first.seq

    bridge.acknowledge(first.seq)
    third = bridge.queue_event("ITEM", "Armor Battery")
    assert third.seq > second.seq


def test_deathlink_payload_avoids_the_field_separator(bridge: Bridge) -> None:
    """The plugin splits an event line on '|', so payload fields use '~'."""
    bridge.queue_event("DEATHLINK", "PlayerOne~a gargantua")
    snapshot(bridge)

    line = next(
        l for l in bridge.in_path.read_text(encoding="utf-8").splitlines()
        if l.startswith("event=")
    )
    assert line.count("|") == 3
    assert "PlayerOne~a gargantua" in line


def test_snapshot_write_is_atomic(bridge: Bridge) -> None:
    snapshot(bridge)
    assert not list(bridge.dir.glob("*.tmp"))


def test_snapshot_survives_a_locked_destination(bridge: Bridge, monkeypatch) -> None:
    """Windows refuses os.replace while the plugin has ap_in.txt open.

    Letting that propagate killed the client's watcher task, which then sat
    there looking connected while delivering nothing.
    """
    def always_locked(src, dst):
        raise PermissionError(32, "in use by another process")

    monkeypatch.setattr("client.bridge.os.replace", always_locked)
    monkeypatch.setattr("client.bridge.REPLACE_RETRY_DELAY", 0)

    snapshot(bridge, items=["Shotgun"])

    assert "items=Shotgun" in bridge.in_path.read_text(encoding="utf-8")
    assert not list(bridge.dir.glob("*.tmp"))


def test_snapshot_retries_before_falling_back(bridge: Bridge, monkeypatch) -> None:
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(32, "in use by another process")
        return real_replace(src, dst)

    monkeypatch.setattr("client.bridge.os.replace", flaky)
    monkeypatch.setattr("client.bridge.REPLACE_RETRY_DELAY", 0)

    snapshot(bridge)

    assert calls["n"] == 3
    assert not list(bridge.dir.glob("*.tmp"))


def test_clear_log_removes_a_stale_temp(bridge: Bridge) -> None:
    """A leftover .tmp is the visible symptom of a previous crashed publish."""
    stale = bridge.in_path.with_suffix(".tmp")
    stale.write_text("half written", encoding="utf-8")

    bridge.clear_log()

    assert not stale.exists()


def test_clear_log_resets_cursor(bridge: Bridge) -> None:
    bridge.out_path.write_text("CHECK|1\n", encoding="utf-8")
    bridge.read_events()
    bridge.clear_log()
    bridge.out_path.write_text("CHECK|2\n", encoding="utf-8")
    assert [e.arg for e in bridge.read_events()] == ["2"]


@pytest.mark.parametrize("suffix", ["", "svencoop"])
def test_find_store_dir_accepts_root_or_svencoop(tmp_path: Path, suffix: str) -> None:
    (tmp_path / "svencoop").mkdir()
    target = tmp_path / suffix if suffix else tmp_path

    result = find_store_dir(target)

    assert result.parts[-4:] == ("scripts", "plugins", "store", "archipelago")
    assert "svencoop" in result.parts


def make_install(root: Path) -> Path:
    maps = root / "svencoop" / "maps"
    maps.mkdir(parents=True)
    (maps / "hl_c00.bsp").write_bytes(b"")
    return root


def test_is_game_dir_accepts_install_root(tmp_path: Path) -> None:
    assert is_game_dir(make_install(tmp_path))


def test_is_game_dir_accepts_the_svencoop_folder(tmp_path: Path) -> None:
    assert is_game_dir(make_install(tmp_path) / "svencoop")


def test_is_game_dir_rejects_an_empty_lookalike(tmp_path: Path) -> None:
    """A folder named right but without the campaign maps is not an install."""
    (tmp_path / "svencoop").mkdir()
    assert not is_game_dir(tmp_path)


@pytest.mark.parametrize("value", ["", None])
def test_is_game_dir_rejects_empty_input(value) -> None:
    assert not is_game_dir(value)


def test_is_game_dir_rejects_unrelated_folder(tmp_path: Path) -> None:
    assert not is_game_dir(tmp_path)
