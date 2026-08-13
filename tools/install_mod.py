"""Install the `hlap` mod folder into a Half-Life installation.

A thin CLI over `half_life.mod`, which is the same code the client's `/install`
command runs. Useful when working on the game side without going through the
Archipelago Launcher.

Usage:
    python tools/install_mod.py --game "F:/SteamLibrary/steamapps/common/Half-Life"
    python tools/install_mod.py --game ... --uninstall
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apworld" / "half_life"))

import mod  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Half-Life install path")
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
    if not has_dll:
        print(
            f"\nNo server dll was bundled, so the mod will not run yet.\n"
            f"Build it from game/ and copy it to {mod.mod_dir(args.game) / mod.DLL_NAME}."
        )
    print("\nStart the game with -game hlap, then launch the Half-Life Client")
    print("from the Archipelago Launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
