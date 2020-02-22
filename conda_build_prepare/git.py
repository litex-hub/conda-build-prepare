#!/usr/bin/env python3

import re
import subprocess


GITHUB_RE = re.compile("github.com[:/](?P<user>[^/\n]+)(/(?P<repo>[^/.].*?))?(.git|/|$)")

def extract_github_parts(url):
    if not url:
        return None, None
    m = GITHUB_RE.search(url)
    if not m:
        return None, None
    user = m.group('user')
    assert user, user
    repo = m.group('repo')
    return user, repo


def extract_github_user(url):
    """
    >>> extract_github_user(None) is None
    True
    >>> extract_github_user("https://git.otherhost.com/") is None
    True
    >>> extract_github_user("https://github.com/mithro")
    'mithro'
    >>> extract_github_user("git+ssh://github.com/mithro")
    'mithro'
    >>> extract_github_user("https://github.com/enjoy-digital/repo.git")
    'enjoy-digital'
    >>> extract_github_user("git+ssh://github.com/other-person/repo.git")
    'other-person'
    >>> extract_github_user("git+ssh://github.com/mithro/repo.git")
    'mithro'
    >>> extract_github_user("git@github.com:conda/conda-build.git")
    'conda'
    >>> extract_github_user("https://github.com/conda/conda-build/pulls")
    'conda'
    """
    return extract_github_parts(url)[0]


def extract_github_repo(url):
    """
    >>> extract_github_repo("https://git.otherhost.com/") is None
    True
    >>> extract_github_repo("https://github.com/mithro") is None
    True
    >>> extract_github_repo("git+ssh://github.com/mithro") is None
    True
    >>> extract_github_repo("https://github.com/enjoy-digital/repo.git")
    'repo'
    >>> extract_github_repo("git+ssh://github.com/other-person/repo.git")
    'repo'
    >>> extract_github_repo("git+ssh://github.com/mithro/repo.git")
    'repo'
    >>> extract_github_repo("git@github.com:conda/conda-build.git")
    'conda-build'
    >>> extract_github_repo("https://github.com/conda/conda-build/pulls")
    'conda-build'
    """
    return extract_github_parts(url)[1]


def upstream(env=env):
    """Get 'upstream' URL for the git repository."""
    remotes = remotes('fetch')

    # Try the remote tracking value for this branch
    try:
        upstream = subprocess.check_output(
            ['git', 'rev-parse', '--symbolic-full-name', '@{u}'], env=env,
        ).decode('utf-8').strip()
        if upstream and '/' in upstream:
            remote, remote_branch = upstream.split('/')
            assert remote in remotes, (remote, remotes)
            return remotes[remote]
    except subprocess.CalledProcessError:
        pass

    # If there is only one remote, use that
    if len(remotes) == 1:
        return remotes.popitem()[-1]

    # Otherwise try using 'origin'
    if 'origin' in remotes:
        return remotes['origin']
    # Or 'upstream'
    if 'upstream' in remotes:
        return remotes['upstream']

    return None


def metadata(**env):
    metadata = {}
    try:
        metadata['commit'] = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], env=env,
        ).decode('utf-8').strip()
    except subprocess.CalledProcessError:
        pass

    try:
        metadata['branch'] = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], env=env,
        ).decode('utf-8').strip()
    except subprocess.CalledProcessError:
        pass


def unshallow(**env):
    if subprocess.check_output(
                ['git', 'rev-parse', '--is-shallow-repository'],
                env=env,
            ).strip() == 'true':
        subprocess.check_call(['git', 'fetch', '--unshallow'])


def fetch_tags(**env):
    subprocess.check_call(['git', 'fetch', '--tags'], env=env)


def list_tags(tag_filter=None, **env):
    tags = subprocess.check_output(
        ['git', 'tag', '--list'], env=env).decode('utf-8')

    return sort_tags(tags.splitlines(), tag_filter)


def tag_version_filter(x):
    """
    >>> tag_version_filter('random') is None
    True
    >>> tag_version_filter('v1.2.3')
    (1, 2, 3)
    >>> tag_version_filter('v0.0.0')
    (0, 0, 0)
    >>> tag_version_filter('v0.10.123')
    (0, 10, 123)
    """
    if not x.startswith('v'):
        return
    v = []
    for b in x[1:].split('.'):
        try:
            v.append(int(b))
        except ValueError:
            v.append(b)
    return tuple(v)


def git_tag_versions(**env):
    return git_tags(git_tag_version_filter, **env)


def git_add_v0(**env):
    pass


def git_describe(**env):
    git_unshallow(**env)
    git_fetch_tags(**env)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
