"""Install the `hlap` mod folder into a Half-Life installation.

A thin CLI over `half_life.mod`, which is the same code the client's `/install`
command runs. Useful when working on the game side without going through the
Archipelago Launcher.

Usage:
    python tools/install_mod.py
    python tools/install_mod.py --game "F:/SteamLibrary/steamapps/common/Half-Life"
    python tools/install_mod.py --uninstall

`--game` defaults to `DEFAULT_GAME`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apworld" / "half_life"))

import mod  # noqa: E402

DEFAULT_GAME = Path("/games/SteamLibrary/steamapps/common/Half-Life")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME,
                        help=f"Half-Life install path (default: {DEFAULT_GAME})")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.uninstall:
            removed = mod.uninstall(args.game)
            print(f"removed {removed} files from {mod.mod_dir(args.game)}")
            print("your own Half-Life install was never touched")
            return 0

        written, has_dll = mod.install(args.game)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))

    print(f"wrote {written} files into {mod.mod_dir(args.game)}")
    content = mod.install_content(args.game)
    for name in content.mounted:
        print(f"{name}: content linked in")
    for name in content.missing:
        print(f"{name}: not installed, skipped")
    for warning in content.warnings:
        print(f"warning: {warning}")
    if not has_dll:
        # Same reasoning as the client's /install: no next step is printed,
        # because without the dll there is nothing to start.
        print(
            f"\nNo server dll was bundled, so the mod cannot run.\n"
            f"Build it from game/ and copy it to {mod.mod_dir(args.game) / mod.DLL_NAME}."
        )
        return 0

    print("\nStart the game with -game hlap, then launch the Half-Life Client")
    print("from the Archipelago Launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
