"""ESC throttle control via a hardware-timed servo-style PWM pulse (pigpio)."""

try:
    import pigpio
except ImportError:
    pigpio = None


class ESC:
    def __init__(self, gpio_pin, min_us=1000, max_us=2000, arm_us=1000, frequency_hz=50):
        if pigpio is None:
            raise RuntimeError(
                "pigpio is not available. Run in mock mode unless this is "
                "actually a Raspberry Pi with pigpio installed and pigpiod running."
            )
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError(
                "Could not connect to pigpiod. Start it with: sudo systemctl start pigpiod"
            )
        self.pin = gpio_pin
        self.min_us = min_us
        self.max_us = max_us
        self.arm_us = arm_us
        self.frequency_hz = frequency_hz
        self.armed = False
        self.pi.set_PWM_frequency(self.pin, frequency_hz)
        self.pi.set_servo_pulsewidth(self.pin, 0)  # no signal until armed

    def _clamp(self, us):
        return max(self.min_us, min(self.max_us, us))

    def arm(self):
        self.pi.set_servo_pulsewidth(self.pin, self.arm_us)
        self.armed = True

    def disarm(self):
        self.pi.set_servo_pulsewidth(self.pin, 0)
        self.armed = False

    def set_throttle_us(self, us):
        if not self.armed:
            raise RuntimeError("ESC is not armed")
        us = self._clamp(us)
        self.pi.set_servo_pulsewidth(self.pin, us)
        return us

    def idle(self):
        """Fail-safe: command the armed idle pulse without disarming."""
        if self.armed:
            self.pi.set_servo_pulsewidth(self.pin, self.arm_us)

    def close(self):
        self.disarm()
        self.pi.stop()
