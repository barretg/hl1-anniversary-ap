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

# The chosen install path is remembered in host.yaml (see client/settings.py), so
# the folder picker only ever appears once.

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
        """Remove the Sven Co-op plugin, its scripts and its bridge files."""
        if not self.ctx.game_dir:
            logger.error("No game folder set. Run /gamedir first.")
            return True
        try:
            removed, deregistered = plugin.uninstall(self.ctx.game_dir)
        except (OSError, ValueError) as exc:
            logger.error(f"Uninstall failed: {exc}")
            return True

        logger.info(f"Removed {removed} files, including the bridge directory.")
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

    def _cmd_amnesty(self, count: str = "") -> bool:
        """Show or set how many deaths are forgiven before a DeathLink goes out."""
        if count:
            try:
                self.ctx.death_link_amnesty = max(0, int(count))
            except ValueError:
                logger.error("Usage: /amnesty <number of deaths>")
                return True
        logger.info(
            f"DeathLink amnesty: {self.ctx.death_link_amnesty} "
            f"death(s) forgiven before one is sent to the multiworld."
        )
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
        # Fingerprint of the id map this apworld was built from. The plugin
        # compares it against its own and pauses checks if they disagree.
        self.data_version = str(self.campaign.get("data_version", ""))

        # Missions this seed left out entirely. No unlock item exists for them.
        self.excluded_chapters: set[str] = set()
        self.unlocked_chapters: set[str] = set()
        self.unlocked_items: set[str] = set()
        # Equipment this seed did not shuffle. No item will ever be sent for it,
        # so the game has to be told up front or it gates it for the whole run --
        # which for the HEV suit meant no armour, ever.
        self.always_unlocked: set[str] = set(optional_item_options())
        self.completed_missions: set[str] = set()
        self.missions_required = len(
            [c for c in self.campaign["chapters"] if not c["is_goal"]]
        )
        self.death_link_enabled = False
        # Deaths the lobby is forgiven before one is reported to the multiworld.
        # The plugin owns the countdown; this is only the allowance it counts from.
        self.death_link_amnesty = 4
        self.goal_sent = False
        self.chat_relay = True
        self.bridge_failures = 0
        # How far through the server's item history we have got. Guards against
        # re-delivering filler when it resends everything on reconnect.
        self.items_seen = 0

        self.resolve_game_dir()

    # -- setup -----------------------------------------------------------

    def resolve_game_dir(self) -> None:
        """Find the install without asking. Only prompt if that fails.

        Order: an explicit --gamedir, the remembered choice, SVENCOOP_DIR, then
        the usual Steam locations. The folder picker is a last resort and never
        appears while a valid folder is known.
        """
        saved = self.load_saved_game_dir()

        for source, candidate in (
            ("--gamedir", self._forced_game_dir),
            ("your saved setting", saved),
            ("SVENCOOP_DIR", os.environ.get("SVENCOOP_DIR", "")),
            ("the default install path", self._guess_game_dir()),
        ):
            if is_game_dir(candidate):
                logger.info(f"Using the Sven Co-op folder from {source}.")
                self.set_game_dir(candidate, remember=False)
                return

        # Say which of the two cases this is, so a folder that stopped being
        # valid is not mistaken for one that was never saved.
        if saved:
            logger.warning(
                f"Your saved Sven Co-op folder is no longer valid: {saved}. "
                f"Please pick it again."
            )
        else:
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
        return settings.read_game_dir()

    @staticmethod
    def save_game_dir(path: str) -> None:
        """Remember the install, and say so loudly if it could not be saved.

        A failure here means being asked for the folder on every launch, which is
        exactly the kind of thing that goes unnoticed if it is only logged at
        debug level.
        """
        try:
            where = settings.write_game_dir(path)
        except OSError as exc:
            logger.warning(
                f"Could not save your game folder: {exc}. "
                f"You will be asked for it again next launch."
            )
            return

        # Read it back rather than trusting the write: a save that silently does
        # nothing is exactly what makes the picker reappear every launch.
        if settings.read_game_dir() != path:
            logger.warning(
                "Your game folder did not save correctly, so you will be asked "
                "for it again next launch."
            )
        else:
            logger.info(f"Saved your Sven Co-op folder to {where}.")

    def set_game_dir(self, path: str, remember: bool = True) -> None:
        """Point the bridge at an install, rejecting anything that is not one.

        `remember` is false when the path came from storage already, so a normal
        startup does not rewrite host.yaml for no reason.
        """
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
        if remember:
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
            self.excluded_chapters = set(slot_data.get("excluded_chapters", ()))
            # Absent from slot data reads as "not shuffled", which grants it: a
            # seed that never sends the item must not leave it locked forever.
            self.always_unlocked = {
                name for name, option in optional_item_options().items()
                if not slot_data.get(option, False)
            }
            self.death_link_enabled = bool(slot_data.get("death_link", False))
            self.death_link_amnesty = int(
                slot_data.get("death_link_amnesty", self.death_link_amnesty)
            )
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
            self.receive_items(args)

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

    def receive_items(self, args: dict) -> None:
        """Apply an item packet.

        The server resends the whole item history on every reconnect, with
        `index` saying where the batch starts. Unlocks are idempotent so they can
        simply be reapplied, but filler is a one-shot effect -- health, armour,
        an ammo top-up -- and re-delivering it on reconnect both floods the
        bridge and means nothing in the game. Two reconnects used to double the
        backlog each time, which is how a few dozen items became hundreds.
        """
        start = int(args.get("index", 0))
        items = args["items"]

        if start == 0:
            # Full resync. Rebuild unlock state from scratch.
            self.unlocked_chapters.clear()
            self.unlocked_items.clear()

        for offset, item in enumerate(items):
            # Only genuinely new items earn a filler delivery.
            is_new = (start + offset) >= self.items_seen
            self.apply_item(item.item, deliver_filler=is_new)

        self.items_seen = max(self.items_seen, start + len(items))

        if self.bridge is not None and self.bridge.queued_count > 50:
            logger.info(
                f"Delivering {self.bridge.queued_count} items to the game; "
                f"this drains over a few seconds."
            )

    def apply_item(self, item_id: int, deliver_filler: bool = True) -> None:
        entry = self.item_by_id.get(item_id)
        if entry is None:
            return
        group = entry.get("group")
        if group == "chapter":
            self.unlocked_chapters.add(entry["chapter"])
        elif group in ("weapon", "optional"):
            self.unlocked_items.add(entry["name"])
        elif group == "filler" and deliver_filler and self.bridge:
            self.bridge.queue_event("ITEM", entry["name"])
        elif group == "trap" and deliver_filler and self.bridge:
            # One-shot like filler, and for the same reason it must not be
            # redelivered on reconnect: nobody wants their traps twice.
            self.bridge.queue_event("TRAP", entry["name"])

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
    def held_item_names(self) -> set[str]:
        """Everything the game should treat as held, received or not.

        Not `item_names`: CommonContext owns that one for its datapackage lookup,
        and shadowing it with a read-only property breaks its constructor.
        """
        return self.unlocked_items | self.always_unlocked

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
            if chapter["key"] in self.excluded_chapters:
                status = "not in this seed"
            elif chapter["is_goal"]:
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


