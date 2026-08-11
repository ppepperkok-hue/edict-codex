"""
PoC test: CWE-22 — Path traversal via file:// URL in add_remote_skill
reads arbitrary local files without allowed_roots check.

Expected: FAIL before fix, PASS after fix.
"""
import json, pathlib, sys, os, tempfile

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
