#!/usr/bin/env python3

import io
import jinja2
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Conda's `pip` doesn't install `ruamel.yaml` because it finds it is already
# installed but the one from Conda has to be imported with `ruamel_yaml`
try:
    from ruamel.yaml import YAML
except ModuleNotFoundError:
    from ruamel_yaml import YAML
yaml = YAML()
yaml.allow_duplicate_keys = True

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


def render_metadata(package_dir, env_dir, verbose=False):
    assert os.path.isdir(package_dir)

    print('Rendering package metadata, please wait...\n')
    meta = None
    try:
        rendered_path = os.path.join(package_dir, 'rendered_metadata.yaml')
        _call_conda_cmd_in_env(f"conda render -f {rendered_path} {package_dir}", env_dir)
        with open(rendered_path, 'r') as rendered_file:
            meta = yaml.load(rendered_file.read())
    except:
        print('Error during package metadata rendering!')
        raise
    finally:
        # Clean the build data created while rendering the metadata.
        _call_conda_cmd_in_env(f"conda build purge-all", env_dir)
        if os.path.exists(rendered_path):
            os.remove(rendered_path)

    return meta


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
        data = yaml.load(open(package_condarc))

    for lc in reversed(get_local_channels()):
        data['channels'].insert(0, lc)

    prefix = run("create", "--name", package, "--strict-channel-priority")
    env_condarc = os.path.join(prefix, 'condarc')
    with open(env_condarc, "w") as f:
        yaml.dump(data, f)

    print(open(env_condarc).read())


def _prepare_single_source(git_repos_dir, src):
    if 'git_url' not in src.keys():
        # Not a git source; won't be prepared or modified
        return None
    else:
        # Clone, checkout the repository and return its local path
        src_path = git_clone(src['git_url'], git_repos_dir)
        if 'git_rev' in src.keys():
            git_checkout(src_path, src['git_rev'])
        git_clone_relative_submodules(src_path, src['git_url'])
        return os.path.abspath(src_path)

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

# A wrapper for subprocess.check_output printing stdout in case of process
# error. By default it isn't printed and can make debugging much harder.
def _check_output(command, **kwargs):
    try:
        return subprocess.check_output(command.split(), encoding='utf-8',
                **kwargs).strip()
    except subprocess.CalledProcessError as e:
        print('!! =======================================================')
        print('!! ERROR: conda-build-prepare subprocess failed!')
        print('!!')
        print('!! Command called: ' + command)
        print('!!')
        print('!! STDERR not captured; look above for errors too! STDOUT:')
        print('!!')
        print(e.output.strip())
        print('!!')
        print('!! =======================================================')
        print()
        raise


