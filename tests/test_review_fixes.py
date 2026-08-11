"""Tests for review findings fixes (P1-2/P1-3/P2-4/P2-9)."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dashboard"))

import kanban_update as kb
import server as srv


def _install_kb(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    tf = data / "tasks_source.json"
    tf.write_text("[]", encoding="utf-8")
    qf = data / "dispatch_queue.json"
    monkeypatch.setattr(kb, "TASKS_FILE", tf)
    monkeypatch.setattr(kb, "QUEUE_FILE", qf)
    monkeypatch.setattr(kb, "TASK_MEMORY_DIR", data / "task_memory")
    monkeypatch.setattr(kb, "MEMORY_DIR", data / "agent_memory")
    cfg = {"agents": [{"id": "shangshu", "allowAgents": ["bingbu"]}]}
    (data / "agent_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return data


def test_task_updated_at_only(tmp_path, monkeypatch, capsys):
    _install_kb(tmp_path, monkeypatch)
    kb.cmd_create("JJC-FIX-01", "updated-at 工具验证", "Zhongshu", "中书省", "中书令")
    kb.cmd_task_view("JJC-FIX-01", updated_at_only=True)
    out = capsys.readouterr().out.strip()
    assert len(out) == len("2026-08-11T00:00:00.000000Z")


def test_dispatch_message_is_role_specific(tmp_path, monkeypatch):
    _install_kb(tmp_path, monkeypatch)
    kb.cmd_create("JJC-FIX-02", "角色化消息验证任务", "Zhongshu", "中书省", "中书令")
    kb.cmd_state("JJC-FIX-02", "Menxia", "提交门下")
    queue = json.loads(kb.QUEUE_FILE.read_text(encoding="utf-8"))
    menxia = next(q for q in queue if q["agentId"] == "menxia" and q["taskId"] == "JJC-FIX-02")
    assert "请审议中书省方案" in menxia["message"]
    assert "请勿重复创建" in menxia["message"]


def test_three_reject_rule_cli(tmp_path, monkeypatch, caplog):
    _install_kb(tmp_path, monkeypatch)
    kb.cmd_create("JJC-FIX-03", "三封强准 CLI 验证", "Zhongshu", "中书省", "中书令")
    kb.cmd_state("JJC-FIX-03", "Menxia", "提交")
    tasks = json.loads(kb.TASKS_FILE.read_text(encoding="utf-8"))
    tasks[0]["review_round"] = 3
    kb.TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")

    kb.cmd_state("JJC-FIX-03", "Zhongshu", "第4次封驳")
    tasks = json.loads(kb.TASKS_FILE.read_text(encoding="utf-8"))
    assert tasks[0]["state"] == "Menxia", "round>=3 封驳必须被拒绝"
    assert any("三封强准" in r.message for r in caplog.records)


def _install_srv(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    task = {
        "id": "JJC-FIX-04",
        "title": "三封强准 server 验证",
        "state": "Menxia",
        "org": "门下省",
        "review_round": 3,
        "flow_log": [],
    }
    (data / "tasks_source.json").write_text(
        json.dumps([task], ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(srv, "DATA", data)
    monkeypatch.setattr(
        srv, "load_tasks", lambda: json.loads((data / "tasks_source.json").read_text(encoding="utf-8"))
    )

    def save(tasks):
        (data / "tasks_source.json").write_text(
            json.dumps(tasks, ensure_ascii=False), encoding="utf-8"
        )

    monkeypatch.setattr(srv, "save_tasks", save)
    return data


def test_three_reject_rule_server(tmp_path, monkeypatch):
    _install_srv(tmp_path, monkeypatch)
    result = srv.handle_review_action("JJC-FIX-04", "reject", "再打回")
    assert result.get("ok") is False
    assert "三封强准" in result.get("error", "")


def test_enqueue_dispatch_dedup(tmp_path, monkeypatch):
    data = _install_srv(tmp_path, monkeypatch)
    queue = data / "dispatch_queue.json"
    queue.write_text("[]", encoding="utf-8")
    srv._enqueue_dispatch("zhongshu", "JJC-FIX-04", "msg1")
    srv._enqueue_dispatch("zhongshu", "JJC-FIX-04", "msg2")
    entries = json.loads(queue.read_text(encoding="utf-8"))
    assert len(entries) == 1, "same taskId+agentId queued entry must not duplicate"
