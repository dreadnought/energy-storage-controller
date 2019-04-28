#!/usr/bin/python3

import argparse
import json
import sys
import time
import datetime
from texttable import Texttable

from devices import SMAEnergyManager

parser = argparse.ArgumentParser()

parser.add_argument("-s", "--serial-number",
                    help="Filter for serial number and hide SN column",
                    type=int, required=False)

parser.add_argument("--check", help="Nagios style check", action="store_true")
parser.add_argument("--output", help="text (default), csv, json output for show commands", type=str, default="text")
parser.add_argument("--loop", help="Endless loop, CTL+C to stop", action="store_true")

args = parser.parse_args()

em = SMAEnergyManager()
if args.serial_number:
    header = ['Time', 'External power supply', 'Grid feed-in']
else:
    header = ['Time', 'Serial Number', 'External power supply', 'Grid feed-in']

if args.output == 'text':
    table = Texttable()
    table.set_deco(Texttable.HEADER)
    if args.serial_number:
        table.set_cols_dtype(['t', 't', 't'])
    else:
        table.set_cols_dtype(['t', 't', 't', 't'])
    table.add_row(header)
elif args.output == 'csv':
    print(';'.join(header))

if args.check:
    status_code = 0  # OK
    status_codes = ('OK', 'WARNING', 'CRITICAL', 'UNKNOWN')
    status_line = ''
    perfdata = []

    sn, em_data = em.read(phases=False)
    perfdata.append('p_import=%0.1f' % em_data['p_import'])
    perfdata.append('p_import=%0.1f' % em_data['p_export'])
    status_line += '%0.1f from grid, ' % em_data['p_import']
    status_line += '%0.1f to grid' % em_data['p_export']
    print("%s - %s | %s" % (status_codes[status_code], status_line, " ".join(perfdata)))
    sys.exit(status_code)

while True:
    try:
        sn, em_data = em.read(phases=False)
        if args.serial_number and sn != args.serial_number:
            continue
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if args.serial_number:
            row = [now, "%0.1f" % em_data['p_import'], "%0.1f" % em_data['p_export']]
        else:
            row = [now, str(sn), "%0.1f" % em_data['p_import'], "%0.1f" % em_data['p_export']]

        if args.output == 'text':
            table.add_row(row)
            print(table.draw())
            table.reset()
        elif args.output == 'json':
            print(json.dumps({sn: em_data}))
        elif args.output == 'csv':
            print(";".join(row))
        else:
            print('unknown output format %s' % args.output)
            break
        if not args.loop:
            break
    except KeyboardInterrupt:
        break
