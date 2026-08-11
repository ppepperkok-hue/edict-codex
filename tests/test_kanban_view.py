"""Tests for M7 read-only CLI commands: task / memo / memory-view / queue-purge."""

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import kanban_update as kb


def _install(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    tasks_file = data / "tasks_source.json"
    tasks_file.write_text("[]", encoding="utf-8")
    queue_file = data / "dispatch_queue.json"
    monkeypatch.setattr(kb, "TASKS_FILE", tasks_file)
    monkeypatch.setattr(kb, "QUEUE_FILE", queue_file)
    monkeypatch.setattr(kb, "TASK_MEMORY_DIR", data / "task_memory")
    monkeypatch.setattr(kb, "MEMORY_DIR", data / "agent_memory")
    return data


def test_task_view_prints_task_summary(tmp_path, monkeypatch, capsys):
    _install(tmp_path, monkeypatch)
    kb.cmd_create("JJC-TEST-VIEW-01", "查看任务测试", "Zhongshu", "中书省", "中书令")
    kb.cmd_task_view("JJC-TEST-VIEW-01")
    out = capsys.readouterr().out
    assert '"id": "JJC-TEST-VIEW-01"' in out
    assert '"state": "Zhongshu"' in out


def test_task_view_missing_task(tmp_path, monkeypatch, capsys):
    _install(tmp_path, monkeypatch)
    kb.cmd_task_view("JJC-NOT-FOUND")
    assert "任务不存在" in capsys.readouterr().out


def test_memo_view_roundtrip(tmp_path, monkeypatch, capsys):
    data = _install(tmp_path, monkeypatch)
    kb.cmd_create("JJC-TEST-MEMO-01", "记忆测试任务", "Zhongshu", "中书省", "中书令")
    kb.cmd_task_memo("JJC-TEST-MEMO-01", "zhongshu", "方案A", "风险1")
    kb.cmd_memo_view("JJC-TEST-MEMO-01")
    out = capsys.readouterr().out
    assert "context_chain" in out
    assert "zhongshu" in out
    assert (data / "task_memory" / "JJC-TEST-MEMO-01.json").exists()


def test_memory_view_roundtrip_and_validation(tmp_path, monkeypatch, capsys):
    data = _install(tmp_path, monkeypatch)
    kb.cmd_memory("menxia", "feedback", "方案常缺回滚", "JJC-TEST-MEMO-01", "review")
    kb.cmd_memory_view("menxia")
    out = capsys.readouterr().out
    assert '"memories"' in out
    assert "方案常缺回滚" in out

    kb.cmd_memory_view("../evil")
    assert "非法 agent_id" in capsys.readouterr().out


def test_queue_purge_keeps_newest(tmp_path, monkeypatch, capsys):
    data = _install(tmp_path, monkeypatch)
    kb.QUEUE_FILE.write_text(
        json.dumps([{"at": f"t{i}", "status": "queued"} for i in range(10)]),
        encoding="utf-8",
    )
    kb.cmd_queue_purge(3)
    remaining = json.loads(kb.QUEUE_FILE.read_text(encoding="utf-8"))
    assert len(remaining) == 3
    assert remaining[-1]["at"] == "t9"
    assert "3 条" in capsys.readouterr().out
