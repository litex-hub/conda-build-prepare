#!/usr/bin/env python3
import os
import json
import subprocess
import yaml
import re
import io
import shutil
import tempfile
import sys

from .prepare import get_local_channels, get_package_condarc
from .git_helpers import git_checkout, git_clone, git_describe, \
        git_rewrite_tags, git_add_tag, git_clone_relative_submodules

def find(key, dictionary):
    """
    >>> list(find("key", { "key" : "value" }))
    ['value']
    >>> list(find("key", { "_" : { "key": "value" } }))
    ['value']
    >>> list(find("key", { "key" : "value", "other" : { "key" : "value2" } }))
    ['value', 'value2']
    >>> list(find("key", { "_" : [ { "key" : "value" } ] }))
    ['value']
    >>> list(find("key", { "_" : [ { "key" : "value" }, { "key": "value2" } ] }))
    ['value', 'value2']
    """
    for k, v in dictionary.items():
        if k == key:
            yield v
        elif isinstance(v, dict):
            for result in find(key, v):
                yield result
        elif isinstance(v, list):
            for d in v:
                if isinstance(d, dict):
                    for result in find(key, d):
                        yield result


def get_git_uris(package_dir_or_metadata):
    meta = get_metadata(package_dir_or_metadata)
    return find("git_url", meta)


def get_package_config(package_dir, env_dir, verbose=False):
    assert os.path.exists(package_dir)

    print('Rendering package metadata, please wait...\n')
    meta = None
    try:
        rendered_path = os.path.join(package_dir, 'rendered_metadata.yaml')
        _call_conda_cmd_in_env(f"conda render -f {rendered_path} {package_dir}", env_dir)
        with open(rendered_path, 'r') as rendered_file:
            meta = yaml.safe_load(rendered_file.read())
    except:
        print('Error during package metadata rendering!')
        raise
    finally:
        # Clean the build data created while rendering the metadata.
        _call_conda_cmd_in_env(f"conda build purge-all", env_dir)
        if os.path.exists(rendered_path):
            os.remove(rendered_path)

    return meta


def dump_config(package_dir_or_metadata):
    meta = get_metadata(package_dir_or_metadata)
    print(yaml.dump(meta))


def get_metadata(package_dir_or_metadata):
    if not isinstance(package_dir_or_metadata, dict):
        return get_package_config(package_dir_or_metadata)
    else:
        return package_dir_or_metadata


def git_cache_path():
    return os.path.join(path(), "conda-bld", "git_cache")


def path():
    return os.environ.get('CONDA_PATH', os.path.expanduser('~/conda'))


def run(cmd, *args):
    conda_bin = os.path.join(path(), "bin", "conda")

    full_cmd = [conda_bin, cmd, '--json', '--yes']
    full_cmd.extend(args)
    result = json.loads(subprocess.check_output(full_cmd).decode('utf-8'))
    if not result['success']:
        raise subprocess.CalledProcessError(
            'Command: {r} failed\n{}'.format(" ".join(full_cmd), result))

    if cmd == "create":
        return result['prefix']


def create_env(package_dir):
    package = os.path.split(package_dir)[-1]
    package_condarc = os.path.join(package_dir, 'condarc')

    data = {}
    if os.path.exists(package_condarc):
        data = yaml.safe_load(open(package_condarc))

    for lc in reversed(get_local_channels()):
        data['channels'].insert(0, lc)

    prefix = run("create", "--name", package, "--strict-channel-priority")
    env_condarc = os.path.join(prefix, 'condarc')
    with open(env_condarc, "w") as f:
        yaml.safe_dump(data, f)

    print(open(env_condarc).read())


def _prepare_single_source(git_repos_dir, src):
    if 'git_url' not in src.keys():
        # Not a git source; won't be prepared and is not modified
        return src
    else:
        # Clone, checkout the repository and set local path as git_url
        src_path = git_clone(src['git_url'], git_repos_dir)
        if 'git_rev' in src.keys():
            git_checkout(src_path, src['git_rev'])
        git_clone_relative_submodules(src_path, src['git_url'])
        src['git_url'] = os.path.abspath(src_path)
        return src

