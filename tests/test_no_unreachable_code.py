"""Static check for statements that can never execute.

This exists because of a real bug: splitting a function left its entire body
indented inside an `except: ... return` block, so the client read game events and
returned without ever processing them or writing a snapshot. It was valid Python,
it imported cleanly, and pyflakes said nothing, so the only symptom was the
bridge silently doing nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SOURCES = sorted(
    path
    for directory in ("apworld", "tools", "tests")
    for path in (REPO / directory).rglob("*.py")
    if "__pycache__" not in path.parts
)

TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def unreachable_statements(tree: ast.AST) -> list[tuple[int, str]]:
    """Statements following an unconditional exit in the same block."""
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for index, statement in enumerate(block[:-1]):
                if isinstance(statement, TERMINATORS):
                    nxt = block[index + 1]
                    found.append((nxt.lineno, type(nxt).__name__))
    return found


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_unreachable_statements(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dead = unreachable_statements(tree)
    assert not dead, (
        f"{path.relative_to(REPO)} has code after an unconditional exit: "
        + ", ".join(f"line {line} ({kind})" for line, kind in dead)
    )


def test_the_check_detects_the_bug_it_was_written_for() -> None:
    source = """
def pump():
    try:
        events = read()
    except OSError:
        return

        for event in events:
            handle(event)
"""
    assert unreachable_statements(ast.parse(source))
