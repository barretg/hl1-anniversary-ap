"""Entry point for the Half-Life (Sven Co-op) client.

Registered as a Launcher component in the world's `__init__.py`, so it appears in
the Archipelago Launcher and can be started with an `archipelago://` URI.
"""

from __future__ import annotations

import asyncio
import os
import sys

import Utils
from CommonClient import (
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)
from NetUtils import ClientStatus

from .. import plugin
from . import settings
from .bridge import Bridge, find_store_dir, is_game_dir

GAME_NAME = "Half-Life (Sven Co-op)"
POLL_INTERVAL = 0.2

# Key under which the chosen install path is remembered between sessions, so the
# folder picker only ever appears once.
STORE_KEY = "game_dir"

# Printed on connect, because these are typed in the game's chat rather than
# here and are easy to forget between sessions.
IN_GAME_COMMANDS = (
    ("!ap", "list every mission and its unlock status"),
    ("!warp <number>", "travel to an unlocked mission"),
    ("!hub", "return to the campaign portal"),
    ("!help", "show these commands in game"),
)

# Only a first guess for where Steam put the game. Sven Co-op is commonly on a
# secondary library drive, in which case the picker takes over.
DEFAULT_GAME_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Sven Co-op",
    r"C:\Program Files\Steam\steamapps\common\Sven Co-op",
]


def browse_for_game_dir() -> str:
    """Ask for the Sven Co-op folder with a native directory picker.

    Runs its own withdrawn Tk root and tears it down again, so it does not
    interfere with the Kivy client window. Returns "" if cancelled or if tk is
    unavailable (a headless or stripped install), in which case `/gamedir <path>`
    is still available.
    """
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        logger.warning("No tkinter available; set the path with /gamedir <path>.")
        return ""

    try:
        root = tkinter.Tk()
        root.withdraw()
        try:
            chosen = filedialog.askdirectory(
                title="Select your Sven Co-op folder (the one containing 'svencoop')",
                mustexist=True,
            )
        finally:
            root.destroy()
    except Exception as exc:  # tk raises bare TclError on a broken display
        logger.warning(f"Could not open the folder picker ({exc}); use /gamedir <path>.")
        return ""

    return chosen or ""


class HalfLifeSvenCommandProcessor(ClientCommandProcessor):
    def _cmd_gamedir(self, path: str = "") -> bool:
        """Change the Sven Co-op folder. With no argument, opens a folder picker."""
        if path:
            self.ctx.set_game_dir(path)
        else:
            self.ctx.prompt_for_game_dir()
        return True

    def _cmd_where(self) -> bool:
        """Show the current Sven Co-op folder, bridge path and plugin status."""
        logger.info(f"Game directory: {self.ctx.game_dir or '(not set)'}")
        logger.info(f"Bridge directory: {self.ctx.bridge.dir if self.ctx.bridge else '(none)'}")
        if self.ctx.game_dir:
            state = "installed" if plugin.is_installed(self.ctx.game_dir) else "not installed"
            logger.info(f"Plugin: {state}")
        return True

    def _cmd_install(self) -> bool:
        """Install the Sven Co-op plugin into the selected game folder."""
        if not self.ctx.game_dir:
            logger.error("No game folder set. Run /gamedir first.")
            return True
        try:
            written, registered = plugin.install(self.ctx.game_dir)
        except (OSError, ValueError) as exc:
            logger.error(f"Install failed: {exc}")
            return True

        logger.info(f"Installed {written} files into {self.ctx.game_dir}.")
        logger.info(
            "Registered the plugin in default_plugins.txt (backup written alongside it)."
            if registered
            else "Plugin was already registered in default_plugins.txt."
        )
        logger.info("Restart the map or the server for the plugin to load.")
        return True

    def _cmd_uninstall(self) -> bool:
        """Remove the Sven Co-op plugin. Leaves your bridge files alone."""
        if not self.ctx.game_dir:
            logger.error("No game folder set. Run /gamedir first.")
            return True
        try:
            removed, deregistered = plugin.uninstall(self.ctx.game_dir)
        except (OSError, ValueError) as exc:
            logger.error(f"Uninstall failed: {exc}")
            return True

        logger.info(f"Removed {removed} plugin files.")
        logger.info(
            "Deregistered the plugin from default_plugins.txt."
            if deregistered
            else "Plugin was not registered in default_plugins.txt."
        )
        return True

    def _cmd_deathlink(self) -> bool:
        """Toggle DeathLink. Remember: any death gibs the whole lobby."""
        self.ctx.death_link_enabled = not self.ctx.death_link_enabled
        asyncio.create_task(
            self.ctx.update_death_link(self.ctx.death_link_enabled), name="UpdateDeathLink"
        )
        logger.info(f"DeathLink {'enabled' if self.ctx.death_link_enabled else 'disabled'}.")
        return True

    def _cmd_missions(self) -> bool:
        """Show mission unlock status."""
        self.ctx.print_missions()
        return True

    def _cmd_chat(self) -> bool:
        """Toggle relaying chat between Sven Co-op and the multiworld."""
        self.ctx.chat_relay = not self.ctx.chat_relay
        logger.info(f"Chat relay {'enabled' if self.ctx.chat_relay else 'disabled'}.")
        return True

    def _cmd_commands(self) -> bool:
        """List the chat commands you type inside Sven Co-op."""
        self.ctx.print_in_game_commands()
        return True