def _add_extra_tags_if_exist(package_dir, repo_path):
    assert os.path.exists(package_dir)
    extra_tags_path = os.path.join(package_dir, 'extra.tags')

    if not os.path.exists(extra_tags_path):
        return
    else:
        print()
        print('Adding tags from extra.tags file...')
        with open(extra_tags_path, 'r') as extra_tags_file:
            for line in extra_tags_file.readlines():
                try:
                    tag, sha = line.replace('\n', '').split()
                    git_add_tag(repo_path, tag, sha, temp_user=True)
                except ValueError:
                    print('Malformed line in extra.tags:')
                    print('\t"{}"'.format(line.replace('\n', '')))
                    print()
                    continue
                except subprocess.CalledProcessError:
                    print('Git had problems adding extra.tags line:')
                    print('\t"{}"'.format(line.replace('\n', '')))
                    print()
                    continue
        print()

def _call_conda_cmd_in_env(cmd_string, env_path):
    assert os.path.isdir(env_path), env_path

    return subprocess.check_output(f'conda run -p {env_path} {cmd_string}'
            .split(), encoding='utf-8', env=os.environ).strip()

_modification_line = '# Modified by the conda-build-prepare\n'

def _comment_file(path):
    assert os.path.exists(path), path

    with open(path, 'r') as f:
        lines = f.readlines()
    with open(path, 'w') as f:
        f.write(_modification_line)
        for line in lines:
            f.write('#' + line)

_modified_cfg_srcs = os.path.join(tempfile.gettempdir(),
        'conda-build-prepare_srcs.txt')


# The package dir is needed to put package's condarc in the right place
def prepare_environment(recipe_dir, env_dir, packages, env_settings):
    assert os.path.exists(os.path.join(recipe_dir, 'meta.yaml')), recipe_dir
    assert not os.path.exists(env_dir), env_dir
    assert os.path.isabs(env_dir), env_dir
    assert type(env_settings) is dict, env_settings

    print('Preparing the environment, please wait...\n')

    # Always install conda-build in the created environment
    packages += ' conda-build'

    # Create environment
    subprocess.check_output(
            # (no-default-packages counteracts create_default_packages option)
            f'conda create --yes --no-default-packages -p {env_dir} {packages}'
            .split())

    # Comment out all config files influencing created environment
    config = _call_conda_cmd_in_env('conda config --show-sources', env_dir)
    config_sources = re.findall('==> (.*) <==', config)
    file_modified = False
    for config_src in config_sources:
        with open(_modified_cfg_srcs, 'a') as tmp:
            # Sources are not only files (e.g. it can be 'envvar')
            if os.path.isabs(config_src):
                _comment_file(config_src)
                file_modified = True
                # Remember files for restoring
                tmp.write(config_src + '\n')
                print(f"Commented out conda configuration file: {config_src}")
    if file_modified:
        print("Use 'restore' as a package argument to restore those files.")
        print()

    # Copy package's condarc file as the most important condarc: $ENV/condarc.
    #
    # It won't be overwritten by 'conda config --env' because this command
    # uses different and less important $ENV/.condarc (DOTcondarc).
    package_condarc = get_package_condarc(recipe_dir)
    if package_condarc is not None:
        shutil.copy(package_condarc, os.path.join(env_dir, 'condarc'))

    # Apply env_settings (dictionary with keys: 'add'/'prepend', 'append', 'set')
    for action in env_settings:
        # It can be a single command for each action
        command = f"conda config --env"
        for key in env_settings[action]:
            if type(env_settings[action][key]) is list:
                values = env_settings[action][key]
            # If not a list, create a single-element list 'values'
            else:
                values = [env_settings[action][key]]
            for value in values:
                command += f" --{action} {key} {value}"
        _call_conda_cmd_in_env(command, env_dir)


def _uncomment_file(path):
    assert os.path.exists(path), path

    with open(path, 'r') as f:
        lines = f.readlines()
    if not lines[0] == _modification_line:
        raise ValueError(f"'{path}' wasn't modified by the conda-build-prepare")
    with open(path, 'w') as f:
        for line in lines[1:]:
            f.write(line.lstrip('#'))

