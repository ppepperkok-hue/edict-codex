"""Regression tests for the dashboard mutation gate (GH-REPAIR-EDICT-AUTH).

Confirmed probes before the fix:
  1. a cross-origin ``text/plain`` POST (a browser "simple request", no CORS
     preflight) reached ``/api/create-task`` and created a task;
  2. the write guard treated an absent ``X-Agent-ID`` as dashboard privilege and
     accepted a spoofed trusted id (``taizi``) on mutating routes.

The gate is fail-closed for browser-originated traffic: a mutating request is
only accepted when it is same-origin, matches an explicitly allowed origin, or
carries no browser origin markers at all (local CLI / agent / token clients).
These tests pin both the rejections and the legitimate positive paths.
"""
import contextlib
import json
import pathlib
import sys
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'dashboard'))
sys.path.insert(0, str(ROOT / 'scripts'))

import auth as auth_mod
import server as srv

TITLE = '身份校验回归测试旨意'


def _install_runtime(tmp_path, monkeypatch):
    """Point the server at a throwaway data dir and return its tasks file."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [
            {'id': 'taizi', 'allowAgents': ['zhongshu']},
            {'id': 'zhongshu', 'allowAgents': ['menxia']},
            {'id': 'menxia', 'allowAgents': ['shangshu']},
            {'id': 'libu', 'allowAgents': []},
        ]
    }), encoding='utf-8')
    tasks_file = data_dir / 'tasks_source.json'
    tasks_file.write_text('[]', encoding='utf-8')

    def _load():
        return json.loads(tasks_file.read_text(encoding='utf-8'))

    def _save(tasks):
        tasks_file.write_text(json.dumps(tasks, ensure_ascii=False), encoding='utf-8')

    monkeypatch.setattr(srv, 'DATA', data_dir)
    monkeypatch.setattr(srv, '_ACTIVE_TASK_DATA_DIR', data_dir)
    monkeypatch.setattr(srv, 'load_tasks', _load)
    monkeypatch.setattr(srv, 'save_tasks', _save)
    # No background refresh subprocess: refresh_live_data.py resolves the real
    # repository scripts/data dir and would rewrite ignored runtime state.
    monkeypatch.setattr(srv, '_trigger_refresh', lambda: None)
    return data_dir, tasks_file


def _stored_tasks(tasks_file):
    return json.loads(tasks_file.read_text(encoding='utf-8'))


@contextlib.contextmanager
def _serve(bind_host='127.0.0.1'):
    """Run the real Handler on an ephemeral loopback (or wildcard) port."""
    httpd = HTTPServer((bind_host, 0), srv.Handler)
    port = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(port, path, body, headers=None):
    conn = HTTPConnection('127.0.0.1', port, timeout=10)
    payload = body if isinstance(body, (bytes, str)) else json.dumps(body)
    try:
        conn.request('POST', path, body=payload, headers=headers or {})
        resp = conn.getresponse()
        raw = resp.read()
        status = resp.status
    finally:
        conn.close()
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}
    return status, parsed


def _json_headers(**extra):
    headers = {'Content-Type': 'application/json'}
    headers.update(extra)
    return headers


# ── rejections: cross-origin browser mutations ──────────────────────────────

def test_cross_origin_text_plain_post_rejected(tmp_path, monkeypatch):
    """The confirmed probe: evil page, simple text/plain POST, task must not be created."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            {'Origin': 'https://evil.example', 'Content-Type': 'text/plain;charset=UTF-8'},
        )

    assert status == 403, f'cross-origin text/plain POST was not rejected: {status} {body}'
    assert _stored_tasks(tasks_file) == [], 'cross-origin POST mutated task data'


def test_cross_origin_json_post_rejected_even_with_allowed_origin_header_shape(tmp_path, monkeypatch):
    """A foreign origin cannot use JSON either (no reflected CORS permission)."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='https://evil.example'),
        )

    assert status == 403, f'cross-origin JSON POST was not rejected: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_cross_origin_post_without_agent_id_rejected(tmp_path, monkeypatch):
    """Absent X-Agent-ID must not become dashboard privilege for a foreign origin."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='http://attacker.example:8080'),
        )

    assert status == 403, f'absent identity + foreign origin was accepted: {status} {body}'
    assert 'cross-origin' in body.get('error', '')
    assert _stored_tasks(tasks_file) == []