class HalfLifeSvenContext(CommonContext):
    game = GAME_NAME
    command_processor = HalfLifeSvenCommandProcessor
    items_handling = 0b111  # everything, including our own placements

    def __init__(
        self, server_address: str | None, password: str | None, game_dir: str = ""
    ) -> None:
        super().__init__(server_address, password)
        self.game_dir: str = ""
        self.bridge: Bridge | None = None
        # An explicit --gamedir wins over everything and must not trigger the
        # picker, so it is applied before resolution rather than after.
        self._forced_game_dir = game_dir

        self.campaign = load_campaign()
        self.chapter_by_unlock_item = {
            entry["name"]: entry["chapter"]
            for entry in self.campaign["items"]
            if entry.get("group") == "chapter"
        }
        self.item_by_id = {entry["id"]: entry for entry in self.campaign["items"]}
        self.location_name_by_id = {
            entry["id"]: entry["name"] for entry in self.campaign["locations"]
        }
        self.goal_chapter = next(c["key"] for c in self.campaign["chapters"] if c["is_goal"])

        self.unlocked_chapters: set[str] = set()
        self.unlocked_items: set[str] = set()
        self.completed_missions: set[str] = set()
        self.missions_required = len(
            [c for c in self.campaign["chapters"] if not c["is_goal"]]
        )
        self.death_link_enabled = False
        self.goal_sent = False
        self.chat_relay = True

        self.resolve_game_dir()

    # -- setup -----------------------------------------------------------

    def resolve_game_dir(self) -> None:
        """Find the install without asking, or fall back to the folder picker.

        Order: the remembered choice, then SVENCOOP_DIR, then the usual Steam
        locations. Only if all three miss does the user get prompted, and the
        answer is remembered so it never asks twice.
        """
        for source, candidate in (
            ("--gamedir", self._forced_game_dir),
            ("saved", self.load_saved_game_dir()),
            ("SVENCOOP_DIR", os.environ.get("SVENCOOP_DIR", "")),
            ("default install path", self._guess_game_dir()),
        ):
            if is_game_dir(candidate):
                logger.info(f"Found Sven Co-op via {source}.")
                self.set_game_dir(candidate)
                return

        logger.info("Sven Co-op not found automatically. Please pick the folder.")
        self.prompt_for_game_dir()

    def prompt_for_game_dir(self) -> None:
        """Open the folder picker and apply the result."""
        chosen = browse_for_game_dir()
        if not chosen:
            logger.warning(
                "No folder selected. Use /gamedir to try again, "
                "or /gamedir <path> to type it directly."
            )
            return
        self.set_game_dir(chosen)

    @staticmethod
    def _guess_game_dir() -> str:
        for candidate in DEFAULT_GAME_DIRS:
            if is_game_dir(candidate):
                return candidate
        return ""

    @staticmethod
    def load_saved_game_dir() -> str:
        return settings.get(STORE_KEY, "") or ""

    @staticmethod
    def save_game_dir(path: str) -> None:
        """Remember the install, and say so loudly if it could not be saved.

        A failure here means being asked for the folder on every launch, which is
        exactly the kind of thing that goes unnoticed if it is only logged at
        debug level.
        """
        try:
            settings.set_value(STORE_KEY, path)
        except OSError as exc:
            logger.warning(
                f"Could not save your game folder to {settings.settings_path()}: {exc}. "
                f"You will be asked for it again next launch."
            )
            return

        if settings.get(STORE_KEY, "") != path:
            logger.warning("Your game folder did not save correctly.")

    def set_game_dir(self, path: str) -> None:
        """Point the bridge at an install, rejecting anything that is not one."""
        if not path:
            self.game_dir = ""
            self.bridge = None
            return

        if not is_game_dir(path):
            logger.error(
                f"{path} does not look like a Sven Co-op install "
                f"(no svencoop/maps/hl_c00.bsp). Pick the folder that contains 'svencoop'."
            )
            return

        self.game_dir = path
        store = find_store_dir(path)
        store.mkdir(parents=True, exist_ok=True)
        self.bridge = Bridge(store)
        self.bridge.clear_log()
        self.save_game_dir(path)
        logger.info(f"Bridging through {store}")

        if not plugin.is_installed(path):
            logger.warning("The Sven Co-op plugin is not installed here. Run /install.")

    # -- Archipelago -----------------------------------------------------

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "Connected":
            slot_data = args.get("slot_data", {})
            self.missions_required = slot_data.get(
                "missions_required", self.missions_required
            )
            self.goal_chapter = slot_data.get("goal_chapter", self.goal_chapter)
            self.death_link_enabled = bool(slot_data.get("death_link", False))
            if self.death_link_enabled:
                asyncio.create_task(self.update_death_link(True), name="UpdateDeathLink")

            # A mission we already finished before a reconnect still counts.
            self.completed_missions = {
                self.chapter_for_location(location_id)
                for location_id in self.checked_locations
                if self.is_mission_complete(location_id)
            } - {""}

            logger.info(
                f"Connected. {self.missions_required} missions needed to open the "
                f"final mission."
            )
            self.print_in_game_commands()

        elif cmd == "ReceivedItems":
            for item in args["items"]:
                self.apply_item(item.item)

        elif cmd == "PrintJSON":
            self.relay_to_game(args)

        elif cmd == "Bounced":
            tags = args.get("tags", [])
            if "DeathLink" in tags and self.death_link_enabled and self.bridge:
                data = args.get("data", {})
                source = data.get("source", "someone")
                cause = data.get("cause") or "an unknown fate"
                # The plugin splits the event line on '|', so the two fields are
                # joined with '~' instead.
                self.bridge.queue_event("DEATHLINK", f"{source}~{cause}")

    def relay_to_game(self, args: dict) -> None:
        """Show multiworld chat in the game.

        Only actual chat, not the item/hint firehose, which would bury the
        `[AP]` check messages the player needs to see. Our own messages are
        skipped because Sven Co-op has already shown them locally.
        """
        if not self.chat_relay or self.bridge is None:
            return
        if args.get("type") != "Chat":
            return
        if args.get("slot") == self.slot:
            return

        text = "".join(part.get("text", "") for part in args.get("data", []))
        text = text.replace("|", "/").replace("\n", " ").strip()
        if text:
            self.bridge.queue_event("CHAT", f"[AP] {text}")

    def apply_item(self, item_id: int) -> None:
        entry = self.item_by_id.get(item_id)
        if entry is None:
            return
        group = entry.get("group")
        if group == "chapter":
            self.unlocked_chapters.add(entry["chapter"])
        elif group in ("weapon", "optional"):
            self.unlocked_items.add(entry["name"])
        elif group == "filler" and self.bridge:
            self.bridge.queue_event("ITEM", entry["name"])

    # -- campaign helpers ------------------------------------------------

    def chapter_for_location(self, location_id: int) -> str:
        for entry in self.campaign["locations"]:
            if entry["id"] == location_id:
                return entry["chapter"]
        return ""

    def is_mission_complete(self, location_id: int) -> bool:
        for entry in self.campaign["locations"]:
            if entry["id"] == location_id:
                return entry["trigger"]["type"] == "chapter_complete"
        return False

    @property
    def goal_open(self) -> bool:
        return len(self.completed_missions - {self.goal_chapter}) >= self.missions_required

    @staticmethod
    def print_in_game_commands() -> None:
        """Remind the player what to type in the game, not here."""
        logger.info("In-game chat commands (press Y in Sven Co-op):")
        for command, description in IN_GAME_COMMANDS:
            logger.info(f"  {command:16} {description}")
        logger.info("Or walk up to a mission console in the hub and press its button.")

    def print_missions(self) -> None:
        for chapter in self.campaign["chapters"]:
            if chapter["is_goal"]:
                status = "OPEN" if self.goal_open else (
                    f"sealed ({len(self.completed_missions)}/{self.missions_required})"
                )
            elif chapter["key"] in self.completed_missions:
                status = "complete"
            elif chapter["key"] in self.unlocked_chapters:
                status = "unlocked"
            else:
                status = "locked"
            logger.info(f"  {chapter['index']:2d}. {chapter['name']:26} [{status}]")

    def on_deathlink(self, data: dict) -> None:
        # CommonContext calls this for DeathLink bounces too; the Bounced handler
        # above already queued it, so there is nothing extra to do here.
        super().on_deathlink(data)


