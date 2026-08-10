"""Install the AngelScript plugin into a Sven Co-op installation.

Copies `angelscript/scripts/**` into `<Sven Co-op>/svencoop/scripts/` and adds
the plugin entry to `default_plugins.txt` if it is not already there.

Usage:
    python tools/install_plugin.py --game "F:/SteamLibrary/steamapps/common/Sven Co-op"
    python tools/install_plugin.py --game ... --uninstall
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO_ROOT / "angelscript" / "scripts"

PLUGIN_ENTRY = """	"plugin"
	{
		"name" "Archipelago"
		"script" "archipelago/ap_main"
	}
"""


def resolve_svencoop(game_dir: Path) -> Path:
    """Accept either the install root or the `svencoop` folder itself."""
    if (game_dir / "svencoop").is_dir():
        return game_dir / "svencoop"
    if game_dir.name == "svencoop":
        return game_dir
    raise SystemExit(f"{game_dir} does not look like a Sven Co-op installation")


def copy_scripts(svencoop: Path) -> list[Path]:
    written: list[Path] = []
    for source in sorted(SOURCE_ROOT.rglob("*")):
        if not source.is_file():
            continue
        target = svencoop / "scripts" / source.relative_to(SOURCE_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append(target)
    return written


def register_plugin(svencoop: Path) -> bool:
    """Add the plugin block to default_plugins.txt. Returns True if changed."""
    config = svencoop / "default_plugins.txt"
    text = config.read_text(encoding="utf-8")

    if '"archipelago/ap_main"' in text:
        return False

    # The file is a single `"plugins" { ... }` block; insert before its final
    # closing brace rather than appending, which would land outside the block.
    index = text.rstrip().rfind("}")
    if index < 0:
        raise SystemExit(f"unexpected format in {config}")

    updated = text[:index] + PLUGIN_ENTRY + text[index:]
    config.with_suffix(".txt.ap-backup").write_text(text, encoding="utf-8")
    config.write_text(updated, encoding="utf-8")
    return True


def unregister_plugin(svencoop: Path) -> bool:
    config = svencoop / "default_plugins.txt"
    text = config.read_text(encoding="utf-8")
    if PLUGIN_ENTRY not in text:
        return False
    config.write_text(text.replace(PLUGIN_ENTRY, ""), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Sven Co-op install path")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    svencoop = resolve_svencoop(args.game)

    if args.uninstall:
        removed = unregister_plugin(svencoop)
        shutil.rmtree(svencoop / "scripts" / "plugins" / "archipelago", ignore_errors=True)
        print("unregistered plugin" if removed else "plugin was not registered")
        print("note: scripts/plugins/store/archipelago was left in place (it holds your bridge files)")
        return 0

    written = copy_scripts(svencoop)
    print(f"copied {len(written)} files into {svencoop / 'scripts'}")

    if register_plugin(svencoop):
        print("registered the plugin in default_plugins.txt (backup written alongside it)")
    else:
        print("plugin already registered in default_plugins.txt")

    print("\nStart a listen server on -sp_campaign_portal, then launch the")
    print("Half-Life (Sven Co-op) Client from the Archipelago Launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
