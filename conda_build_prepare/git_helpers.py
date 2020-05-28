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

def remotes(direction):
    if direction not in ["fetch", "pull"]:
        return None
    remotes = subprocess.check_output( ['git', 'remote', '-v']).decode('utf-8').strip().split("\n")
    return [i for i in remotes if direction in i]

def upstream(**env):
    """Get 'upstream' URL for the git repository."""
    remotes = remotes('fetch')

    # Try the remote tracking value for this branch
    try:
        upstream = subprocess.check_output(
            ['git', 'rev-parse', '--symbolic-full-name', '@{u}'], env=env,
        ).decode('utf-8').strip()
        if upstream and '/' in upstream:
            _, __, remote, remote_branch = upstream.split('/')
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

def sort_tags(tags, tag_filter=None):
    """
    >>> sort_tags(['a', 'c', '1'])
    ['1', 'a', 'c']
    >>> sort_tags(['v1.101.3', 'v1.101.2', 'v1.100.11', 'hello'], tag_version_filter)
    ['v1.100.11', 'v1.101.2', 'v1.101.3']
    """
    if tag_filter is None:
        tag_filter = lambda x: x

    to_sort = []
    for x in tags:
        sort_key = tag_filter(x)
        if sort_key is None:
            continue
        to_sort.append((sort_key, x))
    to_sort.sort()

    return [x for _, x in to_sort]

def git_add_tag(tag, sha, **env):
    subprocess.check_call(['git', 'tag', '-a', tag, sha, f'-m"{tag}"'], env=env)

def git_add_initial_tag(**env):
    first_commit = subprocess.check_output(['git', 'rev-list', '--max-parents=0', 'HEAD'], env=env).decode('utf-8')
    git_add_tag('v0.0', first_commit, env)


def git_drop_tags(tags, **env):
    for tag in tags:
        subprocess.check_call(['git', 'tag', '-d', tag], env=env)


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
    return list_tags(tag_version_filter, **env)


def git_add_v0(**env):
    pass


def git_describe(**env):
    unshallow(**env)
    fetch_tags(**env)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
