"""Persistent client settings.

The failure this guards against is the quiet one: the game folder appearing to
save, then the picker reappearing on the next launch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apworld" / "half_life"))

from client import settings  # noqa: E402


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


def test_round_trip(store: Path) -> None:
    settings.set_value("game_dir", r"F:\Games\Half-Life", store)
    assert settings.get("game_dir", path=store) == r"F:\Games\Half-Life"


def test_survives_a_fresh_read(store: Path) -> None:
    """Nothing is cached in memory, so a new session sees the saved value."""
    settings.set_value("game_dir", "/games/half-life", store)
    assert settings.load(store) == {"game_dir": "/games/half-life"}


def test_missing_file_reads_empty(store: Path) -> None:
    assert settings.load(store) == {}
    assert settings.get("game_dir", "fallback", store) == "fallback"


def test_corrupt_file_reads_empty_rather_than_raising(store: Path) -> None:
    store.write_text("{not json", encoding="utf-8")
    assert settings.load(store) == {}


def test_non_dict_file_reads_empty(store: Path) -> None:
    store.write_text("[1, 2, 3]", encoding="utf-8")
    assert settings.load(store) == {}


def test_setting_one_key_preserves_others(store: Path) -> None:
    settings.save({"game_dir": "/a", "other": 1}, store)
    settings.set_value("game_dir", "/b", store)
    assert settings.load(store) == {"game_dir": "/b", "other": 1}


def test_overwrite_replaces_the_value(store: Path) -> None:
    settings.set_value("game_dir", "/first", store)
    settings.set_value("game_dir", "/second", store)
    assert settings.get("game_dir", path=store) == "/second"


def test_write_is_atomic(store: Path) -> None:
    settings.set_value("game_dir", "/games/half-life", store)
    assert not list(store.parent.glob("*.tmp"))


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "deeper" / "settings.json"
    settings.set_value("game_dir", "/games/half-life", nested)
    assert nested.is_file()


def test_save_failure_raises(tmp_path: Path) -> None:
    """The launcher relies on this to warn instead of failing silently."""
    blocked = tmp_path / "settings.json"
    blocked.mkdir()
    with pytest.raises(OSError):
        settings.save({"game_dir": "/x"}, blocked)


def test_settings_path_is_absolute_and_named() -> None:
    path = settings.settings_path()
    assert path.is_absolute()
    assert path.name.endswith(".json")


# -- host.yaml -------------------------------------------------------------


class AttributeGroup:
    """Stands in for `settings.Group`, which is attribute-based, not a mapping."""

    def __init__(self) -> None:
        setattr(self, settings.GAME_FOLDER_KEY, "")

    def __getitem__(self, key):
        raise TypeError("Group is not subscriptable")

    def __setitem__(self, key, value):
        raise TypeError("Group is not subscriptable")


class FakeSettings:
    """Stands in for Archipelago's settings module."""

    group_type = AttributeGroup

    def __init__(self) -> None:
        self.group = self.group_type()
        setattr(self, settings.SETTINGS_KEY, self.group)
        self.saved = 0

    def get_settings(self):
        return self

    def save(self) -> None:
        self.saved += 1

    @property
    def stored(self) -> str:
        try:
            return getattr(self.group, settings.GAME_FOLDER_KEY)
        except AttributeError:
            return self.group[settings.GAME_FOLDER_KEY]


@pytest.fixture
def host_yaml(monkeypatch, tmp_path: Path) -> FakeSettings:
    fake = FakeSettings()
    monkeypatch.setitem(sys.modules, "settings", fake)
    monkeypatch.setattr(settings, "settings_path", lambda: tmp_path / "legacy.json")
    return fake


def test_write_goes_to_host_yaml(host_yaml: FakeSettings) -> None:
    where = settings.write_game_dir("/games/half-life")

    assert host_yaml.stored == "/games/half-life"
    assert host_yaml.saved == 1
    assert "host.yaml" in where


def test_write_survives_a_group_that_is_not_a_mapping(host_yaml: FakeSettings) -> None:
    """`settings.Group` raises on item access; attribute access is the real API."""
    settings.write_game_dir("/games/half-life")

    assert host_yaml.stored == "/games/half-life"
    assert settings.read_game_dir() == "/games/half-life"


def test_read_prefers_host_yaml(host_yaml: FakeSettings) -> None:
    setattr(host_yaml.group, settings.GAME_FOLDER_KEY, "/from/host")
    settings.set_value(settings.GAME_FOLDER_KEY, "/from/json")

    assert settings.read_game_dir() == "/from/host"


def test_read_falls_back_to_legacy_json(host_yaml: FakeSettings) -> None:
    """Paths saved by earlier versions still work."""
    settings.set_value(settings.GAME_FOLDER_KEY, "/from/json")

    assert settings.read_game_dir() == "/from/json"


def test_legacy_path_migrates_into_host_yaml(host_yaml: FakeSettings) -> None:
    settings.set_value(settings.GAME_FOLDER_KEY, "/from/json")
    settings.write_game_dir(settings.read_game_dir())

    assert host_yaml.stored == "/from/json"


def test_written_path_reads_back(host_yaml: FakeSettings) -> None:
    """The launcher checks exactly this before trusting the save."""
    settings.write_game_dir("/games/half-life")
    assert settings.read_game_dir() == "/games/half-life"


def test_read_is_empty_when_nothing_is_stored(host_yaml: FakeSettings) -> None:
    assert settings.read_game_dir() == ""


def test_write_still_works_without_the_settings_module(monkeypatch, tmp_path: Path) -> None:
    """Running the client outside Archipelago must not lose the path."""
    monkeypatch.setitem(sys.modules, "settings", None)
    monkeypatch.setattr(settings, "settings_path", lambda: tmp_path / "legacy.json")

    settings.write_game_dir("/games/half-life")

    assert settings.read_game_dir() == "/games/half-life"
