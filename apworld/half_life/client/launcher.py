"""Entry point for the Half-Life client.

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

# Universal Tracker, if the player has its apworld installed. Inheriting from its
# context is what puts the Tracker tab in this client's window; without it this is
# the ordinary CommonContext and nothing changes.
#
# The world's `interpret_slot_data` is the other half: the mission the run opens
# with is rolled rather than derived, so UT has to be handed the seed's real
# answer or its logic view drifts from the server's.
try:
    from worlds.tracker.TrackerClient import TrackerGameContext as SuperContext

    TRACKER_LOADED = True
except ModuleNotFoundError:
    SuperContext = CommonContext
    TRACKER_LOADED = False

from .. import mod
from . import settings
from .bridge import Bridge, find_store_dir, is_game_dir

GAME_NAME = "Half-Life"
POLL_INTERVAL = 0.2

# The chosen install path is remembered in host.yaml (see client/settings.py), so
# the folder picker only ever appears once.

# Printed on connect, because these are typed in the game rather than here and
# are easy to forget between sessions.
#
# Two surfaces, one set of commands: chat with a `!`, or the console with the
# `ap_` names. Chat is the one to lead with -- it opens with one key and does not
# pause the game -- and the console versions are real registered server commands
# rather than the dot-prefixed workaround Sven Co-op forced on the previous
# project.
IN_GAME_COMMANDS = (
    ("!ap", "list every mission and its unlock status"),
    ("!tracker [map]", "locations found and still out there, printed to console"),
    ("!find [text]", "point at the nearest unfound check, or one you name"),
    ("!warp <number or name>", "travel to an unlocked mission"),
    ("!warp <mission> <part>", "back to a part of it you have already reached"),
    ("!hub", "return to the hub"),
    ("!help", "show these commands in game"),
)

# Only a first guess for where Steam put the game. Half-Life is commonly on a
# secondary library drive, in which case the picker takes over.
DEFAULT_GAME_DIRS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Half-Life",
    r"C:\Program Files\Steam\steamapps\common\Half-Life",
]


def browse_for_game_dir() -> str:
    """Ask for the Half-Life folder with a native directory picker.

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
                title="Select your Half-Life folder (the one containing 'valve')",
                mustexist=True,
            )
        finally:
            root.destroy()
    except Exception as exc:  # tk raises bare TclError on a broken display
        logger.warning(f"Could not open the folder picker ({exc}); use /gamedir <path>.")
        return ""

    return chosen or ""


class HalfLifeCommandProcessor(ClientCommandProcessor):
    def _cmd_gamedir(self, path: str = "") -> bool:
        """Change the Half-Life folder. With no argument, opens a folder picker."""
        if path:
            self.ctx.set_game_dir(path)
        else:
            self.ctx.prompt_for_game_dir()
        return True

    def _cmd_where(self) -> bool:
        """Show the current Half-Life folder, bridge path and mod status."""
        logger.info(f"Game directory: {self.ctx.game_dir or '(not set)'}")
        logger.info(f"Bridge directory: {self.ctx.bridge.dir if self.ctx.bridge else '(none)'}")
        if self.ctx.game_dir:
            state = "installed" if mod.is_installed(self.ctx.game_dir) else "not installed"
            logger.info(f"Mod: {state}")
        return True

    def _cmd_install(self) -> bool:
        """Install the `hlap` mod folder into the selected game folder."""
        if not self.ctx.game_dir:
            logger.error("No game folder set. Run /gamedir first.")
            return True
        try:
            written, has_dll = mod.install(self.ctx.game_dir)
        except (OSError, ValueError) as exc:
            logger.error(f"Install failed: {exc}")
            return True

        logger.info(f"Installed {written} files into {mod.mod_dir(self.ctx.game_dir)}.")
        if not has_dll:
            logger.warning(
                "This build ships no server dll, so the mod will not run yet. "
                "Build it from the game/ directory of the project and drop it in "
                f"as {mod.DLL_NAME}."
            )
        logger.info("Start Half-Life with -game hlap, then load a map.")
        return True

    def _cmd_uninstall(self) -> bool:
        """Remove the `hlap` mod folder and its bridge files."""
        if not self.ctx.game_dir:
            logger.error("No game folder set. Run /gamedir first.")
            return True
        try:
            removed = mod.uninstall(self.ctx.game_dir)
        except (OSError, ValueError) as exc:
            logger.error(f"Uninstall failed: {exc}")
            return True

        logger.info(f"Removed {removed} files, including the bridge directory.")
        logger.info("Your own Half-Life install was never touched.")
        return True

    def _cmd_deathlink(self) -> bool:
        """Toggle DeathLink."""
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
        """Toggle relaying chat between the game and the multiworld."""
        self.ctx.chat_relay = not self.ctx.chat_relay
        logger.info(f"Chat relay {'enabled' if self.ctx.chat_relay else 'disabled'}.")
        return True

    def _cmd_commands(self) -> bool:
        """List the console commands you type inside the game."""
        self.ctx.print_in_game_commands()
        return True


