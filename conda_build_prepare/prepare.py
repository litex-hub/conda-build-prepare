#!/usr/bin/env python3

import json
import os
import re
import subprocess
import yaml
from git import remotes, extract_github_user
from travis import get_travis_slug

from collections import OrderedDict

#import conda

def get_local_channels():
    local_channels = OrderedDict()

    travis_slug = get_travis_slug()
    if travis_slug:
        user = extract_github_user(travis_slug)
        assert user, travis_slug
        local_channels[user] = None

    for url in remotes('fetch').values():
        user = extract_github_user(url)
        if user:
            local_channels[user] = None

    return tuple(local_channels.keys())


def write_metadata(package_dir):
    metadata_file = os.path.join(package_dir, 'recipe_append.yaml')

    metadata = {
        'extra': {}
    }

    # Try and get the recipe metadata from git

    # Fill in metadata from travis environment
    if os.environ.get('TRAVIS', 'false') == 'true':
        metadata['extra']['travis'] = {
            'job_id': int(os.environ.get('TRAVIS_JOB_ID', repr(-1))),
            'job_num': int(os.environ.get('TRAVIS_JOB_NUMBER', repr(-1))),
            'type': os.environ.get('TRAVIS_EVENT_TYPE'),
        }
        # Override details from git with data from travis
        metadata['extra']['recipe']['repo'] = 'https://github.com/'+get_travis_slug()
        metadata['extra']['recipe']['branch'] = os.environ.get('TRAVIS_BRANCH', '?')
        metadata['extra']['recipe']['commit'] = os.environ.get('TRAVIS_COMMIT', '?')

if __name__ == "__main__":
    import doctest
    doctest.testmod()
