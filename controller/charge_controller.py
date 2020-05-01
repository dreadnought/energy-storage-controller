import datetime
import time

from devices.pwm_rockpis import PWM
from devices.sma_energy_manager import SMAEnergyManagerThread

from cysystemd.daemon import notify, Notification


class Throttler():
    def __init__(self, min_sec):
        self.min_sec = min_sec
        self.reset()

    def trigger(self):
        """
        Return True if the timer was started > min_sec ago
        """
        if self.timer is None or time.time() - self.last_try > self.min_sec * 2:
            self.timer = time.time()
            self.last_try = time.time()
            return False
        elif time.time() - self.timer > self.min_sec:
            self.reset()
            return True
        else:
            self.last_try = time.time()
            return False

    def reset(self):
        self.timer = None
        self.last_try = 0


class ChargeController():
    def __init__(self, config, logger, metrics, smart_plug):
        self.config = config
        self.logger = logger
        self.metrics = metrics
        self.smart_plug = smart_plug
        self.pwm = PWM(logger=logger)

        self.logger.info("%s %s" % (self.smart_plug.state, self.smart_plug.now_power))
        self.init_energy_meter()

        self.levels = {
            # watt: volt
            310: 0.4,
            370: 1.0,  # +60
            440: 1.2,  # +70
            510: 1.4,  # +70
            610: 1.6,  # +100
            660: 1.8,  # +50
            740: 2.0,  # +80
            810: 2.2,  # +70
            890: 2.4,  # +80
            980: 2.6,  # +90
            1060: 2.8,  # +80
            1170: 3.0,  # +110
            1270: 3.2,  # +100
            # the pwm pin supports max. 3.2v
            1750: 0.1,  # voltages <0.4 set the charger to its maximum
        }
        self.min_level = min(self.levels.keys())
        self.off_throttler = Throttler(60 * 5)

    def init_energy_meter(self):
        self.logger.info("Connecting to energy meter")
        self.energy_meter = SMAEnergyManagerThread(serial_number=self.config['sma_energy_manager']['serial_number'],
                                                   metrics=None)
        self.energy_meter.start()
        time.sleep(1)

    def set_output_current(self, watt):
        level = 0
        for l in self.levels:
            if l > watt:
                break
            level = l

        if level == 0:
            # the requested watt is lower than the lowest level that the charger supports
            self.logger.info("Turning off smart plug")
            self.smart_plug.state = 'OFF'
            # set it to the lowest level, for the next start
            level = self.min_level

        new_v = self.levels[level]
        current_v = self.pwm.get_pwm_volt()
        if new_v == current_v:
            self.logger.debug("unchanged %s volt" % new_v)
        else:
            self.logger.info("setting to %s volt (was %s), %s watt" % (new_v, current_v, level))
            self.pwm.set_pwm_volt(new_v)
        return new_v, level

    def stop(self):
        self.energy_meter.stop()
        # self.smart_plug.state = "OFF"
        # if the charger turns on while the controller isn't running, limit it as much as possible
        self.pwm.set_pwm_volt(1.0)

    def sleep_until_tomorrow(self):
        now = datetime.datetime.utcnow()
        tomorrow = now.replace(hour=4, minute=0) + datetime.timedelta(days=1)
        seconds_left = tomorrow.timestamp() - time.time()
        self.logger.info("Sleeping %0.1f hours" % (seconds_left / 3600))
        self.energy_meter.stop()
        while seconds_left > 0:
            seconds_left -= 30
            notify(Notification.WATCHDOG)
        self.logger.info("Waking up...")
        self.init_energy_meter()

    def loop(self):
        WATT_RESERVED = 50  # leave power for other devices
        LOOP_RUN_SEC = 30
        notify(Notification.READY)
        while True:
            if len(self.energy_meter.data) == 0:
                self.logger.warning("No energy meter data")
                time.sleep(10)
                continue
            elif time.time() - self.energy_meter.data['time'] > 60:
                self.logger.error("Energy meter thread dead")
                self.energy_meter.stop()
                self.init_energy_meter()
                time.sleep(10)
                continue

            notify(Notification.WATCHDOG)

            ts = time.time()
            balance = (self.energy_meter.data['p_import'] * -1) + self.energy_meter.data['p_export']

            if self.smart_plug.state == 'OFF':
                self.logger.info("Charger off")
                if balance > 500:
                    # todo: check inverter state
                    self.logger.info("Turning on smart plug")
                    self.smart_plug.state = 'ON'
                    self.off_throttler.reset()
                elif datetime.datetime.now().hour >= 19:
                    self.sleep_until_tomorrow()
                    continue
                else:
                    self.pwm.set_pwm_volt(1.0)
                    time.sleep(LOOP_RUN_SEC)
                    continue

            charger_power = float(self.smart_plug.now_power)
            available_charging_power = balance - WATT_RESERVED + charger_power

            if charger_power > 50 and charger_power < self.min_level - 50:
                if self.off_throttler.trigger():
                    self.logger.info("Fully charged, turning off smart plug")
                    self.smart_plug.state = 'OFF'
                    self.sleep_until_tomorrow()
                    continue
                else:
                    self.logger.info("Fully charged, waiting...")

            v, level = self.set_output_current(available_charging_power)
            self.logger.info("Smart Plug %0.1f, Balance %0.1f, %0.1f watt available -> %s volt" % (
                charger_power, balance, available_charging_power, v))

            points = []
            points.append({
                "measurement": "ChargeController",
                "time": ts,
                "fields": {
                    'power_limit': level,
                    'power_real': charger_power,
                    'volt': v,
                },
            })
            self.metrics.write_metric(points=points)

            time.sleep(LOOP_RUN_SEC)
