import sys
import os

# edit /boot/hw_intfc.conf
# set intfc:pwm2=on
BASE_DIR = "/sys/class/pwm/pwmchip1/pwm0/"
BASE_VOLTAGE = 3.33
BASE_FACTOR = 98140


class PWM():
    def __init__(self, logger):
        self.pwm_init()
        self.logger = logger

    def pwm_init(self):
        if not os.path.isdir(BASE_DIR):
            with open("/sys/class/pwm/pwmchip1/export", 'w') as f:
                f.write("0\n")
        with open("%s/period" % BASE_DIR, 'w') as f:
            f.write("100000\n")

        with open("%s/enable" % BASE_DIR, 'w') as f:
            f.write("1\n")

        with open("%s/polarity" % BASE_DIR, 'w') as f:
            f.write("normal\n")

    def set_pwm_volt(self, volt):
        if volt > BASE_VOLTAGE:
            self.logger.error("Voltage %s > %s, setting to maximum" % (volt, BASE_VOLTAGE))
            volt = BASE_VOLTAGE
        duty = BASE_FACTOR / BASE_VOLTAGE * volt
        self.logger.debug("%s Volt (%s)" % (volt, duty))

        with open("%s/duty_cycle" % BASE_DIR, 'w') as f:
            f.write("%i\n" % duty)

    def get_pwm_volt(self):
        with open("%s/duty_cycle" % BASE_DIR, 'r') as f:
            l = f.readline()
        duty = int(l)
        volt = round(BASE_VOLTAGE / BASE_FACTOR * duty, 2)

        return volt


if __name__ == '__main__':
    import logging

    pwm = PWM(logger=logging)
    pwm.pwm_init()
    pwm.set_pwm_volt(float(sys.argv[1]))
    volt = pwm.get_pwm_volt()
    print(pwm.get_pwm_volt())
