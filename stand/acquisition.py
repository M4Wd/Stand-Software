"""Central acquisition engine: samples all sensors at a fixed rate, computes
derived quantities, optionally records to disk, and publishes each sample to
subscriber queues for the live websocket feed.

Runs its own background thread since the real sensor drivers (GPIO
bit-banging, I2C) are blocking calls.
"""
import asyncio
import threading
import time

from .esc import ESC
from .recorder import TestRecorder
from .sensors.hx711 import HX711
from .sensors.ina260 import INA260
from .sensors.load_cell import LoadCellChannel
from .sensors.mock import MockStand
from .sensors.rpm import RPMCounter

MIN_POWER_FOR_EFFICIENCY_W = 0.5


class AcquisitionEngine:
    def __init__(self, config):
        self.config = config
        self.mode = config["mode"]
        self.data_dir = config["data_dir"]
        self.sample_period = 1.0 / config["sample_rate_hz"]
        self.watchdog_timeout_s = config.get("watchdog_timeout_s", 2.0)

        self._subscribers = []
        self._sub_lock = threading.Lock()
        self._loop = None
        self._running = False
        self._thread = None

        self.latest = None
        self.recorder = None
        self.armed = False
        self.current_throttle_us = config["esc"]["arm_us"]
        self._last_command_ts = time.monotonic()

        self._init_hardware()

    def _init_hardware(self):
        if self.mode == "mock":
            self.mock = MockStand()
            return

        pins = self.config["pins"]
        cal = self.config["calibration"]

        thrust_hx = HX711(pins["thrust_hx711"]["dt"], pins["thrust_hx711"]["sck"])
        self.thrust_channel = LoadCellChannel(thrust_hx, **cal["thrust"])

        torque_hx = HX711(pins["torque_hx711"]["dt"], pins["torque_hx711"]["sck"])
        self.torque_channel = LoadCellChannel(torque_hx, **cal["torque"])

        self.rpm_counter = RPMCounter(pins["rpm_gpio"], self.config["rpm"]["pulses_per_rev"])

        i2c = self.config["i2c"]
        self.power_sensor = INA260(i2c["bus"], i2c["ina260_address"])

        self.esc = ESC(pins["esc_pwm_gpio"], **self.config["esc"])

    # -- lifecycle -----------------------------------------------------

    def attach_loop(self, loop):
        self._loop = loop

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.mode != "mock":
            if self.recorder:
                self.recorder.close()
                self.recorder = None
            self.esc.close()
            self.rpm_counter.close()

    # -- pub/sub for the live websocket ---------------------------------

    def subscribe(self):
        q = asyncio.Queue(maxsize=50)
        with self._sub_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._sub_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _publish(self, sample):
        if self._loop is None:
            return
        with self._sub_lock:
            subs = list(self._subscribers)
        for q in subs:
            self._loop.call_soon_threadsafe(self._put_nowait, q, sample)

    @staticmethod
    def _put_nowait(q, sample):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        q.put_nowait(sample)

    # -- throttle / arming ------------------------------------------------

    def arm(self):
        if self.mode != "mock":
            self.esc.arm()
        self.armed = True
        self._last_command_ts = time.monotonic()

    def disarm(self):
        if self.mode != "mock":
            self.esc.disarm()
        else:
            self.mock.set_throttle_frac(0.0)
        self.armed = False
        self.current_throttle_us = self.config["esc"]["arm_us"]

    def set_throttle_us(self, us):
        if not self.armed:
            raise RuntimeError("not armed")
        self._last_command_ts = time.monotonic()
        if self.mode == "mock":
            lo, hi = self.config["esc"]["min_us"], self.config["esc"]["max_us"]
            us = max(lo, min(hi, us))
            frac = (us - lo) / (hi - lo) if hi > lo else 0.0
            self.mock.set_throttle_frac(frac)
            self.current_throttle_us = us
        else:
            self.current_throttle_us = self.esc.set_throttle_us(us)
        return self.current_throttle_us

    def _watchdog_check(self):
        if not self.armed:
            return
        idle = time.monotonic() - self._last_command_ts > self.watchdog_timeout_s
        if idle and self.current_throttle_us != self.config["esc"]["arm_us"]:
            arm_us = self.config["esc"]["arm_us"]
            if self.mode == "mock":
                self.mock.set_throttle_frac(0.0)
            else:
                self.esc.idle()
            self.current_throttle_us = arm_us

    # -- test recording ---------------------------------------------------

    def start_recording(self, name):
        if self.recorder:
            raise RuntimeError("a recording is already in progress")
        self.recorder = TestRecorder(self.data_dir, name)
        return self.recorder.id

    def stop_recording(self):
        if not self.recorder:
            return None
        run_id = self.recorder.id
        self.recorder.close()
        self.recorder = None
        return run_id

    # -- sampling loop ------------------------------------------------------

    def _read_all(self):
        if self.mode == "mock":
            data = self.mock.read()
        else:
            data = {
                "thrust_g": self.thrust_channel.read(),
                "torque_Ncm": self.torque_channel.read(),
                "rpm": self.rpm_counter.read_rpm(),
            }
            voltage, current = self.power_sensor.read()
            data["voltage_V"] = voltage
            data["current_A"] = current

        power_w = data["voltage_V"] * data["current_A"]
        data["power_W"] = power_w
        data["efficiency_g_per_W"] = (
            data["thrust_g"] / power_w if power_w > MIN_POWER_FOR_EFFICIENCY_W else 0.0
        )
        data["throttle_us"] = self.current_throttle_us
        data["armed"] = self.armed
        data["t"] = time.time()
        return data

    def _run(self):
        next_t = time.monotonic()
        while self._running:
            self._watchdog_check()
            sample = self._read_all()
            self.latest = sample
            if self.recorder:
                self.recorder.write(sample)
            self._publish(sample)

            next_t += self.sample_period
            sleep_for = next_t - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_t = time.monotonic()