class HalfLifeContext(SuperContext):
    game = GAME_NAME
    command_processor = HalfLifeCommandProcessor
    items_handling = 0b111  # everything, including our own placements
    # Universal Tracker's context adds a "Tracker" tag; this client is a game
    # client and must not claim to be a tracker to the server.
    tags = {"AP"}

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
        self.item_by_id = {entry["id"]: entry for entry in self.campaign["items"]}
        self.location_name_by_id = {
            entry["id"]: entry["name"] for entry in self.campaign["locations"]
        }
        # The finale. No item unlocks it; it opens on a count of finished
        # missions, and clearing it wins the slot.
        self.goal_chapter: str = self.campaign["goal_chapter"]
        # Fingerprint of the id map this apworld was built from. The game
        # compares it against its own and pauses checks if they disagree.
        self.data_version = str(self.campaign.get("data_version", ""))

        # Missions this seed left out entirely. No unlock item exists for them.
        self.excluded_chapters: set[str] = set()
        self.unlocked_chapters: set[str] = set()
        self.unlocked_items: set[str] = set()
        # Equipment this seed did not shuffle. No item will ever be sent for it,
        # so the game has to be told up front or it gates it for the whole run --
        # which for the HEV suit meant no armour, ever.
        self.always_unlocked: set[str] = unshuffled_grants()
        # The other half of that answer: equipment the game should simply be left
        # to hand out on its own schedule. Sent as classnames because the gating
        # is by classname, and it has to stop gating these entirely rather than
        # treat them as owned.
        self.ungated_classnames: set[str] = unshuffled_vanilla_classnames()
        # What the run opens with, and what the game must never take away.
        self.starting_weapons: list[str] = list(
            self.campaign.get("starting_weapons", ())
        )
        self.completed_missions: set[str] = set()
        self.missions_required = len(
            [c for c in self.campaign["chapters"] if not c["is_goal"]]
        )
        self.death_link_enabled = False
        # Deaths forgiven before one is reported to the multiworld. The game owns
        # the countdown; this is only the allowance it counts from.
        self.death_link_amnesty = 4
        self.goal_sent = False
        self.chat_relay = True
        self.bridge_failures = 0
        # How far through the server's item history we have got. Guards against
        # re-delivering filler when it resends everything on reconnect.
        self.items_seen = 0
        # Has the history the server had at connect time been taken in yet?
        # Until it has, nothing is "new": `items_seen` counts only this client
        # run, so a freshly started client has seen nothing and would otherwise
        # treat every item it has ever been sent as having just arrived. Reset on
        # every Connected, because each connection resends that history.
        self.items_synced = False

        self.resolve_game_dir()

    # -- setup -----------------------------------------------------------

    def resolve_game_dir(self) -> None:
        """Find the install without asking. Only prompt if that fails.

        Order: an explicit --gamedir, the remembered choice, HALFLIFE_DIR, then
        the usual Steam locations. The folder picker is a last resort and never
        appears while a valid folder is known.
        """
        saved = self.load_saved_game_dir()

        for source, candidate in (
            ("--gamedir", self._forced_game_dir),
            ("your saved setting", saved),
            ("HALFLIFE_DIR", os.environ.get("HALFLIFE_DIR", "")),
            ("the default install path", self._guess_game_dir()),
        ):
            if is_game_dir(candidate):
                logger.info(f"Using the Half-Life folder from {source}.")
                self.set_game_dir(candidate, remember=False)
                return

        # Say which of the two cases this is, so a folder that stopped being
        # valid is not mistaken for one that was never saved.
        if saved:
            logger.warning(
                f"Your saved Half-Life folder is no longer valid: {saved}. "
                f"Please pick it again."
            )
        else:
            logger.info("Half-Life not found automatically. Please pick the folder.")

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
            logger.info(f"Saved your Half-Life folder to {where}.")

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
                f"{path} does not look like a Half-Life install "
                f"(no valve/maps/c0a0.bsp). Pick the folder that contains 'valve'."
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

        if not mod.is_installed(path):
            logger.warning("The hlap mod folder is not installed here. Run /install.")

    # -- Archipelago -----------------------------------------------------

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict) -> None:
        # Universal Tracker does its work in here when its context is the base,
        # so it has to see every packet. Harmless otherwise.
        super().on_package(cmd, args)

        # Any packet can move `checked_locations` on: RoomUpdate carries them
        # after somebody releases, and ReceivedItems after a collect. A mission
        # completion arriving that way is as real as one the game reported.
        if cmd in ("Connected", "RoomUpdate", "ReceivedItems"):
            self.sync_completed_missions()

        if cmd == "Connected":
            # The item history is about to be resent. None of it is new, however
            # much of it this client run has seen.
            self.items_synced = False

            slot_data = args.get("slot_data", {})
            self.missions_required = int(
                slot_data.get("missions_required", self.missions_required)
            )
            self.excluded_chapters = set(slot_data.get("excluded_chapters", ()))
            self.goal_chapter = slot_data.get("goal_chapter", self.goal_chapter)
            # Absent from slot data reads as "not shuffled". Either way the item
            # is never sent, so the game has to be told; what differs is what it
            # is told. See `unshuffled_grants` and `unshuffled_vanilla_classnames`.
            unshuffled = {
                name for name, option in optional_item_options().items()
                if not slot_data.get(option, False)
            }
            self.always_unlocked = unshuffled_grants(unshuffled)
            self.ungated_classnames = unshuffled_vanilla_classnames(unshuffled)
            self.starting_weapons = list(
                slot_data.get("starting_weapons", self.starting_weapons)
            )
            self.death_link_enabled = bool(slot_data.get("death_link", False))
            self.death_link_amnesty = int(
                slot_data.get("death_link_amnesty", self.death_link_amnesty)
            )
            if self.death_link_enabled:
                asyncio.create_task(self.update_death_link(True), name="UpdateDeathLink")

            # A mission we already finished before a reconnect still counts, and
            # `sync_completed_missions` above has already taken care of that.

            logger.info(
                f"Connected. {self.missions_required} missions needed to open "
                f"{self.chapter_name(self.goal_chapter)}."
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
                # The game splits the event line on '|', so the two fields are
                # joined with '~' instead.
                self.bridge.queue_event("DEATHLINK", f"{source}~{cause}")

    def relay_to_game(self, args: dict) -> None:
        """Show multiworld chat in the game.

        Only actual chat, not the item/hint firehose, which would bury the
        `[AP]` check messages the player needs to see. Our own messages are
        skipped because the game has already shown them locally.
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

        The first batch after connecting is that history, and none of it is new
        however this client counts. `items_seen` is a counter in memory, so a
        client that has just started has seen nothing and called the whole
        backlog new: every trap ever received sprang again, a few seconds after
        connecting, in whatever map the player was standing in. That is the
        report of scientists appearing in the hub out of nowhere. A trap is a
        moment, and a moment that has passed is not redeliverable -- so the
        backlog never delivers one, and only what arrives afterwards does.
        """
        start = int(args.get("index", 0))
        items = args["items"]

        if start == 0:
            # Full resync. Rebuild unlock state from scratch.
            self.unlocked_chapters.clear()
            self.unlocked_items.clear()

        # Everything the server had for us at connect time. Applied for its
        # unlocks, never for its one-shot effects.
        backlog = not self.items_synced

        for offset, item in enumerate(items):
            # Only genuinely new items earn a filler delivery.
            is_new = not backlog and (start + offset) >= self.items_seen
            self.apply_item(item.item, deliver_filler=is_new)

        self.items_seen = max(self.items_seen, start + len(items))
        self.items_synced = True

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

    def chapter_name(self, chapter_key: str) -> str:
        for entry in self.campaign["chapters"]:
            if entry["key"] == chapter_key:
                return entry["name"]
        return chapter_key

    def is_mission_complete(self, location_id: int) -> bool:
        for entry in self.campaign["locations"]:
            if entry["id"] == location_id:
                return entry["trigger"]["type"] == "chapter_complete"
        return False

    def sync_completed_missions(self) -> None:
        """Rebuild the finished-mission set from the server's checked locations.

        The server is the authority on what has been checked, and a mission's
        completion *is* a location. Tracking only the `COMPLETE` events the game
        reports made the client disagree with the server the moment a location
        was released or collected from anywhere else: sending a mission's
        completion check by hand did nothing in game, because the client had
        never seen the event that normally accompanies it. `missions_required`
        counts these, so the finale stayed sealed on a completion the server
        already had.

        Additive rather than a replacement: the game may report a completion a
        beat before the check round-trips, and dropping it in between would
        re-seal a finale that had just opened.
        """
        self.completed_missions |= {
            self.chapter_for_location(location_id)
            for location_id in self.checked_locations
            if self.is_mission_complete(location_id)
        } - {""}

    @property
    def slot_identity(self) -> str:
        """Which slot of which seed, which is what the game resets its run on.

        The client's `session` id cannot answer this. It is minted once per
        launch, so it changes when the same slot reconnects from a restarted
        client, which should move nobody, and does not change when the client
        already running connects a *different* slot, which is the case that
        leaves the player standing in a mission the new slot may not have.

        Empty until a slot is connected. That is not "a new slot": a disconnect
        is no news, and the game keeps the last one it was told about.
        """
        if self.slot is None:
            return ""
        return f"{self.seed_name or ''}:{self.slot}"

    @property
    def held_item_names(self) -> set[str]:
        """Everything the game should treat as held, received or not.

        Not `item_names`: CommonContext owns that one for its datapackage lookup,
        and shadowing it with a read-only property breaks its constructor.
        """
        return self.unlocked_items | self.always_unlocked

    @property
    def completed_count(self) -> int:
        """Missions finished, the finale aside."""
        return len(self.completed_missions - {self.goal_chapter})

    @property
    def goal_open(self) -> bool:
        """Has the finale's seal opened?"""
        return self.completed_count >= self.missions_required

    @property
    def open_chapters(self) -> set[str]:
        """Every mission the game should let a player walk into."""
        chapters = set(self.unlocked_chapters)
        if self.goal_open and self.goal_chapter not in self.excluded_chapters:
            chapters.add(self.goal_chapter)
        return chapters

    @property
    def run_complete(self) -> bool:
        """The finale is finished. This is what wins the slot."""
        return self.goal_chapter in self.completed_missions

    @staticmethod
    def print_in_game_commands() -> None:
        """Remind the player what to type in the game, not here."""
        logger.info("In-game commands, in chat (press Y in Half-Life):")
        for command, description in IN_GAME_COMMANDS:
            logger.info(f"  {command:26} {description}")
        logger.info("The same without the ! work in the console as ap, ap_warp, ...")

    def print_missions(self) -> None:
        for chapter in self.campaign["chapters"]:
            key = chapter["key"]
            if key in self.excluded_chapters:
                status = "not in this seed"
            elif key in self.completed_missions:
                status = "complete"
            elif chapter["is_goal"]:
                if self.goal_open:
                    status = "OPEN"
                else:
                    status = f"sealed ({self.completed_count}/{self.missions_required})"
            elif key in self.unlocked_chapters:
                status = "unlocked"
            else:
                status = "locked"
            logger.info(f"  {chapter['index']:2d}. {chapter['name']:26} [{status}]")

    def make_gui(self):
        """Name the window for this game rather than "Archipelago Text Client".

        `super()` rather than `kvui.GameManager` on purpose: when Universal
        Tracker is installed this inherits its UI, which is what carries the
        Tracker tab.
        """
        ui = super().make_gui()
        ui.base_title = f"Archipelago {GAME_NAME} Client"
        return ui

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


def unshuffled_grants(unshuffled: set[str] | None = None) -> set[str]:
    """Unshuffled equipment the game should treat as owned from the first spawn.

    The HEV suit, and nothing else so far: armour is switched on by that item
    alone, so a seed that never sends it has to say up front that it is held.
    """
    from ..data import VANILLA_WHEN_UNSHUFFLED

    if unshuffled is None:
        unshuffled = set(optional_item_options())
    return unshuffled - VANILLA_WHEN_UNSHUFFLED


def unshuffled_vanilla_classnames(unshuffled: set[str] | None = None) -> set[str]:
    """Unshuffled equipment the game should stop gating altogether.

    Classnames rather than item names, because gating is by classname and the
    game has to recognise the pickup it is being told to leave alone.

    The long jump module: the campaign hands it out in Lambda Core, so an
    unshuffled module wants nothing done to it at all. Calling it owned instead
    granted it from the first spawn of the run.
    """
    from ..data import VANILLA_WHEN_UNSHUFFLED

    if unshuffled is None:
        unshuffled = set(optional_item_options())

    wanted = unshuffled & VANILLA_WHEN_UNSHUFFLED
    return {
        classname
        for entry in load_campaign()["items"]
        if entry["name"] in wanted
        for classname in entry.get("classnames", ())
    }


async def game_watcher(ctx: HalfLifeContext) -> None:
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


def publish(ctx: HalfLifeContext, force: bool = False) -> None:
    """Write the current state to the snapshot the game reads."""
    if ctx.bridge is None:
        return
    ctx.bridge.write_snapshot(
        connected=ctx.server is not None,
        chapters=sorted(ctx.open_chapters),
        items=sorted(ctx.held_item_names),
        goal_open=ctx.goal_open,
        death_link=ctx.death_link_enabled,
        death_link_amnesty=ctx.death_link_amnesty,
        excluded=sorted(ctx.excluded_chapters),
        ungated=sorted(ctx.ungated_classnames),
        starting=list(ctx.starting_weapons),
        checked=sorted(ctx.checked_locations),
        missing=sorted(ctx.missing_locations),
        data_version=ctx.data_version,
        slot=ctx.slot_identity,
        force=force,
    )


async def pump(ctx: HalfLifeContext) -> None:
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
            ctx.completed_missions.add(event.arg)
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
            # The game reports every death and says whether its amnesty allowance
            # absorbed this one.
            forgiven = len(event.args) > 2 and event.args[2] == "1"
            if forgiven:
                logger.debug(f"{player} died ({cause}); absorbed by DeathLink amnesty.")
            elif ctx.death_link_enabled:
                await ctx.send_death(f"{player} died to {cause}.")
            else:
                # The game reports every death and lets us decide, so this is the
                # only place that can explain a DeathLink not going out. Say so
                # rather than dropping it silently.
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
            publish(ctx, force=True)

    if new_checks:
        # The game fires every check its checkdata.txt knows about, but the seed
        # may not contain all of them: chargesanity off, or a mission left out.
        # Report only locations this slot actually has. Before the Connected
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

    # A completion the server already had, or one that has just round-tripped,
    # counted before the snapshot goes out rather than a poll later: it is what
    # `goal_open` is computed from, and the game learns of the seal opening from
    # that snapshot and nothing else.
    ctx.sync_completed_missions()

    # Always published, even if reading failed: the snapshot is how the game
    # learns about unlocks, and it must not be skipped just because ap_out.txt
    # was momentarily unreadable.
    publish(ctx)


async def main(args) -> None:
    ctx = HalfLifeContext(args.connect, args.password, args.gamedir)

    ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")

    # Universal Tracker builds its own copy of the multiworld before the UI comes
    # up; without this its tab exists but has nothing in it.
    if TRACKER_LOADED:
        ctx.run_generator()

    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    watcher = asyncio.create_task(game_watcher(ctx), name="GameWatcher")

    await ctx.exit_event.wait()
    watcher.cancel()
    await ctx.shutdown()


def launch(*args: str) -> None:
    parser = get_base_parser(description="Half-Life Archipelago client")
    parser.add_argument("--gamedir", default="", help="Path to the Half-Life install")
    parser.add_argument("url", nargs="?", help="Archipelago connection URI")
    parsed = parser.parse_args(args)

    if parsed.url:
        parsed = Utils.parse_uri(parsed, parser) if hasattr(Utils, "parse_uri") else parsed

    Utils.init_logging("HalfLifeClient", exception_logger="Client")
    asyncio.run(main(parsed))


if __name__ == "__main__":
    launch(*sys.argv[1:])
