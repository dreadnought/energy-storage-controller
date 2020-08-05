#!/usr/bin/python3

import time

from config import config, tz
from controller.inverter_controller import InverterController
from logger import get_logger

logger = get_logger(level='info')


controller = InverterController(config=config, logger=logger, tz=tz)
time.sleep(20)  # give the threads time to start, connect and receive data
controller.loop()
