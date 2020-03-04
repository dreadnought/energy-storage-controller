import sys
import os

BASE_DIR = "/sys/class/gpio"


class GpioPin:
    def __init__(self, pin):
        self.pin = pin
        self.pin_dir = "%s/gpio%i" % (BASE_DIR, pin)
        if not os.path.isdir(self.pin_dir):
            with open("%s/export" % BASE_DIR, 'w') as f:
                f.write("%i\n" % pin)
        with open("%s/direction" % self.pin_dir, 'w') as f:
            f.write("out\n")

    def get_state(self):
        with open("%s/value" % self.pin_dir, 'r') as f:
            value = f.readline()
        return int(value)

    def set_state(self, state):
        with open("%s/value" % self.pin_dir, 'w') as f:
            f.write("%s\n" % int(state))

if __name__ == '__main__':
    import time
    pin = int(sys.argv[1])
    relais = GpioPin(pin=pin)
    print(relais.get_state())
    for state in (True, False, True, False):
        relais.set_state(state)
        print(relais.get_state())
        time.sleep(2)