def test_cross_origin_spoofed_taizi_id_rejected(tmp_path, monkeypatch):
    """A spoofed trusted agent id must not lift a foreign-origin request."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='https://evil.example', **{'X-Agent-ID': 'taizi'}),
        )

    assert status == 403, f'spoofed taizi + foreign origin was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_sec_fetch_cross_site_without_origin_rejected(tmp_path, monkeypatch):
    """Browsers that only send Sec-Fetch-Site are still fail-closed."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(**{'Sec-Fetch-Site': 'cross-site'}),
        )

    assert status == 403, f'Sec-Fetch-Site: cross-site was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_null_origin_rejected(tmp_path, monkeypatch):
    """Sandboxed iframes / file:// pages send Origin: null."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='null'),
        )

    assert status == 403, f'Origin: null was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_non_json_content_type_rejected_for_same_origin(tmp_path, monkeypatch):
    """Same-origin form posts are not a supported mutation channel."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        origin = f'http://127.0.0.1:{port}'
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            {'Origin': origin, 'Content-Type': 'application/x-www-form-urlencoded'},
        )

    assert status == 415, f'form-encoded mutation was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_dns_rebinding_origin_matching_untrusted_host_rejected(tmp_path, monkeypatch):
    """A rebound page is same-origin with itself: Origin == Host == evil.example.

    The browser derives both headers from the attacker hostname after DNS
    rebinding to 127.0.0.1, so "Origin equals Host" alone is not evidence of a
    trusted server address. The Host must be an authoritative bind address or
    an explicitly configured origin.
    """
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin=f'http://evil.example:{port}',
                Host=f'evil.example:{port}',
                **{'Sec-Fetch-Site': 'same-origin'},
            ),
        )

    assert status == 403, f'rebound same-origin write was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == [], 'rebound write mutated task data'


def test_forwarded_host_cannot_launder_untrusted_host(tmp_path, monkeypatch):
    """X-Forwarded-Host is client-forgeable; only the bind address is authoritative."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin=f'http://evil.example:{port}',
                Host=f'evil.example:{port}',
                **{'X-Forwarded-Host': f'127.0.0.1:{port}'},
            ),
        )

    assert status == 403, f'X-Forwarded-Host granted trust: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_allowed_dev_origin_with_untrusted_host_rejected(tmp_path, monkeypatch):
    """An allow-listed Origin does not legitimise an arbitrary Host."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin='http://127.0.0.1:5173',
                Host=f'evil.example:{port}',
            ),
        )

    assert status == 403, f'untrusted Host accepted for a dev origin: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_non_allowlisted_same_site_origin_rejected(tmp_path, monkeypatch):
    """``same-site`` alone is not trust: another local port stays hostile.

    A page served from any other process on loopback (``127.0.0.1:6666``) is
    same-site with the dashboard, but it is neither an allowed origin nor the
    authoritative Host, so its write must be refused.
    """
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='http://127.0.0.1:6666', **{'Sec-Fetch-Site': 'same-site'}),
        )

    assert status == 403, f'non-allowlisted same-site origin was accepted: {status} {body}'
    assert 'cross-origin' in body.get('error', '')
    assert _stored_tasks(tasks_file) == [], 'same-site write mutated task data'


