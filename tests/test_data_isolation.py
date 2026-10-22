"""Guard: running the test suite must not mutate checkout runtime data.

``data/live_status.json`` and ``data/audit_log.json`` are ignored runtime
files, not fixtures. Historically the kanban tests redirected their task and
queue paths but still appended to the real audit log and forked
``refresh_live_data.py`` against the real data directory.

This guard snapshots the watched files, runs one representative test from each
affected module in a subprocess, and requires the snapshot to be byte-identical
afterwards. If isolation regresses, this test fails instead of silently
dirtying real runtime state.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WATCHED = ("live_status.json", "audit_log.json")
REPRESENTATIVE = [
    "tests/test_kanban.py::test_create_and_get",
    "tests/test_kanban_view.py::test_task_view_prints_task_summary",
    "tests/test_e2e_kanban.py::test_normal_title",
    "tests/test_review_fixes.py::test_task_updated_at_only",
    "tests/test_delegate.py::test_delegate_creates_subtask_with_metadata",
]


def _digest(path):
    if not path.exists():
        return None
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _audit_count():
    path = DATA / "audit_log.json"
    if not path.exists():
        return None
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unreadable"
    return len(entries) if isinstance(entries, list) else "not-a-list"


def _snapshot():
    signal = DATA / ".refresh_pending"
    return {
        "files": {name: _digest(DATA / name) for name in WATCHED},
        "audit_entries": _audit_count(),
        # A kanban write also touches this debounce signal; mtime catches it.
        "refresh_pending_mtime": signal.stat().st_mtime_ns if signal.exists() else None,
    }


def test_kanban_runtime_sinks_are_redirected(tmp_path):
    """The autouse fixture must point every kanban sink inside tmp_path."""
    import kanban_update as kb

    runtime = (tmp_path / "kanban_runtime").resolve()
    for attr in ("AUDIT_FILE", "_REFRESH_SIGNAL_FILE", "REFRESH_SCRIPT"):
        resolved = pathlib.Path(getattr(kb, attr)).resolve()
        resolved.relative_to(runtime)  # ValueError when isolation is missing

    signal = DATA / ".refresh_pending"
    before = signal.stat().st_mtime_ns if signal.exists() else None
    kb._trigger_refresh()
    after = signal.stat().st_mtime_ns if signal.exists() else None
    assert after == before, "ctrl refresh must not touch checkout data/"


def test_representative_tests_leave_runtime_data_unchanged():
    """Representative tests from the affected modules leave data/ untouched."""
    before = _snapshot()
    cmd = [
        sys.executable, "-m", "pytest", *REPRESENTATIVE,
        "-q", "-p", "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=300)
    output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"representative tests failed:\n{output}"

    after = _snapshot()
    assert after == before, (
        "representative tests modified ignored runtime data:\n"
        f"before={before}\nafter={after}\n{output}"
    )
