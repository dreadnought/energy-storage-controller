import wiringpi
import time

wiringpi.wiringPiSetup()


class Relay:
    def __init__(self, pin):
        self.pin = pin
        wiringpi.pinMode(pin, wiringpi.OUTPUT)
        self.last_off = 0.0

    def on(self):
        if time.time() - self.last_off < 60:
            print("Relay %s turned off %0.1f seconds ago, waiting" % (self.pin, time.time() - self.last_off))
            return
        wiringpi.digitalWrite(self.pin, 0)

    def off(self):
        wiringpi.digitalWrite(self.pin, 1)
        self.last_off = time.time()


if __name__ == '__main__':
    import time

    for x in range(1, 5):
        print('Relay', x)
        r = Relay(x)
        r.on()
        time.sleep(1)
        r.off()
