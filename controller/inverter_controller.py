#!/usr/bin/python3
import time
import math
from pprint import pprint
import traceback
from datetime import datetime
import pytz

from devices.sma_energy_manager import SMAEnergyManagerThread
from devices.aeconversion_inverter import AEConversionInverterThread
from devices.gpio import GpioPin
from pyedimax.smartplug import SmartPlug
from config import config
from metrics import Metrics

tz = pytz.timezone('Europe/Berlin')


class InverterController():
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.logger.info('init...')
        self.metrics = Metrics(database_name=self.config['influxdb']['database_name'])
        self.logger.info('energy meter...')
        self.energy_meter = SMAEnergyManagerThread(serial_number=config['sma_energy_manager']['serial_number'],
                                                   metrics=self.metrics)
        self.energy_meter.start()
        self.logger.info('battery inverter...')
        self.battery_inverter = AEConversionInverterThread(config=config['aeconversion_inverter'],
                                                           metrics=self.metrics,
                                                           logger=self.logger)
        self.battery_inverter.start()
        self.logger.info('smart plug...')
        self.smart_plug = SmartPlug(config['charger']['smartplug_ip'],
                                    (config['charger']['smartplug_username'], config['charger']['smartplug_password']))

        self.battery_inverter_relay_ac = GpioPin(pin=config['aeconversion_inverter']['gpio_pin'])

        self.logger.info('init done')

    def go_idle(self):
        if self.battery_inverter_relay_ac.get_state() == 1:
            self.logger.info('Turning inverter relay off')
            self.battery_inverter_relay_ac.set_state(False)
        self.logger.debug('Inverter relay off')

    def loop_run(self):
        self.logger.debug('==== start of run %s ====' % datetime.now(tz))
        watt_tolerance = 20
        watt_inverter_start = 100
        if not self.energy_meter.is_healthy():
            self.logger.error('no data from energy meter')
            self.go_idle()
            return False

        em_import = self.energy_meter.data['p_import']
        em_export = self.energy_meter.data['p_export']
        em_balanced = False
        self.logger.debug('%s to, %s from grid' % (em_export, em_import))
        if em_export + em_import < watt_tolerance:
            self.logger.debug('balanced')
            em_balanced = True
        elif em_export == 0.0 and em_import > 0.0:
            # print('pulling energy from grid')
            pass
        elif em_import == 0.0 and em_export > 0.0:
            # print('pushing energy to grid')
            pass
        else:
            self.logger.error('undefined state')

        battery_charger_on = False

        inverter_in_operation = False
        if not self.battery_inverter.is_healthy():
            self.logger.error('Inverter thread unhealthy')
            self.go_idle()
            return

        # print('battery inverter connected')
        self.logger.debug('Inverter', self.battery_inverter.data)
        battery_status = self.check_battery_discharge()
        battery_level = 100 / (self.config['battery']['max_voltage'] - self.config['battery']['min_voltage']) * (
                self.battery_inverter.data['pv_volt'] - self.config['battery']['min_voltage'])
        self.logger.debug("Battery Level: %0.2f%%" % battery_level)

        max_discharge_watt = self.config['battery']['max_discharge_watt']
        if battery_level < 20:
            self.logger.info('battery level <20%, limiting discharge')
            max_discharge_watt = max_discharge_watt / 2

        if not battery_status or battery_charger_on:
            self.logger.info('battery not good, skipping rest')
            self.go_idle()
            return
        elif battery_level < 0.0:
            self.logger.info('battery low, turning inverter off')
            self.battery_inverter_relay_ac.set_state(False)
            return

        inverter_max = self.battery_inverter.inverter.device_parameters['max_watt']
        last_limit = self.battery_inverter.inverter.last_limit
        if em_export > inverter_max:
            self.battery_inverter_relay_ac.set_state(False)
            self.logger.debug("Off, to much export")
        elif last_limit and last_limit == 10:
            self.battery_inverter_relay_ac.set_state(False)
            self.logger.info("Off, last limit 10")
            self.battery_inverter.inverter.last_limit = 0
        elif self.battery_inverter.inverter.is_active():
            inverter_in_operation = True
            self.logger.debug("On")
        else:
            self.logger.debug("Off")
            now = datetime.now(tz)
            if now.hour > 11 and now.hour < 16:
                self.logger.debug('charging time, not activating')
            elif self.smart_plug.state == 'ON':
                print("Charger is running, not activating inverter", flush=True)
                return
            elif battery_level > 25 and em_import > watt_inverter_start:
                # turn on inverter AC if the battery is at least 40% and we need energy
                self.logger.info("Turning inverter on")
                self.battery_inverter_relay_ac.set_state(True)
                time.sleep(10)
                self.battery_inverter.queue_command(command='set_limit', args={'limit': 100})
                return
            else:
                self.logger.info("No reason to activate inverter")

        if not inverter_in_operation:
            pass
        elif not em_balanced or time.time() - self.battery_inverter.inverter.last_limit_change > 60 * 4:
            self.logger.info('Requesting energy')
            # todo: check vs. watt_max
            self.battery_inverter.queue_command("request_energy",
                                                {
                                                    'watt_request': em_import - em_export,
                                                    'watt_tolerance': watt_tolerance,
                                                    'set_limit_interval': 120,
                                                    'watt_max': max_discharge_watt,
                                                })

        self.logger.debug('==== end of run ====')

    def check_battery_discharge(self):
        if self.battery_inverter.data['pv_volt'] > self.config['battery']['min_voltage']:
            return True

        self.logger.info("limiting")
        if self.battery_inverter.data['ac_watt'] > 510:
            self.logger.warning("invalid ac_watt value")
            new_limit = 100
        elif self.battery_inverter.inverter.last_limit:
            new_limit = self.battery_inverter.inverter.last_limit - config['aeconversion_inverter']['limit_step']
        else:
            new_limit = self.battery_inverter.data['ac_watt'] - config['aeconversion_inverter']['limit_step']
        if new_limit < 10:
            self.logger.warning("low voltage")
            return False
        # self.battery_inverter.queue_command(('set_limit', {'limit': new_limit}))
        time.sleep(5)
        return True

    def stop(self):
        self.energy_meter.stop()
        self.battery_inverter.stop()
        self.battery_inverter_relay_ac.set_state(False)

    def loop(self):
        while True:
            try:
                self.loop_run()
                time.sleep(30)
            except KeyboardInterrupt:
                break

        self.stop()
