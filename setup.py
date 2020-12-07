import setuptools

with open("README.rst", "r") as readme_fh:
    readme_text = readme_fh.read()

with open("requirements.txt", "r") as requirements_fh:
    requirements = [ line.strip() for line in requirements_fh.readlines() ]

setuptools.setup(
    name="conda-build-prepare",
    version="0.1",
    description="A tool preparing Conda recipes for building",
    long_description=readme_text,
    long_description_content_type="text/x-rst",
    url="https://github.com/litex-hub/conda-build-prepare",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS"
    ],
    python_requires='>=3.6',
    install_requires=requirements,
)
