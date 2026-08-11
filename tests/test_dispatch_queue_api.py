"""Tests for the dispatch-queue stats endpoint helper (M9)."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'dashboard'))
sys.path.insert(0, str(ROOT / 'scripts'))

import server as srv


def _install_queue(tmp_path, monkeypatch, entries):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    queue_file = data_dir / 'dispatch_queue.json'
    queue_file.write_text(json.dumps(entries), encoding='utf-8')
    monkeypatch.setattr(srv, 'DATA', data_dir)
    return queue_file


def test_dispatch_queue_stats_counts(tmp_path, monkeypatch):
    _install_queue(tmp_path, monkeypatch, [
        {'at': 't1', 'agentId': 'zhongshu', 'status': 'queued'},
        {'at': 't2', 'agentId': 'menxia', 'status': 'dispatched'},
        {'at': 't3', 'agentId': 'bingbu', 'status': 'failed'},
        {'at': 't4', 'agentId': 'hubu', 'status': 'queued'},
    ])
    stats = srv._dispatch_queue_stats()
    assert stats['counts'] == {'queued': 2, 'dispatched': 1, 'failed': 1}
    assert len(stats['entries']) == 4


def test_dispatch_queue_stats_empty(tmp_path, monkeypatch):
    _install_queue(tmp_path, monkeypatch, [])
    stats = srv._dispatch_queue_stats()
    assert stats['counts'] == {'queued': 0, 'dispatched': 0, 'failed': 0}
    assert stats['entries'] == []


def test_dispatch_queue_stats_unknown_status_ignored(tmp_path, monkeypatch):
    _install_queue(tmp_path, monkeypatch, [
        {'at': 't1', 'status': 'queued'},
        {'at': 't2', 'status': 'weird'},
    ])
    stats = srv._dispatch_queue_stats()
    assert stats['counts']['queued'] == 1
