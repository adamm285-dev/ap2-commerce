"""
Gate for docs/MOCKS.md (see AGENTS.md, "Mocks").

Every MOCK(M-NNN) marker in the code must have a ledger entry, every entry must have markers in
exactly the files it lists, and every listed path::symbol must exist. The second half checks the
gate itself, so a broken checker can't pass silently.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_mocks", REPO_ROOT / "scripts" / "check_mocks.py")
check_mocks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_mocks)


def test_mock_ledger_matches_code():
    problems = check_mocks.check(REPO_ROOT)
    assert problems == [], "docs/MOCKS.md and the MOCK(...) markers disagree:\n" + "\n".join(problems)


# ── The gate itself ─────────────────────────────────────────────────────────


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entry(mid: str, where: str, skip: str = "") -> str:
    fields = {"Where": where, "What it fakes": "x", "Why": "x", "To make it real": "x"}
    lines = [f"### {mid}: example"] + [f"- **{k}:** {v}" for k, v in fields.items() if k != skip]
    return "\n".join(lines) + "\n\n"


def test_gate_passes_a_consistent_repo(tmp_path):
    _write(tmp_path, "backend/svc.py", "class Svc:\n    def call(self):\n        # MOCK(M-001): fake call\n        return 1\n")
    _write(tmp_path, "src/api.ts", "// MOCK(M-002): fake fetch\nexport async function load() {}\n")
    _write(tmp_path, "docs/MOCKS.md", _entry("M-001", "`backend/svc.py::Svc.call`") + _entry("M-002", "`src/api.ts::load`"))
    assert check_mocks.check(tmp_path) == []


def test_gate_reports_each_kind_of_drift(tmp_path):
    _write(tmp_path, "backend/a.py", (
        "def real_fn():\n"
        "    # MOCK(M-001): listed and defined\n"
        "    # MOCK(M-002): listed, symbol renamed away\n"
        "    # MOCK(M-009): no ledger entry\n"
        "    # MOCK(M-12): malformed\n"
        "    return 1\n"
    ))
    _write(tmp_path, "backend/c.py", "# MOCK(M-001): marker in a file the entry doesn't list\nx = 1\n")
    _write(tmp_path, "backend/tests/test_x.py", "# MOCK(M-777): test doubles are not scanned\n")
    _write(tmp_path, "docs/MOCKS.md", (
        _entry("M-001", "`backend/a.py::real_fn`")
        + _entry("M-002", "`backend/a.py::missing_fn`")
        + _entry("M-003", "`backend/gone.py::anything`")
        + _entry("M-004", "`backend/a.py::real_fn`")
        + _entry("M-005", "`backend/a.py::real_fn`", skip="Why")
        + _entry("M-001", "`backend/a.py::real_fn`")
    ))
    problems = "\n".join(check_mocks.check(tmp_path))

    assert "M-009: marker in backend/a.py has no entry" in problems
    assert "malformed marker MOCK(M-12)" in problems
    assert "M-001: marker in backend/c.py, but the entry's 'Where' doesn't list that file" in problems
    assert "M-001: appears more than once" in problems
    assert "M-002: missing_fn is not defined in backend/a.py" in problems
    assert "M-003: backend/gone.py does not exist" in problems
    assert "M-003: no MOCK(M-003) marker anywhere in the code" in problems
    assert "M-004: lists backend/a.py, but that file has no MOCK(M-004) marker" in problems
    assert "M-005: ledger entry is missing 'Why'" in problems
    assert "M-777" not in problems
