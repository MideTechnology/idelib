import os.path

from idelib import importer, sync


def test_offset():
    """ Test that session timestamp offset works. """
    filename1 = os.path.join(os.path.dirname(__file__), 'TSF1.IDE')
    doc1 = importer.importFile(filename1)

    accel1 = doc1.channels[80].getSession()
    first1 = accel1[0][0]
    last1 = accel1[-1][0]

    offset = 10 ** 6

    # Positive offset
    accel1.session.offset = offset
    assert accel1[0][0] != first1
    assert accel1[-1][0] != last1
    assert accel1[0][0] == first1 + offset
    assert accel1[-1][0] == last1 + offset

    # Offset reset
    accel1.session.offset = 0
    assert accel1[0][0] == first1
    assert accel1[-1][0] == last1

    # Negative offset
    accel1.session.offset = -offset
    assert accel1[0][0] != first1
    assert accel1[-1][0] != last1
    assert accel1[0][0] == first1 - offset
    assert accel1[-1][0] == last1 - offset


def test_sync_basic():
    """ Test that sync will modify the target file but not the reference.
    """
    cwd = os.path.dirname(__file__)
    doc1 = importer.importFile(os.path.join(cwd, 'TSF1.IDE'))
    doc2 = importer.importFile(os.path.join(cwd, 'TSF2.IDE'))

    accel1 = doc1.channels[80].getSession()
    accel2 = doc2.channels[80].getSession()
    first1 = accel1[0][0]
    last1 = accel1[-1][0]
    first2 = accel2[0][0]
    last2 = accel2[-1][0]
    utc1 = accel1.session.utcStartTime
    utc2 = accel2.session.utcStartTime

    # Sanity check: initial offsets are zero
    assert accel1.session.offset == 0
    assert accel2.session.offset == 0

    sync.sync(doc1, doc2)
    assert accel1.session.offset == 0  # doc1 (the reference) offset unchanged
    assert accel2.session.offset != 0  # doc2 offset modified
    assert accel1[0][0] == first1  # doc1 timestamps unchanged
    assert accel1[-1][0] == last1
    assert accel2[0][0] == first2 + accel2.session.offset  # doc2 timestamps offset
    assert accel2[-1][0] == last2 + accel2.session.offset

    assert accel1.session.utcStartTime == utc1
    assert accel2.session.utcStartTime == utc1
