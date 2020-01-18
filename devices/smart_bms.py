#!/usr/bin/python3
import serial
import struct
import time
import threading
import gatt
import sys

from metrics import Metrics


class SmartBMS:
    BASE_REQUEST = 'DDA50%i00FFF%s77'
    BASE_RESPONSE = 'DD0%i'
    REQUESTS = {
        'status': [3, 'D'],
        'cell_voltages': [4, 'C']
    }

    def __init__(self, device):
        self.serial = None
        self.device = device
        self.status = None

    def connect(self, verbose=True):
        self.serial = serial.Serial(
            port=self.device,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            xonxoff=False,
            writeTimeout=2
        )

    def disconnect(self):
        self.serial.close()

    @staticmethod
    def format_request(name):
        i, c = SmartBMS.REQUESTS[name]
        return bytes.fromhex(SmartBMS.BASE_REQUEST % (i, c))

    @staticmethod
    def response_name(response_bytes):
        response_num = response_bytes[1]
        response_name = None
        for name, num in SmartBMS.REQUESTS.items():
            if num[0] == response_num:
                response_name = name
                break

        return response_name

    def send_command(self, command):
        command = self.format_request(command)
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        # print('writing')
        if not self.serial.write(command):
            print("failed")
            return False

        header = self.serial.read(4)
        if header[0:2] != b'\xdd' + command[2:3]:
            print('invalid header received', header)
            return False
        length = struct.unpack('>H', header[2:4])
        length = length[0]

        response_bytes = self.serial.read(length)
        if len(response_bytes) != length:
            print("invalid response length (got %s, expected %s)" % (len(response_bytes), length))
            return False

        while True:
            b = self.serial.read(1)
            if b == b'\x77':
                # print("end of response found")
                break

        return response_bytes

    def get_status(self):
        response_bytes = self.send_command('status')
        data = self.parse_status_response(response_bytes)

    def parse_status_response(self, response_bytes):
        if response_bytes is False:
            return False

        if len(response_bytes) < 14:
            # print('invalid length %i' % len(response_bytes))
            return False

        parts = struct.unpack('>H h H H H H H H H c c c c', response_bytes[0:22])
        # print(parts)

        # todo: decode the remaining values
        software_version = parts[9].hex()
        data = {
            'total_voltage': parts[0] / 100,
            'current': parts[1] / 100,
            # 'remaining_capacity': parts[2] / 100,
            # 'typical_capacity': parts[3] / 100,
            # 'cycle_times': parts[4],
            # 'production_date': parts[5],
            # 'balance_status': parts[6],
            # 'balance_status_high': parts[7],
            # 'protection_status': parts[8],
            'software_version': "%s.%s" % (software_version[0], software_version[1]),
            # 'rsoc': ord(parts[10]),
            # 'fet_status': parts[11],
            'batteries': ord(parts[12]),
        }
        self.status = data
        return data

    def get_cell_voltages(self):
        response = self.send_command('cell_voltages')
        if response is False:
            print('failed to get voltages')
            return
        return self.parse_cell_voltages(response)

    def parse_cell_voltages(self, response_bytes):
        num_cells = int(len(response_bytes) / 2)
        # print(len(response_bytes), '->', num_cells)
        cells = ['H' for cell in range(0, num_cells)]

        parts = struct.unpack('>%s' % (' '.join(cells)), response_bytes)
        x = 1
        voltages = {}
        for part in parts:
            # print("Cell %i has %s mV" % (x, part))
            voltages[x] = part / 1000
            x += 1

        if self.status and self.status['batteries'] != len(voltages):
            print('number of cell voltages not matching number of cells (%s vs. %s)' % (
            len(voltages), self.status['batteries']))

        return voltages


