#!/usr/bin/env python3
"""Snapshot runtime data/*.json files into data/backups/ (newest N kept).

Usage:
  python scripts/backup_data.py [--keep 10] [--label <name>]

Lock files, refresh signals and the backups directory itself are excluded.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import shutil

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / 'data'
DEFAULT_BACKUPS_DIR = DEFAULT_DATA_DIR / 'backups'

_EXCLUDE_NAMES = {'.refresh_pending', '.refresh_watcher_pid'}
_LOCK_SUFFIX = '.lock'


def _file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _snapshot_stamp() -> str:
    return datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')


def create_backup(data_dir=None, backups_dir=None, keep=10, label='') -> pathlib.Path:
    """Copy runtime files into a fresh snapshot dir and rotate old snapshots."""
    data_dir = pathlib.Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    backups_dir = pathlib.Path(backups_dir) if backups_dir else DEFAULT_BACKUPS_DIR
    backups_dir.mkdir(parents=True, exist_ok=True)

    target = backups_dir / f'backup_{_snapshot_stamp()}'
    if target.exists():
        raise FileExistsError(f'backup dir already exists: {target}')
    target.mkdir(parents=True)

    manifest = {
        'createdAt': datetime.datetime.now().astimezone().isoformat(),
        'label': label,
        'sourceDir': str(data_dir),
        'files': [],
    }
    for path in sorted(data_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name in _EXCLUDE_NAMES or path.name.endswith(_LOCK_SUFFIX):
            continue
        content = path.read_bytes()
        (target / path.name).write_bytes(content)
        manifest['files'].append({
            'name': path.name,
            'size': len(content),
            'sha256': _file_sha256(content),
        })

    (target / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    _rotate(backups_dir, max(1, keep))
    return target


def _rotate(backups_dir: pathlib.Path, keep: int):
    snapshots = sorted(p for p in backups_dir.glob('backup_*') if p.is_dir())
    for stale in snapshots[:-keep]:
        shutil.rmtree(stale)


def _read_manifest(snapshot_dir: pathlib.Path):
    manifest_path = snapshot_dir / 'manifest.json'
    try:
        return json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        return None


def list_backups(backups_dir=None) -> list:
    """Return snapshot metadata sorted by name (oldest first)."""
    backups_dir = pathlib.Path(backups_dir) if backups_dir else DEFAULT_BACKUPS_DIR
    if not backups_dir.exists():
        return []
    items = []
    for path in sorted(backups_dir.glob('backup_*')):
        if not path.is_dir():
            continue
        manifest = _read_manifest(path)
        items.append({
            'path': str(path),
            'name': path.name,
            'createdAt': manifest.get('createdAt') if manifest else None,
            'files': len(manifest.get('files', [])) if manifest else 0,
            'label': manifest.get('label', '') if manifest else '',
        })
    items.sort(key=lambda item: item['name'])
    return items


def main():
    parser = argparse.ArgumentParser(description='Backup runtime data to data/backups/')
    parser.add_argument('--keep', type=int, default=10, help='max snapshots kept (default 10)')
    parser.add_argument('--label', default='', help='optional snapshot label')
    args = parser.parse_args()
    target = create_backup(keep=args.keep, label=args.label)
    print(f'backup created: {target}')


if __name__ == '__main__':
    main()
