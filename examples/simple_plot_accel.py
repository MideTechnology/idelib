"""

This example takes an optional file argument prints times and values of the first
accelerometer channel available in the file.  If matplotlib is installed, then
they will be plotted.

:param filename: The file the analysis will be run on.  Defaults to './Truck_Bed_short.IDE'

python peak_plot.py [--file filename]

"""

import argparse

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
    accel_ch_id = next(ch_id for ch_id in ACCEL_CH_IDS if ch_id in doc.channels)
    accel_data = doc.channels[accel_ch_id].getSession()
    array = accel_data[:]

    times = array[0]
    values = array[1:]

    import numpy as np
    utc_times = (
        np.datetime64(accel_data.session.utcStartTime, 's')
        + times.astype('timedelta64[us]')
    )


    print(times)
    print(values)
    print(utc_times)

    import matplotlib.pyplot as plt
    plt.plot(utc_times, values.T)
    plt.title("Acceleration Data Plot")
    plt.legend(["x-axis", "y-axis", "z-axis"])
    plt.xlabel("time (UTC)")
    plt.ylabel("acceleration")
    plt.show()
