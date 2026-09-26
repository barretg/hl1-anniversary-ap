"""Opposing Force and Blue Shift content, linked into the mod's search path.

Retail installs each game in its own directory next to `valve` (`gearbox`,
`bshift`), only when owned. The `hlap` mod can only fall back to `valve`, so the
other games' models, sounds, sprites and maps are linked into two directories the
engine searches above that fallback:

    hlap_downloads/   standard content    (searched above valve)
    hlap_hd/          HD content          (searched above hlap_downloads, HD on)

Hardlinks where the filesystem allows them, copies where it does not; nothing
under any game's own directory is ever written to.

A file whose path Half-Life, or the other game, ships with different contents
would shadow that copy for every map, which is what breaks Half-Life's HUD or
hands an Opposing Force scientist Half-Life's model with none of the animations
its scripts ask for. Such a file is installed under a campaign directory
inserted before its name instead -- `models/ap_of/scientist.mdl` -- and listed in
`archipelago/content.txt`, where the server dll reads it and redirects that path
while one of the campaign's maps is running. See `game/src/ap_content.h`.

Blue Shift's maps store two header lumps the other way round, which the engine
only accepts when running as `bshift`. Those are copied with the header put back
in the standard order rather than linked.

Text tables the engine loads once for the whole mod (`titles.txt`,
`sound/sentences.txt`, `sound/materials.txt`) are merged: Half-Life's, plus every
key a mounted game adds. A key a game defines differently keeps Half-Life's text.

Everything written is recorded in `archipelago/content_manifest.txt`, which is
exactly what uninstall removes.
"""

from __future__ import annotations

import filecmp
import os
import shutil
import struct
from dataclasses import dataclass, field
from pathlib import Path

DOWNLOADS_DIR = "hlap_downloads"
HD_DIR = "hlap_hd"
CONTENT_FILE = "content.txt"
MANIFEST_FILE = "content_manifest.txt"


@dataclass(frozen=True)
class ContentCampaign:
    key: str
    name: str
    game_dir: str
    # A file under the install root that exists only when the game is owned.
    detect: str
    # The directory inserted before a relocated file's name.
    prefix: str


CONTENT_CAMPAIGNS = (
    ContentCampaign("opposing_force", "Opposing Force", "gearbox",
                    "gearbox/maps/of1a1.bsp", "ap_of"),
    ContentCampaign("blue_shift", "Blue Shift", "bshift",
                    "bshift/maps/ba_tram1.bsp", "ap_bs"),
)

# Linked through when no other game has them. `events` holds the scripts the
# client dll hooks Opposing Force's weapon effects to.
CONTENT_DIRS = ("models", "sound", "sprites", "gfx", "events")
# Relocated on a clash. Everything else that clashes (menu art under `gfx`) is
# the client's, which always shows Half-Life's.
RELOCATED_DIRS = ("models", "sound", "sprites")
# Merged instead of linked; see `merge_titles` and friends.
# `CVOXFILESENTENCEMAX` in the engine and SDK, and `CSENTENCEG_MAX`, which the
# SDK patch raises from 200 for this merge.
SENTENCE_LIMIT = 2048
SENTENCE_GROUP_LIMIT = 512

MERGED_TEXT = {"titles.txt": "titles.txt",
               "sound/sentences.txt": "sound/sentences.txt",
               "sound/materials.txt": "sound/materials.txt"}


@dataclass
class ContentReport:
    mounted: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    linked: int = 0
    copied: int = 0
    relocated: int = 0
    maps: int = 0
    warnings: list[str] = field(default_factory=list)


def _index(root: Path, dirs: tuple[str, ...] = CONTENT_DIRS) -> dict[str, Path]:
    """`{lowercase relative path: file}` under these subdirectories of root."""
    found: dict[str, Path] = {}
    for sub in dirs:
        base = root / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix().lower()
                if rel not in MERGED_TEXT:
                    found.setdefault(rel, path)
    return found


def _same(a: Path | None, b: Path | None) -> bool:
    if a is None or b is None:
        return a is b
    return filecmp.cmp(a, b, shallow=False)


