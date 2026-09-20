"""Package the world folder as a distributable `.apworld`.

An .apworld is a zip whose single top-level folder matches the zip's stem, which
is exactly the layout of `apworld/half_life`.

A release has to carry the server dll, which is a build artifact rather than a
source file: it is gitignored, staged into `mod/files/dlls/` by hand, and so the
easiest mistake to make here is packaging a checkout that has never had one
dropped in. The result installs cleanly and then does not run, which is why the
dll is checked for by default and skipping it takes a flag.

Usage:
    python tools/build_apworld.py [--install "F:/Archipelago/custom_worlds"]
    python tools/build_apworld.py --allow-no-dll   # a dev build, mod won't run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

# apworld container format version, as understood by the Archipelago loader.
MANIFEST_VERSION = 8
MANIFEST_COMPATIBLE_VERSION = 5

REPO_ROOT = Path(__file__).resolve().parent.parent
WORLD_DIR = REPO_ROOT / "apworld" / "half_life"
BUILD_DIR = REPO_ROOT / "build"

# `mod` owns where the dll lives, both inside the package and inside the mod
# folder. Importing it rather than spelling the path again keeps one definition.
sys.path.insert(0, str(WORLD_DIR))

import mod  # noqa: E402

# The staged dll that packaging picks up, as an absolute path.
STAGED_DLL = WORLD_DIR / "mod" / "files" / mod.DLL_NAME

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


def build(out_dir: Path, allow_no_dll: bool = False) -> Path:
    """Zip the world up. Refuses to build without the dll unless told to.

    Checked before the zip is opened, so a refused build leaves whatever was
    built last time alone rather than replacing it with a truncated file.
    """
    if not allow_no_dll and not STAGED_DLL.is_file():
        raise SystemExit(
            f"no server dll staged at {STAGED_DLL}, so this would package an "
            "apworld that installs but cannot run.\n"
            "Build it (see the game/ section of README.md) and copy it there, "
            "or pass --allow-no-dll for a development build."
        )

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
    parser.add_argument(
        "--allow-no-dll",
        action="store_true",
        help="package without the server dll; the mod will not run. Not for a release",
    )
    args = parser.parse_args(argv)

    target = build(args.out, allow_no_dll=args.allow_no_dll)
    size = target.stat().st_size
    print(f"built {target} ({size / 1024:.0f} KiB)")
    if not STAGED_DLL.is_file():
        print("warning: no server dll in this build -- it installs but will not run")

    if args.install:
        args.install.mkdir(parents=True, exist_ok=True)
        destination = args.install / target.name
        shutil.copy2(target, destination)
        print(f"installed to {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
