"""The shape of one campaign: everything about a game that is not shared.

A campaign is one retail game in its own game directory (`valve`, `gearbox`,
`bshift`), with its own chapters, finale and editorial calls. Adding one is a
module that builds a `Campaign` and a line in the registry in `__init__`.

The shape follows the Sven Co-op world's (commit `533e7ad`), not its data: every
chapter, map list and name here comes from a scan of the retail BSPs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# How the game knows a mission is over. See `complete_on` below.
COMPLETE_ON = ("arrival", "forward_exit", "endsection")


@dataclass(frozen=True)
class Campaign:
    key: str
    name: str
    # The game's directory under the Half-Life install, which is where its
    # maps are read from and, in game, where its content is mounted from.
    game_dir: str
    # A file under the install root whose presence means the game is owned.
    detect: str
    # (chapter key, display name, maps in campaign order). Keys are permanent:
    # `data/ids.json` keys every location by chapter.
    chapters: list[tuple[str, str, list[str]]]
    # The finale. Never unlocked by an item: it opens once enough of this
    # campaign's other missions are done, and finishing it is part of the goal.
    goal_chapter: str
    # The scene-setting mission `exclude_intro_missions` drops.
    intro_chapter: str
    # Mission entry gates, as `{chapter key: {"strict"|"always": [group, ...]}}`.
    gates: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # A requirement that starts partway through a mission, as
    # `{map: {"strict"|"always": [group, ...]}}`. Lets a later mod gate one map
    # without splitting the mission around it.
    map_gates: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # Weapon items this campaign brings, `{item: [classname, ...]}`. A weapon
    # shared with an earlier campaign is declared once, by the earlier one.
    weapons: dict[str, list[str]] = field(default_factory=dict)
    # Items this campaign adds to the shared logic groups, `{group: [item]}`.
    # Merged in only when the campaign is built, so another campaign's seeds
    # keep their groups unchanged.
    groups: dict[str, list[str]] = field(default_factory=dict)
    # The item that lets the player hold armour on this campaign's maps.
    armour_item: str = ""
    # Equipment items behind YAML toggles, `{item: [classname, ...]}`.
    optional_items: dict[str, list[str]] = field(default_factory=dict)
    # Weapons that are a check but never an item.
    unrandomised_weapons: dict[str, list[str]] = field(default_factory=dict)
    # This campaign's starting-weapon candidates, as classnames.
    melee: list[str] = field(default_factory=list)
    # `{item: map}` for a weapon check the entity lump cannot place: the weapon
    # is never lying in a map, only dropped by something that is.
    weapon_anchors: dict[str, str] = field(default_factory=dict)
    # Display names for this campaign's presentation of a shared item. Display
    # strings only, never ids.
    weapon_aliases: dict[str, str] = field(default_factory=dict)
    # Which charger classnames produce checks here. Blue Shift's HEV-style wall
    # units are scenery, so it lists health chargers only.
    charger_classnames: tuple[str, ...] = ("func_healthcharger", "func_recharge")
    # Chargers no player can reach that the automatic checks do not catch, as
    # `{map: {(classname, rounded position)}}`.
    unreachable: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # False positives of the reachability analysis, in the same form.
    reachable: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # Maps of this game that are in no chapter on purpose (hazard courses,
    # boot camp), so the scan can fail on any map nobody decided about.
    excluded_maps: frozenset[str] = frozenset()
    # `{chapter key: one of COMPLETE_ON}` where the rule derived from the
    # changelevel graph is wrong: a finale that ends on `trigger_endsection`
    # rather than on arrival.
    complete_on: dict[str, str] = field(default_factory=dict)
    # Lobby entrances are `<prefix>chapter_<n>_button`, `n` counted within this
    # campaign. Empty for Half-Life, which keeps `chapter_<n>_button`.
    hub_button_prefix: str = ""
    # What a player types to name this campaign: `ap_warp of 3`.
    short: str = ""
    # Half-Life predates every other campaign, and its location keys, check
    # names and item names were published without a campaign in them. It keeps
    # those forms; every later campaign's are prefixed with its key or name.
    legacy: bool = False

    def __post_init__(self) -> None:
        keys = [key for key, _, _ in self.chapters]
        for chapter in (self.goal_chapter, self.intro_chapter, *self.gates,
                        *self.complete_on):
            if chapter not in keys:
                raise ValueError(f"{self.key}: {chapter!r} is not one of its chapters")
        maps = [m for _, _, chapter_maps in self.chapters for m in chapter_maps]
        if len(maps) != len(set(maps)):
            raise ValueError(f"{self.key}: a map is in two chapters")
        for mode in self.complete_on.values():
            if mode not in COMPLETE_ON:
                raise ValueError(f"{self.key}: unknown complete_on {mode!r}")

    @property
    def chapter_keys(self) -> list[str]:
        return [key for key, _, _ in self.chapters]

    @property
    def maps(self) -> list[str]:
        return [m for _, _, chapter_maps in self.chapters for m in chapter_maps]

    @property
    def weapon_check_scope(self) -> str:
        """The first field of this campaign's `weapon_pickup` location keys."""
        return "*" if self.legacy else self.key

    def display(self, name: str) -> str:
        """A campaign-wide name as players see it: `Opposing Force: First Knife`."""
        return name if self.legacy else f"{self.name}: {name}"
