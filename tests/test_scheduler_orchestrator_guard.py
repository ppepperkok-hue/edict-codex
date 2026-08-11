"""Scheduler guard tests for the Codex orchestrator integration.

Two regression cases found during the real sub-agent drill (M10):

1. CLI writes (state/progress/todo) refresh ``updatedAt`` but not the
   scheduler heartbeat, so the periodic scanner treated active tasks as
   stalled and auto-retried/escalated/rolled them back.
2. While the orchestrator is consuming a queued dispatch entry, the
   scanner must stay out: it was enqueueing duplicate retries and rolling
   back a task that was actively being worked on.
"""
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'dashboard'))
sys.path.insert(0, str(ROOT / 'scripts'))


def _setup_server(monkeypatch, tmp_path, tasks=None, queue_entries=None):
    """Bootstrap server module with an isolated data directory."""
    import server as srv

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    tasks_path = data_dir / 'tasks_source.json'
    tasks_path.write_text(
        json.dumps(tasks or [], ensure_ascii=False), encoding='utf-8'
    )
    (data_dir / 'agent_config.json').write_text('{}', encoding='utf-8')
    if queue_entries is not None:
        (data_dir / 'dispatch_queue.json').write_text(
            json.dumps(queue_entries, ensure_ascii=False), encoding='utf-8'
        )

    monkeypatch.setattr(srv, 'DATA', data_dir)
    monkeypatch.setattr(srv, '_ACTIVE_TASK_DATA_DIR', data_dir)
    monkeypatch.setattr(srv, 'SCRIPTS', tmp_path / 'scripts')
    monkeypatch.setattr(srv, '_trigger_refresh', lambda: None)
    monkeypatch.setattr(srv, 'dispatch_for_state', lambda *a, **kw: None)
    monkeypatch.setattr(srv, 'wake_agent', lambda *a, **kw: None)
    return srv, data_dir, tasks_path


def _old_ts(seconds=700):
    return (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(seconds=seconds)
    ).isoformat()


def _task(task_id, updated_at, last_progress_at):
    return {
        'id': task_id,
        'title': '调度守卫测试',
        'state': 'Zhongshu',
        'org': '中书省',
        'updatedAt': updated_at,
        '_scheduler': {
            'enabled': True,
            'stallThresholdSec': 600,
            'maxRetry': 2,
            'retryCount': 0,
            'escalationLevel': 0,
            'autoRollback': True,
            'lastProgressAt': last_progress_at,
            'stallSince': None,
            'lastDispatchStatus': 'idle',
            'rollbackCount': 0,
            'snapshot': {
                'state': 'Taizi',
                'org': '太子',
                'now': '',
                'savedAt': last_progress_at,
                'note': 'init',
            },
        },
    }


def test_scan_uses_recent_cli_write_as_progress(monkeypatch, tmp_path):
    """A task whose last CLI write is fresh must not be treated as stalled."""
    srv, _, _ = _setup_server(
        monkeypatch,
        tmp_path,
        tasks=[_task('T-FRESH', updated_at=_old_ts(30), last_progress_at=_old_ts(700))],
        queue_entries=[],
    )

    result = srv.handle_scheduler_scan(threshold_sec=600)
    assert result['ok'] is True
    assert result['count'] == 0


def test_scan_skips_task_with_queued_dispatch(monkeypatch, tmp_path):
    """A stalled-looking task with a queued dispatch must be left alone."""
    stale = _old_ts(700)
    srv, _, _ = _setup_server(
        monkeypatch,
        tmp_path,
        tasks=[_task('T-INF', updated_at=stale, last_progress_at=stale)],
        queue_entries=[
            {
                'at': stale,
                'agentId': 'zhongshu',
                'taskId': 'T-INF',
                'trigger': 'state-transition',
                'message': '请按职责处理',
                'status': 'queued',
            }
        ],
    )

    result = srv.handle_scheduler_scan(threshold_sec=600)
    assert result['ok'] is True
    assert result['count'] == 0


def test_scan_retries_only_when_really_stalled(monkeypatch, tmp_path):
    """Baseline: without recent writes or queued dispatch, retry fires."""
    stale = _old_ts(700)
    srv, _, tasks_path = _setup_server(
        monkeypatch,
        tmp_path,
        tasks=[_task('T-STALE', updated_at=stale, last_progress_at=stale)],
        queue_entries=[],
    )

    result = srv.handle_scheduler_scan(threshold_sec=600)
    assert result['count'] >= 1

    data = json.loads(tasks_path.read_text(encoding='utf-8'))
    assert data[0]['_scheduler']['retryCount'] == 1
