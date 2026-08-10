"""Tests for scripts/backup_data.py and scripts/restore_data.py."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import backup_data
import restore_data


def _make_runtime_dir(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'tasks_source.json').write_text('[{"id":"JJC-1"}]', encoding='utf-8')
    (data / 'agent_config.json').write_text('{"defaultModel":"x"}', encoding='utf-8')
    (data / '.refresh_pending').touch()
    (data / 'tasks_source.json.lock').touch()
    return data


def test_create_backup_excludes_locks_and_signals(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    target = backup_data.create_backup(data_dir=data, backups_dir=backups)

    names = {p.name for p in target.iterdir()}
    assert 'manifest.json' in names
    assert 'tasks_source.json' in names
    assert 'agent_config.json' in names
    assert '.refresh_pending' not in names
    assert 'tasks_source.json.lock' not in names
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['files']) == 2


def test_backup_rotation_keeps_newest(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    for index in range(12):
        (data / 'tasks_source.json').write_text(json.dumps([{'i': index}]), encoding='utf-8')
        backup_data.create_backup(data_dir=data, backups_dir=backups, keep=10)
    snapshots = sorted(p for p in backups.glob('backup_*') if p.is_dir())
    assert len(snapshots) == 10


def test_list_backups_sorted_by_name(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    backup_data.create_backup(data_dir=data, backups_dir=backups, label='first')
    backup_data.create_backup(data_dir=data, backups_dir=backups, label='second')
    items = restore_data.list_backups(backups)
    assert len(items) == 2
    assert items[0]['label'] == 'first'
    assert items[1]['label'] == 'second'


def test_restore_recovers_files_and_keeps_safety_backup(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    snapshot = backup_data.create_backup(data_dir=data, backups_dir=backups, label='baseline')
    (data / 'tasks_source.json').write_text('[]', encoding='utf-8')
    (data / 'agent_config.json').write_text('{}', encoding='utf-8')

    result = restore_data.restore(snapshot, data_dir=data, backups_dir=backups, refresh=False)

    assert result['ok'] is True
    assert json.loads((data / 'tasks_source.json').read_text(encoding='utf-8')) == [
        {'id': 'JJC-1'}
    ]
    assert (data / '.refresh_pending').exists()
    assert pathlib.Path(result['safetyBackup']).is_dir()


def test_restore_rejects_snapshot_outside_backups(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        restore_data.restore(outside, data_dir=data, backups_dir=backups)
        raise AssertionError('restore should reject snapshots outside backups dir')
    except ValueError:
        pass


def test_resolve_snapshot_selectors(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    snapshot = backup_data.create_backup(data_dir=data, backups_dir=backups)
    stamp = snapshot.name.replace('backup_', '')
    assert restore_data.resolve_snapshot('latest', backups) == snapshot
    assert restore_data.resolve_snapshot(stamp, backups) == snapshot
    assert restore_data.resolve_snapshot(stamp[:8], backups) == snapshot
    assert restore_data.resolve_snapshot('not-exist', backups) is None


def test_reset_config_rebuilds_from_template(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    (data / 'config.default.json').write_text(
        json.dumps({'defaultModel': 'template-model'}),
        encoding='utf-8',
    )
    result = restore_data.reset_config(data_dir=data, backups_dir=backups)
    assert result['ok'] is True
    assert json.loads((data / 'agent_config.json').read_text(encoding='utf-8')) == {
        'defaultModel': 'template-model'
    }


def test_latest_prefers_user_snapshot_over_safety_backup(tmp_path):
    data = _make_runtime_dir(tmp_path)
    backups = tmp_path / 'backups'
    user_snapshot = backup_data.create_backup(data_dir=data, backups_dir=backups, label='pre-drill')
    safety_snapshot = backup_data.create_backup(data_dir=data, backups_dir=backups, label='before-restore')

    assert restore_data.resolve_snapshot('latest', backups) == user_snapshot
    stamp = safety_snapshot.name.replace('backup_', '')
    assert restore_data.resolve_snapshot(stamp, backups) == safety_snapshot
