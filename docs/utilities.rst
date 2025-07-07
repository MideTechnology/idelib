IDE File Utilities
==================

``idelib`` provides some useful command-line utilities for converting IDE data to other formats,
and for viewing general information about an IDE file. These are automatically installed when
installing the ``idelib`` package.

Installing
----------

The utilities are part of the ``idelib`` package, so they are installed along with it. The common
way to install is via ``pip`` (which is typically bundled with Python)::

    pip install idelib


Running the scripts
-------------------

These utilities can be run in two ways: via an executable script, or as a Python module.

Running as a Python module
''''''''''''''''''''''''''

You can run the utilities by running Python with the ``-m`` argument, followed by the name of the
submodule and any arguments, e.g.:

* ``python -m idelib.tools.ideexport --help``
* ``python -m idelib.tools.ideexport --help``

While verbose, this is the most reliable way to run the utilities.

Running the executable
''''''''''''''''''''''

When ``idelib`` is installed, it will create an executable file for each utility. The location
of the scripts varies by operating system (Linux/Windows/MacOS/etc.) and by Python environment (e.g., standard Python from
`python.org <https://python.org>`_ or `conda <https://anaconda.org/anaconda/conda>`_), but it should
be in your 'path', so running it is done by typing its name, followed by any arguments:

* ``ideexport --help``
* ``ideinfo --help``

Unfortunately, there are many factors specific to your computer and Python setup that can interfere
with this. Most commonly, the executables are somewhere outside of your 'path' and could not be found,
or security/authorization issues prevented the executables' creation. In either case, the result is
the standard 'not found' error for your OS.

The utilities
-------------

``ideexport``
'''''''''''''

``ideexport`` converts one or more IDE files into text (CSV, etc.) or Matlab MAT v5 files.


.. code-block::

    usage: ideexport.py [-h] [-o OUTPUT] [-t {csv,mat,txt}] [-c CHANNEL] [-m] [-u] [-n] [-r] [-d {comma,tab,pipe}] [-f] FILENAME.IDE [FILENAME.IDE ...]

    Batch IDE Conversion Utility v3.4.0b1 - Copyright (c) 2025 Midé Technology

    positional arguments:
      FILENAME.IDE          The source .IDE file(s) to convert. Wildcards permitted.

    options:
      -h, --help            show this help message and exit
      -o OUTPUT, --output OUTPUT
                            The output path to which to save the exported files. Defaults to the same location as the source file.
      -t {csv,mat,txt}, --type {csv,mat,txt}
                            The type of file to export.
      -c CHANNEL, --channel CHANNEL
                            Export the specific channel. Can be used multiple times. If not used, all channels will export.
      -m, --removemean      Remove the mean from accelerometer data.
      -u, --utc             Write timestamps as UTC 'Unix epoch' time.
      -n, --names           Include channel names in exported filenames.

    Text Export Options (CSV, TXT, etc.):
      -r, --headers         Write 'header' information (column names) as the first row of text-based export.
      -d {comma,tab,pipe}, --delimiter {comma,tab,pipe}
                            The delimiting character, for exporting non-CSV text-based files.
      -f, --isoformat       Write timestamps as ISO-formatted UTC.

``ideinfo``
'''''''''''

``ideinfo`` gathers information about an IDE file, and either displays the text on the console or
writes it to a file.

.. code-block::

    usage: ideinfo.py [-h] [-o OUTPUT] FILENAME.IDE [FILENAME.IDE ...]

    IDE Info Viewer v3.4.0b1 - Copyright (c) 2025 Midé Technology

    positional arguments:
      FILENAME.IDE          The source .IDE file(s) to convert. Wildcards permitted.

    options:
      -h, --help            show this help message and exit
      -o OUTPUT, --output OUTPUT
                            The output path to which to save the info text.