def relocated_path(rel: str, prefix: str) -> str:
    """`models/scientist.mdl` -> `models/ap_of/scientist.mdl`. The dll's rule too."""
    head, _, name = rel.rpartition("/")
    return f"{head}/{prefix}/{name}" if head else f"{prefix}/{name}"


def is_swapped_bsp(path: Path) -> bool:
    """Blue Shift's layout: planes in lump 0, entities in lump 1."""
    with path.open("rb") as handle:
        header = handle.read(4 + 8 * 2)
        if len(header) < 20 or struct.unpack_from("<i", header)[0] != 30:
            return False
        (off0,) = struct.unpack_from("<i", header, 4)
        (off1,) = struct.unpack_from("<i", header, 12)
        handle.seek(off0)
        first = handle.read(64).lstrip()
        handle.seek(off1)
        second = handle.read(64).lstrip()
    return not first.startswith(b"{") and second.startswith(b"{")


def _model_header(path: Path) -> tuple[list[str], bool] | None:
    """(companion sequence-group names, textures in a `T.mdl`) of a studio model."""
    with path.open("rb") as handle:
        header = handle.read(192)
        if len(header) < 192 or header[:4] != b"IDST":
            return None
        groups, group_index, textures = struct.unpack_from("<iii", header, 172)
        names: list[str] = []
        if groups > 1:
            handle.seek(group_index + 104)
            table = handle.read(104 * (groups - 1))
            for k in range(groups - 1):
                raw = table[k * 104 + 32:k * 104 + 96].split(b"\0")[0]
                names.append(raw.decode("latin-1").replace("\\", "/").lower())
    return names, textures == 0


def _model_families(*trees: dict[str, Path]) -> dict[str, set[str]]:
    """`{model: {model, its sequence-group files, its T.mdl}}` for these trees."""
    families: dict[str, set[str]] = {}
    for tree in trees:
        for rel, path in tree.items():
            if not (rel.startswith("models/") and rel.endswith(".mdl")):
                continue
            header = _model_header(path)
            if header is None:
                continue
            names, external_textures = header
            members = families.setdefault(rel, {rel})
            members.update(names)
            if external_textures:
                members.add(rel[:-4] + "t.mdl")
    return families


def _relocated_model(path: Path, prefix: str) -> bytes | None:
    """The model with its sequence-group names moved under prefix, or None."""
    if not path.name.lower().endswith(".mdl"):
        return None
    header = _model_header(path)
    if header is None or not header[0]:
        return None
    data = bytearray(path.read_bytes())
    groups, group_index = struct.unpack_from("<ii", data, 172)
    for k in range(1, groups):
        at = group_index + k * 104 + 32
        name = bytes(data[at:at + 64]).split(b"\0")[0].decode("latin-1")
        moved = relocated_path(name.replace("\\", "/").lower(), prefix).encode("latin-1")
        if len(moved) >= 64:
            raise ValueError(f"{path}: relocated sequence group name too long: {moved!r}")
        data[at:at + 64] = moved.ljust(64, b"\0")
    return bytes(data)


class _Writer:
    def __init__(self, root: Path, report: ContentReport) -> None:
        self.root = root
        self.report = report
        self.written: list[str] = []

    def _target(self, rel: str) -> Path:
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        self.written.append(rel)
        return target

    def link(self, source: Path, rel: str) -> None:
        target = self._target(rel)
        try:
            os.link(source, target)
            self.report.linked += 1
        except OSError:
            shutil.copy2(source, target)
            self.report.copied += 1

    def write(self, rel: str, data: bytes) -> None:
        self._target(rel).write_bytes(data)
        self.report.copied += 1