def optional_item_options() -> dict[str, str]:
    """Optional equipment name -> the YAML toggle that shuffles it."""
    from ..data import OPTIONAL_ITEM_NAMES

    return OPTIONAL_ITEM_NAMES


async def game_watcher(ctx: HalfLifeSvenContext) -> None:
    """Pump the bridge: game events in, snapshot out.

    Nothing in here may raise. An unhandled error kills this task, and the client
    then sits there looking connected while the game silently receives nothing.
    """
    while not ctx.exit_event.is_set():
        await asyncio.sleep(POLL_INTERVAL)

        if ctx.bridge is None:
            continue

        try:
            await pump(ctx)
        except Exception as exc:  # noqa: BLE001 - the watcher must survive anything
            ctx.bridge_failures += 1
            if ctx.bridge_failures in (1, 10, 100):
                logger.warning(f"Bridge error ({ctx.bridge_failures}): {exc}")
        else:
            if ctx.bridge_failures:
                logger.info("Bridge recovered.")
                ctx.bridge_failures = 0


async def pump(ctx: HalfLifeSvenContext) -> None:
    """One poll: drain the game's events, then publish the snapshot."""
    if ctx.bridge is None:
        return

    try:
        events = ctx.bridge.read_events()
    except OSError as exc:
        logger.debug(f"bridge read failed: {exc}")
        events = []

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
            player = event.args[0] if event.args else "Freeman"
            cause = event.args[1] if len(event.args) > 1 else "an unknown fate"
            # The plugin reports every death and says whether its amnesty
            # allowance absorbed this one. Older plugins send no such field,
            # which reads as "not forgiven" and behaves exactly as before.
            forgiven = len(event.args) > 2 and event.args[2] == "1"
            if forgiven:
                logger.debug(f"{player} died ({cause}); absorbed by DeathLink amnesty.")
            elif ctx.death_link_enabled:
                await ctx.send_death(f"{player} died to {cause}.")
            else:
                # The plugin reports every death and lets us decide, so this
                # is the only place that can explain a DeathLink not going
                # out. Say so rather than dropping it silently.
                logger.debug(
                    f"{player} died ({cause}) but DeathLink is off; use /deathlink."
                )
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
                items=sorted(ctx.held_item_names),
                goal_open=ctx.goal_open,
                death_link=ctx.death_link_enabled,
        death_link_amnesty=ctx.death_link_amnesty,
        excluded=sorted(ctx.excluded_chapters),
                data_version=ctx.data_version,
                force=True,
            )

    if new_checks:
        # The plugin fires every check its checkdata.txt knows about, but the
        # seed may not contain all of them: chargesanity off, or a mission left
        # out. Report only locations this slot actually has. Before the Connected
        # packet lands both sets are empty, which is not the same as "no
        # locations", so the filter is skipped until we know.
        in_seed = ctx.missing_locations | ctx.checked_locations
        unseen = [
            cid for cid in new_checks
            if cid not in ctx.checked_locations and (not in_seed or cid in in_seed)
        ]
        if unseen:
            for location_id in unseen:
                logger.info(f"Check: {ctx.location_name_by_id.get(location_id, location_id)}")
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": unseen}])

    # Always published, even if reading failed: the snapshot is how the game
    # learns about unlocks, and it must not be skipped just because ap_out.txt
    # was momentarily unreadable.
    ctx.bridge.write_snapshot(
        connected=ctx.server is not None,
        chapters=sorted(ctx.unlocked_chapters),
        items=sorted(ctx.held_item_names),
        goal_open=ctx.goal_open,
        death_link=ctx.death_link_enabled,
        death_link_amnesty=ctx.death_link_amnesty,
        excluded=sorted(ctx.excluded_chapters),
        data_version=ctx.data_version,
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
