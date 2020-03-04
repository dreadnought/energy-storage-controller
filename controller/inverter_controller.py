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
    def __init__(self, config):
        self.config = config
        print('init...', flush=True)
        self.metrics = Metrics(database_name=self.config['influxdb']['database_name'])
        print('energy meter...', flush=True)
        self.energy_meter = SMAEnergyManagerThread(serial_number=config['sma_energy_manager']['serial_number'],
                                                   metrics=self.metrics)
        self.energy_meter.start()
        print('battery inverter...', flush=True)
        self.battery_inverter = AEConversionInverterThread(config=config['aeconversion_inverter'], metrics=self.metrics)
        self.battery_inverter.start()
        print('smart plug...', flush=True)
        self.smart_plug = SmartPlug(config['charger']['smartplug_ip'],
                                    (config['charger']['smartplug_username'], config['charger']['smartplug_password']))

        self.battery_inverter_relay_ac = GpioPin(pin=64)

        print('init done', flush=True)

    def go_idle(self):
        print('going idle')
        self.battery_inverter_relay_ac.set_state(False)
        #self.battery_charger_relay_ac.off()

    def loop_run(self):
        print('==== start of run %s ====' % datetime.now(tz), flush=True)
        watt_tolerance = 20
        watt_inverter_start = 100
        if not self.energy_meter.is_healthy():
            print('no data from energy meter')
            self.go_idle()
            return False

        em_import = self.energy_meter.data['p_import']
        em_export = self.energy_meter.data['p_export']
        em_balanced = False
        print('%s to, %s from grid' % (em_export, em_import))
        if em_export + em_import < watt_tolerance:
            print('balanced')
            em_balanced = True
        elif em_export == 0.0 and em_import > 0.0:
            # print('pulling energy from grid')
            pass
        elif em_import == 0.0 and em_export > 0.0:
            # print('pushing energy to grid')
            pass
        else:
            print('undefined state')

        battery_charger_on = False

        inverter_in_operation = False
        if not self.battery_inverter.is_healthy():
            print('inverter unhealthy, turning it off')
            self.go_idle()
            return

        # print('battery inverter connected')
        print('Inverter', self.battery_inverter.data)
        battery_status = self.check_battery_discharge()
        battery_level = 100 / (self.config['battery']['max_voltage'] - self.config['battery']['min_voltage']) * (
                self.battery_inverter.data['pv_volt'] - self.config['battery']['min_voltage'])
        print("Battery Level: %0.2f%%" % battery_level)

        max_discharge_watt = self.config['battery']['max_discharge_watt']
        if battery_level < 20:
            print('battery level <20%, limiting discharge')
            max_discharge_watt = max_discharge_watt / 2

        if not battery_status or battery_charger_on:
            print('battery not good, skipping rest')
            self.go_idle()
            return
        elif battery_level < 0.0:
            print('battery low, turning inverter off')
            self.battery_inverter_relay_ac.set_state(False)
            return

        inverter_max = self.battery_inverter.inverter.device_parameters['max_watt']
        last_limit = self.battery_inverter.inverter.last_limit
        if em_export > inverter_max:
            self.battery_inverter_relay_ac.set_state(False)
            print("Off, to much export")
        elif last_limit and last_limit == 10:
            self.battery_inverter_relay_ac.set_state(False)
            print("Off, last limit 10")
            self.battery_inverter.inverter.last_limit = 0
        elif self.battery_inverter.inverter.is_active():
            inverter_in_operation = True
            print("On")
        else:
            print("Off", flush=True)
            now = datetime.now(tz)
            if now.hour > 11 and now.hour < 16:
                print('charging time, not activating')
            elif self.smart_plug.state == 'ON':
                print("Charger is running, not activating inverter", flush=True)
                return
            elif battery_level > 40 and em_import > watt_inverter_start:
                # turn on inverter AC if the battery is at least half filled and we need energy
                print("turning on inverter")
                self.battery_inverter_relay_ac.set_state(True)
                time.sleep(10)
                self.battery_inverter.queue_command(command='set_limit', args={'limit': 100})
                return
            else:
                print("No reason to activate inverter")

        if inverter_in_operation and (not em_balanced or time.time() - self.battery_inverter.inverter.last_limit_change > 60 * 4):
            print('requesting energy')
            # todo: check vs. watt_max
            self.battery_inverter.queue_command("request_energy",
                                                {
                                                    'watt_request': em_import - em_export,
                                                    'watt_tolerance': watt_tolerance,
                                                    'set_limit_interval': 120,
                                                    'watt_max': max_discharge_watt,
                                                })

        print('==== end of run ====', flush=True)

    def check_battery_discharge(self):
        if self.battery_inverter.data['pv_volt'] > self.config['battery']['min_voltage']:
            return True

        print("limiting")
        if self.battery_inverter.data['ac_watt'] > 510:
            print("invalid ac_watt value")
            new_limit = 100
        elif self.battery_inverter.inverter.last_limit:
            new_limit = self.battery_inverter.inverter.last_limit - config['aeconversion_inverter']['limit_step']
        else:
            new_limit = self.battery_inverter.data['ac_watt'] - config['aeconversion_inverter']['limit_step']
        if new_limit < 10:
            print("low voltage")
            return False
        # self.battery_inverter.queue_command(('set_limit', {'limit': new_limit}))
        time.sleep(5)
        return True

    def loop(self):
        while True:
            try:
                self.loop_run()
                time.sleep(30)
            except KeyboardInterrupt:
                break

        self.energy_meter.stop()
        self.battery_inverter.stop()
        self.battery_inverter_relay_ac.set_state(False)