def uninstall_content(game_root: Path) -> int:
    """Remove exactly what the last install wrote. Returns files removed."""
    manifest = game_root / "hlap" / "archipelago" / MANIFEST_FILE
    if not manifest.is_file():
        return 0
    removed = 0
    touched: set[Path] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        rel = line.strip()
        if not rel or rel.startswith("#"):
            continue
        path = game_root / rel
        if path.is_file():
            path.unlink()
            removed += 1
            touched.add(path.parent)
    # Prune directories that emptied, never one that still holds anything.
    for directory in sorted(touched, key=lambda p: len(p.parts), reverse=True):
        while directory != game_root and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            directory = directory.parent
    for rel in (DOWNLOADS_DIR, HD_DIR):
        top = game_root / rel
        if top.is_dir() and not any(top.iterdir()):
            top.rmdir()
    manifest.unlink()
    content = game_root / "hlap" / "archipelago" / CONTENT_FILE
    if content.is_file():
        content.unlink()
    return removed


def install_content(game_root: Path) -> ContentReport:
    """Mount every owned campaign's content. Replaces a previous install."""
    report = ContentReport()
    uninstall_content(game_root)

    present = [c for c in CONTENT_CAMPAIGNS if (game_root / c.detect).is_file()]
    report.missing = [c.name for c in CONTENT_CAMPAIGNS if c not in present]
    report.mounted = [c.name for c in present]
    if not present:
        return report

    writer = _Writer(game_root, report)
    records = ["# written by /install; see game/src/ap_content.h", "V|1"]

    valve_sd = _index(game_root / "valve")
    valve_hd = _index(game_root / "valve_hd")
    trees = {
        c.key: (_index(game_root / c.game_dir), _index(game_root / f"{c.game_dir}_hd"))
        for c in present
    }
    placed: dict[str, Path] = {}

    for campaign in present:
        records.append(f"C|{campaign.key}|{campaign.game_dir}|{campaign.prefix}")
        sd, hd = trees[campaign.key]
        others = [trees[c.key] for c in present if c is not campaign]

        def decide(rel: str) -> str:
            """"skip", "link" or "move" for one path of this campaign."""
            own_sd, own_hd = sd.get(rel), hd.get(rel)

            def differs(other_sd: dict[str, Path], other_hd: dict[str, Path]) -> bool:
                # Standard against standard and HD against HD where both
                # exist; otherwise whichever copy each side has.
                tiers = [(a, b) for a, b in ((own_sd, other_sd.get(rel)),
                                             (own_hd, other_hd.get(rel))) if a and b]
                if not tiers:
                    tiers = [(own_sd or own_hd, other_sd.get(rel) or other_hd.get(rel))]
                return not all(_same(a, b) for a, b in tiers)

            if rel in valve_sd or rel in valve_hd:
                # Valve's copy is always visible at this path. The same bytes
                # need nothing, whatever the other game ships.
                return "move" if differs(valve_sd, valve_hd) else "skip"
            if any(differs(*other) for other in others
                   if rel in other[0] or rel in other[1]):
                return "move"
            return "link"

        decisions = {rel: decide(rel) for rel in set(sd) | set(hd)}
        # A model's companion files are opened by the names stored inside it,
        # not through the dll, so a model and its companions move together.
        for members in _model_families(sd, hd).values():
            if any(decisions.get(m) == "move" for m in members):
                for member in members:
                    if member in sd or member in hd or member in valve_sd:
                        decisions[member] = "move"

        for rel in sorted(decisions):
            decision = decisions[rel]
            own_sd, own_hd = sd.get(rel), hd.get(rel)
            if decision == "skip":
                continue
            if decision == "link":
                if rel in placed:
                    continue  # the same bytes are already visible
                if own_sd:
                    writer.link(own_sd, f"{DOWNLOADS_DIR}/{rel}")
                if own_hd:
                    writer.link(own_hd, f"{HD_DIR}/{rel}")
                placed[rel] = own_sd or own_hd
                continue
            if rel.split("/", 1)[0] not in RELOCATED_DIRS or rel.endswith((".txt", ".lst")):
                continue  # read by the client by a fixed name: Half-Life's stays
            moved = relocated_path(rel, campaign.prefix)
            # The standard copy must exist even if only the HD one differs,
            # since the redirect applies whatever the HD setting is.
            fallback = own_sd or valve_sd.get(rel) or own_hd
            for source, top in ((fallback, DOWNLOADS_DIR), (own_hd, HD_DIR)):
                if source is None:
                    continue
                patched = _relocated_model(source, campaign.prefix)
                if patched is None:
                    writer.link(source, f"{top}/{moved}")
                else:
                    writer.write(f"{top}/{moved}", patched)
            records.append(f"R|{campaign.key}|{rel}")
            report.relocated += 1

        maps_dir = game_root / campaign.game_dir / "maps"
        valve_maps = {p.name.lower() for p in (game_root / "valve" / "maps").glob("*")}
        for bsp in sorted(maps_dir.iterdir()) if maps_dir.is_dir() else []:
            name = bsp.name.lower()
            if not name.endswith(".bsp") or name in valve_maps or f"maps/{name}" in placed:
                continue
            rel = f"{DOWNLOADS_DIR}/maps/{name}"
            if is_swapped_bsp(bsp):
                data = bytearray(bsp.read_bytes())
                data[4:12], data[12:20] = data[12:20], data[4:12]
                writer.write(rel, bytes(data))
            else:
                writer.link(bsp, rel)
            placed[f"maps/{name}"] = bsp
            records.append(f"M|{campaign.key}|{name[:-4]}")
            report.maps += 1

        valve_wads = {p.name.lower() for p in (game_root / "valve").glob("*")}
        for wad in sorted((game_root / campaign.game_dir).iterdir()):
            name = wad.name.lower()
            # Wads, and a game's own skill settings (skillopfor.cfg), which the
            # dll execs after skill.cfg.
            wanted = name.endswith(".wad") or (name.startswith("skill") and name.endswith(".cfg"))
            if wad.is_file() and wanted and name not in valve_wads \
                    and name not in placed:
                writer.link(wad, f"{DOWNLOADS_DIR}/{name}")
                placed[name] = wad

    for rel, merge in (("titles.txt", merge_titles),
                       ("sound/sentences.txt", merge_keyed_lines),
                       ("sound/materials.txt", merge_materials)):
        base = game_root / "valve" / rel
        if not base.is_file():
            continue
        text = valve_text = base.read_text(encoding="latin-1")
        for campaign in present:
            extra = game_root / campaign.game_dir / rel
            if not extra.is_file():
                continue
            extra_text = extra.read_text(encoding="latin-1")
            text = merge(text, extra_text)
            # A key this game defines differently gets its own copy under a
            # new name, which the dll uses on the game's maps.
            if rel == "titles.txt":
                added, renames = renamed_titles(valve_text, extra_text, campaign.prefix)
                kind = "T"
            elif rel == "sound/sentences.txt":
                added, renames = renamed_sentences(valve_text, extra_text, campaign.prefix)
                kind = "S"
            else:
                continue
            if added:
                text = text.rstrip("\n") + "\n" + "\n".join(added) + "\n"
            records.extend(f"{kind}|{campaign.key}|{key}|{new}"
                           for key, new in renames.items())
        writer.write(f"hlap/{rel}", text.encode("latin-1"))
        if rel == "sound/sentences.txt":
            names = list(_keyed(text))
            groups = {name.rstrip("0123456789") for name in names
                      if name[-1:].isdigit()}
            if len(names) > SENTENCE_LIMIT or len(groups) > SENTENCE_GROUP_LIMIT:
                report.warnings.append(
                    f"{len(names)} sentences in {len(groups)} groups is over the "
                    f"engine's {SENTENCE_LIMIT} / {SENTENCE_GROUP_LIMIT}; some NPC "
                    "lines will be silent"
                )

    store = game_root / "hlap" / "archipelago"
    store.mkdir(parents=True, exist_ok=True)
    (store / CONTENT_FILE).write_text("\n".join(records) + "\n", encoding="utf-8")
    (store / MANIFEST_FILE).write_text(
        "# every file /install linked or wrote for OF/BS content\n"
        + "\n".join(writer.written) + "\n",
        encoding="utf-8",
    )
    return report


