"""
PoC test: CWE-22 — Path traversal via file:// URL in add_remote_skill
reads arbitrary local files without allowed_roots check.

Expected: FAIL before fix, PASS after fix.
"""
import json, pathlib, sys, os, tempfile

import pytest

# Setup project paths
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / 'dashboard'))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))


def test_file_url_path_traversal_blocked(tmp_path):
    """file:// URLs pointing outside allowed_roots must be rejected."""
    import server as srv

    # Create a fake data dir with agent_config
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [{'id': 'testagent', 'skills': []}]
    }))
    srv.DATA = data_dir

    # Create a "secret" file outside any allowed root
    secret_dir = tmp_path / 'secrets'
    secret_dir.mkdir()
    secret_file = secret_dir / 'SKILL.md'
    # Must have valid frontmatter to pass content validation
    secret_file.write_text('---\nname: evil\n---\nSECRET DATA\n')

    # Attempt to read via file:// URL — this should be BLOCKED
    result = srv.add_remote_skill('testagent', 'evilskill', f'file://{secret_file}')

    # The fix should reject this because the path is outside allowed_roots
    assert result['ok'] is False, (
        f"VULNERABILITY: file:// URL read arbitrary file outside allowed_roots! "
        f"Result: {result}"
    )
    assert '路径' in result.get('error', '') or 'allow' in result.get('error', '').lower(), (
        f"Expected path restriction error, got: {result.get('error')}"
    )


def test_file_url_within_allowed_roots_works(tmp_path, monkeypatch):
    """file:// URLs within allowed_roots should still work after the fix."""
    import server as srv

    # Setup
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [{'id': 'testagent', 'skills': []}]
    }))
    srv.DATA = data_dir

    monkeypatch.setattr(srv, 'BASE', tmp_path)
    monkeypatch.setattr(srv, 'SKILLS_ROOT', tmp_path / 'skills')

    # Place a valid skill file inside the project root (an allowed root)
    skill_src = tmp_path / 'shared_skills' / 'goodskill'
    skill_src.mkdir(parents=True)
    good_file = skill_src / 'SKILL.md'
    good_file.write_text('---\nname: goodskill\ndescription: a good skill\n---\n\n# Good Skill\n\nDoes good things.\n')

    result = srv.add_remote_skill('testagent', 'goodskill', f'file://{good_file}')

    assert result['ok'] is True, (
        f"file:// URL within allowed_roots should work! Result: {result}"
    )


def test_file_url_etc_passwd_blocked(tmp_path):
    """Classic /etc/passwd read via file:// must be blocked."""
    import server as srv

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [{'id': 'testagent', 'skills': []}]
    }))
    srv.DATA = data_dir

    result = srv.add_remote_skill('testagent', 'readpasswd', 'file:///etc/passwd')

    # Must be rejected (either file doesn't exist, or path not in allowed_roots)
    assert result['ok'] is False, (
        f"VULNERABILITY: file:// read /etc/passwd! Result: {result}"
    )


def test_read_skill_content_utf8(tmp_path, monkeypatch):
    """UTF-8 SKILL.md must be readable via read_skill_content (GBK default would crash)."""
    import server as srv

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    skill_root = tmp_path / '.agents' / 'skills'
    (skill_root / 'menxia').mkdir(parents=True)
    skill_md = skill_root / 'menxia' / 'SKILL.md'
    skill_md.write_text(
        '---\nname: menxia\ndescription: 门下省技能\n---\n\n# 门下省\n四维审议\n',
        encoding='utf-8',
    )
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [{'id': 'menxia', 'skills': [
            {'name': 'menxia', 'path': str(skill_md)},
        ]}]
    }), encoding='utf-8')

    monkeypatch.setattr(srv, 'BASE', tmp_path)
    monkeypatch.setattr(srv, 'SKILLS_ROOT', skill_root)
    srv.DATA = data_dir

    result = srv.read_skill_content('menxia', 'menxia')
    assert result['ok'] is True, f'Expected ok=True, got: {result}'
    assert '四维审议' in result.get('content', '')