class AnyDevice(gatt.Device):
    def connect_succeeded(self):
        super().connect_succeeded()
        print("[%s] Connected" % (self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)
        print("[%s] Connection failed: %s" % (self.mac_address, str(error)))

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        # self.is_disconnected = True
        print("[%s] Disconnected" % (self.mac_address))
        self.connect()

    def services_resolved(self):
        super().services_resolved()
        self.response_queue = []

        print("[%s] Resolved services" % (self.mac_address))
        for service in self.services:
            if not service.uuid.startswith("0000ff00"):
                continue
            print("[%s]  Service [%s]" % (self.mac_address, service.uuid))
            for characteristic in service.characteristics:
                if characteristic.uuid.startswith("0000ff01"):
                    self.c_read = characteristic
                    characteristic.enable_notifications()
                elif characteristic.uuid.startswith("0000ff02"):
                    self.c_write = characteristic
                else:
                    continue
                print("[%s]    Characteristic [%s]" % (self.mac_address, characteristic.uuid))

        print(self.c_read, "\n", self.c_write)

    def characteristic_write_value_succeeded(self, characteristic):
        # print("write succeeded")
        # self.c_read.read_value()
        pass

    def characteristic_write_value_failed(self, characteristic, error):
        print("write failed", error)

    def characteristic_value_updated(self, characteristic, value):
        # print("value:", len(value), repr(value))
        self.response_queue.append([time.time(), value])


class BluetoothThread(threading.Thread):
    def __init__(self, mac_address):
        threading.Thread.__init__(self)
        self.is_running = False
        self.mac_address = mac_address

    def run(self):
        self.is_running = True
        self.manager = gatt.DeviceManager(adapter_name='hci0')
        self.device = AnyDevice(mac_address=self.mac_address, manager=self.manager)
        # self.is_disconnected = False
        self.device.connect()
        try:
            self.manager.run()
        except KeyboardInterrupt:
            print('interrupt')
            self.manager.stop()
        self.is_running = False
        print('BluetoothThread: stopped')

    def write(self, request_bytes):
        self.device.c_write.write_value(request_bytes)


class SmartBMSThread(threading.Thread):
    def __init__(self, mac_address, metrics):
        threading.Thread.__init__(self)
        self.is_running = False
        self.mac_address = mac_address
        self.metrics = metrics
        self.data = {'status': None, 'cell_voltages': None}
        self.last_run_completed = None

    def init_bt_thread(self):
        self.bt_thread = BluetoothThread(mac_address=self.mac_address)
        self.bt_thread.start()

    def run(self):
        self.is_running = True
        self.init_bt_thread()
        time.sleep(1)

        smart_bms = SmartBMS(device=None)
        incomplete = None

        while self.is_running and self.bt_thread.is_running:
            print('==== start of run ====', flush=True)
            updated_data = []
            if not self.bt_thread.device.is_connected():
                print('not connected')
                time.sleep(5)
                continue
            # print('status')
            self.bt_thread.write(smart_bms.format_request('status'))
            time.sleep(0.5)
            # print('cells')
            self.bt_thread.write(smart_bms.format_request('cell_voltages'))
            time.sleep(1)

            while len(self.bt_thread.device.response_queue) > 0:
                ts, response_bytes = self.bt_thread.device.response_queue.pop(0)
                if response_bytes[-1:] != b'\x77':
                    incomplete = response_bytes
                    # print('incomplete')
                    # print(repr(response_bytes[-1:]))

                    continue
                if incomplete:
                    response_bytes = incomplete + response_bytes
                    incomplete = None
                    # print('completed')
                # print(len(response_bytes), repr(response_bytes))
                name = smart_bms.response_name(response_bytes)
                # print(name)
                if not name:
                    continue
                # cut head and end marker
                response_bytes = response_bytes[4:-3]
                if name == 'status':
                    status = smart_bms.parse_status_response(response_bytes)
                    status['time'] = ts
                    self.data[name] = status
                    updated_data.append(name)
                elif name == 'cell_voltages':
                    cell_voltages = smart_bms.parse_cell_voltages(response_bytes)
                    cell_voltages['time'] = ts
                    self.data[name] = cell_voltages
                    updated_data.append(name)

            if updated_data:
                for name in updated_data:
                    points = []
                    data_copy = self.data[name].copy()
                    ts = data_copy['time']
                    del data_copy['time']
                    if name == 'status':
                        points.append({
                            "measurement": "SmartBMS%s" % name.replace('_', '').capitalize(),
                            "tags": {
                                "mac_address": self.mac_address,
                            },
                            "time": ts,
                            "fields": data_copy,
                        })
                    elif name == 'cell_voltages':
                        for cell, voltage in data_copy.items():
                            if cell == 'time':
                                continue
                            points.append({
                                "measurement": "SmartBMSCellVoltages",
                                "tags": {
                                    "mac_address": self.mac_address,
                                    "cell": cell,
                                },
                                "time": ts,
                                "fields": {'voltage': voltage},
                            })
                    self.metrics.write_metric(points=points)

            print('==== end of run ====', flush=True)
            self.last_run_completed = time.time()
            time.sleep(15)
        print('SmartBMSThread: stopped')
        self.is_running = False

    def stop(self):
        print('SmartBMSThread: stopping')
        self.is_running = False
        self.bt_thread.manager.stop()