def _title_blocks(text: str) -> list[tuple[str, list[str]]]:
    """`(KEY, lines)` per message, each carrying the `$` settings in force."""
    blocks: list[tuple[str, list[str]]] = []
    settings: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("$"):
            settings[stripped.split()[0].lower()] = lines[i]
        elif stripped and not stripped.startswith("//") and stripped != "{":
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip() == "{":
                k = j
                while k < len(lines) and lines[k].strip() != "}":
                    k += 1
                blocks.append((stripped.upper(),
                               list(settings.values()) + lines[i:k + 1]))
                i = k
        i += 1
    return blocks


def _title_text(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if not line.strip().startswith("$")]


def renamed_titles(base: str, extra: str, prefix: str) -> tuple[list[str], dict[str, str]]:
    """Extra's messages that base defines differently, renamed `AP_OF_<KEY>`.

    Returns (lines to append, {key: new key}).
    """
    have = dict(_title_blocks(base))
    added: list[str] = []
    renames: dict[str, str] = {}
    for key, lines in _title_blocks(extra):
        if key not in have or _title_text(lines) == _title_text(have[key]):
            continue
        new = f"{prefix.upper()}_{key}"
        out = list(lines)
        for i, line in enumerate(out):
            if line.strip().upper() == key:
                out[i] = new
                break
        added += out + [""]
        renames[key] = new
    return added, renames


