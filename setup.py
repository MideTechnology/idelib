from setuptools import setup, find_packages

setup(
    name="SlamStickLab",
    packages=find_packages(),
    python_requires='==2.7.*',
    install_requires='scipy numpy matplotlib pyftdi==0.13.4 pywin32'.split(),
    # setup_requires=['pytest-runner'],
    # tests_require=['pytest'],
)
