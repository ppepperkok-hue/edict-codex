"""Regression tests for CLI Windows console compatibility (GBK pipes)."""
import os
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "kanban_update.py"


def _run_with_gbk(*args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "gbk"
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        env=env,
        cwd=str(ROOT),
        **kwargs,
    )


def test_help_does_not_crash_under_gbk():
    """--help must print (with emoji in the docstring) even when stdout is GBK."""
    result = _run_with_gbk("--help")
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "看板任务更新工具" in result.stdout.decode("utf-8", "replace")


def test_unknown_command_exits_cleanly_under_gbk():
    result = _run_with_gbk("no-such-command")
    assert result.returncode == 1, result.stderr.decode("utf-8", "replace")
    assert "看板任务更新工具" in result.stdout.decode("utf-8", "replace")
