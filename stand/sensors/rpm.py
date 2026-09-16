"""RPM measurement via GPIO edge counting (optical or hall-effect sensor)."""
import threading
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class RPMCounter:
    def __init__(self, gpio_pin, pulses_per_rev=1):
        if GPIO is None:
            raise RuntimeError(
                "RPi.GPIO is not available. Run in mock mode unless this is "
                "actually a Raspberry Pi with RPi.GPIO installed."
            )
        self.pin = gpio_pin
        self.pulses_per_rev = max(pulses_per_rev, 1)
        self._count = 0
        self._lock = threading.Lock()
        self._last_read = time.monotonic()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.pin, GPIO.FALLING, callback=self._on_pulse)

    def _on_pulse(self, _channel):
        with self._lock:
            self._count += 1

    def read_rpm(self):
        """Returns RPM averaged over the time since the last call."""
        now = time.monotonic()
        with self._lock:
            count = self._count
            self._count = 0
        dt = now - self._last_read
        self._last_read = now
        if dt <= 0:
            return 0.0
        revs = count / self.pulses_per_rev
        return (revs / dt) * 60.0

    def close(self):
        GPIO.remove_event_detect(self.pin)
