from collections import namedtuple

import pytest
import numpy as np

from idelib.transforms import Transform, AccelTransform, Univariate


@pytest.fixture()
def genericTransform():
    yield Transform()


@pytest.fixture()
def badTransform():
    tf = Transform()
    tf._function = None
    yield tf


@pytest.fixture(
        params=[
            ((0,), 0),
            ((1,), 0),
            ((3, 1), 0),
            ((3, 1), 5),
            ],
        ids=[
            'zero-trivial',
            'constant',
            'simple-linear',
            'referenced-lindar',
            ],
        )
def univariate(request):
    coeffs, reference = request.param
    tf = Univariate(coeffs, reference=reference)
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

    @pytest.mark.parametrize('session, offset',
                             [(None, 0),
                              (namedtuple('fakeSession', 'startTime')(startTime=1), 1),
                              ])
    def testCall(self, session, offset, genericTransform):
        timestamp = 0
        value = 10

        assert genericTransform(timestamp, value, session=session) == (timestamp + offset, value)

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


class TestAccelTransform:

    @pytest.mark.parametrize('amin, amax, calId',
                             [
                                 (-100., 100., 0),
                                 (0., 10., 1),
                                 (0., 1e-10, 200)
                             ])
    def testInit(self, amin, amax, calId):
        tf = AccelTransform(amin=amin, amax=amax, calId=calId)

        assert tf.id == calId
        assert tf.range == (amin, amax)
        assert tf._str == '(x / 32767.0) * {:.3f}'.format(amax)
        assert tf._source == 'lambda x: x * {:4f}'.format(amax/32767.0)

    @pytest.mark.parametrize('amin, amax, calId',
                             [
                                 (-100., 100., 0),
                                 (0., 10., 1),
                                 (0., 1e-10, 200)
                             ])
    def testCopy(self, amin, amax, calId):
        tf = AccelTransform(amin=amin, amax=amax, calId=calId)

        assert tf == tf.copy()


class TestUnivariate:

    def testInplace(self, univariate):
        values = np.arange(5)
        out = np.zeros(5)
        univariate.inplace(values, out=out)

        if len(univariate.coefficients) == 1:
            a = univariate.coefficients[0]
            np.testing.assert_array_equal(out, np.ones(5)*a)
        elif len(univariate.coefficients) == 2:
            a, b = univariate.coefficients
            ref = univariate.references[0]
            np.testing.assert_array_equal(out, a*(values - ref) + b)
        else:
            raise


class TestBivariate:

    def testInplace(self):
        pass


class TestCombinedPoly:

    def testInplace(self):
        pass


class TestPolyPoly:

    def testInplace(self):
        pass
