conda-build-prepare
===================

This repository contains a tool for unified conda package building.

The ``conda-build-prepare`` tool creates almost completely fixed package recipe, conda environment and git repositories by rendering metadata and embedding crucial data inside of them thus making the package building much more consistent regardless of the building time and environment.

It also extracts data from the repository containing the recipe and populates the ``recipe_append.yaml`` file, which is automatically added to the metadata (as of ``conda-build`` v3.0).

After running the tool, to build the package in the prepared environment, run::

  conda activate $DIRECTORY/conda-env
  conda build $DIRECTORY/recipe

or::

  conda run -p $DIRECTORY/conda-env conda build $DIRECTORY/recipe

(``$DIRECTORY`` is the argument passed to the ``conda-build-prepare`` using ``--out``).

Stages of preparation:

#. preparing the working directory,
#. extracting the build environment information,
#. preparing the build environment,
#. rendering the recipe,
#. cloning git source repositories,
#. preparing git tags for better version description,
#. embedding script_env variables.

Options::

    package_dir         Path to the directory containing ``meta.yaml`` of the package
    --out=DIRECTORY     Use DIRECTORY to store generated files on which ``conda build`` should be run
    -v, --verbose       Add more verbosity to output

Preparing the working directory
-------------------------------

The ``--out`` parameter value (``$DIRECTORY``) is used as a target directory name, in which ``conda-env``, ``git-repos`` and ``recipe`` directories will be created.
The directory specified as a ``package_dir`` will be copied as the ``$DIRECTORY/recipe`` directory.

While all packages are expected to have a ``meta.yaml``, the ``prescript.${TOOLCHAIN_ARCH}.sh`` can be used to download or generate it.
It is executed right after copying the ``package_dir``.

Extracting the build environment information
--------------------------------------------

Conda packages are provided with the following metadata:

#. repository of the original recipe/build scripts,
#. type of environment: local build (default), Travis CI, etc.,
#. additional Travis build info (following the https://github.com/SymbiFlow/conda-packages/blob/master/conda-meta-extra.sh).

Preparing the build environment
-------------------------------

Conda environment created in ``$DIRECTORY/conda-env`` will contain basic packages necessary for building and rendering metadata, i.e. ``python``, ``conda-build``, ``conda-verify``, ``anaconda-client``, ``jinja2``, ``pexpect`` and ``ripgrep`` (``ripgrep`` only on Linux and macOS).

After creating this environment, the ``conda-build-prepare`` will look for all ``condarc`` files influencing it.
All such files found by the tool will be "neutralized" by commenting them out.
Their paths are added to the ``conda-build-prepare_srcs.txt`` inside the system's temp dir (``tempfile.gettempdir()``) for restoring.

The commented out user or global ``condarc`` files can be restored by running ``conda-build-prepare`` with the word ``restore`` instead of a ``package_dir``.

Then, package's condarc (``condarc``, ``condarc_linux``, ``condarc_macos`` or ``condarc_windows`` from ``package_dir``) will be set as the most important one (``conda-env/condarc``) and other basic settings will be applied to this environment.

Rendering the recipe
--------------------

The goal is to set each package used for building with specific version.
This will allow to always use the same packages during building even if some newer version of any of the required ``build`` or ``host`` package emerges.

Conda environment created in ``$DIRECTORY/conda-env`` is used for rendering the recipe to ensure the same settings with future building (channels, channel priority etc.).

After all of the tool's stages are completed, the rendered version of the recipe will replace ``meta.yaml`` that was there before rendering.
Contents of the original ``meta.yaml`` will be placed at the end of the file as a comment.

``recipe_append.yaml`` will be incorporated in the rendered recipe automatically by the ``conda render``.

Cloning git source repositories
-------------------------------

Due to problems with Conda's own repository management [TODO: what exactly?], ``conda-build-prepare`` clones the repository by itself and allows ``conda build`` to operate on the prefetched copy.

Each ``git_url`` source repository is cloned to the ``$DIRECTORY/git-repos`` directory.
The relative submodules of those cloned repositories (where submodule's url starts with ``../``) will also be cloned.
It's because ``git`` will expect them in the same parent directory for initializing the submodule.

The resulting recipe will have each ``git_url`` replaced with the local path to a repository cloned from the original ``git_url``.

Preparing git tags for better version description
-------------------------------------------------

The previous version of conda-related tooling used to rewrite git tags in order to let conda automatically detect the version via ``git-describe``.

The ``conda-build-prepare`` tool makes version format unified among various packages.
This is achieved by checking recipe source's git tags for any version-like part and modifying it by leaving only this version-like part prefixed with a ``v`` after rewriting.

The following version formats are supported:

- ``vX.Y``,
- ``vX.Y.Z``,
- ``vX.Y.Z-rcQ``,
- all of the above variations with punctuation replaced with dashes or underscores.

If no valid tags are found, a v0.0 tag is created on the oldest commit in the repo.

After that, the package version will be set with the ``git describe`` result on such repository after replacing dashes with underscores because of the ``package/version`` key restrictions.

Embedding script_env variables
------------------------------

The recipe can allow some environment variables to influence building through ``build/script_env`` key.
To unify the building process, ``conda-build-prepare`` embeds all such variables inside the ``conda-env`` with the values they're set to at that time.

Such embedded variables are set while activating conda environment (or runnning ``conda run``).
If environment already has those variables set, the embedded variables will replace them.

If during this stage there are some ``script_env`` variables not set with any value in the environment, they will be removed from the ``script_env`` to never influence building this package.
