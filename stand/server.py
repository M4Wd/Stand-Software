import asyncio
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import recorder
from .acquisition import AcquisitionEngine
from .config import load_config, save_config
from .sweep import SweepRunner

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB_DIR = os.path.join(_REPO_ROOT, "web")

app = FastAPI(title="Drone Test Stand")

config = load_config()
engine = AcquisitionEngine(config)
sweep = SweepRunner(engine)


@app.on_event("startup")
async def on_startup():
    engine.attach_loop(asyncio.get_running_loop())
    engine.start()


@app.on_event("shutdown")
async def on_shutdown():
    engine.stop()


# ---------------------------------------------------------------- schemas

class TareRequest(BaseModel):
    channel: str  # "thrust" | "torque"


class CalibrateRequest(BaseModel):
    channel: str
    known_value: float


class ThrottleRequest(BaseModel):
    us: int


class TestStartRequest(BaseModel):
    name: str = "test"


class SweepStartRequest(BaseModel):
    min_us: int
    max_us: int
    step_us: int
    hold_s: float
    name: str = "sweep"


def _require_hardware():
    if engine.mode == "mock":
        raise HTTPException(400, "not applicable in mock mode")


def _channel(name):
    if name == "thrust":
        return engine.thrust_channel
    if name == "torque":
        return engine.torque_channel
    raise HTTPException(400, f"unknown channel '{name}'")


# ---------------------------------------------------------------- status

@app.get("/api/status")
def get_status():
    return {
        "mode": engine.mode,
        "armed": engine.armed,
        "throttle_us": engine.current_throttle_us,
        "recording": engine.recorder.id if engine.recorder else None,
        "sweep_active": sweep.active,
        "sweep_status": sweep.status,
        "esc": config["esc"],
    }


@app.get("/api/config")
def get_config():
    return config


# ---------------------------------------------------------------- calibration

@app.post("/api/tare")
def tare(req: TareRequest):
    _require_hardware()
    channel = _channel(req.channel)
    offset = channel.tare()
    config["calibration"][req.channel]["offset"] = offset
    save_config(config)
    return {"channel": req.channel, "offset": offset}


@app.post("/api/calibrate")
def calibrate(req: CalibrateRequest):
    _require_hardware()
    channel = _channel(req.channel)
    scale = channel.calibrate(req.known_value)
    config["calibration"][req.channel]["scale"] = scale
    save_config(config)
    return {"channel": req.channel, "scale": scale}


# ---------------------------------------------------------------- throttle

@app.post("/api/arm")
def arm():
    if sweep.active:
        raise HTTPException(400, "cannot arm manually while a sweep is running")
    engine.arm()
    return {"armed": True}


@app.post("/api/disarm")
def disarm():
    if sweep.active:
        raise HTTPException(400, "stop the sweep first")
    engine.disarm()
    return {"armed": False}


@app.post("/api/throttle")
def set_throttle(req: ThrottleRequest):
    if sweep.active:
        raise HTTPException(400, "throttle is controlled by the active sweep")
    if not engine.armed:
        raise HTTPException(400, "not armed")
    us = engine.set_throttle_us(req.us)
    return {"throttle_us": us}


# ---------------------------------------------------------------- test recording

@app.post("/api/test/start")
def test_start(req: TestStartRequest):
    if sweep.active:
        raise HTTPException(400, "a sweep is already running")
    try:
        run_id = engine.start_recording(req.name)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"run_id": run_id}


@app.post("/api/test/stop")
def test_stop():
    run_id = engine.stop_recording()
    return {"run_id": run_id}


# ---------------------------------------------------------------- sweep

@app.post("/api/sweep/start")
def sweep_start(req: SweepStartRequest):
    try:
        sweep.start(req.min_us, req.max_us, req.step_us, req.hold_s, req.name)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"started": True}


@app.post("/api/sweep/stop")
def sweep_stop():
    sweep.stop()
    return {"stopping": True}


# ---------------------------------------------------------------- runs

@app.get("/api/runs")
def list_runs():
    return recorder.list_runs(config["data_dir"])


@app.get("/api/runs/{run_id}/download")
def download_run(run_id: str):
    run = recorder.get_run(config["data_dir"], run_id)
    if not run:
        raise HTTPException(404, "run not found")
    path = os.path.join(config["data_dir"], run["file"])
    return FileResponse(path, media_type="text/csv", filename=run["file"])


# ---------------------------------------------------------------- live websocket

@app.websocket("/api/live")
async def live(ws: WebSocket):
    await ws.accept()
    q = engine.subscribe()
    try:
        if engine.latest:
            await ws.send_json(engine.latest)
        while True:
            sample = await q.get()
            await ws.send_json(sample)
    except WebSocketDisconnect:
        pass
    finally:
        engine.unsubscribe(q)


# ---------------------------------------------------------------- static frontend

app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