def _call_conda_cmd_in_env(cmd_string, env_path):
    assert os.path.isdir(env_path), env_path

    return _check_output(f'conda run -p {env_path} {cmd_string}')

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
def prepare_environment(recipe_dir, env_dir, package_list, env_settings,
        top_channels):
    assert os.path.exists(os.path.join(recipe_dir, 'meta.yaml')), recipe_dir
    assert not os.path.exists(env_dir), env_dir
    assert os.path.isabs(env_dir), env_dir
    assert isinstance(env_settings, dict), env_settings
    assert isinstance(package_list, list), package_list

    print('Preparing the environment, please wait...\n')

    # Convert a list of packages to a string
    packages = ' '.join(package_list)

    # Always install conda-build in the created environment
    if 'conda-build' not in packages:
        packages += ' conda-build'

    # Create environment
    # (no-default-packages counteracts create_default_packages option)
    _check_output(f'conda create --yes --no-default-packages -p {env_dir} '
            + packages)

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

    # Apply env_settings (dictionary with keys: 'add'/'prepend', 'append', 'set')
    # to the second most important condarc file: `$ENV/.condarc` (DOTcondarc).
    for action in env_settings:
        # It can be a single command for each action
        command = f"conda config --env"
        for key in env_settings[action]:
            if isinstance(env_settings[action][key], list):
                values = env_settings[action][key]
            # If not a list, create a single-element list 'values'
            else:
                values = [env_settings[action][key]]
            for value in values:
                command += f" --{action} {key} {value}"
        _call_conda_cmd_in_env(command, env_dir)

    # Set package's `condarc` file as the most important one: `$ENV/condarc`.
    # If there's a `channels` key, then the `--channels` args are put on top.
    package_condarc = get_package_condarc(recipe_dir)
    if package_condarc is not None:
        with open(package_condarc, 'r') as f:
            condarc_yaml = yaml.load(f.read())
        if 'channels' in condarc_yaml:
            for channel in top_channels:
                condarc_yaml['channels'].insert(0, channel)
        with open(os.path.join(env_dir, 'condarc'), 'w') as f:
            yaml.dump(condarc_yaml, f)


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

    meta_path = os.path.join(package_dir, 'meta.yaml')
    with(open(meta_path, 'r+')) as meta_file:
        # Read 'meta.yaml' contents
        meta_contents = meta_file.read()
        original_meta = meta_contents

        # Load yaml with mostly dummy Jinja2 structures used in Conda recipes
        def _pin_compatible(package_name, min_pin='x.x.x.x.x.x', max_pin='x', lower_bound=None, upper_bound=None):
            return ''
        def _pin_subpackage(package_name, min_pin='x.x.x.x.x.x', max_pin='x', exact=False):
            return ''
        conda_context = {
                'environ':              os.environ,
                'os':                   os,
                'GIT_BUILD_STR':        '',
                'GIT_DESCRIBE_HASH':    '',
                'GIT_DESCRIBE_NUMBER':  '',
                'GIT_DESCRIBE_TAG':     '',
                'GIT_FULL_HASH':        '',
                'compiler':             lambda _: '',
                'pin_compatible':       _pin_compatible,
                'pin_subpackage':       _pin_subpackage,
                'resolved_packages':    lambda _: [],
                }
        jinja_rendered_meta = jinja2.Template(meta_contents).render(conda_context)

        safe_yaml = YAML(typ='safe')
        safe_yaml.allow_duplicate_keys = True
        # Yaml loader doesn't like [OS] after quoted strings (which are OK for Conda)
        # Quotes are removed before loading as they are irrelevant at this point
        meta = safe_yaml.load(jinja_rendered_meta.replace('"', ''))

        if len(list(find("git_url", meta))) < 1:
            print('No git repositories in the package recipe; tag rewriting will be skipped.')
            print()
        else:
            sources = meta['source']

            # Make sources a one-element list if it's not a list
            if not isinstance(sources, list):
                sources = [ sources ]

            if 'git_url' not in sources[0]:
                print("First source isn't a git repository; tag rewriting will be skipped.")
                print()
            else:
                # Clone sources and make conda use always those
                print('Cloning git sources...')
                print()

                os.mkdir(git_repos_dir)
                first_git_repo_path = None

                for src in sources:
                    # The recipe can have some mix of git and non-git sources
                    if 'git_url' in src:
                        local_git_url = _prepare_single_source(git_repos_dir, src)
                        meta_contents = meta_contents.replace(
                                f"git_url: {src['git_url']}", f"git_url: {local_git_url}")
                        if first_git_repo_path is None:
                            first_git_repo_path = local_git_url

                # Set version based on modified git repo
                print('Modifying git tags to set proper package version...')

                git_rewrite_tags(first_git_repo_path)
                _add_extra_tags_if_exist(package_dir, first_git_repo_path)
                version = git_describe(first_git_repo_path).replace('-', '_')
                meta_contents = re.sub(r'(\s+version:).+', r'\1 ' + str(version),
                        meta_contents)

                # Reset 'meta.yaml' and save metadata without GIT_* vars
                meta_file.seek(0)
                meta_file.truncate()
                meta_file.write(meta_contents)

    # Render metadata
    meta = render_metadata(package_dir, env_dir)

    # Embed script_envs in the environment
    print("Embedding 'build/script_env' variables in the environment...")

    if 'build' in meta.keys() and 'script_env' in meta['build'].keys():
        env_vars = meta['build']['script_env']
        assert isinstance(env_vars, list), env_vars

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

        # Restore `{{ compiler('c/cxx') }}` even though their corresponding packages have already
        # been added to the recipe. Their presence has some additional influence on `conda-build`.
        for lang, extra_specifiers in re.findall(r'''
                \{\{\s*
                compiler
                [\(\'"\s]+      # (' or (" with optional spaces
                ([a-zA-Z]+)     # lang (c/cxx/...)
                [\)\'"\s]+      # ') or ") with optional spaces
                \}\}
                (.*)            # extra_specifiers (e.g. 4.0 [linux])
                ''', ''.join(meta_lines), re.VERBOSE):
            # OS specifier will only work in quoted string if it's after '#' (double '#' is OK)
            extra_specifiers = extra_specifiers.replace('[', '# [')
            # lang has to be surrounded by double quotes; PyYaml dumps single ones wrong for Conda
            yaml_compiler = '{{ compiler("' + lang + '") }}' + extra_specifiers
            # In case there's no such section for the current OS ({{ compiler }} is for other OS)
            if 'build' not in meta['requirements']:
                meta['requirements']['build'] = []
            meta['requirements']['build'].append(yaml_compiler)

        meta_file.seek(0)
        meta_file.write('# Rendered by conda-build-prepare\n')
        meta_file.write('# Original meta.yaml can be found at the end of this file\n')
        meta_file.write('\n')

        # Convert local git_urls with cygpath, if available
        if sys.platform in ['cygwin', 'msys', 'win32']:
            if isinstance(meta['source'], list):
                for src in meta['source']:
                    _try_cygpath_on_git_url(src)
            else:
                _try_cygpath_on_git_url(meta['source'])
        yaml.dump(meta, meta_file)
        meta_file.write('\n')

        # Save original meta.yaml contents as a comment at the end
        meta_file.write('# Original meta.yaml:\n')
        meta_file.write('#\n')
        meta_file.write('# ' + original_meta.replace('\n', '\n# ')[:-2])

def _try_cygpath_on_git_url(src_dict):
    try:
        if 'git_url' in src_dict.keys() and os.path.isdir(src_dict['git_url']):
            src_dict['git_url'] = _check_output(
                    "cygpath -a " + src_dict['git_url'])
    except FileNotFoundError:  # No cygpath
        pass


if __name__ == "__main__":
    import doctest
    doctest.testmod()
