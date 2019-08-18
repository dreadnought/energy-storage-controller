import socket
import struct
import threading
import time


class SMAEnergyManager:
    def __init__(self):
        self.sock = None
        self.connect()

    def connect(self):
        if self.sock:
            self.sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', 9522))
        multicast_request = struct.pack("4sl", socket.inet_aton('239.12.255.254'), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, multicast_request)
        self.sock = sock

    def parse_block_bytes(self, block_bytes, counter=False):
        block_data = {}
        result = struct.unpack('>I 4x Q 4x I 4x Q 4x L 4x Q 4x I 4x Q 4x I 4x Q 4x I 4x Q', block_bytes[:116])

        x = 0
        for key in ('p_import', 'p_export', 'q_import', 'q_export', 's_import', 's_export'):
            block_data[key] = result[x] / 10
            if counter:
                block_data['%s_counter' % key] = result[x + 1] / 3600000
            x += 2

        pos = 120
        if len(block_bytes) == 140:
            result = struct.unpack('>I 4x I', block_bytes[pos:pos + 12])
            block_data['thd'] = result[0] / 1000
            block_data['v'] = result[1] / 1000
            pos += 16

        block_data['cos_phi'] = struct.unpack('>I', block_bytes[pos:pos + 4])[0] / 1000

        return block_data

    def read(self, phases, counter=False):
        message_bytes = self.sock.recv(600)
        serial_number = struct.unpack('>I', message_bytes[20:24])[0]

        data = {}
        data['time'] = time.time()
        data['sum'] = self.parse_block_bytes(message_bytes[32:156], counter=counter)
        if phases:
            data['L1'] = self.parse_block_bytes(message_bytes[160:300], counter=counter)
            data['L2'] = self.parse_block_bytes(message_bytes[304:444], counter=counter)
            data['L3'] = self.parse_block_bytes(message_bytes[448:588], counter=counter)
            return serial_number, data
        else:
            data['sum']['time'] = data['time']
            return serial_number, data['sum']

    def stop(self):
        self.sock.close()
        print('socket closed')


class SMAEnergyManagerThread(threading.Thread):
    def __init__(self, serial_number):
        threading.Thread.__init__(self)
        self.is_running = False
        self.smaem = SMAEnergyManager()
        self.data = {}
        self.start_time = None
        if serial_number:
            self.serial_number = serial_number
        else:
            self.serial_number = None

    def stop(self):
        print('SMAEnergyManagerThread stopping...')
        self.is_running = False
        self.smaem.stop()

    def run(self):
        self.is_running = True
        self.start_time = time.time()
        while self.is_running:
            serial_number, data = self.smaem.read(phases=False)
            if self.serial_number:
                self.data = data
            else:
                self.data[serial_number] = data
        print('SMAEnergyManagerThread stopped')

    def is_healthy(self):
        if not self.is_running:
            return False
        if len(self.data) == 0:
            return False
        t_diff = time.time() - self.data['time']
        if t_diff > 120.0:
            print('SMAEnergyManagerThread: no data for %s seconds' % int(time.time() - self.data['time']))
            return False
        elif t_diff > 60.0:
            print('SMAEnergyManagerThread: reconnecting')
            self.smaem.connect()
            return False

        return True

if __name__ == '__main__':
    from pprint import pprint

    smaem_thread = SMAEnergyManagerThread(serial_number=None)
    smaem_thread.start()
    while True:
        pprint(smaem_thread.data)
        time.sleep(2)
