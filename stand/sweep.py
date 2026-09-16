"""Automated throttle sweep: ramps the ESC through a range of pulse widths,
holding at each step, while the acquisition engine's normal recorder logs
every sample. This mirrors the "Dynamic/Auto Test" mode on commercial
thrust stands.
"""
import threading
import time


class SweepRunner:
    def __init__(self, engine):
        self.engine = engine
        self._thread = None
        self._stop_flag = threading.Event()
        self.active = False
        self.status = {}

    def start(self, min_us, max_us, step_us, hold_s, name=None):
        if self.active:
            raise RuntimeError("a sweep is already running")
        if self.engine.recorder:
            raise RuntimeError("a manual recording is already in progress")
        if step_us <= 0 or max_us < min_us:
            raise ValueError("invalid sweep range")

        self._stop_flag.clear()
        self.active = True
        self._thread = threading.Thread(
            target=self._run,
            args=(min_us, max_us, step_us, hold_s, name or "sweep"),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_flag.set()

    def _run(self, min_us, max_us, step_us, hold_s, name):
        steps = list(range(min_us, max_us + 1, step_us))
        if steps[-1] != max_us:
            steps.append(max_us)

        run_id = self.engine.start_recording(name)
        try:
            self.engine.arm()
            for i, us in enumerate(steps):
                if self._stop_flag.is_set():
                    break
                self.status = {"step": i + 1, "total": len(steps), "throttle_us": us, "run_id": run_id}
                self.engine.set_throttle_us(us)
                time.sleep(hold_s)
            self.engine.set_throttle_us(min_us)
            time.sleep(1.0)
        finally:
            self.engine.disarm()
            self.engine.stop_recording()
            self.active = False
            self.status = {}