def test_same_site_dns_rebinding_host_rejected(tmp_path, monkeypatch):
    """A rebound page is same-site with itself; the Host check still refuses it.

    ``same-site`` must not be evaluated before the authoritative-Host check,
    otherwise rebinding ``evil.example`` to loopback would skip the only real
    address evidence.
    """
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin=f'http://evil.example:{port}',
                Host=f'evil.example:{port}',
                **{'Sec-Fetch-Site': 'same-site'},
            ),
        )

    assert status == 403, f'same-site rebound Host was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_explicit_origin_with_cross_site_still_rejected(tmp_path, monkeypatch):
    """The allowlist grants ``same-site``, never ``cross-site``."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, 'ALLOWED_ORIGIN', 'http://dashboard.internal:9000')
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin='http://dashboard.internal:9000',
                **{'Sec-Fetch-Site': 'cross-site'},
            ),
        )

    assert status == 403, f'cross-site request from an allowed origin was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_duplicate_host_headers_are_ambiguous():
    """Two Host headers must not resolve to a trusted authority."""
    import email.message

    message = email.message.Message()
    message['Host'] = '127.0.0.1:7891'
    message['Host'] = 'evil.example:7891'
    message['Origin'] = 'http://127.0.0.1:7891'

    server = type('Bound', (), {'server_address': ('127.0.0.1', 7891)})()
    assert srv._origin_trusted(message, server) is False


def test_cross_origin_password_setup_rejected(tmp_path, monkeypatch):
    """The public auth endpoints must be behind the gate too (no CSRF password capture)."""
    data_dir, _ = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(auth_mod, '_auth_file', data_dir / 'auth.json')
    monkeypatch.setattr(auth_mod, '_secret_key', b'test-secret-key')
    with _serve() as port:
        status, body = _post(
            port,
            '/api/auth/setup',
            {'password': 'attacker-chosen'},
            _json_headers(Origin='https://evil.example'),
        )

    assert status == 403, f'cross-origin password setup was accepted: {status} {body}'
    assert auth_mod.is_configured() is False


# ── positive cases: legitimate dashboard / agent / CLI writes ───────────────

def test_same_origin_dashboard_post_allowed(tmp_path, monkeypatch):
    """The built dashboard posts JSON from its own origin, without X-Agent-ID."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin=f'http://127.0.0.1:{port}', **{'Sec-Fetch-Site': 'same-origin'}),
        )

    assert status == 200, f'same-origin dashboard write was blocked: {status} {body}'
    assert body['ok'] is True
    assert body['taskId'].startswith('JJC-')


def test_local_cli_post_without_origin_allowed(tmp_path, monkeypatch):
    """kanban CLI / curl / agent scripts send no Origin and keep working."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(port, '/api/create-task', {'title': TITLE}, _json_headers())

    assert status == 200, f'local CLI write was blocked: {status} {body}'
    assert body['ok'] is True


def test_vite_dev_origin_allowed(tmp_path, monkeypatch):
    """The documented local Vite dev server stays a legitimate caller."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='http://127.0.0.1:5173'),
        )

    assert status == 200, f'allow-listed dev origin was blocked: {status} {body}'
    assert body['ok'] is True


def test_vite_dev_origin_with_same_site_allowed(tmp_path, monkeypatch):
    """A real Vite browser reports ``same-site`` for the ``:5173`` -> ``:7891`` hop.

    Loops ignore the port when the browser derives ``Sec-Fetch-Site``, so the
    documented dev pairing is same-site, not same-origin. The allow-listed
    origin must keep its trust in that case (regression GH-EDICT-SAME-SITE).
    """
    _, _ = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin='http://127.0.0.1:5173',
                **{'Sec-Fetch-Site': 'same-site'},
            ),
        )

    assert status == 200, f'Vite same-site write was blocked: {status} {body}'
    assert body['ok'] is True
    assert body['taskId'].startswith('JJC-')


def test_explicit_cors_origin_with_same_site_allowed(tmp_path, monkeypatch):
    """A same-site ``--cors`` deployment (``dashboard.internal:9000``) works."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, 'ALLOWED_ORIGIN', 'http://dashboard.internal:9000')
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin='http://dashboard.internal:9000',
                **{'Sec-Fetch-Site': 'same-site'},
            ),
        )

    assert status == 200, f'--cors same-site write was blocked: {status} {body}'
    assert body['ok'] is True


def test_explicit_cors_origin_allowed(tmp_path, monkeypatch):
    """--cors is the documented opt-in for reverse-proxy deployments."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, 'ALLOWED_ORIGIN', 'http://dashboard.internal:9000')
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Origin='http://dashboard.internal:9000'),
        )

    assert status == 200, f'--cors origin was blocked: {status} {body}'
    assert body['ok'] is True


