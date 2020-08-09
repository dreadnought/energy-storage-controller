#!/usr/bin/python3

import argparse
import json
import sys
import time

from devices import AEConversionInverter

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--inverter-id",
                    help="ID of the inverter, last 5 digits of the serial number, without leading zeros",
                    type=int, required=True)

parser.add_argument("-d", "--device",
                    help="RS485 device, e.g. /dev/ttyUSB0",
                    type=str, required=True)

parser.add_argument("--show-data", help="show data", action="store_true")
parser.add_argument("--show-status", help="show status", action="store_true")
parser.add_argument("--show-yield", help="show yield", action="store_true")
parser.add_argument("--check", help="Nagios style check", action="store_true")
parser.add_argument("--set-limit", help="set limit to X watt", type=int)
parser.add_argument("--output", help="text (default), csv, json output for show commands", type=str, default="text")
parser.add_argument("--retry", help="retry X times if the request fails, default 5", type=int, default=5)

args = parser.parse_args()

inv = AEConversionInverter(inverter_id=args.inverter_id,
                           device=args.device,
                           request_retries=args.retry,
                           exit_after_retries=True)

if args.output in ('json', 'csv') or args.check:
    verbose = False
else:
    verbose = True
response = inv.connect(verbose=verbose)
if not response:
    sys.exit(1)


if args.show_data:
    data = inv.get_data()

    if args.output == 'csv':
        print(";".join(data.keys()))
        values = []
        for value in data.values():
            values.append(str(value))
        print(";".join(values))
    elif args.output == 'json':
        print(json.dumps(data))
    else:
        kv = {
            'pv_amp': 'PV (A)',
            'pv_volt': 'PV (V)',
            'pv_watt': 'PV (W)',
            'ac_watt': 'AC (W)'
        }
        for key, text in kv.items():
            print("%s: %s" % (text, data[key]))
    sys.exit()

if args.show_status:
    status = inv.get_status()

    if args.output == 'csv':
        print('Not implemented')
        sys.exit(1)
    elif args.output == 'json':
        print(json.dumps(status))
    else:
        print('States:')
        for state in status['states']:
            print('\t%s' % state)
        if 'errors' in status:
            print('\nErrors:')
            for state in status['errors']:
                print('\t%s' % state)
        if 'disturbances' in status:
            print('\nDisturbances:')
            for state in status['disturbances']:
                print('\t%s' % state)

    sys.exit()

if args.show_yield:
    y = inv.get_yield()
    if args.output == 'csv':
        print('Not implemented')
        sys.exit(1)
    elif args.output == 'json':
        print(json.dumps(y))
    else:
        print("Watt: %s" % y['watt'])
        print("Wh:   %s" % y['watt_hours'])
    sys.exit()

if args.check:
    status = inv.get_status()
    status_code = 0  # OK
    status_codes = ('OK', 'WARNING', 'CRITICAL', 'UNKNOWN')
    status_line = ''

    data = inv.get_data()
    perfdata = []
    if data:
        for key, value in data.items():
            perfdata.append('%s=%s' % (key, value))

    if 'disturbances' in status:
        status_code = 2
        status_line = ', '.join(status['disturbances'])
    elif 'errors' in status:
        status_code = 2
        status_line = ', '.join(status['errors'])

    if status_code == 0:
        status_line = '%s watt' % data['ac_watt']

    print("%s - %s | %s" % (status_codes[status_code], status_line, " ".join(perfdata)))
    sys.exit(status_code)

if args.set_limit:
    response = inv.set_limit(args.set_limit)
    if response:
        print('OK')
    else:
        print('Failed')
    sys.exit()
