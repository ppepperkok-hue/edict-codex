#!/usr/bin/env python3
"""Aggregate official stats from local JSON data -> data/officials_stats.json.

Reads tasks_source.json (progress_log/flow_log), agent_config.json (model
settings) and audit_log.json instead of OpenClaw runtime files.
"""
import datetime
import pathlib
import logging

from file_lock import atomic_json_write
from utils import read_json

log = logging.getLogger('officials')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s', datefmt='%H:%M:%S')

BASE = pathlib.Path(__file__).resolve().parent.parent
DATA = BASE / 'data'

DEFAULT_MODEL = 'anthropic/claude-sonnet-4-6'

MODEL_PRICING = {
    'anthropic/claude-sonnet-4-6':  {'in': 3.0, 'out': 15.0, 'cr': 0.30, 'cw': 3.75},
    'anthropic/claude-opus-4-5':    {'in': 15.0, 'out': 75.0, 'cr': 1.50, 'cw': 18.75},
    'anthropic/claude-haiku-3-5':   {'in': 0.8, 'out': 4.0,  'cr': 0.08, 'cw': 1.0},
    'openai/gpt-4o':                {'in': 2.5, 'out': 10.0, 'cr': 1.25, 'cw': 0},
    'openai/gpt-4o-mini':           {'in': 0.15, 'out': 0.6,  'cr': 0.075, 'cw': 0},
    'google/gemini-2.0-flash':      {'in': 0.075, 'out': 0.3, 'cr': 0, 'cw': 0},
    'google/gemini-2.5-pro':        {'in': 1.25, 'out': 10.0, 'cr': 0, 'cw': 0},
}

OFFICIALS = [
    {'id': 'taizi',   'label': '太子',  'role': '太子',    'emoji': '🤴', 'rank': '储君'},
    {'id': 'zhongshu', 'label': '中书省', 'role': '中书令',  'emoji': '📜', 'rank': '正一品'},
    {'id': 'menxia',  'label': '门下省', 'role': '侍中',    'emoji': '🔍', 'rank': '正一品'},
    {'id': 'shangshu', 'label': '尚书省', 'role': '尚书令',  'emoji': '📮', 'rank': '正一品'},
    {'id': 'libu',    'label': '礼部',  'role': '礼部尚书', 'emoji': '📝', 'rank': '正二品'},
    {'id': 'hubu',    'label': '户部',  'role': '户部尚书', 'emoji': '💰', 'rank': '正二品'},
    {'id': 'bingbu',  'label': '兵部',  'role': '兵部尚书', 'emoji': '⚔️', 'rank': '正二品'},
    {'id': 'xingbu',  'label': '刑部',  'role': '刑部尚书', 'emoji': '⚖️', 'rank': '正二品'},
    {'id': 'gongbu',  'label': '工部',  'role': '工部尚书', 'emoji': '🔧', 'rank': '正二品'},
    {'id': 'libu_hr', 'label': '吏部',  'role': '吏部尚书', 'emoji': '👔', 'rank': '正二品'},
    {'id': 'zaochao', 'label': '钦天监', 'role': '朝报官',  'emoji': '📰', 'rank': '正三品'},
]


def _as_int(value) -> int:
    """Coerce unknown progress_log usage values to int (missing -> 0)."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_ts(value):
    """Parse ISO or epoch-ms timestamp; return datetime or None."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(value / 1000, tz=datetime.timezone.utc)
        except (ValueError, OSError):
            return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def get_model(agent_id: str, agent_cfg: dict) -> str:
    """Return the configured model for an agent (default fallback)."""
    default = agent_cfg.get('defaultModel') or DEFAULT_MODEL
    for entry in agent_cfg.get('agents', []):
        if entry.get('id') == agent_id and entry.get('model'):
            return entry['model']
    if agent_id == 'taizi':
        for entry in agent_cfg.get('agents', []):
            if entry.get('id') == 'main' and entry.get('model'):
                return entry['model']
    return default


def scan_progress(tasks: list, agent_id: str) -> dict:
    """Aggregate usage and activity from progress_log entries per agent."""
    tokens_in = tokens_out = cache_read = cache_write = messages = sessions = 0
    last_ts = None
    for task in tasks:
        for entry in task.get('progress_log') or []:
            if entry.get('agent') != agent_id:
                continue
            tokens_in += _as_int(entry.get('tokens_in'))
            tokens_out += _as_int(entry.get('tokens_out'))
            cache_read += _as_int(entry.get('cache_read'))
            cache_write += _as_int(entry.get('cache_write'))
            messages += 1
            ts = _parse_ts(entry.get('at') or entry.get('ts'))
            if ts and (last_ts is None or ts > last_ts):
                last_ts = ts
    sessions = sum(1 for task in tasks if any(
        e.get('agent') == agent_id for e in (task.get('progress_log') or [])
    ))
    return {
        'tokens_in': tokens_in,
        'tokens_out': tokens_out,
        'cache_read': cache_read,
        'cache_write': cache_write,
        'sessions': sessions,
        'messages': messages,
        'last_ts': last_ts,
        'last_active': last_ts.astimezone().strftime('%Y-%m-%d %H:%M') if last_ts else None,
    }


