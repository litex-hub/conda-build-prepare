#!/usr/bin/env python3

import os

def get_travis_slug():
    travis_repo_slug = os.environ.get('TRAVIS_REPO_SLUG')
    if travis_repo_slug:
        return travis_repo_slug
    travis_pull_request_slug = os.environ.get('TRAVIS_PULL_REQUEST_SLUG')
    if travis_pull_request_slug:
        return travis_repo_slug
