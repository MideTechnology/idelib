import setuptools

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

INSTALL_REQUIRES = [
    'numpy',
    'ebmlite>=3.1.0'
    ]

TEST_REQUIRES = [
    'pytest>=4.6',
    'pytest-xdist[psutil]',
    'mock',
    'pytest-cov',
    'sphinx',
    'scipy;python_version<"3.10"',
    ]

DOCS_REQUIRES = [
    "sphinx",
    "pydata-sphinx-theme",
    ]

EXAMPLE_REQUIRES = [
    'matplotlib'
    ]

setuptools.setup(
        name='idelib',
        version='3.2.4',
        author='Mide Technology',
        author_email='help@mide.com',
        description='Python API for accessing IDE data recordings',
        long_description=long_description,
        long_description_content_type='text/markdown',
        url='https://github.com/MideTechnology/idelib',
        license='MIT',
        classifiers=['Development Status :: 5 - Production/Stable',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Programming Language :: Python :: 3.5',
                     'Programming Language :: Python :: 3.6',
                     'Programming Language :: Python :: 3.7',
                     'Programming Language :: Python :: 3.8',
                     'Programming Language :: Python :: 3.9',
                     'Programming Language :: Python :: 3.10',
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
        python_requires='>=3.5, <3.11',
        install_requires=INSTALL_REQUIRES,
        extras_require={
            'test': INSTALL_REQUIRES + TEST_REQUIRES,
            'docs': INSTALL_REQUIRES + DOCS_REQUIRES,
            'example': INSTALL_REQUIRES + EXAMPLE_REQUIRES,
            },
)
