import pytest

import numpy as np

from idelib.transforms import Transform, AccelTransform


@pytest.fixture()
def genericTransform():
    return Transform()


@pytest.fixture()
def badTransform():
    tf = Transform()
    tf._function = None
    return tf


class TestTransform:

    def testInit(self, genericTransform):
        assert genericTransform._source == "lambda x: x"

    def testInitAttrs(self):
        tf = Transform(attributes={'attr1': 10})
        assert tf.attributes['attr1'] == 10

    def testCopy(self, genericTransform):
        tfCopy = genericTransform.copy()
        assert genericTransform == tfCopy

    def testStr(self, genericTransform):
        assert str(genericTransform) == 'x'

    def testRepr(self, genericTransform):
        assert repr(genericTransform) == '<Transform: (x)>'

    def testHash(self, genericTransform):
        assert hash(genericTransform) == hash('x')

    def testEq(self, genericTransform):
        assert genericTransform == Transform()

    @pytest.mark.parametrize('other', [(5,), (AccelTransform(),)])
    def testNeq(self, other, genericTransform):
        assert genericTransform != other

    def testFunction(self, genericTransform):
        x = np.arange(5)
        np.testing.assert_array_equal(genericTransform.function(x), x)

    @pytest.mark.parametrize('which, expected', [('generic', True), ('bad', False)])
    def testIsValid(self, which, expected, genericTransform, badTransform):
        if which == 'generic':
            tf = genericTransform
        elif which == 'bad':
            tf = badTransform
        else:
            raise

        assert tf.isValid() == expected

    def testUseMean(self, genericTransform):
        with pytest.warns(UserWarning):
            assert genericTransform.useMean is False

    def testAddWatcher(self):
        tf = Transform()
        tf.addWatcher(tf)

        assert tf in list(tf._watchers)
