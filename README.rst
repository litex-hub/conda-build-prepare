conda-build-prepare
===================

This repository contains a tool for unified conda package building.

It extracts data from the recipe repositories and puts it into metadata of the built package.

While all packages are expected to have a ``meta.yaml`` file (or, at least, a script that will prepare it), the ``conda-build-prepare`` tool populates the ``recipe_append.yaml`` file, which is automatically added to metadata (as of ``conda-build`` v3.0).

Stages of preparation:

#. preparing the working directory,
#. preparing the build environment,
#. cleaning up git tags,
#. extracting the build environment information.

Options::

    package_dir         Path to the directory containing ``meta.yaml`` of the package
    --out=DIRECTORY     Use DIRECTORY to store generated files on which ``conda build`` should be run
    -v, --verbose       Add more verbosity to output

Preparing the working directory
-------------------------------

Due to problems with Conda's own repository management [TODO: what exactly?], ``conda-build-prepare`` clones the repository by itself and allows ``conda build`` to operate on the prefetched copy.

The ``--out`` parameter value is used as a target directory name, in which the build scripts and ``yaml`` files are put, along with the target repository.

If no ``--out`` parameter is provided, then a temporary directory is created.

Preparing the build environment
-------------------------------

TODO

Open questions:

#. How to force Conda to not use condarc?
#. How to prepare the environment for subsequent use of ``conda build``?
   Generate a script that will be run instead of ``conda build``?

Cleaning up git tags
--------------------

The previous version of conda-related tooling used to rewrite git tags in order to let conda automatically detect the version via ``git-describe``.

While we use the information extracted from tags, the exact version is provided to ``recipe_append.yaml`` via the ``version`` key.

The following version formats are supported:

- ``vX.Y``,
- ``vX.Y.Z``,
- ``vX.Y.Z-rcQ``,
- all of the above variations with punctuation replaced with dashes or underscores.

If there are no tags denoting the version, ``v0.0`` is used instead.

Extracting the build environment information
--------------------------------------------

Conda packages are provided with the following metadata:

#. repository of the original recipe/build scripts,
#. type of environment: local build (default), Travis CI, etc.,
#. additional Travis build info (following the https://github.com/SymbiFlow/conda-packages/blob/master/conda-meta-extra.sh).