def load_campaign() -> dict:
    from ..data import load_campaign as _load

    return _load()


async def game_watcher(ctx: HalfLifeSvenContext) -> None:
    """Pump the bridge: game events in, snapshot out."""
    while not ctx.exit_event.is_set():
        await asyncio.sleep(POLL_INTERVAL)

        if ctx.bridge is None:
            continue

        try:
            events = ctx.bridge.read_events()
        except OSError as exc:
            logger.debug(f"bridge read failed: {exc}")
            continue

        new_checks: list[int] = []
        for event in events:
            if event.kind == "CHECK":
                new_checks.append(int(event.arg))
            elif event.kind == "COMPLETE":
                ctx.completed_missions.add(event.arg)
            elif event.kind == "GOAL":
                if not ctx.goal_sent and ctx.server and not ctx.server.socket.closed:
                    ctx.goal_sent = True
                    await ctx.send_msgs(
                        [{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]
                    )
                    logger.info("Goal complete!")
            elif event.kind == "ACK":
                ctx.bridge.acknowledge(int(event.arg))
            elif event.kind == "DEATH":
                if ctx.death_link_enabled:
                    player = event.args[0] if event.args else "Freeman"
                    cause = event.args[1] if len(event.args) > 1 else "an unknown fate"
                    await ctx.send_death(f"{player} died to {cause}.")
            elif event.kind == "CHAT":
                if ctx.chat_relay and ctx.server and not ctx.server.socket.closed:
                    player = event.args[0] if event.args else "?"
                    text = event.args[1] if len(event.args) > 1 else ""
                    if text:
                        await ctx.send_msgs([{"cmd": "Say", "text": f"[{player}] {text}"}])
            elif event.kind == "HELLO":
                logger.info(f"Game is on {event.arg}.")
                ctx.bridge.write_snapshot(
                    connected=ctx.server is not None,
                    chapters=sorted(ctx.unlocked_chapters),
                    items=sorted(ctx.unlocked_items),
                    goal_open=ctx.goal_open,
                    death_link=ctx.death_link_enabled,
                    force=True,
                )

        if new_checks:
            unseen = [cid for cid in new_checks if cid not in ctx.checked_locations]
            if unseen:
                for location_id in unseen:
                    logger.info(f"Check: {ctx.location_name_by_id.get(location_id, location_id)}")
                await ctx.send_msgs(
                    [{"cmd": "LocationChecks", "locations": unseen}]
                )

        ctx.bridge.write_snapshot(
            connected=ctx.server is not None,
            chapters=sorted(ctx.unlocked_chapters),
            items=sorted(ctx.unlocked_items),
            goal_open=ctx.goal_open,
            death_link=ctx.death_link_enabled,
        )


async def main(args) -> None:
    ctx = HalfLifeSvenContext(args.connect, args.password, args.gamedir)

    ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    watcher = asyncio.create_task(game_watcher(ctx), name="GameWatcher")

    await ctx.exit_event.wait()
    watcher.cancel()
    await ctx.shutdown()


def launch(*args: str) -> None:
    parser = get_base_parser(description="Half-Life (Sven Co-op) Archipelago client")
    parser.add_argument("--gamedir", default="", help="Path to the Sven Co-op install")
    parser.add_argument("url", nargs="?", help="Archipelago connection URI")
    parsed = parser.parse_args(args)

    if parsed.url:
        parsed = Utils.parse_uri(parsed, parser) if hasattr(Utils, "parse_uri") else parsed

    Utils.init_logging("HalfLifeSvenClient", exception_logger="Client")
    asyncio.run(main(parsed))


if __name__ == "__main__":
    launch(*sys.argv[1:])
