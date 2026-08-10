"""Bridge protocol tests. These need neither Sven Co-op nor an Archipelago server."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apworld" / "half_life_sven"))

from client.bridge import Bridge, find_store_dir  # noqa: E402


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
