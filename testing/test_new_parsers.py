import pytest

from idelib.parsers import renameKeys, valEval, parseAttribute


@pytest.mark.parametrize(
        'inDict, newNames, output',
        [({'keyA': 'value a'}, {'keyA': 'keyB'}, {'keyB': 'value a'})]
        )
def testRenameKeys(inDict, newNames, output):
    assert renameKeys(inDict, newNames) == output


@pytest.mark.parametrize(
        'input, output',
        [('1', 1),
         ('10*20', 200),
         ('pi', 3.14159),
         ('cos(pi/2)', 0),
         (b'pi', 3.14159),
         (b'cos(pi/2)', 0),
         ]
        )
def testValEval(input, output):
    assert valEval(input) == pytest.approx(output)
