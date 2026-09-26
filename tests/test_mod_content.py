"""Linking Opposing Force and Blue Shift content into the mod's search path.

Synthetic installs only: each test builds a tiny `Half-Life/` with the pieces
it needs.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apworld" / "half_life"))

from mod import content  # noqa: E402


def put(root: Path, rel: str, data: bytes | str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def bsp(swapped: bool) -> bytes:
    entities = b'{\n"classname" "worldspawn"\n}\n\x00'
    planes = b"\x00" * 20
    lumps = [b""] * 15
    lumps[0], lumps[1] = (planes, entities) if swapped else (entities, planes)
    offset, table, body = 4 + 15 * 8, [], b""
    for lump in lumps:
        table += [offset + len(body), len(lump)]
        body += lump
    return struct.pack("<i30i", 30, *table) + body


@pytest.fixture
def game(tmp_path: Path) -> Path:
    root = tmp_path / "Half-Life"
    put(root, "valve/maps/c0a0.bsp", bsp(False))
    put(root, "valve/models/scientist.mdl", "hl scientist")
    put(root, "valve/models/shared.mdl", "same everywhere")
    put(root, "valve/sprites/hud.txt", "hl hud")
    put(root, "valve/titles.txt", "HL1TITLE\n{\nBlack Mesa\n}\n")
    put(root, "valve/sound/sentences.txt", "HG_ALERT0 hgrunt/alert\n")

    put(root, "gearbox/maps/of1a1.bsp", bsp(False))
    put(root, "gearbox/models/scientist.mdl", "of scientist")
    put(root, "gearbox/models/shared.mdl", "same everywhere")
    put(root, "gearbox/models/w_knife.mdl", "knife")
    put(root, "gearbox/sprites/hud.txt", "of hud")
    put(root, "gearbox/OPFOR.WAD", "wad")
    put(root, "gearbox_hd/models/scientist.mdl", "of scientist hd")
    put(root, "gearbox/titles.txt",
        "$position -1 0.6\nHL1TITLE\n{\nnot this\n}\nOF1A1TITLE\n{\nWelcome\n}\n")
    put(root, "gearbox/sound/sentences.txt", "HG_ALERT0 other\nFG_HELLO fgrunt/hi\n")

    put(root, "bshift/maps/ba_tram1.bsp", bsp(True))
    put(root, "bshift/models/scientist.mdl", "hl scientist")
    put(root, "bshift/sound/ambience/only.wav", "bs sound")
    return root


def records(root: Path) -> list[str]:
    return (root / "hlap/archipelago" / content.CONTENT_FILE).read_text().splitlines()


def test_nothing_happens_without_either_game(tmp_path: Path) -> None:
    root = tmp_path / "Half-Life"
    put(root, "valve/maps/c0a0.bsp", bsp(False))
    report = content.install_content(root)
    assert report.mounted == [] and not (root / content.DOWNLOADS_DIR).exists()


def test_a_clashing_file_is_relocated_and_never_shadows_valve(game: Path) -> None:
    report = content.install_content(game)
    assert report.mounted == ["Opposing Force", "Blue Shift"]
    downloads = game / content.DOWNLOADS_DIR
    assert not (downloads / "models/scientist.mdl").exists()
    assert (downloads / "models/ap_of/scientist.mdl").read_text() == "of scientist"
    assert (game / content.HD_DIR / "models/ap_of/scientist.mdl").read_text() == (
        "of scientist hd"
    )
    assert "R|opposing_force|models/scientist.mdl" in records(game)


def test_identical_and_unique_files(game: Path) -> None:
    content.install_content(game)
    downloads = game / content.DOWNLOADS_DIR
    # Byte-identical to valve's: nothing to add.
    assert not (downloads / "models/shared.mdl").exists()
    assert not (downloads / "models/ap_bs/scientist.mdl").exists()
    # Only this game has it: linked straight through, name lowercased.
    assert (downloads / "models/w_knife.mdl").exists()
    assert (downloads / "sound/ambience/only.wav").exists()
    assert (downloads / "opfor.wad").exists()


def test_hud_text_is_not_relocated(game: Path) -> None:
    """The client reads it by a fixed name; only a client dll could use it."""
    content.install_content(game)
    assert not list((game / content.DOWNLOADS_DIR).rglob("hud.txt"))


def test_maps_are_listed_and_blue_shift_headers_put_back(game: Path) -> None:
    content.install_content(game)
    lines = records(game)
    assert "M|opposing_force|of1a1" in lines and "M|blue_shift|ba_tram1" in lines
    converted = game / content.DOWNLOADS_DIR / "maps/ba_tram1.bsp"
    assert not content.is_swapped_bsp(converted)
    assert content.is_swapped_bsp(game / "bshift/maps/ba_tram1.bsp")


def test_text_tables_keep_half_life_and_rename_clashes(game: Path) -> None:
    put(game, "valve/sound/sentences.txt",
        "HG_ALERT0 hgrunt/alert\nHEV_A0 fvox/bell\nHG_ALERT1 hgrunt/go\n")
    put(game, "gearbox/sound/sentences.txt",
        "HG_ALERT0 other\nHG_ALERT1 other\nHEV_A0 common/null\nFG_HELLO fgrunt/hi\n")
    content.install_content(game)
    titles = (game / "hlap/titles.txt").read_text()
    assert "Black Mesa" in titles and "Welcome" in titles
    assert "AP_OF_HL1TITLE\n{\nnot this\n}" in titles
    assert "$position -1 0.6" in titles
    sentences = (game / "hlap/sound/sentences.txt").read_text().splitlines()
    assert "HG_ALERT0 hgrunt/alert" in sentences and "FG_HELLO fgrunt/hi" in sentences
    # One shared copy for the same words; the silenced line adds nothing.
    assert [line for line in sentences if line.startswith("AP_OF_")] == ["AP_OF_AA other"]
    assert {r for r in records(game) if r[0] in "TS"} == {
        "T|opposing_force|HL1TITLE|AP_OF_HL1TITLE",
        "S|opposing_force|HG_ALERT0|AP_OF_AA",
        "S|opposing_force|HG_ALERT1|AP_OF_AA",
        "S|opposing_force|HEV_A0|",
    }


def test_uninstall_removes_exactly_what_was_written(game: Path) -> None:
    put(game, f"{content.DOWNLOADS_DIR}/players_own.txt", "keep me")
    content.install_content(game)
    removed = content.uninstall_content(game)
    assert removed > 0
    left = [p for p in (game / content.DOWNLOADS_DIR).rglob("*") if p.is_file()]
    assert left == [game / content.DOWNLOADS_DIR / "players_own.txt"]
    assert not (game / content.HD_DIR).exists()
    assert not (game / "hlap/titles.txt").exists()
    assert (game / "gearbox/models/scientist.mdl").read_text() == "of scientist"


def test_reinstall_is_idempotent(game: Path) -> None:
    first = content.install_content(game)
    second = content.install_content(game)
    assert (first.linked + first.copied) == (second.linked + second.copied)


def studio(groups: list[str], label: bytes = b"") -> bytes:
    """A studio header with these companion sequence groups after its own."""
    header = bytearray(192)
    header[:4] = b"IDST"
    table = b"".join(b"default".ljust(32, b"\0") + name.encode().ljust(64, b"\0")
                     + bytes(8) for name in ["models\\self.mdl", *groups])
    struct.pack_into("<iii", header, 172, len(groups) + 1, len(header), 1)
    return bytes(header) + table + label


def group_names(path: Path) -> list[str]:
    data = path.read_bytes()
    count, index = struct.unpack_from("<ii", data, 172)
    return [data[index + k * 104 + 32:index + k * 104 + 96].split(b"\0")[0].decode()
            for k in range(1, count)]


def test_a_relocated_model_takes_its_companions_along(game: Path) -> None:
    put(game, "valve/models/zombie.mdl", studio(["models\\zombie01.mdl"], b"hl"))
    put(game, "valve/models/zombie01.mdl", "hl anims")
    put(game, "gearbox/models/zombie.mdl",
        studio(["models\\zombie01.mdl", "models\\zombie02.mdl"], b"of"))
    # Identical to valve's, and one only this game has: both still move.
    put(game, "gearbox/models/zombie01.mdl", "hl anims")
    put(game, "gearbox/models/zombie02.mdl", "of anims")
    content.install_content(game)
    moved = game / "hlap_downloads/models/ap_of"
    assert group_names(moved / "zombie.mdl") == ["models/ap_of/zombie01.mdl",
                                                 "models/ap_of/zombie02.mdl"]
    assert (moved / "zombie01.mdl").read_text() == "hl anims"
    assert (moved / "zombie02.mdl").read_text() == "of anims"
    assert not (game / "hlap_downloads/models/zombie02.mdl").exists()
    # The game's own file is untouched.
    assert group_names(game / "gearbox/models/zombie.mdl")[0] == "models\\zombie01.mdl"


def test_installed_records_what_was_mounted(game: Path) -> None:
    assert content.read_installed(game) is None
    content.install_content(game)
    assert content.read_installed(game) == {
        "half_life": True, "opposing_force": True, "blue_shift": True}
    (game / "bshift/maps/ba_tram1.bsp").unlink()
    content.install_content(game)
    assert content.read_installed(game)["blue_shift"] is False
    content.uninstall_content(game)
    assert content.read_installed(game) is None


def test_installed_is_written_with_neither_game(tmp_path: Path) -> None:
    root = tmp_path / "Half-Life"
    put(root, "valve/maps/c0a0.bsp", bsp(False))
    content.install_content(root)
    assert content.read_installed(root) == {
        "half_life": True, "opposing_force": False, "blue_shift": False}
    content.uninstall_content(root)
    assert content.read_installed(root) is None
