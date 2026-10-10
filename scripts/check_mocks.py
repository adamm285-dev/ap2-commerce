"""
Mock ledger gate: docs/MOCKS.md must agree with the MOCK(M-NNN) markers in the code.

Reports a problem when:
  - a marker's ID has no ledger entry, or a marker is malformed
  - a ledger entry has no marker anywhere in the code
  - an entry lists a file that has no marker for that ID, or a marker sits in a file its entry doesn't list
  - a listed path doesn't exist, or the listed symbol isn't defined in that file
  - an entry is missing one of its four fields, or an ID appears twice

    python scripts/check_mocks.py    # prints problems and exits 1 if the ledger and code disagree
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

LEDGER = "docs/MOCKS.md"
SCAN_DIRS = ("backend", "scripts", "src")
CODE_SUFFIXES = {".py", ".ts", ".tsx"}
# Test doubles and vendored code are not product mocks
EXCLUDED_DIRS = {"node_modules", "dist", "__pycache__", "vendor", "tests"}
FIELDS = ("Where", "What it fakes", "Why", "To make it real")

ENTRY_RE = re.compile(r"^###\s+(M-\d{3})\b", re.MULTILINE)
MARKER_RE = re.compile(r"(?:#|//)\s*MOCK\((M-\d{3})\)")
ANY_MARKER_RE = re.compile(r"(?:#|//)\s*MOCK\(([^)]*)\)")


def parse_ledger(text: str) -> Tuple[Dict[str, List[Tuple[str, str]]], List[str]]:
    """Returns ({id: [(path, symbol), ...]}, problems)."""
    entries: Dict[str, List[Tuple[str, str]]] = {}
    problems: List[str] = []
    headings = list(ENTRY_RE.finditer(text))
    for i, heading in enumerate(headings):
        mid = heading.group(1)
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[heading.end():end]
        if mid in entries:
            problems.append(f"{mid}: appears more than once in {LEDGER}")
        fields = {}
        for name in FIELDS:
            match = re.search(rf"^\s*-\s*\*\*{re.escape(name)}:\*\*\s*(.+)$", body, re.MULTILINE)
            if match and match.group(1).strip():
                fields[name] = match.group(1)
            else:
                problems.append(f"{mid}: ledger entry is missing '{name}'")
        where = []
        for item in re.findall(r"`([^`]+)`", fields.get("Where", "")):
            if "::" not in item:
                problems.append(f"{mid}: 'Where' item `{item}` is not path::symbol")
                continue
            path, symbol = item.split("::", 1)
            where.append((path.strip(), symbol.strip()))
        if "Where" in fields and not where:
            problems.append(f"{mid}: 'Where' lists no path::symbol")
        entries[mid] = where
    return entries, problems


def _code_files(root: Path, scan_dirs: Iterable[str]) -> Iterable[Path]:
    for d in scan_dirs:
        base = root / d
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix not in CODE_SUFFIXES or not path.is_file():
                continue
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts[:-1]):
                continue
            yield path


def find_markers(root: Path, scan_dirs: Iterable[str]) -> Tuple[Dict[str, Set[str]], List[str]]:
    """Returns ({id: {relative file paths}}, problems)."""
    markers: Dict[str, Set[str]] = {}
    problems: List[str] = []
    for path in _code_files(root, scan_dirs):
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for raw in ANY_MARKER_RE.findall(line):
                if not re.fullmatch(r"M-\d{3}", raw):
                    problems.append(f"{rel}:{lineno}: malformed marker MOCK({raw}); use MOCK(M-NNN)")
            for mid in MARKER_RE.findall(line):
                markers.setdefault(mid, set()).add(rel)
    return markers, problems


def _python_symbols(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: Set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(f"{node.name}.{sub.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _symbol_defined(path: Path, symbol: str) -> bool:
    if path.suffix == ".py":
        return symbol in _python_symbols(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.search(rf"\b(?:function|const|let|var|class)\s+{re.escape(symbol)}\b", text) is not None


def check(root: Path, scan_dirs: Iterable[str] = SCAN_DIRS) -> List[str]:
    """Returns every disagreement between the ledger and the code; empty means they match."""
    ledger_path = root / LEDGER
    if not ledger_path.is_file():
        return [f"{LEDGER} not found"]
    entries, problems = parse_ledger(ledger_path.read_text(encoding="utf-8"))
    markers, marker_problems = find_markers(root, scan_dirs)
    problems += marker_problems

    for mid in sorted(set(markers) - set(entries)):
        problems.append(f"{mid}: marker in {', '.join(sorted(markers[mid]))} has no entry in {LEDGER}")

    for mid, where in sorted(entries.items()):
        marked_files = markers.get(mid, set())
        listed_files = {path for path, _ in where}
        if not marked_files:
            problems.append(f"{mid}: no MOCK({mid}) marker anywhere in the code")
        for path in sorted(listed_files - marked_files):
            if (root / path).is_file():
                problems.append(f"{mid}: lists {path}, but that file has no MOCK({mid}) marker")
        for path in sorted(marked_files - listed_files):
            problems.append(f"{mid}: marker in {path}, but the entry's 'Where' doesn't list that file")
        for path, symbol in where:
            target = root / path
            if not target.is_file():
                problems.append(f"{mid}: {path} does not exist")
            elif not _symbol_defined(target, symbol):
                problems.append(f"{mid}: {symbol} is not defined in {path}")
    return problems


def main() -> int:
    problems = check(Path(__file__).resolve().parent.parent)
    if problems:
        print(f"{LEDGER} and the code disagree ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"{LEDGER} matches the MOCK markers in the code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