def _letters(n: int) -> str:
    """0 -> "AA", 1 -> "AB": a suffix with no digits, so no sentence group forms."""
    return chr(ord("A") + n // 26 % 26) + chr(ord("A") + n % 26) if n < 676 else \
        _letters(n // 676 - 1) + _letters(n % 676)


def renamed_sentences(base: str, extra: str, prefix: str) -> tuple[list[str], dict[str, str]]:
    """Extra's sentences that base defines differently, under new names.

    Returns (lines to append, {name: new name}). A sentence the game silences
    (`common/null`) maps to "" and adds nothing, and sentences with the same
    words share one name: the engine holds 2048 in all.
    """
    have = _keyed(base)
    by_words: dict[str, str] = {}
    added: list[str] = []
    renames: dict[str, str] = {}
    for key, line in _keyed(extra).items():
        if key not in have:
            continue
        words = line.split("//", 1)[0].split()[1:]
        if words == have[key].split("//", 1)[0].split()[1:]:
            continue
        if words == ["common/null"]:
            renames[key] = ""
            continue
        text = " ".join(words)
        if text not in by_words:
            by_words[text] = f"{prefix.upper()}_{_letters(len(by_words))}"
            added.append(f"{by_words[text]} {text}")
        renames[key] = by_words[text]
    return added, renames


def merge_titles(base: str, extra: str) -> str:
    have = {key for key, _ in _title_blocks(base)}
    added = [lines for key, lines in _title_blocks(extra) if key not in have]
    if not added:
        return base
    out = base.rstrip("\n") + "\n\n// --- added by the hlap installer ---\n"
    for lines in added:
        out += "\n".join(lines) + "\n\n"
    return out


def _keyed(text: str) -> dict[str, str]:
    keyed: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.split("//", 1)[0].strip()
        if stripped and not stripped.startswith("$"):
            keyed.setdefault(stripped.split()[0].upper(), line)
    return keyed


def merge_keyed_lines(base: str, extra: str) -> str:
    """Sentences: `NAME words...`, one per line."""
    have = _keyed(base)
    added = [line for key, line in _keyed(extra).items() if key not in have]
    if not added:
        return base
    return base.rstrip("\n") + "\n" + "\n".join(added) + "\n"


def merge_materials(base: str, extra: str) -> str:
    """Materials: `<type> <TEXTURE>`, keyed by the texture name."""
    def textures(text: str) -> dict[str, str]:
        found: dict[str, str] = {}
        for line in text.splitlines():
            parts = line.split("//", 1)[0].split()
            if len(parts) == 2:
                found.setdefault(parts[1].upper(), line)
        return found

    have = textures(base)
    added = [line for key, line in textures(extra).items() if key not in have]
    if not added:
        return base
    return base.rstrip("\n") + "\n" + "\n".join(added) + "\n"
