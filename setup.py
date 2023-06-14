import codecs
import os
import setuptools

def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_version(rel_path):
    for line in read(rel_path).splitlines():
        if line.startswith('__version__'):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")


INSTALL_REQUIRES = [
    'numpy',
    'ebmlite>=3.1.0'
    ]

TEST_REQUIRES = [
    'pytest>=4.6',
    'pytest-xdist[psutil]',
    'mock',
    'pytest-cov',
    'sphinx==4.2.0',
    'scipy;python_version<"3.10"',
    ]

DOCS_REQUIRES = [
    "sphinx==4.2.0",
    "pydata-sphinx-theme==0.7.2",
    "nbsphinx",
    ]

EXAMPLE_REQUIRES = [
    'matplotlib'
    ]

setuptools.setup(
        name='idelib',
        version=get_version('idelib/__init__.py'),
        author='Mide Technology',
        author_email='help@mide.com',
        description='Python API for accessing IDE data recordings',
        long_description=read('README.md'),
        long_description_content_type='text/markdown',
        url='https://github.com/MideTechnology/idelib',
        license='MIT',
        classifiers=['Development Status :: 5 - Production/Stable',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Programming Language :: Python :: 3.6',
                     'Programming Language :: Python :: 3.7',
                     'Programming Language :: Python :: 3.8',
                     'Programming Language :: Python :: 3.9',
                     'Programming Language :: Python :: 3.10',
                     'Programming Language :: Python :: 3.11',
                     'Topic :: Scientific/Engineering',
                     ],
        keywords='ebml binary ide mide',
        packages=setuptools.find_packages(exclude=('testing',)),
        package_dir={'idelib': './idelib'},
        package_data={
            'idelib': ['schemata/*'],
        },
        project_urls={
            "Bug Tracker": "https://github.com/MideTechnology/idelib/issues",
            "Documentation": "https://mide-technology-idelib.readthedocs-hosted.com/en/latest/",
            "Source Code": "https://github.com/MideTechnology/idelib",
            },
        test_suite='./testing',
        python_requires='>=3.5',
        install_requires=INSTALL_REQUIRES,
        extras_require={
            'test': INSTALL_REQUIRES + TEST_REQUIRES,
            'docs': INSTALL_REQUIRES + DOCS_REQUIRES,
            'example': INSTALL_REQUIRES + EXAMPLE_REQUIRES,
            },
)
