from glob import glob
import os.path

from idelib import importer
from idelib.tools import ideexport, ideinfo


def test_ideexport_basic(tmpdir_factory):
    """ Basic ideexport test, verify the correct number of files are created.
    """
    filename = './testing/test3.IDE'
    basename = os.path.splitext(os.path.basename(filename))[0]

    path = tmpdir_factory.mktemp('test_ideexport')
    ideexport.main(['--output', str(path), filename])
    ideexport.main(['--output', str(path), '-t', 'mat', filename])

    doc = importer.openFile(filename)
    csvs = glob(str(path / '*.csv'))
    mats = glob(str(path / '*.mat'))
    assert len(doc.channels) == len(csvs)
    assert len(doc.channels) == len(mats)
    assert os.path.exists(path / f'{basename}_info.txt')


def test_ideexport_csv(tmpdir_factory):
    """ Verify the number of exported rows matches the number of events in
        the original IDE.
    """
    filename = './testing/test3.IDE'
    basename = os.path.splitext(os.path.basename(filename))[0]
    path = tmpdir_factory.mktemp('test_ideexport')

    with importer.importFile(filename) as doc:
        ideexport.main(['--output', str(path), filename])
        for ch in doc.channels.values():
            events = ch.getSession()
            csvname = f'{path}/{basename}_Ch{ch.id:02d}.csv'
            with open(csvname, 'r') as f:
                lines = len(f.readlines())
                assert lines == len(events)


def test_ideinfo_basic(tmpdir_factory):
    """ Test that ideinfo creates an info file.
    """
    filename = './testing/test3.IDE'
    basename = os.path.splitext(os.path.basename(filename))[0]
    outfile = str(tmpdir_factory.mktemp('test_ideinfo') / f'{basename}.txt')

    ideinfo.main(['--output', outfile, filename])
    assert os.path.exists(outfile)
