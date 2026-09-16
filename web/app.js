"use strict";

// ---------------------------------------------------------------- helpers

function fmt(v, digits = 1) {
  if (v === undefined || v === null || Number.isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

function showMsg(el, text, kind) {
  el.textContent = text;
  el.className = "msg" + (kind ? " " + kind : "");
}

// ---------------------------------------------------------------- strip chart

class StripChart {
  constructor(canvas, series, windowSec = 30) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.series = series; // { key: color }
    this.windowSec = windowSec;
    this.data = {};
    for (const k in series) this.data[k] = [];
    this._resize();
    window.addEventListener("resize", () => this._resize());
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, rect.width * dpr);
    this.canvas.height = Math.max(1, rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = rect.width;
    this.h = rect.height;
  }

  push(t, sample) {
    for (const k in this.series) {
      const v = sample[k];
      if (v === undefined) continue;
      const arr = this.data[k];
      arr.push([t, v]);
      const cutoff = t - this.windowSec;
      while (arr.length && arr[0][0] < cutoff) arr.shift();
    }
  }

  draw() {
    const ctx = this.ctx;
    const w = this.w, h = this.h;
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "#262b35";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = (h / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    const now = Array.isArray(Object.values(this.data)[0]) && Object.values(this.data)[0].length
      ? Math.max(...Object.values(this.data).map((a) => (a.length ? a[a.length - 1][0] : 0)))
      : 0;
    const tMin = now - this.windowSec;

    for (const key in this.series) {
      const arr = this.data[key];
      if (arr.length < 2) continue;
      let min = Infinity, max = -Infinity;
      for (const [, v] of arr) {
        if (v < min) min = v;
        if (v > max) max = v;
      }
      if (min === max) { min -= 1; max += 1; }
      const pad = (max - min) * 0.1;
      min -= pad; max += pad;

      ctx.strokeStyle = this.series[key];
      ctx.lineWidth = 2;
      ctx.beginPath();
      arr.forEach(([t, v], i) => {
        const x = ((t - tMin) / this.windowSec) * w;
        const y = h - ((v - min) / (max - min)) * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
  }
}

const forceChart = new StripChart(document.getElementById("chart-force"), {
  thrust_g: "#4da3ff",
  torque_Ncm: "#f5a623",
});
const rpmChart = new StripChart(document.getElementById("chart-rpm"), { rpm: "#3ecf8e" });
const elecChart = new StripChart(document.getElementById("chart-elec"), {
  voltage_V: "#4da3ff",
  current_A: "#f0555a",
});
const powerChart = new StripChart(document.getElementById("chart-power"), {
  power_W: "#4da3ff",
  efficiency_g_per_W: "#3ecf8e",
});
const allCharts = [forceChart, rpmChart, elecChart, powerChart];

function redrawLoop() {
  allCharts.forEach((c) => c.draw());
  requestAnimationFrame(redrawLoop);
}
requestAnimationFrame(redrawLoop);

// ---------------------------------------------------------------- live readouts

function onSample(sample) {
  document.getElementById("v-thrust").textContent = fmt(sample.thrust_g, 0);
  document.getElementById("v-torque").textContent = fmt(sample.torque_Ncm, 2);
  document.getElementById("v-rpm").textContent = fmt(sample.rpm, 0);
  document.getElementById("v-voltage").textContent = fmt(sample.voltage_V, 2);
  document.getElementById("v-current").textContent = fmt(sample.current_A, 2);
  document.getElementById("v-power").textContent = fmt(sample.power_W, 1);
  document.getElementById("v-eff").textContent = fmt(sample.efficiency_g_per_W, 2);
  document.getElementById("v-throttle").textContent = fmt(sample.throttle_us, 0);

  const armedBadge = document.getElementById("armed-badge");
  armedBadge.textContent = sample.armed ? "armed" : "disarmed";
  armedBadge.className = "badge " + (sample.armed ? "armed" : "disarmed");

  const t = sample.t;
  allCharts.forEach((c) => c.push(t, sample));
}

// ---------------------------------------------------------------- websocket

let ws;
function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/live`);
  const badge = document.getElementById("conn-badge");
  ws.onopen = () => { badge.textContent = "connected"; badge.className = "badge connected"; };
  ws.onclose = () => {
    badge.textContent = "disconnected";
    badge.className = "badge disconnected";
    setTimeout(connectWs, 1000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (ev) => onSample(JSON.parse(ev.data));
}
connectWs();

// ---------------------------------------------------------------- status polling

async function refreshStatus() {
  try {
    const status = await api("GET", "/api/status");
    const modeBadge = document.getElementById("mode-badge");
    modeBadge.textContent = status.mode;
    modeBadge.className = "badge mode-" + status.mode;

    const slider = document.getElementById("throttle-slider");
    slider.min = status.esc.min_us;
    slider.max = status.esc.max_us;

    document.getElementById("sweep-progress").style.width =
      status.sweep_active && status.sweep_status.total
        ? `${(status.sweep_status.step / status.sweep_status.total) * 100}%`
        : "0%";
  } catch (e) { /* ignore transient errors */ }
}
setInterval(refreshStatus, 1000);
refreshStatus();

async function refreshRuns() {
  const runs = await api("GET", "/api/runs");
  const body = document.getElementById("runs-body");
  body.innerHTML = "";
  for (const run of runs) {
    const tr = document.createElement("tr");
    const started = new Date(run.start_time * 1000).toLocaleString();
    tr.innerHTML = `<td>${run.name}</td><td>${started}</td><td>${fmt(run.duration_s, 1)}s</td><td>${run.sample_count}</td>
      <td><a href="/api/runs/${run.id}/download">Download CSV</a></td>`;
    body.appendChild(tr);
  }
}
refreshRuns();

// ---------------------------------------------------------------- controls

document.getElementById("stop-btn").onclick = async () => {
  try { await api("POST", "/api/sweep/stop"); } catch (e) {}
  try { await api("POST", "/api/disarm"); } catch (e) {}
};

document.getElementById("arm-btn").onclick = async () => {
  try {
    await api("POST", "/api/arm");
    showMsg(document.getElementById("throttle-msg"), "Armed.", "ok");
  } catch (e) { showMsg(document.getElementById("throttle-msg"), e.message, "error"); }
};
document.getElementById("disarm-btn").onclick = async () => {
  await api("POST", "/api/disarm");
  showMsg(document.getElementById("throttle-msg"), "Disarmed.", "ok");
};

const slider = document.getElementById("throttle-slider");
const throttleLabel = document.getElementById("throttle-us-label");
slider.oninput = () => { throttleLabel.textContent = slider.value; };
slider.onchange = async () => {
  try {
    await api("POST", "/api/throttle", { us: Number(slider.value) });
  } catch (e) { showMsg(document.getElementById("throttle-msg"), e.message, "error"); }
};

document.getElementById("tare-btn").onclick = async () => {
  const channel = document.getElementById("cal-channel").value;
  const msg = document.getElementById("cal-msg");
  try {
    const r = await api("POST", "/api/tare", { channel });
    showMsg(msg, `${channel} tared (offset=${fmt(r.offset, 1)}).`, "ok");
  } catch (e) { showMsg(msg, e.message, "error"); }
};
document.getElementById("calibrate-btn").onclick = async () => {
  const channel = document.getElementById("cal-channel").value;
  const known = Number(document.getElementById("cal-known-value").value);
  const msg = document.getElementById("cal-msg");
  if (!known) { showMsg(msg, "Enter a known reference value first.", "error"); return; }
  try {
    const r = await api("POST", "/api/calibrate", { channel, known_value: known });
    showMsg(msg, `${channel} calibrated (scale=${fmt(r.scale, 4)}).`, "ok");
  } catch (e) { showMsg(msg, e.message, "error"); }
};

document.getElementById("test-start-btn").onclick = async () => {
  const name = document.getElementById("test-name").value || "test";
  const msg = document.getElementById("test-msg");
  try {
    const r = await api("POST", "/api/test/start", { name });
    showMsg(msg, `Recording started (${r.run_id}).`, "ok");
  } catch (e) { showMsg(msg, e.message, "error"); }
};
document.getElementById("test-stop-btn").onclick = async () => {
  const msg = document.getElementById("test-msg");
  const r = await api("POST", "/api/test/stop");
  showMsg(msg, r.run_id ? `Recording stopped (${r.run_id}).` : "No recording was active.", "ok");
  refreshRuns();
};

document.getElementById("sweep-start-btn").onclick = async () => {
  const msg = document.getElementById("sweep-msg");
  try {
    await api("POST", "/api/sweep/start", {
      min_us: Number(document.getElementById("sweep-min").value),
      max_us: Number(document.getElementById("sweep-max").value),
      step_us: Number(document.getElementById("sweep-step").value),
      hold_s: Number(document.getElementById("sweep-hold").value),
      name: document.getElementById("sweep-name").value || "sweep",
    });
    showMsg(msg, "Sweep started.", "ok");
  } catch (e) { showMsg(msg, e.message, "error"); }
};
document.getElementById("sweep-stop-btn").onclick = async () => {
  await api("POST", "/api/sweep/stop");
  showMsg(document.getElementById("sweep-msg"), "Stopping sweep...", "ok");
};

setInterval(() => {
  if (document.getElementById("sweep-progress").style.width !== "0%") refreshRuns();
}, 4000);
