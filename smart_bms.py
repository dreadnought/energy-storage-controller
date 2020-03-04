#!/usr/bin/python3
import time

from devices.smart_bms import SmartBMSThread
from metrics import Metrics

from config import config
import sys


def new_thread(mac_address):
    bms_thread = SmartBMSThread(mac_address=mac_address, metrics=metrics)
    bms_thread.start()
    return bms_thread


metrics = Metrics(database_name=config['influxdb']['database_name'])
mac_address = config['bms']['mac_address']
bms_thread = new_thread(mac_address)

# bms.connect()
while bms_thread.is_running:
    try:
        # pprint(bms_thread.data)
        # print("", flush=True)
        if not bms_thread.last_run_completed:
            print("no completed run")
        elif time.time() - bms_thread.last_run_completed > 120:
            print("bms thread dead")
            bms_thread = new_thread(mac_address)
        time.sleep(30)
    except KeyboardInterrupt:
        break

bms_thread.stop()