def _setup_sibling_env(tmp_path, monkeypatch, configured=False):
    """Set up an allowed root plus a sibling whose name shares its prefix."""
    import server as srv

    work = tmp_path / 'work'
    data_dir = work / 'data'
    data_dir.mkdir(parents=True)
    evil_root = tmp_path / 'work-evil'
    evil_root.mkdir()
    skill_md = evil_root / 'SKILL.md'
    skill_md.write_text('---\nname: evil\n---\nSECRET DATA\n', encoding='utf-8')
    skills = [{'name': 'evil', 'path': str(skill_md)}] if configured else []
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [{'id': 'testagent', 'skills': skills}]
    }), encoding='utf-8')

    monkeypatch.setattr(srv, 'BASE', work / 'dashboard')
    monkeypatch.setattr(srv, 'SKILLS_ROOT', tmp_path / 'skills')
    monkeypatch.setattr(srv, 'DATA', data_dir)
    return srv, skill_md


def test_read_skill_content_sibling_prefix_blocked(tmp_path, monkeypatch):
    """A sibling whose name starts with the allowed root must not be readable."""
    srv, _ = _setup_sibling_env(tmp_path, monkeypatch, configured=True)

    result = srv.read_skill_content('testagent', 'evil')
    assert result['ok'] is False, f'VULNERABILITY: sibling path was read: {result}'
    assert '路径' in result.get('error', '')


def test_file_url_sibling_prefix_blocked(tmp_path, monkeypatch):
    """file:// URLs for a sibling of the allowed root must be rejected."""
    srv, skill_md = _setup_sibling_env(tmp_path, monkeypatch)

    result = srv.add_remote_skill('testagent', 'evilskill', f'file://{skill_md}')
    assert result['ok'] is False, f'VULNERABILITY: sibling file:// URL was read: {result}'
    assert '路径' in result.get('error', '')


def test_local_path_sibling_prefix_blocked(tmp_path, monkeypatch):
    """Relative local paths for a sibling of the allowed root must be rejected."""
    srv, _ = _setup_sibling_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = srv.add_remote_skill('testagent', 'evilskill', './work-evil/SKILL.md')
    assert result['ok'] is False, f'VULNERABILITY: sibling local path was read: {result}'
    assert '路径' in result.get('error', '')


def test_disallowed_nonexistent_path_reports_containment_error(tmp_path, monkeypatch):
    """Containment is checked before exists(): a missing out-of-root path must not reveal its absence."""
    srv, _ = _setup_sibling_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    missing_file = tmp_path / 'outside' / 'missing.md'  # deliberately never created
    assert not missing_file.exists()

    file_url = srv.add_remote_skill('testagent', 'evilskill', f'file://{missing_file}')
    assert file_url['ok'] is False, f'file:// outside root was accepted: {file_url}'
    assert '路径' in file_url.get('error', ''), f'Expected containment error, got: {file_url}'
    assert '不存在' not in file_url.get('error', ''), f'Existence leaked through error: {file_url}'

    local = srv.add_remote_skill('testagent', 'evilskill', './outside/missing.md')
    assert local['ok'] is False, f'local path outside root was accepted: {local}'
    assert '路径' in local.get('error', ''), f'Expected containment error, got: {local}'
    assert '不存在' not in local.get('error', ''), f'Existence leaked through error: {local}'


def test_disallowed_existing_path_still_containment_error(tmp_path, monkeypatch):
    """An existing but out-of-root file must still fail with the containment error."""
    srv, evil_md = _setup_sibling_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = srv.add_remote_skill('testagent', 'evilskill', f'file://{evil_md}')
    assert result['ok'] is False, f'VULNERABILITY: out-of-root file read: {result}'
    assert '路径' in result.get('error', ''), f'Expected containment error, got: {result}'


@pytest.mark.skipif(os.name != 'nt', reason='Windows-only case-insensitive / mixed-separator semantics')
def test_read_skill_content_windows_case_and_separator_allowed(tmp_path, monkeypatch):
    """Windows case-insensitive, mixed-separator paths inside the root stay readable."""
    import server as srv

    work = tmp_path / 'work'
    data_dir = work / 'data'
    data_dir.mkdir(parents=True)
    skill_md = work / 'skills' / 'menxia' / 'SKILL.md'
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text('---\nname: menxia\n---\n四维审议\n', encoding='utf-8')
    odd_path = str(skill_md).upper().replace('\\', '/')
    (data_dir / 'agent_config.json').write_text(json.dumps({
        'agents': [{'id': 'menxia', 'skills': [
            {'name': 'menxia', 'path': odd_path},
        ]}]
    }), encoding='utf-8')

    monkeypatch.setattr(srv, 'BASE', work / 'dashboard')
    monkeypatch.setattr(srv, 'DATA', data_dir)

    result = srv.read_skill_content('menxia', 'menxia')
    assert result['ok'] is True, f'Legitimate Windows path was rejected: {result}'
    assert '四维审议' in result.get('content', '')
