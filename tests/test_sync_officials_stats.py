"""Tests for scripts/sync_officials_stats.py JSON aggregation."""
import json
import pathlib
import sys
import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import sync_officials_stats as stats


def _make_tasks():
    return [
        {
            'id': 'JJC-20260810-001',
            'title': '测试旨意一',
            'state': 'Done',
            'org': '礼部',
            'flow_log': [
                {'at': '2026-08-10T01:00:00Z', 'from': '皇上', 'to': '中书省'},
                {'at': '2026-08-10T02:00:00Z', 'from': '中书省', 'to': '礼部'},
            ],
            'progress_log': [
                {'agent': 'libu', 'at': '2026-08-10T02:30:00Z', 'tokens_in': 1000, 'tokens_out': 2000},
            ],
        },
        {
            'id': 'JJC-20260810-002',
            'title': '测试旨意二',
            'state': 'Doing',
            'org': '工部',
            'flow_log': [
                {'at': '2026-08-10T03:00:00Z', 'from': '皇上', 'to': '尚书省'},
                {'at': '2026-08-10T04:00:00Z', 'from': '尚书省', 'to': '工部'},
            ],
            'progress_log': [
                {'agent': 'gongbu', 'at': '2026-08-10T04:10:00Z', 'tokens_in': 500, 'tokens_out': 300},
                {'agent': 'gongbu', 'at': '2026-08-10T04:20:00Z', 'tokens_in': 200, 'tokens_out': 100},
            ],
        },
    ]


def test_scan_progress_aggregates_usage():
    usage = stats.scan_progress(_make_tasks(), 'gongbu')
    assert usage['tokens_in'] == 700
    assert usage['tokens_out'] == 400
    assert usage['messages'] == 2
    assert usage['sessions'] == 1
    assert usage['last_active'] is not None


def test_get_model_prefers_agent_override():
    cfg = {
        'defaultModel': 'openai/gpt-4o',
        'agents': [
            {'id': 'zhongshu', 'model': 'google/gemini-2.5-pro'},
            {'id': 'main', 'model': 'anthropic/claude-haiku-3-5'},
        ],
    }
    assert stats.get_model('zhongshu', cfg) == 'google/gemini-2.5-pro'
    assert stats.get_model('taizi', cfg) == 'anthropic/claude-haiku-3-5'
    assert stats.get_model('menxia', cfg) == 'openai/gpt-4o'


def test_calc_cost_uses_model_pricing():
    usage = {'tokens_in': 1_000_000, 'tokens_out': 1_000_000, 'cache_read': 0, 'cache_write': 0}
    assert stats.calc_cost(usage, 'openai/gpt-4o') == 12.5


def test_get_task_stats_counts_flow_and_participation():
    task_stats = stats.get_task_stats('礼部', _make_tasks())
    assert task_stats['tasks_done'] == 1
    assert task_stats['tasks_active'] == 0
    assert task_stats['flow_participations'] == 1
    assert [e['id'] for e in task_stats['participated_edicts']] == ['JJC-20260810-001']


def test_main_writes_payload(tmp_path, monkeypatch):
    tasks_path = tmp_path / 'tasks_source.json'
    tasks_path.write_text(json.dumps(_make_tasks()), encoding='utf-8')
    (tmp_path / 'agent_config.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(stats, 'DATA', tmp_path)
    stats.main()
    payload = json.loads((tmp_path / 'officials_stats.json').read_text(encoding='utf-8'))
    assert payload['totals']['tasks_done'] == 1
    assert payload['top_official']
    by_id = {item['id']: item for item in payload['officials']}
    assert by_id['gongbu']['tokens_in'] == 700
    assert by_id['gongbu']['tasks_active'] == 1


def test_build_heartbeat_uses_utc_timestamps():
    now = datetime.datetime.now(datetime.timezone.utc)
    active = stats.build_heartbeat({'last_ts': now - datetime.timedelta(minutes=1)})
    idle = stats.build_heartbeat({'last_ts': now - datetime.timedelta(hours=2)})
    unknown = stats.build_heartbeat({'last_ts': None})
    assert active['status'] == 'active'
    assert idle['status'] == 'idle'
    assert unknown['status'] == 'idle'
