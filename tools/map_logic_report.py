"""Draft `MAP_LOGIC` from map logic discovery (TRANSITION_RANDO.md section 8.3).

Reads the `maplogic` lines of the aptest results: each scenario's notes, and
what had been given before each one. A scenario covers a chapter in one
direction (`Map logic: Office Complex 2 (backward, kept state)`); each note
names the map it was made on (`[c1a2b] T3 needs MP5`), and is drafted under
that map. Results from the older one-scenario-per-entry titles still read. Prints a review table and a Python
fragment per map for a human to edit into the campaign module's `map_logic`.
It never writes a campaign module itself.

A transition note (`T3 needs MP5`) proposes a gate for reaching that
transition from the entry: the narrowest requirement group holding the named
item (or every held item, if none is named), with the other candidates listed.
`oneway <kind> @x y z yaw` proposes a one-way edge with a return teleporter at
that spot. Anything else is carried into the fragment as a comment.

Usage:
    python tools/map_logic_report.py [--results <aptest_results.txt>] [--diff] [maps...]

`--diff` compares each drafted map against the campaign module's current
`map_logic`, to show what a re-test changed.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import pprint
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAMPAIGN_JSON = REPO / "apworld" / "half_life" / "data" / "campaign.json"
LINUX_GAME_ROOT = Path("/games/SteamLibrary/steamapps/common/Half-Life")
GROUP = "maplogic"

TITLE = re.compile(r"^Map logic: (?P<map>\S+) from (?P<entry>\S+) \((?P<how>[^)]*)\)$")
# A chapter in one direction: `<chapter name> <1-4> (<pass>)`.
CHAPTER_TITLE = re.compile(r"^Map logic: (?P<chapter>.+) (?P<n>[1-4]) \((?P<how>[^)]*)\)$")
MAP_PREFIX = re.compile(r"^\[(?P<map>[^\]\s]+)\]\s*")
NEEDS = re.compile(r"^T(?P<n>\d+)\s+needs\s+(?P<what>.+)$", re.I)
ONE_WAY_T = re.compile(r"^T(?P<n>\d+)\s+one-?way\s*(?P<kind>\w*)", re.I)
ONE_WAY_AT = re.compile(r"^oneway\s+(?P<kind>\w+).*@\s*(?P<x>-?[\d.]+)\s+(?P<y>-?[\d.]+)"
                        r"\s+(?P<z>-?[\d.]+)\s+(?P<yaw>-?[\d.]+)\s*$", re.I)
SEGMENT = re.compile(r"^seg\s+(?P<name>\w+)", re.I)
RETURN_KINDS = ("lift", "drop", "shaft", "door")


@dataclass
class Note:
    text: str
    held: list[str]
    map: str = ""  # where it was made; empty for the scenario's own map


@dataclass
class Attempt:
    """One run of a scenario: its notes, then its verdict (empty while open)."""
    map: str
    entry: str
    notes: list[Note] = field(default_factory=list)
    verdict: str = ""
    final: str = ""
    held: list[str] = field(default_factory=list)


def held_after(given: str) -> list[str]:
    """What the scenario held beyond the crowbar, from the 8th field."""
    held: list[str] = []
    for step in (s.strip() for s in given.split(";") if s.strip()):
        if step.startswith("-"):
            if step[1:] in held:
                held.remove(step[1:])
        elif step not in held:
            held.append(step)
    return held


def read_attempts(lines: list[str]) -> dict[str, Attempt]:
    """The latest attempt per scenario title. A pass or fail closes one; notes
    after it start the next."""
    latest: dict[str, Attempt] = {}
    open_: dict[str, Attempt] = {}
    for line in lines:
        parts = line.split("|")
        if len(parts) < 7 or parts[6] != GROUP:
            continue
        if match := TITLE.match(parts[2]):
            where, entry = match["map"], match["entry"]
        elif match := CHAPTER_TITLE.match(parts[2]):
            where, entry = "", f"{match['chapter']} {match['n']} ({match['how']})"
        else:
            continue
        title, verdict, note = parts[2], parts[3], parts[4]
        given = parts[7] if len(parts) > 7 else ""
        attempt = open_.setdefault(title, Attempt(where, entry))
        if verdict == "note":
            prefix = MAP_PREFIX.match(note)
            attempt.notes.append(Note(note[prefix.end():] if prefix else note,
                                      held_after(given), prefix["map"] if prefix else ""))
        elif verdict in ("pass", "fail"):
            attempt.verdict, attempt.final, attempt.held = verdict, note, held_after(given)
            latest[title] = open_.pop(title)
    for title, attempt in open_.items():
        # Notes with no verdict yet: newer than any closed attempt.
        latest[title] = attempt
    return latest


def candidates(what: str, held: list[str], groups: dict[str, list[str]]) -> list[str]:
    """Requirement groups that could be the gate, narrowest first."""
    named = what.strip().strip("`")
    if named in groups:
        return [named]
    items = [i for i in held if i.lower() == named.lower()] or held
    if not items:
        return []
    found = [g for g, members in groups.items() if all(i in members for i in items)]
    return sorted(found, key=lambda g: (len(groups[g]), g))


@dataclass
class Draft:
    """What the notes say about one map."""
    map: str
    labels: dict[int, str]  # T number -> transition id
    gates: dict[str, list[tuple[str, list[str], str]]] = field(default_factory=dict)
    one_way: list[dict] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    rows: list[tuple[str, ...]] = field(default_factory=list)


def label_order(transitions: list[dict], map_name: str) -> dict[int, str]:
    """`T<n>` -> id, in the order the harness labels them: by id number."""
    ids = sorted((t["id"] for t in transitions if t["map"] == map_name),
                 key=lambda i: int(i.rpartition(":")[2]))
    return {n: i for n, i in enumerate(ids, 1)}


def by_map(attempts: list[Attempt]) -> dict[str, list[Attempt]]:
    """Each attempt's notes under the map each was made on. An attempt with no
    notes stays under its own map, when it has one."""
    out: dict[str, list[Attempt]] = {}
    for attempt in attempts:
        maps: dict[str, list[Note]] = {}
        for note in attempt.notes:
            maps.setdefault(note.map or attempt.map, []).append(note)
        if not maps and attempt.map:
            maps[attempt.map] = []
        for map_name, notes in maps.items():
            if map_name:
                out.setdefault(map_name, []).append(Attempt(
                    map_name, attempt.entry, notes, attempt.verdict, attempt.final,
                    attempt.held))
    return out


def draft_map(map_name: str, attempts: list[Attempt], transitions: list[dict],
              groups: dict[str, list[str]]) -> Draft:
    draft = Draft(map_name, label_order(transitions, map_name))
    for attempt in sorted(attempts, key=lambda a: a.entry):
        for note in attempt.notes:
            held = ", ".join(note.held) or "crowbar only"
            text = note.text.strip()
            proposed = ""
            if m := NEEDS.match(text):
                tid = draft.labels.get(int(m["n"]))
                options = candidates(m["what"], note.held, groups)
                proposed = options[0] if options else "?"
                if tid is None:
                    draft.comments.append(f"{attempt.entry}: no T{m['n']} here: {text}")
                else:
                    draft.gates.setdefault(tid, []).append((attempt.entry, options, text))
            elif m := ONE_WAY_AT.match(text):
                kind = m["kind"].lower()
                draft.one_way.append({
                    "from": "?", "to": "?", "one_way": True,
                    "return": {"at": [round(float(m[a])) for a in "xyz"],
                               "yaw": round(float(m["yaw"])) % 360,
                               "kind": kind if kind in RETURN_KINDS else "?"},
                })
                proposed = "one_way edge"
            elif m := ONE_WAY_T.match(text):
                tid = draft.labels.get(int(m["n"]), f"T{m['n']}")
                draft.comments.append(f"{tid} one-way {m['kind'] or '?'} "
                                      f"(from {attempt.entry}): override its two_way")
                proposed = "transition override"
            elif m := SEGMENT.match(text):
                draft.comments.append(f"segment {m['name']} (from {attempt.entry}): {text}")
                proposed = "segment"
            else:
                draft.comments.append(f"{attempt.entry}: {text}")
            draft.rows.append((map_name, attempt.entry, attempt.verdict or "open",
                               held, text, proposed))
        if not attempt.notes:
            draft.rows.append((map_name, attempt.entry, attempt.verdict or "open",
                               ", ".join(attempt.held) or "crowbar only",
                               attempt.final or "(no notes)", ""))
        if attempt.verdict == "fail":
            draft.comments.append(f"{attempt.entry} failed: {attempt.final}")
    return draft


def fragment(draft: Draft) -> dict:
    """The proposed `MAP_LOGIC` entry: a start segment holding every transition
    nothing gates, and one segment per gated transition behind its gate."""
    segments = ["start"]
    placed: dict[str, str] = {}
    edges: list[dict] = []
    for tid in draft.labels.values():
        if tid not in draft.gates:
            placed[tid] = "start"
            continue
        name = "to_" + tid.rpartition(":")[2]
        segments.append(name)
        placed[tid] = name
        options = draft.gates[tid][0][1]
        edges.append({"from": "start", "to": name, "always": options[:1] or ["?"]})
        edges.append({"from": name, "to": "start"})
    edges.extend(draft.one_way)
    return {"segments": segments, "transitions": placed, "edges": edges}


def render(draft: Draft) -> str:
    """The fragment as Python source, comments included."""
    lines = [f"    {draft.map!r}: {{"]
    body = fragment(draft)
    lines.append(f"        \"segments\": {body['segments']!r},")
    lines.append(f"        \"transitions\": {body['transitions']!r},")
    lines.append("        \"edges\": [")
    for edge in body["edges"]:
        note = ""
        if edge.get("always"):
            tid = next(t for t, s in body["transitions"].items() if s == edge["to"])
            notes = draft.gates[tid]
            others = sorted({g for _, opts, _ in notes for g in opts[1:]})
            note = "  # " + "; ".join(f"{e}: {t}" for e, _, t in notes) + (
                f" (or: {', '.join(others)})" if others else "")
        lines.append(f"            {edge!r},{note}")
    lines.append("        ],")
    lines.append("        # \"tier\": set by hand (3.3).")
    for comment in draft.comments:
        lines.append(f"        # {comment}")
    lines.append("    },")
    return "\n".join(lines)


def current_map_logic() -> dict[str, dict]:
    sys.path.insert(0, str(REPO / "tools"))
    from campaigns import KNOWN_CAMPAIGNS
    return {m: v for c in KNOWN_CAMPAIGNS for m, v in c.map_logic.items()}


def default_results() -> Path:
    root = Path(os.environ.get("HL_ROOT") or LINUX_GAME_ROOT)
    return root / "hlap" / "archipelago" / "aptest_results.txt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=None,
                        help="aptest_results.txt (default: the installed mod's, "
                             "under HL_ROOT or the Linux Steam path)")
    parser.add_argument("--diff", action="store_true",
                        help="compare each draft against the current map_logic")
    parser.add_argument("maps", nargs="*", help="only these maps")
    args = parser.parse_args(argv)
    results = args.results or default_results()
    if not results.is_file():
        parser.error(f"{results} not found")

    data = json.loads(CAMPAIGN_JSON.read_text(encoding="utf-8"))
    attempts = read_attempts(results.read_text(encoding="utf-8").splitlines())
    grouped = {m: a for m, a in by_map(list(attempts.values())).items()
               if not args.maps or m in args.maps}
    if not grouped:
        print("No maplogic results.")
        return 0
    drafts = [draft_map(m, a, data["transitions"], data["requirement_groups"])
              for m, a in sorted(grouped.items())]

    if args.diff:
        current = current_map_logic()
        for draft in drafts:
            old = pprint.pformat(current.get(draft.map, {}), width=88).splitlines()
            new = pprint.pformat(fragment(draft), width=88).splitlines()
            diff = list(difflib.unified_diff(old, new, f"{draft.map} (current)",
                                             f"{draft.map} (draft)", lineterm=""))
            print("\n".join(diff) if diff else f"{draft.map}: unchanged")
        return 0

    header = ("map", "entry", "verdict", "held", "note", "proposed")
    rows = [header] + [row for d in drafts for row in d.rows]
    widths = [min(40, max(len(r[i]) for r in rows)) for i in range(len(header))]
    for row in rows:
        print("  ".join(cell[:40].ljust(w) for cell, w in zip(row, widths)).rstrip())
    print()
    print("MAP_LOGIC = {")
    for draft in drafts:
        print(render(draft))
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
