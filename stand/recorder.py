"""CSV logging of test runs plus a simple JSON index of past runs."""
import csv
import json
import os
import re
import time

FIELDS = [
    "t",
    "throttle_us",
    "thrust_g",
    "torque_Ncm",
    "rpm",
    "voltage_V",
    "current_A",
    "power_W",
    "efficiency_g_per_W",
]

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize(name):
    name = _SAFE_NAME.sub("_", name.strip()) or "run"
    return name[:60]


class TestRecorder:
    def __init__(self, data_dir, name):
        self.name = _sanitize(name)
        self.start_time = time.time()
        self.id = time.strftime("%Y%m%d-%H%M%S")
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.filename = f"{self.id}_{self.name}.csv"
        self.path = os.path.join(data_dir, self.filename)
        self._file = open(self.path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        self._writer.writeheader()
        self.sample_count = 0

    def write(self, sample):
        self._writer.writerow({k: sample.get(k) for k in FIELDS})
        self.sample_count += 1
        if self.sample_count % 20 == 0:
            self._file.flush()

    def close(self):
        self._file.flush()
        self._file.close()
        _append_index(self)


def _index_path(data_dir):
    return os.path.join(data_dir, "runs.json")


def _append_index(recorder):
    path = _index_path(recorder.data_dir)
    runs = []
    if os.path.exists(path):
        with open(path) as f:
            runs = json.load(f)
    runs.append(
        {
            "id": recorder.id,
            "name": recorder.name,
            "file": recorder.filename,
            "start_time": recorder.start_time,
            "duration_s": round(time.time() - recorder.start_time, 2),
            "sample_count": recorder.sample_count,
        }
    )
    with open(path, "w") as f:
        json.dump(runs, f, indent=2)


def list_runs(data_dir):
    path = _index_path(data_dir)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        runs = json.load(f)
    return sorted(runs, key=lambda r: r["start_time"], reverse=True)


def get_run(data_dir, run_id):
    for run in list_runs(data_dir):
        if run["id"] == run_id:
            return run
    return None
