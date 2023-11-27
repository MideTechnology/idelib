#!
"""
Package for reading and analyzing Mide Instrumentation Data Exchange (MIDE)
files.
"""

__author__ = "David Randall Stokes"
__copyright__ = "Copyright (c) 2023 Midé Technology"

__maintainer__ = "Midé Technology"
__email__ = "help@mide.com"

__version__ = '3.2.9'

__status__ = "Production/Stable"

from .importer import importFile

# Add EBML schema path to ebmlite search paths
import ebmlite

SCHEMA_PATH = "{idelib}/schemata"
if SCHEMA_PATH not in ebmlite.SCHEMA_PATH:
    ebmlite.SCHEMA_PATH.insert(0, SCHEMA_PATH)