def test_reverse_proxy_preserving_public_host_allowed(tmp_path, monkeypatch):
    """A proxy that forwards the public Host is trusted via --cors."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, 'ALLOWED_ORIGIN', 'http://dashboard.internal:9000')
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin='http://dashboard.internal:9000',
                Host='dashboard.internal:9000',
            ),
        )

    assert status == 200, f'proxy-preserved Host was blocked: {status} {body}'
    assert body['ok'] is True


def test_reverse_proxy_rewriting_host_to_upstream_allowed(tmp_path, monkeypatch):
    """A proxy that rewrites Host to the bind address still works with --cors."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(srv, 'ALLOWED_ORIGIN', 'https://dashboard.example.com')
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin='https://dashboard.example.com',
                Host=f'127.0.0.1:{port}',
            ),
        )

    assert status == 200, f'upstream-rewritten Host was blocked: {status} {body}'
    assert body['ok'] is True


def test_localhost_alias_same_origin_allowed(tmp_path, monkeypatch):
    """A browser that used http://localhost:<port> is still same-origin."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin=f'http://localhost:{port}',
                Host=f'localhost:{port}',
            ),
        )

    assert status == 200, f'loopback alias was blocked: {status} {body}'
    assert body['ok'] is True


def test_wildcard_bind_lan_ip_literal_allowed(tmp_path, monkeypatch):
    """--host 0.0.0.0 keeps LAN access via a literal interface address."""
    _, _ = _install_runtime(tmp_path, monkeypatch)
    with _serve(bind_host='0.0.0.0') as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin=f'http://192.0.2.10:{port}',
                Host=f'192.0.2.10:{port}',
            ),
        )

    assert status == 200, f'LAN IP literal was blocked: {status} {body}'
    assert body['ok'] is True


def test_wildcard_bind_still_rejects_rebound_hostname(tmp_path, monkeypatch):
    """A wildcard bind must not turn the Host check off for DNS names."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve(bind_host='0.0.0.0') as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(
                Origin=f'http://evil.example:{port}',
                Host=f'evil.example:{port}',
            ),
        )

    assert status == 403, f'rebound host accepted on wildcard bind: {status} {body}'
    assert _stored_tasks(tasks_file) == []


def test_agent_permission_matrix_still_enforced_for_local_caller(tmp_path, monkeypatch):
    """Trusted local origin keeps the ADR-009 role matrix: only taizi may create tasks."""
    _, tasks_file = _install_runtime(tmp_path, monkeypatch)
    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(**{'X-Agent-ID': 'zhongshu'}),
        )

    assert status == 403, f'zhongshu was allowed to create a task: {status} {body}'
    assert '仅太子' in body.get('error', '')
    assert _stored_tasks(tasks_file) == []


def test_token_authenticated_local_post_allowed(tmp_path, monkeypatch):
    """With auth enabled a bearer token still authorises a no-Origin CLI write."""
    data_dir, _ = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(auth_mod, '_auth_file', data_dir / 'auth.json')
    monkeypatch.setattr(auth_mod, '_secret_key', b'test-secret-key')
    assert auth_mod.setup_password('correct horse battery')['ok'] is True
    token = auth_mod.create_token()

    with _serve() as port:
        status, body = _post(
            port,
            '/api/create-task',
            {'title': TITLE},
            _json_headers(Authorization=f'Bearer {token}'),
        )

    assert status == 200, f'token-authenticated write was blocked: {status} {body}'
    assert body['ok'] is True


def test_missing_token_rejected_when_auth_enabled(tmp_path, monkeypatch):
    """Auth enabled + no credential stays a 401 (unchanged behaviour)."""
    data_dir, tasks_file = _install_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(auth_mod, '_auth_file', data_dir / 'auth.json')
    monkeypatch.setattr(auth_mod, '_secret_key', b'test-secret-key')
    assert auth_mod.setup_password('correct horse battery')['ok'] is True

    with _serve() as port:
        status, body = _post(port, '/api/create-task', {'title': TITLE}, _json_headers())

    assert status == 401, f'unauthenticated write was accepted: {status} {body}'
    assert _stored_tasks(tasks_file) == []
