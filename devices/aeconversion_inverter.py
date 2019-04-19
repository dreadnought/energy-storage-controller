import serial
import time
import threading
import struct

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
    "MPP_INITIALIZED:",
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
        self.last_limit = None
        self.last_status = None
        self.device_parameters = None

    def _c_crc(self, message_hex):
        x = 0
        m = self.inverter_id_bytes + message_hex

        for i in range(0, len(m)):
            x ^= m[i]

        _crc_hex = x.to_bytes(2, byteorder='big')
        _data_hex = b"\x21" + self.inverter_id_bytes + message_hex + _crc_hex + b"\x0D"
        return _data_hex

    def _read(self, message_bytes, init=False):
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

        response_bytes = self.serial.readline()
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
            timeout=1,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
            writeTimeout=2
        )

        try:
            self.device_parameters = self.get_device_parameters()
        except Exception as e:
            print(e)
            self.device_parameters = None
        if not self.device_parameters:
            print('Failed to connect to inverter %s over %s' % (self.inverter_id, self.serial.port))
            return False

        if verbose:
            print('%s device, max. %sW, version %s' % (self.device_parameters['type'],
                                                       self.device_parameters['max_watt'],
                                                       self.device_parameters['version']))

        if self.device_parameters['type'] not in ('250-45', '350-60', '350-90', '500-90'):
            print('unsupported device type')
            self.device_parameters = False
            return False

        return True

    def stop(self):
        self.serial.close()

    def get_data(self):
        message = b"\x03\xED"
        response_bytes = self._read(message)

        if not response_bytes:
            return False
        elif len(response_bytes) < 37 or len(response_bytes) > 37:
            print("get_data: invalid length %s" % len(response_bytes))
            return False

        parts = struct.unpack('>3x I I I I I I I I 2x', response_bytes[:37])

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

        if data['pv_watt'] > self.device_parameters['max_watt'] * 2 or data['temperature'] > 1000:
            print('get_data: invalid data' % data)
            return False

        return data

    @staticmethod
    def _check_bits(in_hex, code_list):
        bits = bin(int(in_hex, 16))[2:]
        codes = []
        for bit in range(1, len(bits) + 1, 1):
            if int(bits[bit * -1]) == 1:
                codes.append(code_list[bit - 1])
        return codes

    def get_status(self):
        response_bytes = self._read(b"\x03\xF0")
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
            # print("error", bin(int(error, 16)))
            errors = self._check_bits(error, error_codes)
            data['errors'] = errors
        if disturb:
            # print("disturb", bin(int(disturb, 16)))
            disturbs = self._check_bits(disturb, disturb_codes)
            data['disturbances'] = disturbs

        return data

    def get_yield(self):
        response_bytes = self._read(b"\x03\xFD")
        if len(response_bytes) != 13:
            return False

        parts = struct.unpack('>3x I I', response_bytes[:11])
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
        response_bytes = self._read(message)
        response = response_bytes.hex()
        if not response:
            return False
        elif response == '212710370d':
            status = self.get_status()
            if 'POWER_LIMIT_SET' not in status['states']:
                print('POWER_LIMIT_SET not in status states')
                return False

            self.last_limit = limit
            return limit
        else:
            print('set_limit failed')
            return False


class AEConversionInverterThread(threading.Thread):
    def __init__(self, config):
        threading.Thread.__init__(self)
        self.is_running = False
        self.start_time = None
        self.connected = False
        self.data = {}
        self.command_queue = []
        self.inverter = AEConversionInverter(device=config['device'],
                                             inverter_id=config['inverter_id'])

    def stop(self):
        print('thread stopping...')
        self.is_running = False
        self.inverter.stop()

    def run(self):
        self.is_running = True
        self.start_time = time.time()
        self.connected = False
        while self.is_running:
            if not self.inverter.device_parameters:
                try:
                    self.inverter.connect()
                except Exception as e:
                    print('failed to connect')
                    print(e)
                    return False
                time.sleep(10)
                continue

            retry_queue = []
            while len(self.command_queue) > 0:
                command, value = self.command_queue.pop(0)
                if command == 'set_limit':
                    try:
                        self.inverter.set_limit(value)
                    except Exception as e:
                        print('set_limit failed')
                        print(e)
                        retry_queue.append((command, value))
            self.command_queue.extend(retry_queue)
            data = self.inverter.get_data()
            self.connected = True
            data['time'] = time.time()
            self.data = data

            time.sleep(5)
        print('thread stopped')
