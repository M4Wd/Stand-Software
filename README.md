# Drone Test Stand

A self-hosted web dashboard for a DIY drone/prop test stand, running on a
Raspberry Pi. Same idea as the Tyto Robotics RCbenchmark software, but as a
lightweight Python/FastAPI app you run directly on the Pi wired to your own
stand's sensors: live thrust, torque, RPM, voltage, current, power and
efficiency, plus recorded test runs and automated throttle sweeps.

## Architecture

```
stand/sensors/    hardware drivers (HX711 load cells, RPM pulse counter, INA260) + mock simulator
stand/esc.py      ESC throttle control via pigpio servo PWM
stand/acquisition.py   background sampling loop, derived values, watchdog, pub/sub
stand/recorder.py      CSV logging of test runs + runs.json index
stand/sweep.py         automated throttle sweep runner
stand/server.py        FastAPI app: REST API + live websocket + serves web/
web/              browser dashboard (vanilla HTML/CSS/JS, no build step)
config.yaml       pin mapping, calibration, ESC limits, sweep defaults
```

Everything runs as a single process. The acquisition loop samples all
sensors at a fixed rate in a background thread (sensor drivers are blocking
GPIO/I2C calls), computes power and thrust-per-watt efficiency, and pushes
each sample out over a websocket to every connected browser tab. Recording a
test just means the same sample stream also gets written to a CSV file.

## Hardware wiring (mode: hardware)

Default GPIO pin assignments live in `config.yaml` — change them to match
your wiring, no code changes needed.

| Channel | Sensor | Interface | Config key |
|---|---|---|---|
| Thrust | load cell -> HX711 ADC | bit-banged 2-wire (DT/SCK) | `pins.thrust_hx711` |
| Torque | load cell -> HX711 ADC | bit-banged 2-wire (DT/SCK) | `pins.torque_hx711` |
| RPM | optical/hall pulse sensor | GPIO interrupt | `pins.rpm_gpio`, `rpm.pulses_per_rev` |
| Voltage/Current | INA260 | I2C (address 0x40 default) | `i2c` |
| Throttle out | ESC signal wire | hardware PWM via pigpio | `pins.esc_pwm_gpio` |

Notes:
- Each load cell needs its **own** HX711 breakout (two total: thrust,
  torque) since HX711 only has one input channel used at a time.
- `rpm.pulses_per_rev` is however many sensor pulses correspond to one
  full revolution of the prop/motor (e.g. 1 for a single reflective marker).
- The INA260 must be wired in series with the ESC's main power feed so it
  sees full motor current — check its current rating against your motor.
- The ESC signal wire's ground must be common with the Pi's ground.

### Safety

A test stand spins a real propeller. Software cannot replace a physical
kill switch:
- Wire a **hardware emergency stop** that cuts battery power to the ESC,
  independent of the Pi.
- The app includes a software watchdog (`watchdog_timeout_s` in
  `config.yaml`): if no throttle command is received for that long while
  armed, it automatically commands the ESC back to idle. This covers a
  dropped browser tab/network link, not a hung Pi.
- The dashboard's red **STOP** button immediately disarms and cancels any
  running sweep.
- Always run with the prop clear of people and loose objects, and remove
  the prop entirely while first testing calibration/wiring.

## Running in mock mode (no hardware needed)

Useful for developing/testing the dashboard on any machine before wiring
anything up. `config.yaml` defaults to `mode: mock`, which simulates a
plausible thrust/RPM/electrical response to throttle input.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Then open `http://localhost:8000`.

## Deploying on the Raspberry Pi

```bash
git clone <this-repo> drone-stand
cd drone-stand
bash scripts/install.sh
```

This enables I2C/SPI, installs `pigpiod` (needed for ESC PWM), creates a
virtualenv, and installs a `drone-stand` systemd service that starts the
app on boot. Once your wiring is connected, set `mode: hardware` in
`config.yaml` and `sudo systemctl restart drone-stand`. The dashboard is
then reachable from any device on the network at `http://<pi-ip>:8000`.

## Using the dashboard

1. **Calibrate** each load cell once: tare with no load, then place a known
   reference weight and enter its value (grams for thrust, N·cm for torque)
   to capture the calibration point. This is saved back into `config.yaml`.
2. **Arm**, then use the throttle slider for manual control, or run an
   **automated sweep** (min/max/step in microseconds, hold time per step) to
   auto-ramp through a throttle range — every sample during the sweep is
   logged automatically.
3. Start/stop a **manual recording** any time to log a free-form test run.
4. Past runs are listed at the bottom of the dashboard with a CSV download
   link, containing every sampled channel plus timestamp and throttle.

## REST API summary

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/status` | GET | mode, armed state, throttle, active sweep |
| `/api/live` | WS | live sample stream |
| `/api/tare` | POST | `{channel}` zero a load cell |
| `/api/calibrate` | POST | `{channel, known_value}` set scale from a reference load |
| `/api/arm` / `/api/disarm` | POST | ESC arm state |
| `/api/throttle` | POST | `{us}` manual throttle command |
| `/api/test/start` / `/api/test/stop` | POST | manual recording |
| `/api/sweep/start` / `/api/sweep/stop` | POST | automated throttle sweep |
| `/api/runs` | GET | list past runs |
| `/api/runs/{id}/download` | GET | CSV download |
