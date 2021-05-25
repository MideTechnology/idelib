.. _global_vars:

enDAQ Lab Automation
====================

The Scripting menu enables users to programmatically interact with enDAQ Lab via a Python API. This page aims to familiarize you with the the Python API's basic features.


.. _viewer_obj:

The ``viewer`` object
---------------------

Every instance of the main enDAQ Lab application comprises a ``viewer`` object that implements the core of the application's functionalities. Because of how central it is, the ``viewer`` object is intentionally made available in the Python Console's global variables to allow users to access its wide breadth of functionality. While many of the methods/members therein have no merit in being invoked externally, there are a handful of them that are useful for script automation; each of these useful members/methods are discussed below.


Opening/closing a recording file
--------------------------------

Normally, we can open a recording file by clicking `File → Open...` from the menu bar. To automate this, we can instead call ``viewer.openFile(filename)`` with the path of a recording file for the ``filename`` parameter. This will also load the recording data into the main plot view, just as it would if you were to open the file manually from the menu bar.

Similarly, we can also close a recording file that was previously loaded into enDAQ Lab by calling ``viewer.closeFile()``.


Inspecting loaded file data
---------------------------

Every ``viewer`` object is responsible for *at most* one recording file; that recording file is stored as a :class:`Dataset` object at ``viewer.dataset``. For more information on what the :class:`Dataset` class provides, see :ref:`dataset_desc`.


Plots & plot tabs
-----------------

The main view contains a number of tabs, each for a separate plot of the recording data. To retrieve the ``Plot`` object stored in the active tab, we can call ``viewer.getTab()``:

>>> viewer.getTab()
<Plot 0: "16g DC Acceleration (3 sources)">

The data being plotted can be accessed through the tab's `sources` attribute. This is a list of :class:`EventArray` objects (the data for the individual plot lines) in the order in which the plots are drawn (i.e., the bottom-most is first, the topmost is last):

>>> viewer.getTab().sources
[<EventArray u'16g DC Acceleration:Z (16g), 0' at 0x16ee5e48>, <EventArray u'16g DC Acceleration:Y (16g), 0' at 0x16ec9860>, <EventArray u'16g DC Acceleration:X (16g), 0' at 0x16ee5278>]
>>> viewer.getTab().sources[2]
<EventArray u'16g DC Acceleration:X (16g), 0' at 0x16ee5278>

For more information on what the :class:`EventArray` class provides, see :ref:`eventarray_desc`.
