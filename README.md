# Energy Storage Controller



## Tools

### aec-cli.py
Commandline tool to interact with [AEconversion](http://www.aeconversion.de/en/micro-inverters.html) micro inverters.
```bash
$ ./aec-cli.py -i 629 -d /dev/ttyUSB0 --show-yield --h
usage: aec-cli.py [-h] -i INVERTER_ID -d DEVICE [--show-data] [--show-status]
                  [--show-yield] [--check] [--set-limit SET_LIMIT]
                  [--output OUTPUT] [--retry RETRY]

optional arguments:
  -h, --help            show this help message and exit
  -i INVERTER_ID, --inverter-id INVERTER_ID
                        ID of the inverter, last 5 digits of the serial
                        number, without leading zeros
  -d DEVICE, --device DEVICE
                        RS485 device, e.g. /dev/ttyUSB0
  --show-data           show data
  --show-status         show status
  --show-yield          show yield
  --check               Nagios style check
  --set-limit SET_LIMIT
                        set limit to X watt
  --output OUTPUT       text (default), csv, json output for show commands
  --retry RETRY         retry X times if the request fails, default 5
```

Examples
```bash

$ ./aec-cli.py -i 123 -d /dev/ttyUSB0 --show-data
500-90 device, max. 510.0W, version TF0.9.21     533
PV (A): 0.31
PV (V): 57.77
PV (W): 16.1
AC (W): 15.53
$ ./aec-cli.py -i 123 -d /dev/ttyUSB0 --set-limit 100
500-90 device, max. 510.0W, version TF0.9.21     533
OK
$ ./aec-cli.py -i 123 -d /dev/ttyUSB0 --show-status
500-90 device, max. 510.0W, version TF0.9.21     533
States:
	ENERGY_DC_OK
	POWER_LIMIT_SET
```

