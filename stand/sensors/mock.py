"""Simulated stand for development and UI testing without real hardware.

Generates plausible thrust/torque/RPM/electrical curves as a function of the
commanded throttle, with a little noise, so the whole app can be exercised
end-to-end before it's ever plugged into the real stand.
"""
import random
import time


class MockStand:
    def __init__(self):
        self.throttle_frac = 0.0  # 0..1, settles toward commanded value
        self._target_frac = 0.0
        self._last_t = time.monotonic()

    def set_throttle_frac(self, frac):
        self._target_frac = max(0.0, min(1.0, frac))

    def _step(self):
        now = time.monotonic()
        dt = max(0.0, now - self._last_t)
        self._last_t = now
        # First-order lag so throttle changes look like a real motor spooling up/down.
        rate = 3.0  # 1/seconds
        self.throttle_frac += (self._target_frac - self.throttle_frac) * min(1.0, rate * dt)

    def read(self):
        self._step()
        t = self.throttle_frac
        jitter = lambda amp: random.uniform(-amp, amp)

        rpm = 12000.0 * t + jitter(40)
        thrust_g = 950.0 * (t ** 1.8) + jitter(3)
        torque_ncm = 6.5 * (t ** 1.6) + jitter(0.05)
        voltage = 16.8 - 1.3 * t + jitter(0.03)
        current = 0.2 + 24.0 * (t ** 1.7) + jitter(0.08)

        return {
            "thrust_g": max(0.0, thrust_g),
            "torque_Ncm": max(0.0, torque_ncm),
            "rpm": max(0.0, rpm),
            "voltage_V": max(0.0, voltage),
            "current_A": max(0.0, current),
        }
