"""Bit-banged driver for the HX711 24-bit ADC used with strain-gauge load cells.

Two of these run on the stand: one for the thrust load cell, one for the
torque load cell. Each needs its own DT (data) / SCK (clock) GPIO pair.
"""
import threading
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

# Gain/channel select is encoded as extra clock pulses after the 24 data bits:
# 1 pulse -> channel A, gain 128 (default, what load cells use)
# 2 pulses -> channel B, gain 32
# 3 pulses -> channel A, gain 64
_GAIN_PULSES = {128: 1, 64: 3, 32: 2}


class HX711:
    def __init__(self, dt_pin, sck_pin, gain=128):
        if GPIO is None:
            raise RuntimeError(
                "RPi.GPIO is not available. Run in mock mode unless this is "
                "actually a Raspberry Pi with RPi.GPIO installed."
            )
        if gain not in _GAIN_PULSES:
            raise ValueError(f"unsupported gain {gain}, must be one of {list(_GAIN_PULSES)}")
        self.dt = dt_pin
        self.sck = sck_pin
        self._gain_pulses = _GAIN_PULSES[gain]
        self._lock = threading.Lock()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.dt, GPIO.IN)
        GPIO.setup(self.sck, GPIO.OUT)
        GPIO.output(self.sck, False)

    def _ready(self):
        return GPIO.input(self.dt) == 0

    def read_raw(self, timeout=0.5):
        """Blocks until the chip has a sample ready, then shifts out 24 bits."""
        with self._lock:
            start = time.monotonic()
            while not self._ready():
                if time.monotonic() - start > timeout:
                    raise TimeoutError(f"HX711 on GPIO{self.dt}/{self.sck} not ready")
                time.sleep(0.0005)

            count = 0
            for _ in range(24):
                GPIO.output(self.sck, True)
                count = (count << 1) | GPIO.input(self.dt)
                GPIO.output(self.sck, False)

            # Extra pulses select gain/channel for the *next* conversion.
            for _ in range(self._gain_pulses):
                GPIO.output(self.sck, True)
                GPIO.output(self.sck, False)

            if count & 0x800000:  # sign-extend 24-bit two's complement
                count -= 1 << 24
            return count
