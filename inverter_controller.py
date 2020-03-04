#!/usr/bin/python3

import time

from config import config
from controller.inverter_controller import InverterController


controller = InverterController(config=config)
time.sleep(20)  # give the threads time to start, connect and receive data
controller.loop()
