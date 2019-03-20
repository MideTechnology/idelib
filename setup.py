from setuptools import setup, find_packages

setup(
    name="SlamStickLab",
    version=1.9.0,
    packages=find_packages(),
    python_requires='==2.7.*',
    install_requires=('scipy numpy matplotlib pyftdi==0.13.4 pyserial pywin32'
                      ''.split()),
    tests_require=['mock'],
    # setup_requires=['pytest-runner'],
    # tests_require=['pytest'],
)
