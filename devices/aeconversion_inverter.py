import math
import serial
import struct
import threading
import time
import traceback

error_codes = (
    "TEMP_SENSOR",
    "TEMP_HIGH",
    "IAC_CRITICAL",
    "UAC_HIGH",
    "UAC_HIGH_CRITICAL",
    "UAC_LOW_CRITICAL",
    "FREQUENCY_LOW",
    "FREQUENCY_HIGH",
    "EEPROM_CRC",
    "ATTINY_FREQ_LOW",
    "ATTINY_FREQ_HIGH",
    "ATTINY_UAC_LOW",
    "ATTINY_UAC_HIGH",
    "ATTINY_TIMEOUT",
    "HOST_TIMEOUT",
    "U_PV_HIGH",
    "EMERGENCY_STOP",
    "ISLAND_DETECTION",
    "RELAIS_ATTINY",
    "RELAIS_SAM7",
    "RELAIS_ATTINY",
    "AC_EMERGENCY_STOP",
    "ATTINY_IMPLAUSIBLY",
    "DC_POWER",
    "UAC_LOW",
    "RESTART_FORBIDDEN",
    "SURGE_TEST"
)

state_codes = (
    "READY_AC",
    "ENERGY_DC_OK",
    "MPP_INITIALIZED",
    "POWER_LIMIT_SET",
    "TRANSMIT",
    "CALIBRATE",
    "STORE_SETUP",
    "ATTINY_OK",
    "REGIONAL_LOCK",
    "ATTINY_PARAM_OK",
    "POWER_SORTAGE",
    "SYNC_AC",
)

disturb_codes = (
    "PLL_LOW",
    "ADC_CONVERSION",
    "UDC_OVERFLOW",
    "UDC_LOW",
    "IAC_HIGH",
    "IAC_ZERO",
    "PI_HIGH",
    "PI_LOW",
    "ADC_LOW",
    "FREQU_1",
    "FREQU_2",
    "FREQU_3",
    "FREQU_4",
    "FREQU_5",
    "FREQU_6",
)


