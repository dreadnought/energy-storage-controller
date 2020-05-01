#!/usr/bin/python3
import time
from cysystemd.daemon import notify, Notification

from devices.smart_bms import SmartBMSThread
from devices.gpio import GpioPin
from logger import get_logger
from metrics import Metrics

from config import config

logger = get_logger(level='info')
metrics = Metrics(database_name=config['influxdb']['database_name'])
bms_thread = SmartBMSThread(mac_address=config['bms']['mac_address'], metrics=metrics, logger=logger)
bms_thread.start()
received_data = False
time.sleep(3)

battery_inverter_relay_ac = GpioPin(pin=config['aeconversion_inverter']['gpio_pin'])

while bms_thread.is_running:
    try:
        # pprint(bms_thread.data)
        # print("", flush=True)
        time_diff = time.time() - bms_thread.last_run_completed
        if not bms_thread.last_run_completed:
            logger.warning("No data received yet")
        elif time_diff > 30:
            logger.error("BMS thread didn't receive data for %0.1f seconds" % time_diff)
        else:
            if not received_data:
                logger.info("First received data")
                notify(Notification.READY)
                received_data = True
            notify(Notification.WATCHDOG)

        if bms_thread.data['cell_voltages'] is not None:
            for cell, voltage in bms_thread.data['cell_voltages'].items():
                if cell == 'time':
                    continue

                if voltage < 2.9 and battery_inverter_relay_ac.get_state() == 1:
                    logger.warning(f"voltage {voltage} of cell {cell} is low, turning off inverter")
                    battery_inverter_relay_ac.set_state(False)


        time.sleep(10)
    except KeyboardInterrupt:
        break

bms_thread.stop()
