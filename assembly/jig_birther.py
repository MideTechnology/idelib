"""
This is just a dirty hack to flip some pins on a timer so that the FW tests
are stepped through. Don't use for ...anything!

Hardware description:
=====================
The target board uses an FTDI USB-Serial chip in bitbang mode to control 8
DIO pins over USB. The pin mappings are:

* D7: BOARD_SENSE (I) : High; Pulled low (physical ground) by target board
    when it is placed.
* D6: SWDIO (I) : Test complete (Ready for next test) indication from target
    board.
* D5: SWCLK (I) : Test pass/fail indication from target board. Bootloader
    entry signal (factory loader).
* D4: !RESET (O) : Hardware Reset to target board.
* D3: XYZ_CTL (O) : Analog stimulus control. HIGH for ~1.65V stimulus, LOW
    for ~0V stimulus.
* D2: SYNC_STIM (x) : Not currently used.
* D1: !RECORD_SW (O) :  Test step command to target board. Bootloader entry
    signal (Mide loader).
* D0: IO_BATT_SW (O) : Battery simulator control. HIGH to simulate full
    battery, LOW to simulate charging battery (current sink).


General principle of operation:
===============================
Initialize FTDI chip and set initial pin directions and states:
   Pin Directions: As indicated ('boot' configuration)
   Pin States: !RESET = LOW (hold target in reset)

Wait for BOARD_SENSE (normally high) to go LOW.

Set !RECORD_SW LOW and SWCLK HIGH to ensure entry into bootloader mode, for
either factory or any Mide bootloader version.

Set !RESET HIGH (released) to let target boot.

Wait for target USB device to appear (USB-CDC; "EFM32 USB CDC Serial")
    If no device after a few seconds (5?) -> FAIL (Check board alignment,
        USB and CPU components, crystals)
    Else, target communication check: PASS

Connect to target USB-serial port (bootloader); confirm bootloader string;
get CHIPID and version.
    ### OPTIONAL: If version does not match Mide current loader
        version -> update bootloader.
    ### NOTE: We'll probably skip this step until confirmed that jig board
        contact is reliable - could soft-brick if contact lost during
        bootloader update.

Send selftest FW binary.

Set pin directions to 'run' configuration and set !RECORD_SW HIGH (SWCLK
should be LOW, i.e. input with no pullup) to skip bootloader.

Reset target (!RESET LOW, wait a bit, !RESET HIGH)

Wait ###FIXME### seconds (5+) for selftest FW to start and I/O states to
stabilize.


 For each test:
 ==============
    * Ensure board still present (BOARD_SENSE LOW)
        -> GLITCH if not (bad contact; results invalid)
    * Ensure SWDIO (Ready) is HIGH (target ready)
        -> GLITCH if not (ready state was confirmed by design, e.g. startup
        delay, or upon leaving last test)
    * Lower !RECORD_SW (command start of test)
    * Wait for SWDIO (Ready) to go LOW (indicates command received / test
        running)
        -> FAIL if timeout (~1 second)
    * Raise !RECORD_SW (acknowledge test running / result not read)
    * Wait for SWDIO to go HIGH (indicates ready / completion of test)
        -> FAIL if timeout (~5 seconds)
    * Read pass/fail result (SWCLK).
        -> FAIL if failure indicated.


Logging:
========
* DetectTime, RemoveTime, CHIPID, InitialBootVer, Test0, ...Test11
* Results for completed tests marked PASS or FAIL respectively
* Unknown fields (e.g. comm failure or timeout during test; maybe caused by
    intermittent jig/board connection) marked e.g. "--" or "?"
* Detection and removal times logged separately to identify obvious bad board
    contact, e.g. failures with suspiciously short test times.
* Logging CHIPID identifies reworked units and number of retests.


TODO:
=====
* Figure out why the drivers are so flaky under Windows and the Beagleboard.
* Everything should probably be moved into the class and made more modular.
  Only if we try to automate future testing, though.

"""

import platform
import sys
import time

from pyftdi import ftdi 

#===============================================================================
# 
#===============================================================================

LINUX = 'linux' in platform.system().lower()


##############################################################################
#
##############################################################################

class SpinnyCallback(object):
    FRAMES = "|/-\\"
    INTERVAL = 0.125

    def __init__(self, *args, **kwargs):
        self.frames = kwargs.pop('frames', self.FRAMES)
        self.spinIdx = 0
        self.clear = '\x08' * len(self.frames[0])
        self.cancelled = False
        self.nextTime = time.time() + self.INTERVAL

    def update(self, *args, **kwargs):
        if time.time() < self.nextTime:
            return
        sys.stdout.write("%s%s" % (self.frames[self.spinIdx], self.clear))
        sys.stdout.flush()
        self.spinIdx = (self.spinIdx + 1) % len(self.frames)
        self.nextTime = time.time() + self.INTERVAL

spinner = SpinnyCallback()

##############################################################################
#
##############################################################################