class AEConversionInverter:
    def __init__(self, device, inverter_id):
        self.serial = None
        self.device = device
        self.inverter_id = inverter_id
        self.inverter_id_bytes = inverter_id.to_bytes(2, byteorder='big')
        self.metrics = None
        self.device_parameters = None
        self.last_limit = None  # last set limit in watt
        self.last_limit_change = None  # time when the last limit was set

    def _c_crc(self, message_hex):
        x = 0
        m = self.inverter_id_bytes + message_hex

        for i in range(0, len(m)):
            x ^= m[i]

        _crc_hex = x.to_bytes(2, byteorder='big')
        _data_hex = b"\x21" + self.inverter_id_bytes + message_hex + _crc_hex + b"\x0D"
        return _data_hex

    def _read(self, message_bytes, init=False, min_length=4):
        if not init and not self.device_parameters:
            # check that we are talking to a valid device
            print('Not connected')
            return False

        if not self.serial.isOpen():
            self.serial.open()

        full_message = self._c_crc(message_bytes)
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.serial.write(full_message)

        response_bytes = b""
        while True:
            b = self.serial.read(1)
            if len(b) == 0:
                print("Incomplete response read")
                return False
            if b == b'\x0d' and len(response_bytes) >= min_length:
                # valid/complete answers have to end with \x0d
                break
            elif b == b'\x0d':
                # print('found at', len(response_bytes), 'but to short')
                pass
            response_bytes += b

        if len(response_bytes) == 0:
            print('No response received')
            return False

        return response_bytes

    @staticmethod
    def _decode_value(i):
        if i == '':
            return None
        return round(i / 2 ** 16, 2)

    def connect(self, verbose=True):
        self.serial = serial.Serial(
            port=self.device,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
            writeTimeout=2
        )

        try:
            self.device_parameters = self.get_device_parameters()
        except Exception as e:
            print(e)
            print(traceback.format_exc())
            self.device_parameters = None
        if not self.device_parameters:
            print('Failed to connect to inverter %s over %s' % (self.inverter_id, self.serial.port))
            return False

        if verbose:
            print('%s device, max. %sW, version %s' % (self.device_parameters['type'],
                                                       self.device_parameters['max_watt'],
                                                       self.device_parameters['version']))

        if self.device_parameters['type'] not in ('250-45', 'PV350W', '350-60', '350-90', '500-90'):
            print('unsupported device type "%s"' % self.device_parameters['type'])
            self.device_parameters = False
            return False

        return True

    def stop(self):
        self.serial.close()

    def get_data(self, verbose=True):
        message = b"\x03\xED"
        response_bytes = self._read(message, min_length=36)

        if not response_bytes:
            return False
        elif len(response_bytes) < 36 or len(response_bytes) > 38:
            print("get_data: invalid length %s" % len(response_bytes))
            print("get_data: %s" % response_bytes.hex())
            return False

        parts = struct.unpack('>3x I I I I I I I I x', response_bytes[:36])

        data = {
            # '_u_s_ac': self._decode_value(parts[0]),
            # '_i_s_ac': self._decode_value(parts[1]),
            'pv_amp': self._decode_value(parts[2]),
            'pv_volt': self._decode_value(parts[3]),
            'ac_watt': self._decode_value(parts[4]),
            'pv_watt': self._decode_value(parts[5]),
            'temperature': self._decode_value(parts[6]),
            # '_dc_ac': _self._decode_value(parts[7]),
        }

        if data['pv_watt'] > self.device_parameters['max_watt'] * 2 or data['ac_watt'] > self.device_parameters[
            'max_watt'] * 2:
            if verbose:
                print('get_data: invalid data %s' % data)
            return False
        if data['temperature'] > 1000:
            if verbose:
                print('get_data: invalid temperature reading %s' % data['temperature'])
            data['temperature'] = 0.0

        data['time'] = time.time()
        self.metrics = data
        return data

    @staticmethod
    def _check_bits(in_hex, code_list):
        bits = bin(int(in_hex, 16))[2:]
        codes = []
        for bit in range(1, len(bits), 1):
            if int(bits[bit * -1]) == 1:
                codes.append(code_list[bit - 1])
        return codes

    def get_status(self):
        response_bytes = self._read(b"\x03\xF0")

        if not response_bytes:
            print('get_status failed')
            return False
        response = response_bytes.hex()

        if response[0:6] != '212713':
            print('unexpected answer')

        state = response[7:14]
        error = response[15:22]
        disturb = response[23:30]

        data = {}

        states = self._check_bits(state, state_codes)
        data['states'] = states

        if error:
            errors = self._check_bits(error, error_codes)
            data['errors'] = errors
        if disturb:
            disturbs = self._check_bits(disturb, disturb_codes)
            data['disturbances'] = disturbs

        return data

    def get_yield(self):
        response_bytes = self._read(b"\x03\xFD")
        if len(response_bytes) != 12:
            return False

        parts = struct.unpack('>3x I I x', response_bytes)
        data = {
            'watt': self._decode_value(parts[0]),
            'watt_hours': self._decode_value(parts[1]),
        }
        return data

    def get_device_parameters(self):
        response_bytes = self._read(b"\x03\xF6", init=True)
        if not response_bytes:
            return False

        parts = struct.unpack('>7x 6s 38x 16s I', response_bytes[:71])
        data = {
            'max_watt': self._decode_value(parts[2]),
            'type': parts[0].decode(),
            'version': parts[1].decode(),
        }
        return data

    def set_limit(self, limit):
        if int(limit) > self.device_parameters['max_watt']:
            print("ERROR: Limit %i W higher than device max. %i W" % (limit, self.device_parameters['max_watt']))
            return

        message_bytes = b"\x03\xFE"

        _p = int(limit) * 2 ** 16
        message = message_bytes + _p.to_bytes(4, byteorder='big')
        try:
            response_bytes = self._read(message)
        except serial.serialutil.SerialException as e:
            print('setting limit failed')
            print(e)
            return False
        if not response_bytes:
            return False
        response = response_bytes.hex()
        if not response:
            return False
        elif response == '212710370d':
            status = self.get_status()
            if 'POWER_LIMIT_SET' not in status['states']:
                print('POWER_LIMIT_SET not in status states')
                return False

            self.last_limit = limit
            self.last_limit_change = time.time()
            return limit
        else:
            print('set_limit failed (%s)' % response)
            return False

    def request_energy(self, watt_request, watt_max=None, watt_tolerance=20, set_limit_interval=60, max_increase=50):
        # set the limit relative to the already produced power
        if not self.metrics:
            print('no metrics for energy request')
            return False
        used_watt = watt_request + self.metrics['ac_watt']

        if watt_max:
            watt_max = min(watt_max, self.device_parameters['max_watt'])
        else:
            watt_max = self.device_parameters['max_watt']

        if self.last_limit and watt_max > self.last_limit and watt_max - self.last_limit > max_increase:
            increase = self.last_limit + max_increase
            print('%s watt increase, reducing to %s' % (watt_max - self.last_limit, increase))
            watt_max = increase

        calculated_limit = min(used_watt + watt_tolerance, watt_max)
        force_limit = False
        if calculated_limit < 0:
            calculated_limit = 10
            if self.last_limit != 10:
                force_limit = True

        is_in_tolerance = math.isclose(calculated_limit, self.last_limit, abs_tol=watt_tolerance)
        if self.last_limit and is_in_tolerance and not force_limit:
            print('current limit (%0.2f) in tolerance' % self.last_limit)
        else:
            if not self.last_limit:
                print('unkown inverter limit')
            if self.last_limit_change and time.time() - self.last_limit_change < set_limit_interval:
                print("limit set %0.1f seconds ago, waiting" % (time.time() - self.last_limit_change))
            else:
                print('set limit %0.1f' % calculated_limit)
                result = self.set_limit(calculated_limit)
                if result is False:
                    print('retry next round')
                else:
                    print('Limit set to %0.1f' % result)

    def is_active(self):
        # is the inverter producing energy?

        if not self.metrics:
            return False

        if self.metrics['ac_watt'] > 0.0:
            return True

        return False


