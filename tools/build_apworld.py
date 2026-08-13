"""Package the world folder as a distributable `.apworld`.

An .apworld is a zip whose single top-level folder matches the zip's stem, which
is exactly the layout of `apworld/half_life`.

Usage:
    python tools/build_apworld.py [--install "F:/Archipelago/custom_worlds"]
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

# apworld container format version, as understood by the Archipelago loader.
MANIFEST_VERSION = 8
MANIFEST_COMPATIBLE_VERSION = 5

REPO_ROOT = Path(__file__).resolve().parent.parent
WORLD_DIR = REPO_ROOT / "apworld" / "half_life"
BUILD_DIR = REPO_ROOT / "build"

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", "test"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        yield path


def packaged_manifest() -> str:
    """The manifest with the packaging-only fields a zipped apworld needs.

    `version` and `compatible_version` are required in a `.apworld` but not in a
    folder world, so they are added here instead of being committed.
    """
    manifest = json.loads((WORLD_DIR / "archipelago.json").read_text(encoding="utf-8"))
    manifest["version"] = MANIFEST_VERSION
    manifest["compatible_version"] = MANIFEST_COMPATIBLE_VERSION
    return json.dumps(manifest, indent=1) + "\n"


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{WORLD_DIR.name}.apworld"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files(WORLD_DIR):
            arcname = Path(WORLD_DIR.name) / path.relative_to(WORLD_DIR)
            if path.name == "archipelago.json":
                archive.writestr(str(arcname), packaged_manifest())
            else:
                archive.write(path, arcname)

    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=BUILD_DIR)
    parser.add_argument(
        "--install",
        type=Path,
        help="also copy the result here, e.g. <Archipelago>/custom_worlds",
    )
    args = parser.parse_args(argv)

    target = build(args.out)
    size = target.stat().st_size
    print(f"built {target} ({size / 1024:.0f} KiB)")

    if args.install:
        args.install.mkdir(parents=True, exist_ok=True)
        destination = args.install / target.name
        shutil.copy2(target, destination)
        print(f"installed to {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
