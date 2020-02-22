#!/usr/bin/env python3

import json
import os
import re
import subprocess
import yaml

from collections import OrderedDict

#import conda

def get_local_channels():
    local_channels = OrderedDict()

    travis_slug = get_travis_slug()
    if travis_slug:
        user = get_github_user(travis_slug)
        assert user, travis_slug
        local_channels[user] = None

    for url in git_remotes('fetch').values():
        user = get_github_user(url)
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
        metadata['extra']['recipe']['repo'] = 'https://github.com/'+travis_repo_slug()
        metadata['extra']['recipe']['branch'] = os.environ.get('TRAVIS_BRANCH', '?')
        metadata['extra']['recipe']['commit'] = os.environ.get('TRAVIS_COMMIT', '?')


def sort_tags(tags, tag_filter=None):
    """
    >>> sort_tags(['a', 'c', '1'])
    ['1', 'a', 'c']
    >>> sort_tags(['v1.101.3', 'v1.101.2', 'v1.100.11', 'hello'], git_tag_version_filter)
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



if __name__ == "__main__":
    import doctest
    doctest.testmod()
