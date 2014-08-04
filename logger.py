'''
Wrapper for the logging system.

Created on Aug 4, 2014

@author: dstokes
'''

import logging
logger = logging.getLogger('SlamStickLab')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")
