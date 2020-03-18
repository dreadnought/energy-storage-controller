#!/usr/bin/python3
import time
try:
    from cysystemd.daemon import notify, Notification
    SYSTEMD_WATCHDOG = True
except ImportError:
    print("can't import cysystemd")
    SYSTEMD_WATCHDOG = False

from devices.smart_bms import SmartBMSThread
from logger import get_logger
from metrics import Metrics

from config import config


logger = get_logger(level='info')
metrics = Metrics(database_name=config['influxdb']['database_name'])
bms_thread = SmartBMSThread(mac_address=config['bms']['mac_address'], metrics=metrics, logger=logger)
bms_thread.start()
received_data = False
time.sleep(3)

while bms_thread.is_running:
    try:
        # pprint(bms_thread.data)
        # print("", flush=True)
        if not bms_thread.last_run_completed:
            logger.warning("no completed run")
        elif time.time() - bms_thread.last_run_completed > 30:
            logger.error("bms thread dead")
        else:
            if not received_data:
                logger.info("received data")
                received_data = True
            if SYSTEMD_WATCHDOG:
                notify(Notification.WATCHDOG)
        time.sleep(10)
    except KeyboardInterrupt:
        break

bms_thread.stop()
