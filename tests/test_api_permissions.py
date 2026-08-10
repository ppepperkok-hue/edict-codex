"""Tests for the X-Agent-ID write-permission middleware."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'dashboard'))
sys.path.insert(0, str(ROOT / 'scripts'))

import server as srv


def _install_runtime(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [
            {'id': 'taizi', 'allowAgents': ['zhongshu']},
            {'id': 'zhongshu', 'allowAgents': ['menxia', 'shangshu']},
            {'id': 'menxia', 'allowAgents': ['shangshu', 'zhongshu']},
            {
                'id': 'shangshu',
                'allowAgents': ['zhongshu', 'menxia', 'hubu', 'libu', 'bingbu', 'xingbu', 'gongbu', 'libu_hr'],
            },
            {'id': 'hubu', 'allowAgents': ['shangshu']},
            {'id': 'libu', 'allowAgents': ['shangshu']},
            {'id': 'libu_hr', 'allowAgents': ['shangshu']},
            {'id': 'zaochao', 'allowAgents': []},
        ]
    }), encoding='utf-8')
    tasks = [{
        'id': 'JJC-T-001',
        'title': '礼仪文书',
        'state': 'Doing',
        'org': '礼部',
    }]
    (data_dir / 'tasks_source.json').write_text(json.dumps(tasks), encoding='utf-8')
    monkeypatch.setattr(srv, 'DATA', data_dir)
    monkeypatch.setattr(
        srv,
        'load_tasks',
        lambda: json.loads((data_dir / 'tasks_source.json').read_text(encoding='utf-8')),
    )
    return data_dir


def test_missing_header_rejected_on_agent_channel(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    result = srv._guard_agent_write('', '/api/task-todos', {'taskId': 'JJC-T-001'})
    assert result is not None
    assert 'X-Agent-ID' in result['error']


def test_unknown_agent_rejected(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    result = srv._guard_agent_write('hacker', '/api/task-todos', {'taskId': 'JJC-T-001'})
    assert result is not None
    assert 'unknown agent' in result['error']


def test_invalid_agent_id_rejected(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    result = srv._guard_agent_write('../evil', '/api/task-todos', {})
    assert result is not None


def test_task_outside_org_rejected(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    result = srv._guard_agent_write('zhongshu', '/api/task-todos', {'taskId': 'JJC-T-001'})
    assert result is not None
    assert '无权' in result['error']


def test_task_owner_agent_allowed(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    assert srv._guard_agent_write('libu', '/api/task-todos', {'taskId': 'JJC-T-001'}) is None


def test_taizi_has_full_authority(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    assert srv._guard_agent_write('taizi', '/api/create-task', {}) is None
    assert srv._guard_agent_write('taizi', '/api/set-model', {}) is None
    assert srv._guard_agent_write('taizi', '/api/task-todos', {'taskId': 'JJC-T-001'}) is None


def test_agent_wake_respects_allow_list(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    assert srv._guard_agent_write('menxia', '/api/agent-wake', {'agentId': 'shangshu'}) is None
    assert srv._guard_agent_write('menxia', '/api/agent-wake', {'agentId': 'hubu'}) is not None
    assert srv._guard_agent_write('zaochao', '/api/agent-wake', {'agentId': 'shangshu'}) is not None
    assert srv._guard_agent_write('shangshu', '/api/agent-wake', {'agentId': 'libu'}) is None


def test_create_task_restricted_to_taizi(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    result = srv._guard_agent_write('zhongshu', '/api/create-task', {})
    assert result is not None
    assert '仅太子' in result['error']


def test_model_panel_restricted_to_hr(tmp_path, monkeypatch):
    _install_runtime(tmp_path, monkeypatch)
    assert srv._guard_agent_write('hubu', '/api/set-model', {}) is not None
    assert srv._guard_agent_write('libu_hr', '/api/set-model', {}) is None


def test_http_agent_channel_requires_header(tmp_path, monkeypatch):
    import threading
    import time
    from http.client import HTTPConnection
    from http.server import HTTPServer

    data_dir = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, '_ACTIVE_TASK_DATA_DIR', data_dir)

    port = 18972
    httpd = HTTPServer(('127.0.0.1', port), srv.Handler)
    thread = threading.Thread(target=httpd.handle_request, daemon=True)
    thread.start()
    time.sleep(0.1)

    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request(
        'POST',
        '/api/task-todos',
        body=json.dumps({'taskId': 'JJC-T-001', 'todos': []}),
        headers={'Content-Type': 'application/json'},
    )
    resp = conn.getresponse()
    body = json.loads(resp.read())
    conn.close()
    httpd.server_close()

    assert resp.status == 403
    assert 'X-Agent-ID' in body['error']