class TestJig(object):
    """
    """

    PIN_NBOARD_SENSE = 0x80
    PIN_SWDIO = 0x40
    PIN_SWCLK = 0x20
    PIN_NRESET = 0x10
    PIN_XYZ_CTL = 0x08
    PIN_SYNC_STIM = 0x04
    PIN_NRECORD_SW = 0x02
    PIN_IO_BATT_SW = 0x01

    # Pin direction maps. For FT232 and similar, 1 = OUTPUT and 0 = INPUT.
    PIN_DIRECTIONS_BOOT = 0x3F # D7..6 inputs, D5..0 outputs
    PIN_DIRECTIONS_RUN = 0x1F # D7..5 inputs, D4...0 outputs
    PIN_DIRECTIONS_DEBUG = 0x0F # D7..4 inputs, D3...0 outputs (!RESET in)

    results = ['PASS', 'FAIL', 'TIMEOUT', 'GLITCH'] # possible results of a test

    def __init__(self, vendor=0x0403, product=0x6001, interface=1, timeout=30):
        self.vendor = vendor
        self.product = product
        self.interface = interface
        self.h = ftdi.Ftdi()
#        print "Discovered devices:"
#        print self.h.find_all([(vendor, product)], nocache=False) # debug; no device detected at all until forcing libusb-win32 ('libusb0') driver under Win32...

        quitTime = time.time() + timeout
        connected = False
        while not connected:
            try:
                self.h.open_bitbang(self.vendor, self.product, self.interface,
                                    direction=self.PIN_DIRECTIONS_BOOT)
                connected = True
                break
            except ftdi.FtdiError as err:
                print err
                if time.time() > quitTime:
                    raise err
            time.sleep(5)

        self.h.open_bitbang(self.vendor, self.product, self.interface,
                            direction=self.PIN_DIRECTIONS_BOOT)

        print "Connected device:", self.h.ic_name # debug

        self.overall_result = True


    def set_bitmode(self, direction, mode=0x01):
        """
        """
        # Linux won't allow the FTDI device to be re-opened, and Windows
        # doesn't seem to completely reset otherwise.
        if LINUX:
            self.h.set_bitmode(direction, mode)
            self.h.purge_buffers()
        else:
            self.h.open_bitbang(self.vendor, self.product, self.interface,
                                direction=direction)



    def wait_for_board_sense(self, timeout=10):
        ''' Wait for target board to be present on test jig.
        '''
        # ensure we start the board in bootloader when it arrives
        self.set_test_mode_boot()
        print "Waiting for target board..."
        quitTime = time.time() + timeout
        while(self.read_pin(self.PIN_NBOARD_SENSE)):
            if time.time() > quitTime:
                return False
            time.sleep(0.2)
        return True


    def reset_target(self):
        '''
        '''
        self.set_reset()
        time.sleep(0.5)
        self.release_reset()


    def set_test_mode_boot(self):
        ''' Configure pin directions and states to activate target board
            bootloader on startup.
        '''
#        self.h.open_bitbang(self.vendor, self.product, self.interface,
#                            direction=self.PIN_DIRECTIONS_BOOT)
        self.set_bitmode(self.PIN_DIRECTIONS_BOOT, 0x01)
        # self.h.purge_buffers()
        self.set_reset()
        self.raise_pin(self.PIN_SWCLK)
        self.lower_pin(self.PIN_NRECORD_SW)


    def set_test_mode_run(self):
        ''' Configure pin directions and states to activate target board user app on startup '''
        self.h.open_bitbang(self.vendor, self.product, self.interface, direction = self.PIN_DIRECTIONS_RUN)
        self.set_reset()
        self.lower_pin(self.PIN_SWCLK)


    def set_reset(self):
        ''' Place target board in RESET.
        '''
        self.lower_pin(self.PIN_NRESET)


    def release_reset(self):
        ''' Release target board from RESET.
        '''
        self.raise_pin(self.PIN_NRESET)


    def set_pins(self, pinmap):
        ''' Set all pin states at once via bitmap.
        '''
        self.h.write_data([pinmap])


    def get_pins(self):
        ''' Get all pin states at once via bitmap.
        '''
        return self.h.read_pins()


    def raise_pin(self, pins):
        ''' Raise one or more pins specified by 'pins' mask. Other pins
            are not affected.
        '''
        self.set_pins(self.get_pins() | pins)


    def lower_pin(self, pins):
        ''' Lower one or more pins specified by 'pins' mask. Other
            pins are not affected.
        '''
        # FIXME: CHECKME: This is suspect...
        self.set_pins((self.get_pins() & ~pins) & 0xFF)


    def read_pin(self, pins):
        ''' Read and return the boolean state of one or more pins. Other
            pins are ignored.
        '''
        return bool(self.get_pins() & pins)


    def close(self):
        self.h.close()


##############################################################################
#
##############################################################################


if __name__ == "__main__":
    c = TestJig() # open FTDI chip in bitbang mode
    
    c.close()

#print "Done!"
