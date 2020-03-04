import subprocess
import sys

BASE_DIR = "/sys/devices/pwm-ctrl"
BASE_VOLTAGE = 3.2
BASE_FACTOR = 1024


class PWM():
    def __init__(self, logger):
        self.load_modules()
        self.pwm_init()
        self.logger = logger

    def load_modules(self):
        modules_required = ('pwm-meson', 'pwm-ctrl')

        for module in modules_required:
            subprocess.call(['modprobe', module])

        modules_found = []
        with open('/proc/modules', 'r') as f:
            for line in f.readlines():
                if line.startswith("pwm_"):
                    modules_found.append(line.split(" ", 1)[0])

        for module in modules_required:
            if module.replace('-', '_') not in modules_found:
                self.logger.error("Module %s not loaded" % module)
                sys.exit(1)

    def pwm_init(self):
        with open("%s/freq0" % BASE_DIR, 'w') as f:
            f.write("100000\n")

        with open("%s/enable0" % BASE_DIR, 'w') as f:
            f.write("1\n")

    def set_pwm_volt(self, volt):
        duty = BASE_FACTOR / BASE_VOLTAGE * volt
        self.logger.debug("%s Volt (%s)" % (volt, duty))

        with open("%s/duty0" % BASE_DIR, 'w') as f:
            f.write("%s\n" % duty)

    def get_pwm_volt(self):
        with open("%s/duty0" % BASE_DIR, 'r') as f:
            l = f.readline()
        duty = int(l)
        volt = round(BASE_VOLTAGE / BASE_FACTOR * duty, 2)

        return volt
