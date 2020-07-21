"""

This example takes an optional file argument prints the RMS of the first
accelerometer channel and the rms in the frequency range between lowFreq
and highFreq.

:param filename: The file the analysis will be run on.  Defaults to './Truck_Bed_short.IDE'
:param lowFreq: The lower frequency of the bandpass applied to the file in Hz.
                highFreq must also be specified.  Defaults to 200
:param highFreq: The lower frequency of the bandpass applied to the file in Hz.
                 Defaults to 400

python freq_band_rms.py [--file filename] [--freq lowFreq  highFreq]

"""

import argparse

import numpy as np

import idelib


def rms(array, axis=-1):
    """
    Calcualtes the RMS of a signal.
    """
    return np.sqrt(np.mean(np.abs(array) ** 2, axis=axis))


def freq_band_rms(array, dt, min_freq=0, max_freq=np.inf):
    """
    Calcualtes the RMS of a signal within a specific frequency band.
    """
    n = array.shape[-1]
    fft = np.fft.fft(array, norm="ortho")
    abs_freqs = np.abs(np.fft.fftfreq(n, d=dt))

    band_mask = (min_freq <= abs_freqs) & (abs_freqs <= max_freq)
    return np.sqrt(np.sum(np.abs(fft[..., band_mask]) ** 2, axis=-1) / n)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Calculate the RMS on a file "
                                                 "across all frequencies and "
                                                 "within a specific band of "
                                                 "frequencies")

    parser.add_argument("--file",
                        nargs=1,
                        default=["./Truck_Bed_Short.IDE"],
                        help="The file to process")
    parser.add_argument("--freq",
                        nargs=2,
                        default=[200, 400],
                        help="The frequency range to inspect, in Hz",
                        type=int)

    args = parser.parse_args()

    doc = idelib.importFile(args.file[0])

    min_freq, max_freq = args.freq  # Hz

    # The maximum number of samples to process from a single stream
    sample_limit = 10**6

    # Accelerometer Channel IDs
    ACCEL_CH_IDS = (8, 32, 80)

    # Run for each channel, skipping channels which aren't in the list above
    for ch_id in ACCEL_CH_IDS:
        if ch_id not in doc.channels:
            continue

        accel_channel = doc.channels[ch_id]
        eventlist = accel_channel.getSession()

        if len(eventlist) > sample_limit:
            print("sample count too high: truncating results to first {} samples"
                  .format(sample_limit))
        array = eventlist[:sample_limit]  # truncates to first `n` samples
        times = array[0]
        values = array[1:]

        dt_est = np.mean(np.diff(times)) * 1e-6

        time_rms = rms(values, axis=-1)
        freq_rms = freq_band_rms(
            values, dt_est, min_freq=min_freq, max_freq=max_freq,
        )

        print('RMS of', accel_channel.name)
        print('\tx-axis: ', time_rms[0])
        print('\ty-axis: ', time_rms[1])
        print('\tz-axis: ', time_rms[2])

        print('RMS of {} in frequency band [{}, {}] Hz'.format(
            accel_channel.name, min_freq, max_freq,
        ))
        print('\tx-axis: ', freq_rms[0])
        print('\ty-axis: ', freq_rms[1])
        print('\tz-axis: ', freq_rms[2])

        print()  # adds newline
