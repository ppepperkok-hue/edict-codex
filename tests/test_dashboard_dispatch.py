"""Tests for dashboard auto-dispatch queue integration (no OpenClaw CLI)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'dashboard'))
sys.path.insert(0, str(ROOT / 'scripts'))


def test_dispatch_records_queue_entry_and_scheduler_status(monkeypatch, tmp_path):
    """Dispatch should enqueue into dispatch_queue.json and mark scheduler queued."""
    import server as srv

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    task_id = 'JJC-20260415-004'
    task = {
        'id': task_id,
        'title': '小任务',
        'state': 'Taizi',
        'org': '太子',
        'updatedAt': '2026-04-15T15:34:16Z',
    }
    tasks_path = data_dir / 'tasks_source.json'
    tasks_path.write_text(json.dumps([task], ensure_ascii=False), encoding='utf-8')
    (data_dir / 'agent_config.json').write_text('{}', encoding='utf-8')

    monkeypatch.setattr(srv, 'DATA', data_dir)
    monkeypatch.setattr(srv, '_ACTIVE_TASK_DATA_DIR', data_dir)

    class ImmediateThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            if self.target:
                self.target()

    monkeypatch.setattr(srv.threading, 'Thread', ImmediateThread)

    srv.dispatch_for_state(task_id, task, 'Taizi', trigger='test')

    queue = json.loads((data_dir / 'dispatch_queue.json').read_text(encoding='utf-8'))
    assert queue[-1]['agentId'] == 'taizi'
    assert queue[-1]['taskId'] == task_id
    assert queue[-1]['status'] == 'queued'

    updated = json.loads(tasks_path.read_text(encoding='utf-8'))[0]
    sched = updated['_scheduler']
    assert sched['lastDispatchStatus'] == 'queued'
    assert sched['lastDispatchAgent'] == 'taizi'
    assert any('派发已入队' in item['remark'] for item in updated['flow_log'])
