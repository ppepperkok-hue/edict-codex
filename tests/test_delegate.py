"""Tests for the delegation protocol (M8/M10): cmd_delegate, depth/circle
guards, and cmd_delegate_result write-back to the parent task memory."""

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
    monkeypatch.setattr(kb, "TASKS_FILE", tasks_file)
    monkeypatch.setattr(kb, "TASK_MEMORY_DIR", data / "task_memory")
    monkeypatch.setattr(kb, "MEMORY_DIR", data / "agent_memory")
    monkeypatch.setattr(kb, "QUEUE_FILE", data / "dispatch_queue.json")
    cfg = {
        "agents": [
            {"id": "taizi", "allowAgents": ["zhongshu"]},
            {"id": "zhongshu", "allowAgents": ["menxia", "shangshu"]},
            {"id": "menxia", "allowAgents": ["shangshu", "zhongshu"]},
            {"id": "shangshu", "allowAgents": ["hubu", "libu", "bingbu", "xingbu", "gongbu", "libu_hr"]},
            {"id": "bingbu", "allowAgents": []},
        ]
    }
    (data / "agent_config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return data


def _load(tmp_path):
    tasks_file = tmp_path / "data" / "tasks_source.json"
    return json.loads(tasks_file.read_text(encoding="utf-8"))


def test_delegate_creates_subtask_with_metadata(tmp_path, monkeypatch):
    data = _install(tmp_path, monkeypatch)
    kb.cmd_create("JJC-PARENT-01", "测试父任务创建", "Assigned", "尚书省", "尚书令")
    kb.cmd_delegate("JJC-PARENT-01", "shangshu", "bingbu", "审查示例代码", "返回风险清单")

    tasks = _load(tmp_path)
    sub = next(t for t in tasks if t.get("type") == "delegation")
    assert sub["parent_task"] == "JJC-PARENT-01"
    assert sub["state"] == "Doing"
    assert sub["delegation"]["to"] == "bingbu"
    assert sub["delegation"]["instruction"] == "审查示例代码"
    assert sub["delegation"]["return_spec"] == "返回风险清单"
    assert sub["delegation"]["delegation_depth"] == 1
    assert sub["delegation"]["delegation_path"] == ["shangshu", "bingbu"]


def test_delegate_rejects_circle(tmp_path, monkeypatch, capsys):
    _install(tmp_path, monkeypatch)
    kb.cmd_create("JJC-CIRCLE-01", "测试循环委派防护", "Assigned", "尚书省", "尚书令")
    kb.cmd_delegate("JJC-CIRCLE-01", "shangshu", "bingbu", "指令1")
    tasks = _load(tmp_path)
    sub = next(t for t in tasks if t.get("type") == "delegation")
    sub_id = sub["id"]

    kb.cmd_delegate(sub_id, "bingbu", "shangshu", "指令2")
    tasks = _load(tmp_path)
    delegations = [t for t in tasks if t.get("type") == "delegation"]
    assert len(delegations) == 1, "circular delegation must be rejected"


def test_delegate_result_writes_back_to_parent_memory(tmp_path, monkeypatch):
    data = _install(tmp_path, monkeypatch)
    kb.cmd_create("JJC-PARENT-02", "测试委派结果回写", "Assigned", "尚书省", "尚书令")
    kb.cmd_delegate("JJC-PARENT-02", "shangshu", "libu", "写文档", "返回文档路径")
    tasks = _load(tmp_path)
    sub = next(t for t in tasks if t.get("type") == "delegation")
    sub_id = sub["id"]

    kb.cmd_delegate_result(sub_id, "docs/report.md")

    tasks = _load(tmp_path)
    sub_after = next(t for t in tasks if t["id"] == sub_id)
    assert sub_after["state"] == "Done"
    assert sub_after["delegation_result"] == "docs/report.md"

    memo_file = data / "task_memory" / "JJC-PARENT-02.json"
    assert memo_file.exists()
    memo = json.loads(memo_file.read_text(encoding="utf-8"))
    chain = memo["context_chain"]
    assert chain[-1]["agent"] == "libu"
    assert "docs/report.md" in chain[-1]["key_decisions"][0]


def test_delegate_enforces_allow_agents_matrix(tmp_path, monkeypatch, capsys):
    _install(tmp_path, monkeypatch)
    kb.cmd_create("JJC-PARENT-03", "权限矩阵委派验证", "Assigned", "尚书省", "尚书令")

    # Leaf ministry must not delegate (empty allowAgents -> recursion stop).
    kb.cmd_delegate("JJC-PARENT-03", "bingbu", "hubu", "越权委派")
    tasks = _load(tmp_path)
    delegations = [t for t in tasks if t.get("type") == "delegation"]
    assert len(delegations) == 0
    assert "无权委派" in capsys.readouterr().out

    # Unknown from-agent is rejected.
    kb.cmd_delegate("JJC-PARENT-03", "stranger", "hubu", "未知来源")
    assert "不存在" in capsys.readouterr().out

    # Authorized delegation still works.
    kb.cmd_delegate("JJC-PARENT-03", "shangshu", "bingbu", "审查代码", "返回风险清单")
    tasks = _load(tmp_path)
    assert any(t.get("type") == "delegation" for t in tasks)
