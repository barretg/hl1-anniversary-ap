"""Install the AngelScript plugin into a Sven Co-op installation.

A thin CLI over `half_life_sven.plugin`, which is the same code the client's
`/install` command runs. Useful when working on the plugin without going through
the Archipelago Launcher.

Usage:
    python tools/install_plugin.py --game "F:/SteamLibrary/steamapps/common/Sven Co-op"
    python tools/install_plugin.py --game ... --uninstall
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apworld" / "half_life_sven"))

import plugin  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Sven Co-op install path")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.uninstall:
            removed, changed = plugin.uninstall(args.game)
            print(f"removed {removed} plugin files")
            print(
                "deregistered from default_plugins.txt"
                if changed
                else "plugin was not registered"
            )
            print("scripts/plugins/store/archipelago was left in place (it holds bridge files)")
            return 0

        written, changed = plugin.install(args.game)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))

    print(f"copied {written} files into {plugin.resolve_svencoop(args.game) / 'scripts'}")
    print(
        "registered the plugin in default_plugins.txt (backup written alongside it)"
        if changed
        else "plugin already registered in default_plugins.txt"
    )
    print("\nStart a listen server on -sp_campaign_portal, then launch the")
    print("Half-Life (Sven Co-op) Client from the Archipelago Launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
