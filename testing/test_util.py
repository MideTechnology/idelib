import datetime
import time

import pytest

import idelib.util

NOW_DATETIME = datetime.datetime.now()
NOW_STRUCT_TIME = time.localtime()
NOW_UTC = time.time()

ATTRIBUTES = [{},
              {'string': 'this is a unicode string'},
              {'bytes': b'this is a bytes string'},
              {'float': 0.1},
              {'int': 10},
              {'datetimeTypes': NOW_DATETIME},
              {'time.struct_time': NOW_STRUCT_TIME},
              [['int', (2, 'IntAttribute')]],
              [['int', ([2, 3, 4, 5], 'IntAttribute')]],
              [('datetime datetime', NOW_DATETIME)],
              [('datetime struct', NOW_STRUCT_TIME)],
              [('datetime int', (NOW_UTC, 'DateAttribute'))],
             ]

ENCODED_ATTRIBUTES = [[],
                      [{'AttributeName': 'string', 'UnicodeAttribute': 'this is a unicode string'}],
                      [{'AttributeName': 'bytes', 'StringAttribute': b'this is a bytes string'}],
                      [{'AttributeName': 'float', 'FloatAttribute': 0.1}],
                      [{'AttributeName': 'int', 'IntAttribute': 10}],
                      [{'AttributeName': 'datetimeTypes', 'DateAttribute': NOW_DATETIME}],
                      [{'AttributeName': 'time.struct_time', 'DateAttribute': NOW_STRUCT_TIME}],
                      [{'AttributeName': 'int', 'IntAttribute': 2}],
                      [{'AttributeName': 'int', 'IntAttribute': [2, 3, 4, 5]}],
                      [{'AttributeName': 'datetime datetime', 'DateAttribute': NOW_DATETIME}],
                      [{'AttributeName': 'datetime struct', 'DateAttribute': NOW_STRUCT_TIME}],
                      [{'AttributeName': 'datetime int', 'DateAttribute': int(NOW_UTC)}],
                    ]


@pytest.mark.parametrize(
        "test_input, expected",
        zip(ATTRIBUTES, ENCODED_ATTRIBUTES)
        )
def test_encode_attributes(test_input, expected):

    assert idelib.util.encode_attributes(test_input) == expected