def calc_cost(usage: dict, model: str) -> float:
    """Estimate USD cost from token usage (unknown models fall back to default)."""
    price = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    usd = (
        usage['tokens_in'] / 1e6 * price['in']
        + usage['tokens_out'] / 1e6 * price['out']
        + usage['cache_read'] / 1e6 * price['cr']
        + usage['cache_write'] / 1e6 * price['cw']
    )
    return round(usd, 4)


def get_task_stats(org_label: str, tasks: list) -> dict:
    """Count done/active tasks and flow participation for an org."""
    done = [t for t in tasks if t.get('state') == 'Done' and t.get('org') == org_label]
    active = [t for t in tasks if t.get('state') in ('Doing', 'Review', 'Assigned') and t.get('org') == org_label]
    participated = []
    flow_count = 0
    for task in tasks:
        if str(task.get('id', '')).startswith('JJC'):
            mentioned = any(
                flow.get('from') == org_label or flow.get('to') == org_label
                for flow in (task.get('flow_log') or [])
            )
            if mentioned:
                participated.append({
                    'id': task.get('id', ''),
                    'title': task.get('title', ''),
                    'state': task.get('state', ''),
                })
        flow_count += sum(
            1 for flow in (task.get('flow_log') or [])
            if flow.get('from') == org_label or flow.get('to') == org_label
        )
    return {
        'tasks_done': len(done),
        'tasks_active': len(active),
        'flow_participations': flow_count,
        'participated_edicts': participated,
    }


def build_heartbeat(usage: dict) -> dict:
    """Map last progress activity to a dashboard heartbeat status."""
    last_ts = usage.get('last_ts')
    if not last_ts:
        return {'status': 'idle', 'label': '⚪ 待命', 'ageSec': None}
    age = max(0, int((datetime.datetime.now(datetime.timezone.utc) - last_ts).total_seconds()))
    if age <= 10 * 60:
        return {'status': 'active', 'label': f'🟢 活跃 {int(age / 60)}分钟前', 'ageSec': age}
    if age <= 60 * 60:
        return {'status': 'recent', 'label': f'🟡 最近活跃 {int(age / 60)}分钟前', 'ageSec': age}
    return {'status': 'idle', 'label': '⚪ 待命', 'ageSec': age}


def main():
    tasks = read_json(DATA / 'tasks_source.json', [])
    agent_cfg = read_json(DATA / 'agent_config.json', {})

    result = []
    for official in OFFICIALS:
        model = get_model(official['id'], agent_cfg)
        usage = scan_progress(tasks, official['id'])
        task_stats = get_task_stats(official['label'], tasks)
        cost_usd = calc_cost(usage, model)
        result.append({
            **official,
            'model': model,
            'model_short': model.split('/')[-1] if isinstance(model, str) and '/' in model else str(model),
            'sessions': usage['sessions'],
            'tokens_in': usage['tokens_in'],
            'tokens_out': usage['tokens_out'],
            'cache_read': usage['cache_read'],
            'cache_write': usage['cache_write'],
            'tokens_total': usage['tokens_in'] + usage['tokens_out'],
            'messages': usage['messages'],
            'cost_usd': cost_usd,
            'cost_cny': round(cost_usd * 7.25, 2),
            'last_active': usage['last_active'],
            'heartbeat': build_heartbeat(usage),
            **task_stats,
            'merit_score': task_stats['tasks_done'] * 10 + task_stats['flow_participations'] * 2 + min(usage['sessions'], 20),
        })

    result.sort(key=lambda item: item['merit_score'], reverse=True)
    for index, item in enumerate(result):
        item['merit_rank'] = index + 1

    totals = {
        'tokens_total': sum(item['tokens_total'] for item in result),
        'cache_total': sum(item['cache_read'] + item['cache_write'] for item in result),
        'cost_usd': round(sum(item['cost_usd'] for item in result), 2),
        'cost_cny': round(sum(item['cost_cny'] for item in result), 2),
        'tasks_done': sum(item['tasks_done'] for item in result),
    }
    top = max(result, key=lambda item: item['merit_score'], default={})

    payload = {
        'generatedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'officials': result,
        'totals': totals,
        'top_official': top.get('label', ''),
    }
    atomic_json_write(DATA / 'officials_stats.json', payload)
    log.info(f'{len(result)} officials | cost=¥{totals["cost_cny"]} | top={top.get("label", "")}')


if __name__ == '__main__':
    main()
