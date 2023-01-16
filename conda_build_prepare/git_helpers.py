#!/usr/bin/env python3

import os
import re
import subprocess
import urllib.parse

from datetime import datetime, timezone

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


def _call_custom_git_cmd_cp(git_repo, cmd_string, check=True,
        stderr=subprocess.PIPE) -> subprocess.CompletedProcess:
    cmd = cmd_string.split()
    if cmd[0] != 'git':
        cmd.insert(0, 'git')
    return subprocess.run(cmd, check=check, cwd=git_repo,
            encoding='utf-8', stderr=stderr, stdout=subprocess.PIPE)


def _call_custom_git_cmd(git_repo, cmd_string, check=True, quiet=False) -> str:
    stdout = _call_custom_git_cmd_cp(
                git_repo, cmd_string, check,
                # None means "don't capture"
                stderr=subprocess.DEVNULL if quiet else None
            ).stdout
    return stdout.strip()


# It's possible to have a git tag named differently than it's internally known as.
# See 'misnamed' in git's 'builtin/describe.c' source file for details.
#
# Let's check whether git printed a warning about such a situation to STDERR and
# use the internal name of the tag if so. Two versions of the warning were used.
def handle_git_describe_stderr(stderr) -> str:
    for pattern in [
                "tag '.*' is really '(.*)' here",          # since git v1.5.5
                "tag '(.*)' is externally known as '.*'",  # since git v2.27
            ]:
        match = re.search(pattern, stderr)
        if match:
            return match.group(1)

    # Let's print the stderr if it wasn't any of these messages.
    print(stderr)
    return None


def get_first_reachable_tag(git_repo):
    try:
        cp = _call_custom_git_cmd_cp(git_repo, 'describe --tags --abbrev=0')
        tag_name = cp.stdout.strip()
        if cp.stderr:
            misnamed_tag = handle_git_describe_stderr(cp.stderr)
            if misnamed_tag:
                return misnamed_tag
        return tag_name
    except subprocess.CalledProcessError:
        return None


def _set_git_config(git_repo, setting, value):
    _call_custom_git_cmd(git_repo, f'config {setting} {value}')

def _unset_git_config(git_repo, setting):
    _call_custom_git_cmd(git_repo, f'config --unset {setting}')

class GitUserContext:
    def __init__(self, git_repo, name, email):
        self._name = name
        self._email = email
        self._repo = git_repo

    def __enter__(self):
        _set_git_config(self._repo, 'user.name', self._name)
        _set_git_config(self._repo, 'user.email', self._email)

    def __exit__(self, exc_type, exc_value, traceback):
        _unset_git_config(self._repo, 'user.name')
        _unset_git_config(self._repo, 'user.email')


def git_add_tag(git_repo, tag, sha, temp_user=True):
    git_cmd = f'tag --annotate --force -m"{tag}" {tag} {sha}'
    if temp_user:
        with GitUserContext(git_repo, 'conda-build-prepare',
                'conda-build-prepare@github.com'):
            _call_custom_git_cmd(git_repo, git_cmd)
    else:
        _call_custom_git_cmd(git_repo, git_cmd)
    print(f"Successfully tagged '{sha}' object as '{tag}'")


def git_add_initial_tag(git_repo, temp_user=True):
    first_commit = _call_custom_git_cmd(git_repo, 'rev-list --max-parents=0 HEAD')
    git_add_tag(git_repo, '0.0', first_commit, temp_user)


def git_drop_tag(git_repo, tag):
    _call_custom_git_cmd(git_repo, f'tag -d {tag}')


def tag_extract_version(tag):
    """
    >>> tag_extract_version('random') is None
    True
    >>> tag_extract_version('random-1.23.4')
    'v1.23.4'
    >>> tag_extract_version('random0.5')
    'v0.5'
    >>> tag_extract_version('random-a.b.c') is None
    True
    >>> tag_extract_version('random-5') is None
    True
    >>> tag_extract_version('0.78.9random')
    'v0.78.9'
    >>> tag_extract_version('50_78-91-xrandom')
    'v50_78-91'
    >>> tag_extract_version('0-78-91-rc5_random')
    'v0-78-91-rc5'
    >>> tag_extract_version('7_8_rc12-lessrandom')
    'v7_8_rc12'
    """
    version_spec = r"""[0-9]+[_.\-][0-9]+  # required major and minor
                       ([_.\-][0-9]+)?     # optional micro
                       ([_.\-][0-9]+)?     # optional extra number
                       ([._\-]*rc[0-9]+)?  # optional release candidate"""

    version_search = re.search(version_spec, tag, re.VERBOSE)
    if version_search is None:
        return None
    else:
        version_found = version_search.group(0)
        return version_found


def git_rewrite_tags(git_repo):
    print(f'\nRewriting tags in "{os.path.abspath(git_repo)}"...\n')

    while True:
        tag = get_first_reachable_tag(git_repo)
        if tag is None:
            # Add '0.0' tag on initial commit and skip rewriting.
            git_add_initial_tag(git_repo)
            break
        tag_version = tag_extract_version(tag)
        if tag_version is None:
            git_drop_tag(git_repo, tag)
        else:
            if tag_version != tag:
                # Add tag again but with pure version-like name
                commit = _call_custom_git_cmd(git_repo, f'rev-list -n 1 {tag}')
                git_drop_tag(git_repo, tag)
                git_add_tag(git_repo, tag_version, commit)
            # Finish rewriting after the first successfully rewritten tag
            break


def git_describe(git_repo):
    return _call_custom_git_cmd(git_repo, f'describe --long --tags')


def git_clone(url, parent_dir, dir_name=None):
    assert os.path.exists(parent_dir)

    if dir_name is None:
        dir_name = extract_github_repo(url)
        # If not a GitHub URL, just get the last part (excluding .git)
        if dir_name is None:
            dir_name = re.search(r'.+/([^/]+)(.git)?', url).groups()[0]

    repo_path = os.path.join(parent_dir, dir_name)

    assert not os.path.exists(repo_path)
    _call_custom_git_cmd(None, f'clone {url} {repo_path}')

    return repo_path


def git_clone_relative_submodules(git_repo, git_url):
    gitmodules_path = os.path.join(git_repo, '.gitmodules')

    if os.path.exists(gitmodules_path):
        with open(gitmodules_path, 'r') as f:
            gitmodules = f.read()
        # The URLs are stripped from starting '../' for urljoin to work
        # properly; oherwise two parts of the git_url are substituted
        rel_modules = re.findall('url = \.\./(\S+)', gitmodules)
        for rel_module in rel_modules:
            module_url = urllib.parse.urljoin(git_url, rel_module)
            repo_parent = os.path.dirname(git_repo)

            # rel_module is passed to make sure cloning destination
            # directory will have this exact name (e.g. .git suffix)
            git_clone(module_url, repo_parent, rel_module)


def git_checkout(git_repo, revision):
    _call_custom_git_cmd(git_repo, f'checkout {revision}')


def git_get_head_time(git_repo):
    timestamp_str = _call_custom_git_cmd(git_repo, 'git log --format=%ct -n1')
    return datetime.fromtimestamp(int(timestamp_str), timezone.utc)


def is_inside_git_repo(path):
    git_cmd = 'git rev-parse --is-inside-work-tree'
    git_stdout = _call_custom_git_cmd(path, git_cmd, check=False, quiet=True)
    return git_stdout == 'true'


if __name__ == "__main__":
    import doctest
    doctest.testmod()
