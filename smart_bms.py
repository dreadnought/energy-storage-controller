#!/usr/bin/python3
import time
from cysystemd.daemon import notify, Notification

from dalybms import DalyBMSBluetooth
from devices.gpio import GpioPin
from logger import get_logger
from metrics import Metrics

from config import config

logger = get_logger(level='info')
received_data = False
time.sleep(3)

battery_inverter_relay_ac = GpioPin(pin=config['aeconversion_inverter']['gpio_pin'])

import asyncio
import multiprocessing

class DalyBMSConnection():
    def __init__(self, mac_address, logger, metrics_queue):
        self.logger = logger
        self.bt_bms = DalyBMSBluetooth(logger=logger)
        self.mac_address = mac_address
        self.metrics_queue = metrics_queue
        self.last_data_received = None

    async def connect(self):
        await self.bt_bms.connect(mac_address=self.mac_address)

    async def update_cell_voltages(self):
        cell_voltages = await self.bt_bms.get_cell_voltages()
        logger.debug(cell_voltages)
        points = []

        if not cell_voltages:
            logger.warning("failed to receive cell voltages")
            return
        cell_voltages_time = time.time()
        for cell, voltage in cell_voltages.items():
            points.append({
                "measurement": "SmartBMSCellVoltages",
                "tags": {
                    "mac_address": self.mac_address,
                    "cell": cell,
                },
                "time": cell_voltages_time,
                "fields": {'voltage': voltage},
            })

            if voltage < 2.9 and battery_inverter_relay_ac.get_state() == 1:
                logger.warning(f"voltage {voltage} of cell {cell} is low, turning off inverter")
                battery_inverter_relay_ac.set_state(False)
        self.last_data_received = time.time()
        self.metrics_queue.put(points)


    async def update_soc(self):
        soc = await self.bt_bms.get_soc()
        self.logger.debug(soc)
        if not soc:
            logger.warning("failed to receive SOC")
            return
        point = {
            "measurement": "SmartBMSStatus",
            "tags": {
                "mac_address": self.mac_address,
            },
            "time": time.time(),
            "fields": soc,
        }
        self.metrics_queue.put([point])
        self.last_data_received = time.time()


async def main(con):
    logger.info("Connecting")
    await con.connect()
    logger.info("Starting loop")
    received_data = False
    while con.bt_bms.client.is_connected:
        logger.debug("run start")
        await con.update_soc()
        await con.update_cell_voltages()
        #all = await con.bt_bms.get_all()
        #print(all)

        if con.last_data_received is None:
            logger.warning("Failed receive data")
            await asyncio.sleep(10)
            continue
        time_diff = time.time() - con.last_data_received
        if time_diff > 30:
            logger.error("BMS thread didn't receive data for %0.1f seconds" % time_diff)
        else:
            if not received_data:
                logger.info("First received data")
                notify(Notification.READY)
                received_data = True
            notify(Notification.WATCHDOG)

        logger.debug("run done")
        await asyncio.sleep(10)
    await con.bt_bms.disconnect()
    con.metrics_queue.close()
    logger.info("Loop ended")

def write_metric(queue):
    # Subprocess
    metrics_connection = Metrics(database_name=config['influxdb']['database_name'])
    while True:
        try:
            points = queue.get(block=True)
            metrics_connection.write_metric(points=points)
        except KeyboardInterrupt:
            break

metrics_queue = multiprocessing.Queue()
p = multiprocessing.Process(target=write_metric, args=(metrics_queue,))
p.start()
con = DalyBMSConnection(mac_address=config['bms']['mac_address'], logger=logger,
                            metrics_queue=metrics_queue)
loop = asyncio.get_event_loop()
asyncio.ensure_future(main(con))
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

loop.run_until_complete(con.bt_bms.disconnect())
metrics_queue.close()
p.terminate()
logger.info("Final End")
