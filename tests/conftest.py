"""Shared pytest isolation for Edict-Codex runtime data.

``scripts/kanban_update.py`` resolves its runtime files from the checkout
(``_BASE / "data"``). Individual tests redirect ``TASKS_FILE`` and
``QUEUE_FILE``, but ``AUDIT_FILE`` and the refresh trigger kept pointing at
the real ``data/`` directory, so running the suite appended to the ignored
``data/audit_log.json`` and forked ``refresh_live_data.py``, which rewrote
``data/live_status.json``.

Two layers keep tests off the checkout's runtime data:

* the session fixture neutralises ``_trigger_refresh`` for the whole session,
  including dashboard daemon threads that can outlive a per-test monkeypatch;
* the function fixture redirects the kanban audit/signal paths to ``tmp_path``.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# (module, original _trigger_refresh) pairs installed for the session.
_PATCHED_REFRESH = []


def _kanban_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import kanban_update

    return kanban_update


def _disable_background_refresh():
    """Replace every loaded module's ``_trigger_refresh`` with a no-op.

    Called at session start and again per test so modules imported later are
    covered. Patching is session-wide on purpose: dashboard dispatch starts
    daemon threads, and a late thread must not fork ``refresh_live_data.py``
    against the checkout after a test's monkeypatch was already undone.
    """
    for module in (_kanban_module(), sys.modules.get("server")):
        if module is None:
            continue
        refresh = getattr(module, "_trigger_refresh", None)
        if not callable(refresh):
            continue
        if any(patched is module for patched, _ in _PATCHED_REFRESH):
            continue
        _PATCHED_REFRESH.append((module, refresh))
        module._trigger_refresh = lambda: None


@pytest.fixture(scope="session", autouse=True)
def session_wide_no_background_refresh():
    _disable_background_refresh()
    yield
    for module, refresh in _PATCHED_REFRESH:
        module._trigger_refresh = refresh
    _PATCHED_REFRESH.clear()


@pytest.fixture(autouse=True)
def isolate_kanban_runtime(tmp_path, monkeypatch):
    """Keep kanban audit/signal side effects inside ``tmp_path``."""
    _disable_background_refresh()
    kb = _kanban_module()
    runtime = tmp_path / "kanban_runtime"
    runtime.mkdir()
    monkeypatch.setattr(kb, "AUDIT_FILE", runtime / "audit_log.json")
    monkeypatch.setattr(kb, "_REFRESH_SIGNAL_FILE", runtime / ".refresh_pending")
    monkeypatch.setattr(kb, "REFRESH_SCRIPT", runtime / "refresh_live_data.py")
