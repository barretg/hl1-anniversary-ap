"""Entry point for the Half-Life (Sven Co-op) client.

Registered as a Launcher component in the world's `__init__.py`, so it appears in
the Archipelago Launcher and can be started with an `archipelago://` URI.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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

from .bridge import Bridge, find_store_dir

GAME_NAME = "half_life_sven"
POLL_INTERVAL = 0.2

# Where to look for the game when the user has not told us. Sven Co-op is a Steam
# title, so the library could be on any drive; these are only a first guess and
# `/gamedir` overrides them.
DEFAULT_GAME_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Sven Co-op",
    r"C:\Program Files\Steam\steamapps\common\Sven Co-op",
]


class HalfLifeSvenCommandProcessor(ClientCommandProcessor):
    def _cmd_gamedir(self, path: str = "") -> bool:
        """Set the Sven Co-op install directory (the folder containing svencoop)."""
        if not path:
            logger.info(f"Game directory: {self.ctx.game_dir or '(not set)'}")
            logger.info(f"Bridge directory: {self.ctx.bridge.dir if self.ctx.bridge else '(none)'}")
            return True
        self.ctx.set_game_dir(path)
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


class HalfLifeSvenContext(CommonContext):
    game = GAME_NAME
    command_processor = HalfLifeSvenCommandProcessor
    items_handling = 0b111  # everything, including our own placements

    def __init__(self, server_address: str | None, password: str | None) -> None:
        super().__init__(server_address, password)
        self.game_dir: str = ""
        self.bridge: Bridge | None = None

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

        self.set_game_dir(os.environ.get("SVENCOOP_DIR", "") or self._guess_game_dir())

    # -- setup -----------------------------------------------------------

    @staticmethod
    def _guess_game_dir() -> str:
        for candidate in DEFAULT_GAME_DIRS:
            if Path(candidate, "svencoop").is_dir():
                return candidate
        return ""

    def set_game_dir(self, path: str) -> None:
        self.game_dir = path
        if not path:
            logger.warning(
                "Sven Co-op directory not found. Set it with /gamedir <path to Sven Co-op>."
            )
            self.bridge = None
            return
        store = find_store_dir(path)
        store.mkdir(parents=True, exist_ok=True)
        self.bridge = Bridge(store)
        self.bridge.clear_log()
        logger.info(f"Bridging through {store}")

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

        elif cmd == "ReceivedItems":
            for item in args["items"]:
                self.apply_item(item.item)

        elif cmd == "Bounced":
            tags = args.get("tags", [])
            if "DeathLink" in tags and self.death_link_enabled and self.bridge:
                data = args.get("data", {})
                source = data.get("source", "someone")
                cause = data.get("cause") or "an unknown fate"
                # The plugin splits the event line on '|', so the two fields are
                # joined with '~' instead.
                self.bridge.queue_event("DEATHLINK", f"{source}~{cause}")

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
    ctx = HalfLifeSvenContext(args.connect, args.password)
    if args.gamedir:
        ctx.set_game_dir(args.gamedir)

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
