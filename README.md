# Energy Storage Controller

## Devices

### AEconversion micro inverter

Usage: Feed energy from battery to grid, while limiting the output to the actual power usage.

Interface: RS485 over USB

Other implementations:
- [Solaranzeige](https://solaranzeige.de/) (PHP)
- [aeclogger](https://github.com/akrypth/aeclogger) (C)
- [AEC-Webserver](https://github.com/alexanderkunz/AEC-Webserver) (Python)

### SMA Energy Meter / Home Manager 2.0

Usage: Measure energy imported/exported from/to grid.

Interface: Multicast over Ethernet

Other implementations:
- [SMA-EM](https://github.com/datenschuft/SMA-EM) (Python)


### Smart BMS

Usage: Monitor battery cell voltages

Interface: UART over USB

Other implementations:
- [BatteryMonitor](https://github.com/simat/BatteryMonitor) (Python)

### Relays

Usage: Turn on/off AC for inverter.

### Smart Plug

Usage: Turn on/off AC for charger and measure it's power consumption.

## Controller

### Charge Controller

Controls a charger via a PWM signal, to consume all power that would otherwise be exported to the grid.

#### References

## Tools

### aec-cli.py
Commandline tool to interact with [AEconversion](http://www.aeconversion.de/en/micro-inverters.html) micro inverters.
```
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
```

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

### sme-em-cli.py

Commandline tool to read metrics from SMA energy meter.

```
$ ./sma-em-cli.py -h
usage: sma-em-cli.py [-h] [-s SERIAL_NUMBER] [--check] [--output OUTPUT]
                     [--loop]

optional arguments:
  -h, --help            show this help message and exit
  -s SERIAL_NUMBER, --serial-number SERIAL_NUMBER
                        Filter for serial number and hide SN column
  --check               Nagios style check
  --output OUTPUT       text (default), csv, json output for show commands
  --loop                Endless loop, CTL+C to stop

```

Examples
```
$ ./sma-em-cli.py --loop
Time                  Serial Number   External power supply   Grid feed-in
2019-04-28 12:58:40   3002851234      0.0                     2488.9      
2019-04-28 12:58:41   3002851234      0.0                     2535.6      
2019-04-28 12:58:42   3002851234      0.0                     2521.6

$ ./sma-em-cli.py -s 3002851234 --output csv
Time;External power supply;Grid feed-in
2019-04-28 13:00:00;0.0;2020.9

```