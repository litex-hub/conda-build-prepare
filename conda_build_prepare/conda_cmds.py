#!/usr/bin/env python3
import os
import json
import subprocess
import yaml
from prepare import get_local_channels

def run(cmd, *args):
    conda_path = os.environ.get('CONDA_PATH', os.path.expanduser('~/conda'))
    conda_bin = os.path.join(conda_path, "bin", "conda")

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

    prefix = run_conda("create", "--name", package, "--strict-channel-priority")
    env_condarc = os.path.join(prefix, 'condarc')
    with open(env_condarc, "w") as f:
        yaml.safe_dump(data, f)

    print(open(env_condarc).read())


