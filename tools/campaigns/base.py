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
    # Gates on every check in a map except arriving there, in the same form.
    # For a map that can be entered freely but not done without an item.
    map_check_gates: dict[str, dict[str, list[str]]] = field(default_factory=dict)
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
    # `{item: [maps or copies]}` whose copies (placed or dropped) do not count
    # toward its "First ..." check: a prop out of bounds, a scripted monster
    # that never fights. A bare map covers every copy on it; `map@x y z` one
    # copy, by its origin, and the map's next copy is used instead. Each
    # mission's source moves on to its next copy.
    unreachable_copies: dict[str, list[str]] = field(default_factory=dict)
    # `{item: [maps or copies]}` confirmed reachable in play where the maps
    # alone could not prove it, in the same form as `unreachable_copies`. Logic is unchanged; the scenario harness
    # stops asking about them (`tests/aptest/aptest.py --unproven`).
    confirmed_copies: dict[str, list[str]] = field(default_factory=dict)
    # `{map: {item: gates}}` for a mission's copy of a weapon that sits past
    # something its mission and map do not ask for. Same shape as `gates`.
    weapon_source_gates: dict[str, dict[str, dict[str, list[str]]]] = field(
        default_factory=dict
    )
    # Gates on single charger or pool checks, `{map: {"classname:*model":
    # gates}}`, for one spot in a map that needs more than the map does (the
    # displacer's Xen room).
    location_gates: dict[str, dict[str, dict[str, list[str]]]] = field(
        default_factory=dict
    )
    # Display names for this campaign's presentation of a shared item. Display
    # strings only, never ids.
    weapon_aliases: dict[str, str] = field(default_factory=dict)
    # One-off checks for a map event: `{map: [(category, targetname, name)]}`.
    # The check is sent when the map fires that targetname, and the category is
    # its trigger type, which is what the YAML option switching it off names.
    fired_checks: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    # Which charger classnames produce checks here. Blue Shift's HEV-style wall
    # units are scenery, so it lists health chargers only.
    charger_classnames: tuple[str, ...] = ("func_healthcharger", "func_recharge")
    # Chargers no player can reach that the automatic checks do not catch, as
    # `{map: {(classname, rounded position)}}`.
    unreachable: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # Pickups no player can reach that the automatic checks do not catch, as
    # `{map: {(classname, (x, y, z))}}`: the origin keyvalue for a placed one,
    # the crate's rounded centre for one a crate drops.
    unreachable_pickups: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # Scientists and barneys that cannot be killed, or whose death fails the
    # mission, that the automatic exclusions miss: `{map: {(classname, (x, y,
    # z))}}`, the origin keyvalue.
    unkillable_npcs: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # NPCs the automatic exclusions drop that play shows are fair checks: one a
    # `killtarget` only removes after the player has passed, or an intro NPC
    # the line-of-sight test missed. Same form.
    killable_npcs: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # `monster_generic` stand-ins wearing a scientist's or guard's model that
    # can be killed, as `{map: {(kind, (x, y, z))}}` with kind "scientist" or
    # "barney" and the origin keyvalue. Most generics are corpses, puppets in a
    # sealed cutscene, or story characters, so only listed ones count.
    generic_npcs: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # NPCs whose death breaks the run in a way the reload test cannot see (a
    # softlock), as `{map: {(classname, (x, y, z))}}`: checks behind
    # `include_critical_npcs`, kept whatever the automatic exclusions say.
    critical_npcs: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # Two placed NPCs the map swaps in play, deleting the one the player meets
    # and moving a stand-in into its place: `{map: {(classname, (x, y, z)) of
    # the one met: ((classname, (x, y, z)) of the stand-in, name, note[,
    # safe])}}`. One check, at the first one's spot, sent by either; the note
    # is what `!find` and `!trace` say about the swap. `safe` when the
    # stand-in can be killed without failing the mission, which keeps the
    # check out of `include_critical_npcs` even if the first one's death fails it.
    swapped_npcs: dict[str, dict[tuple[str, tuple[int, int, int]], tuple]] = field(
        default_factory=dict
    )
    # NPCs the map deletes as their scripted death (thrown, then swapped for a
    # corpse), as `{map: {(classname, (x, y, z))}}`: that removal sends.
    removal_deaths: dict[str, set[tuple[str, tuple[int, int, int]]]] = field(
        default_factory=dict
    )
    # Logic for single NPCs, `{map: {(classname, (x, y, z)): gates}}` with
    # gates as a location's (`{"always": [group, ...]}`): one only reachable
    # with the Displacer, say.
    npc_gates: dict[str, dict[tuple[str, tuple[int, int, int]], dict]] = field(
        default_factory=dict
    )
    # Where `ap_find` points for an NPC that is not met where it is placed:
    # `{map: {(classname, (x, y, z)): (x, y, z)}}`.
    npc_positions: dict[str, dict[tuple[str, tuple[int, int, int]],
                                  tuple[float, float, float]]] = field(
        default_factory=dict
    )
    # NPCs whose check names a later part than their map, because the player
    # reaches them from there: `{map: {(classname, (x, y, z)): part map}}`.
    npc_parts: dict[str, dict[tuple[str, tuple[int, int, int]], str]] = field(
        default_factory=dict
    )
    # The train the player rides in each intro map, by targetname. An intro
    # map's NPCs count only if they can be seen from its route.
    intro_trains: dict[str, str] = field(default_factory=dict)
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
    # Transitions mode (see .claude/TRANSITION_RANDO.md). Chapters whose rollout
    # step is done, by key. Only these are valid in the YAML's chapter lists.
    transition_supported: frozenset[str] = frozenset()
    # The finale's boss fight, the changelevel that fires when it is won
    # (`(map, target map)`), and the closing scene it leads to. The ending map
    # is cut from the world in transitions mode; the boss exit is the win.
    boss_map: str = ""
    boss_exit: tuple[str, str] = ("", "")
    ending_map: str = ""
    # `{transition id: {field: value}}` corrections to the built transition
    # table: kind, partner, two_way, frame, orb_at, fixed, dead.
    transition_overrides: dict[str, dict] = field(default_factory=dict)
    # The scripted train rides, `{name: {"train": globalname, "maps": {map:
    # {"entry": id | None, "exit": id}}}}`. Seeded by hand (risk 4).
    train_sequences: dict[str, dict] = field(default_factory=dict)
    # `MAP_LOGIC` (3.3): `{map: {"segments", "transitions", "edges", "tier"}}`,
    # drafted by `tools/map_logic_report.py` from the `maplogic` aptest group.
    # A map not in it is one segment under the chapter's existing gates.
    map_logic: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        keys = [key for key, _, _ in self.chapters]
        for chapter in (self.goal_chapter, self.intro_chapter, *self.gates,
                        *self.complete_on):
            if chapter not in keys:
                raise ValueError(f"{self.key}: {chapter!r} is not one of its chapters")
        maps = [m for _, _, chapter_maps in self.chapters for m in chapter_maps]
        if len(maps) != len(set(maps)):
            raise ValueError(f"{self.key}: a map is in two chapters")
        for map_name in (*self.map_check_gates, *self.weapon_source_gates,
                         *self.location_gates,
                         *(m.split("@")[0] for ms in self.unreachable_copies.values()
                           for m in ms),
                         *(m.split("@")[0] for ms in self.confirmed_copies.values()
                           for m in ms)):
            if map_name not in maps:
                raise ValueError(f"{self.key}: gate or copy on {map_name!r}, "
                                 "which is not one of its maps")
        firsts = {chapter_maps[0] for _, _, chapter_maps in self.chapters}
        for map_name in self.map_gates:
            # A mission's first map is gated by the mission's own gates.
            if map_name not in maps or map_name in firsts:
                raise ValueError(f"{self.key}: map gate on {map_name!r}, which is "
                                 "not a later map of one of its missions")
        for chapter in self.transition_supported:
            if chapter not in keys:
                raise ValueError(f"{self.key}: transition_supported names "
                                 f"{chapter!r}, which is not one of its chapters")
        for map_name in (self.boss_map, *self.boss_exit, self.ending_map):
            if map_name and map_name not in maps:
                raise ValueError(f"{self.key}: boss or ending map {map_name!r} "
                                 "is not one of its maps")
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
