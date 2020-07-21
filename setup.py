import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

INSTALL_REQUIRES = [
    'numpy',
    'ebmlite>=3.0.0'
    ]

TEST_REQUIRES = [
    'pytest>=4.6',
    'mock',
    'pytest-cov',
    ]

EXAMPLE_REQUIRES = [
    'matplotlib'
    ]

setuptools.setup(
        name='idelib-archive',
        version='3.0.0rc1',
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
                     'Topic :: Scientific/Engineering',
                     ],
        keywords='ebml binary ide mide',
        packages=setuptools.find_packages(),
        package_dir={'': '.'},
        package_data={
            '': ['schemata/*'],
        },
        test_suite='tests',
        install_requires=INSTALL_REQUIRES,
        extras_require={
            'test': INSTALL_REQUIRES + TEST_REQUIRES,
            'example': INSTALL_REQUIRES + EXAMPLE_REQUIRES,
            },
)