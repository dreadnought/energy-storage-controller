import socket
import struct
import threading
import time


class SMAEnergyManager:
    def __init__(self, logger):
        self.sock = None
        self.logger = logger

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
        if len(block_bytes) < 116:
            self.logger.warning("response length %i < 116 bytes, counter=%i" % (len(block_bytes), counter))
            return
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
        message_bytes = self.sock.recv(608)
        serial_number = struct.unpack('>I', message_bytes[20:24])[0]

        if len(message_bytes) == 58:
            return False, False
        elif len(message_bytes) < 558:
            self.logger.warning("response length %i < 558 bytes, phases=%s, counter=%s" % (len(message_bytes), phases, counter))
            return False, False

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
        if self.sock:
            self.sock.close()
            self.logger.info('SMAEnergyManager: socket closed')
            self.sock = None


class SMAEnergyManagerThread(threading.Thread):
    def __init__(self, serial_number, metrics, logger):
        threading.Thread.__init__(self)
        self.is_running = False
        self.logger = logger
        self.smaem = SMAEnergyManager(logger=logger)
        self.data = {}
        self.start_time = None
        if serial_number:
            self.serial_number = serial_number
        else:
            self.serial_number = None
        self.metrics = metrics
        self.last_metrics = 0

    def stop(self):
        self.logger.info('SMAEnergyManagerThread stopping...')
        self.is_running = False
        self.smaem.stop()

    def run(self):
        self.is_running = True
        self.start_time = time.time()
        self.smaem.connect()
        while self.is_running:
            serial_number, data = self.smaem.read(phases=False)
            if data is False:
                continue
            if self.serial_number:
                self.data = data
                points = []
                data_copy = data.copy()
                ts = data_copy['time']
                del data_copy['time']
                points.append({
                    "measurement": "SMAEnergyManagerSum",
                    "tags": {
                        "serial_number": self.serial_number,
                    },
                    "time": ts,
                    "fields": data_copy,
                })
                if time.time() - self.last_metrics > 5 and self.metrics:
                    self.metrics.write_metric(points=points)
                    self.last_metrics = time.time()
            else:
                self.data[serial_number] = data
        self.logger.info('SMAEnergyManagerThread stopped')

    def is_healthy(self):
        if not self.is_running:
            return False
        if len(self.data) == 0:
            return False
        t_diff = time.time() - self.data['time']
        if t_diff > 120.0:
            self.logger.warning('SMAEnergyManagerThread: no data for %s seconds' % int(time.time() - self.data['time']))
            return False
        elif t_diff > 60.0:
            self.logger.warning('SMAEnergyManagerThread: reconnecting')
            self.smaem.connect()
            return False

        return True


if __name__ == '__main__':
    from pprint import pprint
    from logger import get_logger
    logger = get_logger(level='info')

    smaem_thread = SMAEnergyManagerThread(serial_number=None, logger=logger, metrics=None)
    smaem_thread.start()
    while True:
        pprint(smaem_thread.data)
        time.sleep(2)
