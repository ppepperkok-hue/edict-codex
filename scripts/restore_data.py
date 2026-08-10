#!/usr/bin/env python3
"""Restore runtime data from data/backups/ snapshots, safely.

Usage:
  python scripts/restore_data.py --list
  python scripts/restore_data.py --time latest
  python scripts/restore_data.py --time "YYYY-MM-DD HH:MM:SS"
  python scripts/restore_data.py --path <snapshot-dir>
  python scripts/restore_data.py --reset-config

Every restore first snapshots the current state (label=before-restore), then
restores files, touches the refresh signal and runs refresh_live_data.py.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

import backup_data

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / 'data'
DEFAULT_BACKUPS_DIR = DEFAULT_DATA_DIR / 'backups'
REFRESH_SCRIPT = PROJECT_ROOT / 'scripts' / 'refresh_live_data.py'
_LOCK_SUFFIX = '.lock'


def _is_within(parent: pathlib.Path, child: pathlib.Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def list_backups(backups_dir=None) -> list:
    return backup_data.list_backups(backups_dir or DEFAULT_BACKUPS_DIR)


def resolve_snapshot(selector: str, backups_dir=None):
    """Resolve 'latest', a timestamp prefix, or an exact snapshot name."""
    backups_dir = pathlib.Path(backups_dir) if backups_dir else DEFAULT_BACKUPS_DIR
    if not backups_dir.exists():
        return None
    snapshots = sorted(p for p in backups_dir.glob('backup_*') if p.is_dir())
    if not snapshots:
        return None
    if not selector or selector == 'latest':
        # Prefer user-created snapshots over safety snapshots produced by
        # restore itself (label=before-restore / before-reset-config).
        safety_labels = ('before-restore', 'before-reset-config')
        user_snapshots = [
            p
            for p in snapshots
            if (backup_data._read_manifest(p) or {}).get('label') not in safety_labels
        ]
        return (user_snapshots or snapshots)[-1]
    candidate = backups_dir / selector
    if candidate.is_dir():
        return candidate
    normalized = selector.replace('-', '').replace(':', '').replace(' ', '_')
    candidate = backups_dir / f'backup_{normalized}'
    if candidate.is_dir():
        return candidate
    matches = [p for p in snapshots if p.name.replace('backup_', '').startswith(normalized)]
    return matches[-1] if matches else None


def _copy_snapshot(snapshot_dir: pathlib.Path, data_dir: pathlib.Path) -> list:
    copied = []
    for path in sorted(snapshot_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == 'manifest.json' or path.name.endswith(_LOCK_SUFFIX):
            continue
        shutil.copy2(path, data_dir / path.name)
        copied.append(path.name)
    return copied


def _touch_refresh_signal(data_dir: pathlib.Path):
    (data_dir / '.refresh_pending').touch()


def restore(snapshot_dir, data_dir=None, backups_dir=None, refresh=True) -> dict:
    """Restore files from a snapshot; back up current state first."""
    data_dir = pathlib.Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    backups_dir = pathlib.Path(backups_dir) if backups_dir else DEFAULT_BACKUPS_DIR
    snapshot_dir = pathlib.Path(snapshot_dir)
    if not _is_within(backups_dir, snapshot_dir):
        raise ValueError(f'snapshot must live under backups dir: {snapshot_dir}')
    if not snapshot_dir.is_dir():
        raise FileNotFoundError(f'snapshot not found: {snapshot_dir}')

    data_dir.mkdir(parents=True, exist_ok=True)
    safety = backup_data.create_backup(
        data_dir=data_dir, backups_dir=backups_dir, label='before-restore'
    )
    copied = _copy_snapshot(snapshot_dir, data_dir)
    _touch_refresh_signal(data_dir)

    refreshed = False
    if refresh and REFRESH_SCRIPT.exists():
        try:
            subprocess.run(
                [sys.executable, str(REFRESH_SCRIPT)],
                capture_output=True,
                timeout=30,
            )
            refreshed = True
        except Exception:
            refreshed = False

    return {
        'ok': True,
        'snapshot': str(snapshot_dir),
        'safetyBackup': str(safety),
        'files': copied,
        'refreshed': refreshed,
    }


def reset_config(data_dir=None, backups_dir=None) -> dict:
    """Rebuild agent_config.json from the tracked config.default.json template."""
    data_dir = pathlib.Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    backups_dir = pathlib.Path(backups_dir) if backups_dir else DEFAULT_BACKUPS_DIR
    template = data_dir / 'config.default.json'
    if not template.exists():
        raise FileNotFoundError(f'config template not found: {template}')
    data_dir.mkdir(parents=True, exist_ok=True)
    safety = backup_data.create_backup(
        data_dir=data_dir, backups_dir=backups_dir, label='before-reset-config'
    )
    shutil.copy2(template, data_dir / 'agent_config.json')
    return {'ok': True, 'safetyBackup': str(safety), 'source': str(template)}


def main():
    parser = argparse.ArgumentParser(description='Restore runtime data from snapshots')
    parser.add_argument('--list', action='store_true', help='list available snapshots')
    parser.add_argument('--time', default='latest', help='snapshot selector (latest / timestamp)')
    parser.add_argument('--path', default=None, help='explicit snapshot directory')
    parser.add_argument('--no-refresh', action='store_true', help='skip refresh after restore')
    parser.add_argument('--reset-config', action='store_true', help='rebuild config from template')
    args = parser.parse_args()

    if args.list:
        for item in list_backups():
            print(
                f"{item['name']}  files={item['files']}  "
                f"createdAt={item['createdAt']}  label={item['label']}"
            )
        return
    if args.reset_config:
        print(json.dumps(reset_config(), ensure_ascii=False, indent=2))
        return

    snapshot_dir = pathlib.Path(args.path) if args.path else resolve_snapshot(args.time)
    if not snapshot_dir:
        print('no matching snapshot; run --list first', file=sys.stderr)
        sys.exit(1)
    result = restore(snapshot_dir, refresh=not args.no_refresh)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
