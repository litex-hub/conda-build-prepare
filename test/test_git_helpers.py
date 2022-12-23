import time

import conda_build_prepare.git_helpers as gh

COMMIT_DELAY = 1


def git_commit_and_tag(filepath, msg, tag=None):
    now = time.time()
    with open(filepath, 'w') as f:
        f.write(f'{now}')
    gh._call_custom_git_cmd(filepath.parent, f'add {filepath}')
    gh._call_custom_git_cmd(filepath.parent, f'commit -m {msg}')
    if tag:
        gh._call_custom_git_cmd(filepath.parent, f'tag {tag}')
    time.sleep(COMMIT_DELAY)


def test_get_first_reachable_tag(tmp_path):
    repo = tmp_path
    gh._call_custom_git_cmd(repo, 'init -b main')
    gh._call_custom_git_cmd(
        repo, 'config --local user.email "you@example.com"'
    )
    gh._call_custom_git_cmd(
        repo, 'config --local user.name "Your Name"'
    )
    git_commit_and_tag(repo / 'foo', 'first', tag=None)

    initial_rev = gh._call_custom_git_cmd(repo, 'rev-parse HEAD')
    gh._call_custom_git_cmd(repo, 'checkout -b fixup')
    git_commit_and_tag(repo / 'foo', 'unreachable', tag='v0.0-unreachabe')

    gh._call_custom_git_cmd(repo, 'checkout main')
    git_commit_and_tag(repo / 'foo', 'second', tag='v0.1')

    git_commit_and_tag(repo / 'foo', 'untagged', tag=None)

    gh._call_custom_git_cmd(repo, 'checkout main')
    git_commit_and_tag(repo / 'foo', 'third', tag='v0.2')

    gh._call_custom_git_cmd(repo, f'tag v0.0-retroactive {initial_rev}')
    assert gh.get_first_reachable_tag(repo) == 'v0.2'
