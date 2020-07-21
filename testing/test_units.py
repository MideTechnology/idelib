""" """
import numpy as np

import pytest

from idelib.unit_conversion import (Celsius2Fahrenheit,
                                    Celsius2Kelvin,
                                    Gravity2MPerSec2,
                                    Meters2Feet,
                                    Pa2PSI,
                                    Pa2atm,
                                    Pressure2Feet,
                                    Pressure2Meters)


# safe values, no real worries here
conversion_table = [(-40,      -40,         Celsius2Fahrenheit()),
                    (0,        32,          Celsius2Fahrenheit()),
                    (-40,      233.15,      Celsius2Kelvin()),
                    (0,        273.15,      Celsius2Kelvin()),
                    (0,        0,           Gravity2MPerSec2()),
                    (1,        9.80665,     Gravity2MPerSec2()),
                    (0,        0,           Meters2Feet()),
                    (1,        3.28084,     Meters2Feet()),
                    (0,        0,           Pa2PSI()),
                    (1,        1.450377e-4, Pa2PSI()),
                    (0,        0,           Pa2atm()),
                    (1,        9.869232e-6, Pa2atm()),
                    (101325.0, 0,           Pressure2Feet()),
                    (80000.0,  6394.32,     Pressure2Feet()),
                    (101325.0, 0,           Pressure2Meters()),
                    (80000.0,  1948.99,     Pressure2Meters()),
                    ]
conversion_table += [(np.ones(10)*x, np.ones(10)*y, z) for x, y, z in conversion_table]

@pytest.mark.parametrize(
        'input, output, converter',
        conversion_table
        )
def test_converters(input, output, converter):
    assert converter.convert(input) == pytest.approx(output)


@pytest.mark.parametrize(
        'input, output, converter',
        conversion_table
        )
def test_converters_revert(input, output, converter):
    assert converter.revert(output) == pytest.approx(input)


unsafe_table = [(None, TypeError,  Celsius2Fahrenheit()),
                ('a',  TypeError,  Celsius2Fahrenheit()),
                (None, TypeError,  Celsius2Kelvin()),
                ('a',  TypeError,  Celsius2Kelvin()),
                (None, TypeError,  Gravity2MPerSec2()),
                ('a',  TypeError,  Gravity2MPerSec2()),
                (None, TypeError,  Meters2Feet()),
                ('a',  TypeError,  Meters2Feet()),
                (None, TypeError,  Pa2PSI()),
                ('a',  TypeError,  Pa2PSI()),
                (None, TypeError,  Pa2atm()),
                ('a',  TypeError,  Pa2atm()),
                (None, TypeError,  Pressure2Feet()),
                ('a',  TypeError,  Pressure2Feet()),
                pytest.param(-1,
                             ValueError,
                             Pressure2Feet(),
                             marks=pytest.mark.skip(reason='value errors not implemented yet')),
                (None, TypeError,  Pressure2Meters()),
                ('a',  TypeError,  Pressure2Meters()),
                pytest.param(-1,
                             ValueError,
                             Pressure2Meters(),
                             marks=pytest.mark.skip(reason='value errors not implemented yet')),
                ]


@pytest.mark.parametrize(
        'input, err, converter',
        unsafe_table
        )
def test_bad_conversion(input, err, converter):
    with pytest.raises(err):
        print(converter.convert(input))


@pytest.mark.parametrize(
        'input, err, converter',
        unsafe_table
        )
def test_bad_reversion(input, err, converter):
    with pytest.raises(err):
        print(converter.revert(input))