def restore_config_files():
    if not os.path.exists(_modified_cfg_srcs):
        print('There are no config files to restore')
        return

    with open(_modified_cfg_srcs, 'r') as paths_file:
        # Don't use split with '\n' as the returned list's last element is ''
        paths = paths_file.read().split()
        for config_path in paths:
            try:
                _uncomment_file(config_path)
            except Exception as e:
                print(f"Problem while restoring {config_path}:")
                print(f"{repr(e)}")
                print()
    os.remove(_modified_cfg_srcs)


def prepare_recipe(package_dir, git_repos_dir, env_dir):
    assert os.path.exists(package_dir), package_dir
    assert not os.path.exists(git_repos_dir), git_repos_dir
    assert os.path.exists(env_dir), env_dir

    # Render metadata

    meta = get_package_config(package_dir, env_dir)

    if len(list(get_git_uris(meta))) < 1:
        print('\nNo git repositories in the package recipe; version won\'t be set.\n')
    else:
        # Download sources and make conda use always those
        print('Downloading git sources...\n')

        sources = meta['source']
        os.mkdir(git_repos_dir)
        if isinstance(sources, list):
            new_sources = []
            for src in sources:
                new_sources.append(_prepare_single_source(git_repos_dir, src))
                print()
        else:
            new_sources = _prepare_single_source(git_repos_dir, sources)
        meta['source'] = new_sources

        # Set version based on modified git repo
        print('Modifying git tags to set proper package version...\n')

        git_uris = list(get_git_uris(meta))
        # For multiple git repositories in sources, the first one is always used
        first_git_repo_path = git_uris[0]

        git_rewrite_tags(first_git_repo_path)
        _add_extra_tags_if_exist(package_dir, first_git_repo_path)
        version = git_describe(first_git_repo_path).replace('-', '_')
        meta['package']['version'] = version

    # Embed script_envs in the environment
    print("Embedding 'build/script_env' variables in the environment...")

    if 'build' in meta.keys() and 'script_env' in meta['build'].keys():
        env_vars = meta['build']['script_env']
        assert type(env_vars) is list, env_vars

        vars_string = ''
        env_vars_set = []
        for env_var in env_vars:
            if env_var in os.environ.keys():
                vars_string += f"{env_var}={os.environ[env_var]} "
                env_vars_set.append(env_var)
            else:
                print(f"{env_var} variable isn't set; won't be allowed during building.")
        if vars_string:
            _call_conda_cmd_in_env(f"conda env config vars set {vars_string}", env_dir)
        meta['build']['script_env'] = env_vars_set

    # Save rendered recipe as meta.yaml

    meta_path = os.path.join(package_dir, 'meta.yaml')
    with open(meta_path, 'r+') as meta_file:
        meta_lines = meta_file.readlines()

        meta_file.seek(0)
        meta_file.write('# Rendered by the conda-build-prepare\n')
        meta_file.write('# Original meta.yaml can be found at the end of this file\n')
        meta_file.write('\n')
        # Save the 'package' section first (Windows needs it)
        pkg_section = { 'package': meta.pop('package') }
        meta_file.write(yaml.safe_dump(pkg_section))
        # Convert local git_urls with cygpath, if available
        if sys.platform in ['cygwin', 'msys', 'win32']:
            if type(meta['source']) is list:
                for src in meta['source']:
                    _try_cygpath_on_git_url(src)
            else:
                _try_cygpath_on_git_url(meta['source'])
        meta_file.write(yaml.safe_dump(meta))
        meta_file.write('\n')
        meta_file.write('# Original meta.yaml:\n')
        meta_file.write('#\n')
        meta_file.writelines(list(map(lambda line: '#' + line, meta_lines)))

def _try_cygpath_on_git_url(src_dict):
    try:
        if 'git_url' in src_dict.keys() and os.path.isdir(src_dict['git_url']):
            src_dict['git_url'] = subprocess.check_output(
                    ['cygpath', '-a', src_dict['git_url']],
                    encoding='utf-8', env=os.environ).strip()
    except FileNotFoundError:  # No cygpath
        pass


if __name__ == "__main__":
    import doctest
    doctest.testmod()
