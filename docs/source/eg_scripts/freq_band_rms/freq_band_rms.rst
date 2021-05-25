Example Script: Calculate Frequency-Banded RMS
==============================================

For each accelerometer subchannel, this script calculates the signal's total RMS (root-mean-square), and uses Parseval's Theorem to calculate the RMS of the content that lies within a specified frequency band.


.. literalinclude:: ../enDAQ-Lab-scripts/scripts/freq_band_rms.py
   :language: python2

Example text output::

    ### Running script from tab 'freq_band_rms.py' at 2020-04-01 13:32:40
    RMS of 500g PE Acceleration
        x-axis:  1.7778701857767032
        y-axis:  1.2255001035990056
        z-axis:  1.1097607332472412
    RMS of 500g PE Acceleration in frequency band [200, 400] Hz
        x-axis:  0.07792391732877917
        y-axis:  0.06185447652149359
        z-axis:  0.22011619263891302
    
    RMS of 40g DC Acceleration
        x-axis:  0.4830285786939296
        y-axis:  0.42821384219749065
        z-axis:  0.45257324546501443
    RMS of 40g DC Acceleration in frequency band [200, 400] Hz
        x-axis:  0.013730349656119129
        y-axis:  0.025704347755011694
        z-axis:  0.030860869748786348
    
    ### Finished running script from tab 'freq_band_rms.py'

:download:`Download script <../enDAQ-Lab-scripts/scripts/freq_band_rms.py>`.
