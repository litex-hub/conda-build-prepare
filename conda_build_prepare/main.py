#!/usr/bin/env python3
import argparse
import os
from prepare import prepare_directory

def existingDir(dir_name):
    dir_name = os.path.join(os.path.abspath(os.path.curdir), dir_name)
    if(not os.path.isdir(dir_name)):
        raise argparse.ArgumentTypeError(f"{dir_name} is not a valid directory")
    return dir_name

def newDir(dir_name):
    dir_name = os.path.join(os.path.abspath(os.path.curdir), dir_name)
    if(os.path.exists(dir_name)):
        raise argparse.ArgumentTypeError(f"{dir_name} already exists")
    return dir_name

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="conda-build-prepare", description="Conda helper tool for repository preparation")
    parser.add_argument("package", action="store", type=existingDir, help="Target package directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="Add more verbosity to output")
    parser.add_argument("--dir", action="store", required=True, type=newDir, dest="directory", help="Use DIRECTORY to store generated files and cloned repository")
    args = parser.parse_args()