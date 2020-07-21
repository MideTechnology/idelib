"""

This example takes an optional file argument prints the peak acceleration value
of the first accelerometer channel, and the time of the peak.  If matplotlib is
installed, it will also plot the subchannel.

:param filename: The file the analysis will be run on.  Defaults to './Truck_Bed_short.IDE'

python peak_plot.py [--file filename]

"""

import argparse

import numpy as np

import idelib

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Calculate the peak acceleration "
                                                 "and time of the peak.")

    parser.add_argument("--file",
                        nargs=1,
                        default=["./Truck_Bed_Short.IDE"],
                        help="The file to process")

    args = parser.parse_args()

    doc = idelib.importFile(args.file[0])

    # Pick an acceration channel
    ACCEL_CH_IDS = (8, 32, 80)
    # Selects the first valid accelerometer channel
    accel_ch_id = next(ch_id for ch_id in ACCEL_CH_IDS if ch_id in doc.channels)
    x_axis_index = 0
    array = doc.channels[accel_ch_id].subchannels[x_axis_index].getSession()[:]

    times = array[0]
    values = array[1]

    # Calculate bounds for largest peak (+-10ms)
    peak_index = np.abs(values).argmax()
    peak_time = times[peak_index]
    peak_value = values[peak_index]
    peak_slice = slice(*np.searchsorted(
        times, [peak_time - 10e3, peak_time + 10e3]
    ))

    print('peak time: {}us'.format(peak_time))
    print('peak value:', peak_value)

    import matplotlib.pyplot as plt

    plt.plot(times[peak_slice], values[peak_slice])
    plt.scatter(peak_time, peak_value, color='r')
    plt.title("X-axis Acceleration Peak")
    plt.xlabel("time (microseconds)")
    plt.ylabel("acceleration")
    plt.show()
