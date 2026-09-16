"""Calibrated load-cell channel built on top of a raw HX711 reading."""


class LoadCellChannel:
    def __init__(self, hx711, offset=0.0, scale=1.0):
        self.hx711 = hx711
        self.offset = offset
        self.scale = scale or 1.0

    def read_raw(self):
        return self.hx711.read_raw()

    def read(self):
        """Returns the calibrated physical value (grams for thrust, N*cm for torque)."""
        raw = self.hx711.read_raw()
        return (raw - self.offset) / self.scale

    def tare(self, samples=15):
        """Zeroes the channel at the current (unloaded) reading."""
        vals = [self.hx711.read_raw() for _ in range(samples)]
        self.offset = sum(vals) / len(vals)
        return self.offset

    def calibrate(self, known_value, samples=15):
        """Call with a known reference load (e.g. a calibration weight) applied.

        known_value must be in the same units the channel should report
        (grams for thrust, N*cm for torque).
        """
        if known_value == 0:
            raise ValueError("known_value must be non-zero")
        vals = [self.hx711.read_raw() for _ in range(samples)]
        raw_avg = sum(vals) / len(vals)
        self.scale = (raw_avg - self.offset) / known_value
        return self.scale