class AEConversionInverterThread(threading.Thread):
    def __init__(self, config, metrics, logger):
        threading.Thread.__init__(self)
        self.is_running = False
        self.start_time = None
        self.connected = False
        self.last_connection_attempt = 0
        self.data = {}
        self.command_queue = []
        self.logger = logger
        self.inverter = AEConversionInverter(device=config['device'],
                                             inverter_id=config['inverter_id'])
        self.metrics = metrics

    def stop(self):
        self.logger.info('AEConversionInverterThread: stopping...')
        self.is_running = False
        self.inverter.stop()

    def run(self):
        self.is_running = True
        self.start_time = time.time()
        self.is_connected = False
        while self.is_running:
            #print("run")
            if not self.inverter.device_parameters:
                try:
                    self.last_connection_attempt = time.time()
                    self.inverter.connect()
                except Exception as e:
                    self.logger.error('failed to connect')
                    print(e)
                    return False
                time.sleep(10)
                continue
            #print(self.command_queue)
            retry_queue = []
            while len(self.command_queue) > 0:
                if not self.is_healthy():
                    self.logger.error("AEConversionInverterThread: unhealthy, not executing commands")
                    print(self.command_queue)
                    break
                command, kwargs = self.command_queue.pop(0)
                print(command, kwargs)
                try:
                    if command == 'set_limit':
                        result = self.inverter.set_limit(**kwargs)
                        # todo: set again after 5 minutes
                    elif command == 'request_energy':
                        result = self.inverter.request_energy(**kwargs)
                    else:
                        print('unknown command "%s" in queue' % command)
                        result = False
                except Exception as e:
                    print(e)
                    print(traceback.format_exc())
                    result = False
                if result is False:
                    print('%s failed' % command)
                    # todo: if failure count > 5: drop
                    retry_queue.append((command, kwargs))
                else:
                    # skip reading data
                    continue

            self.command_queue.extend(retry_queue)
            try:
                data = self.inverter.get_data(verbose=False)
            except serial.serialutil.SerialException:
                self.logger.error('AEConversionInverterThread: failed to get data from inverter')
                data = False
            if data is not False:
                self.is_connected = True
                self.data = data
                points = []
                data_copy = data.copy()
                ts = data_copy['time']
                del data_copy['time']
                points.append({
                    "measurement": "AEConversionInverterData",
                    "tags": {
                        "inverter_id": self.inverter.inverter_id,
                        "dev": self.inverter.device,
                    },
                    "time": ts,
                    "fields": data_copy,
                })
                self.metrics.write_metric(points=points)

            time.sleep(10)
        self.logger.info('AEConversionInverterThread: stopped')

    def queue_command(self, command, args):
        self.command_queue.append([command, args])

    def is_healthy(self):
        if not self.is_running or not self.is_connected:
            return False
        if len(self.data) == 0:
            return False
        t_diff = time.time() - self.data['time']
        if t_diff > 120.0:
            self.logger.warning('AEConversionInverterThread: no data for %s seconds' % int(time.time() - self.data['time']))
        if t_diff > 60.0:
            self.logger.warning("reconnecting")
            self.inverter.stop()
            if time.time() - self.last_connection_attempt < 60:
                self.last_connection_attempt = time.time()
                self.inverter.connect()
                time.sleep(10)
            return False

        return True
