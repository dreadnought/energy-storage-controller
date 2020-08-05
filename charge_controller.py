#!/usr/bin/python3

from pyedimax.smartplug import SmartPlug

from config import config, tz
from controller.charge_controller import ChargeController
from logger import get_logger
from metrics import Metrics

logger = get_logger(level='info')

smart_plug_auth = (config['charger']['smartplug_username'], config['charger']['smartplug_password'])
smart_plug = SmartPlug(config['charger']['smartplug_ip'], smart_plug_auth)

m = Metrics(database_name=config['influxdb']['database_name'])
cc = ChargeController(config=config, logger=logger, metrics=m, smart_plug=smart_plug, tz=tz)
volt = cc.pwm.get_pwm_volt()
logger.info('%0.2f volt at start' % volt)

try:
    cc.loop()
except KeyboardInterrupt:
    cc.stop()
