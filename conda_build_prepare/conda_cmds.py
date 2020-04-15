#!/usr/bin/env python3
import os
import json
import subprocess
import yaml
from prepare import get_local_channels

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

def get_git_uris(package_dir):
    meta = get_package_config(package_dir)
    return find("git_url", meta)

def get_package_config(package_dir):
    package_meta_yaml = os.path.join(package_dir, "meta.yaml")
    if not os.path.exists(package_meta_yaml):
        raise Exception(f"Missing meta.yaml in {package_dir}")
    with open(package_meta_yaml, "r") as f:
        return yaml.load(f)

def dump_config(package_dir):
    print(repr(get_package_config(package_dir)))

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

if __name__ == "__main__":
    import doctest
    doctest.testmod()