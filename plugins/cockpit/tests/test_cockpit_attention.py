"""Attention derives from receipt/publication state, never shell activity."""
from orcan_cockpit.attention import attention_reason, matching_workspaces


def test_receipt_and_publication_states():
    assert attention_reason({'status': 'passed', 'acknowledged': None})
    assert not attention_reason({'status': 'failed', 'acknowledged': 'received'})
    assert attention_reason({'status': 'passed'})
    assert attention_reason({'status': 'queued', 'publication_state': 'uncertain'})
    assert not attention_reason({'status': 'running'})
    assert not attention_reason({'status': 'queued', 'publication_state': 'published'})


def test_workspace_matches_canonical_paths(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(repo)
    rows = [{'session': 'one', 'projects': [{'path': str(link)}]},
            {'session': 'two', 'projects': [{'path': str(repo)}]},
            {'session': 'other', 'projects': []}]
    assert matching_workspaces({'repo': str(repo)}, rows) == rows[:2]
    assert matching_workspaces({}, rows) == []


def test_linked_worktree_matches_main_project(tmp_path):
    repo = tmp_path / 'repo'
    common = repo / '.git'
    admin = common / 'worktrees' / 'feature'
    admin.mkdir(parents=True)
    (admin / 'commondir').write_text('../..\n')
    worktree = tmp_path / 'feature'
    worktree.mkdir()
    (worktree / '.git').write_text(f'gitdir: {admin}\n')
    rows = [{'session': 'main', 'projects': [{'path': str(repo)}]}]
    assert matching_workspaces({'repo': str(worktree)}, rows) == rows


def test_storage_blocks_have_distinct_attention_messages():
    messages = {
        reason: attention_reason({'status': 'queued', 'admission_reason': reason})
        for reason in ('disk_space', 'worktree_budget', 'worktree_accounting')
    }
    assert all(messages.values())
    assert len(set(messages.values())) == 3
    assert 'budget' in messages['worktree_budget']
    assert 'measured' in messages['worktree_accounting']
