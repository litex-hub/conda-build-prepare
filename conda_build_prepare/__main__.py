#!/usr/bin/env python
import argparse
import os
import sys

from .conda_cmds import prepare_environment, prepare_recipe, restore_config_files
from .prepare import prepare_directory

def existingDir(dir_name):
    if dir_name == 'restore':
        restore_config_files()
        sys.exit(0)

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
    parser.add_argument("recipe", action="store", type=existingDir, metavar="RECIPE", help="The directory with a recipe to be prepared; use 'restore' as a RECIPE to restore conda configuration files previously commented out by the tool.")
    parser.add_argument("--dir", action="store", required=True, type=newDir, dest="directory", help="Such directory will be created with the recipe, conda environment and sources prepared to build the package.")
    parser.add_argument("--channels", action="store", required=False, metavar="CHANNEL", nargs="+", help="Each CHANNEL will be added to the environment's '.condarc' (with the last one on top).")
    parser.add_argument("--packages", action="store", required=False, metavar="PACKAGE", nargs="+", help="Each PACKAGE will be installed in the output conda environment alongside 'conda-build'.")
    args = parser.parse_args()

    os.mkdir(args.directory)
    # These directories will contain prepared recipe, conda environment and source repositories
    recipe_dir = os.path.join(args.directory, 'recipe')
    env_dir = os.path.join(args.directory, 'conda-env')
    git_dir = os.path.join(args.directory, 'git-repos')

    prepare_directory(args.recipe, recipe_dir)

    # Those will be applied in the prepared environment
    env_settings = {
            'set': {
                'safety_checks': 'disabled',
                'channel_priority': 'strict',
                'always_yes': 'yes',
                },
            }
    if args.channels is not None:
        env_settings['prepend'] = { 'channels': args.channels }

    prepare_environment(recipe_dir, env_dir, args.packages or [], env_settings)

    prepare_recipe(recipe_dir, git_dir, env_dir)

    print()
    print("To build the package in the prepared environment, run:")
    print(f"  conda activate {os.path.relpath(env_dir)}")
    print(f"  conda build {os.path.relpath(recipe_dir)}")
    print("or:")
    print(f"  conda run -p {os.path.relpath(env_dir)} conda build {os.path.relpath(recipe_dir)}")
    print()

