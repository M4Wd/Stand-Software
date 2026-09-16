"""Minimal I2C driver for the TI INA260 voltage/current/power sensor.

Written directly against the register map (no Adafruit/CircuitPython
dependency) to keep the hardware footprint small:
  0x01 Current   register, 1.25 mA/LSB, signed 16-bit
  0x02 BusVoltage register, 1.25 mV/LSB, unsigned 16-bit
"""

try:
    import smbus2
except ImportError:
    smbus2 = None

_REG_CURRENT = 0x01
_REG_VOLTAGE = 0x02

_CURRENT_LSB = 1.25e-3  # amps
_VOLTAGE_LSB = 1.25e-3  # volts


class INA260:
    def __init__(self, bus=1, address=0x40):
        if smbus2 is None:
            raise RuntimeError(
                "smbus2 is not available. Run in mock mode unless this is "
                "actually a Raspberry Pi with smbus2 installed."
            )
        self.bus = smbus2.SMBus(bus)
        self.address = address

    def _read_reg_u16(self, reg):
        data = self.bus.read_i2c_block_data(self.address, reg, 2)
        return (data[0] << 8) | data[1]

    def read_voltage(self):
        return self._read_reg_u16(_REG_VOLTAGE) * _VOLTAGE_LSB

    def read_current(self):
        raw = self._read_reg_u16(_REG_CURRENT)
        if raw & 0x8000:
            raw -= 1 << 16
        return raw * _CURRENT_LSB

    def read(self):
        """Returns (voltage_V, current_A)."""
        return self.read_voltage(), self.read_current()
