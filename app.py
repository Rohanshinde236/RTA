"""
app.py
Flask web UI for RTA Monitoring System

Run: python app.py
Open: http://localhost:5000

Pages:
  /           -- Dashboard (status + start/stop/restart)
  /regions    -- Region configuration
  /agents     -- Agent settings
  /skills     -- Skill thresholds
  /logs       -- Live log viewer
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, redirect, render_template_string, request, url_for, send_from_directory
from flask_socketio import SocketIO, emit
from markupsafe import Markup

# -- Setup ---------------------------------------------------------------------
app        = Flask(__name__, static_folder=None)   # static handled by catch-all below
app.secret_key = "rta-monitor-secret-2026"
socketio   = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CFG_PATH   = os.path.join(BASE_DIR, "config.json")
LOG_DIR    = os.path.join(BASE_DIR, "log")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH         = os.path.join(LOG_DIR, "rta_v3.log")
STARTUP_LOG_PATH = os.path.join(LOG_DIR, "rta_startup.log")
ENV_PATH   = os.path.join(BASE_DIR, "config.env")

# Process handle for run_all.py
_process      = None
_process_lock = threading.Lock()
_log_lines    = []   # in-memory last 200 log lines
_max_log_lines = 200
_run_mode     = "full"  # "full" = Scrape & Monitor | "scrape" = Scrape only

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -- Config helpers ------------------------------------------------------------

def load_cfg() -> dict:
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg: dict) -> bool:
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Save config error: {e}")
        return False


def load_env() -> dict:
    """Load config.env as key-value dict."""
    env = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


# -- Process management --------------------------------------------------------

def get_status() -> str:
    global _process
    with _process_lock:
        if _process is None:
            return "stopped"
        if _process.poll() is None:
            return "running"
        _process = None   # clean up dead process reference
        return "stopped"


def start_system(mode: str = "full"):
    global _process, _run_mode
    with _process_lock:
        if _process and _process.poll() is None:
            return False, "Already running"
        try:
            _run_mode = mode
            err_log = open(STARTUP_LOG_PATH, "w", encoding="utf-8")

            _process = subprocess.Popen(
                [sys.executable, "-u", os.path.join(BASE_DIR, "run_all.py"), "--mode", mode],
                cwd=BASE_DIR,
                stdout=err_log,
                stderr=err_log,
            )
            t = threading.Thread(target=_read_logs, args=(_process,), daemon=True)
            t.start()
            t2 = threading.Thread(target=_read_startup_log, daemon=True)
            t2.start()

            label = "Scrape Only" if mode == "scrape" else "Scrape & Monitor"
            return True, f"System started — {label}"
        except Exception as e:
            return False, str(e)


def stop_system():
    global _process
    with _process_lock:
        if _process is None or _process.poll() is not None:
            return False, "Not running"
        try:
            _process.terminate()
            try:
                _process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _process.kill()
            _process = None
            return True, "System stopped"
        except Exception as e:
            return False, str(e)


def restart_system(mode: str = None):
    stop_system()
    time.sleep(2)
    return start_system(mode or _run_mode)


def _read_startup_log():
    """Also stream rta_startup.log into live logs."""
    import time
    path = STARTUP_LOG_PATH
    last_pos = 0
    for _ in range(120):  # watch for 2 minutes
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(last_pos)
                    lines = f.readlines()
                    last_pos = f.tell()
                for line in lines:
                    line = line.rstrip()
                    if line:
                        _log_lines.append(line)
        except Exception:
            pass
        time.sleep(1)


def _read_logs(proc):
    """Read from rta_v3.log file into _log_lines buffer."""
    global _log_lines
    import time
    log_path = LOG_PATH
    last_pos = 0
    while proc.poll() is None:
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    last_pos = f.tell()
                for line in new_lines:
                    line = line.rstrip()
                    if line:
                        _log_lines.append(line)
                        if len(_log_lines) > _max_log_lines:
                            _log_lines = _log_lines[-_max_log_lines:]
        except Exception:
            pass
        time.sleep(1)


# -- HTML Template -------------------------------------------------------------

BASE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>RTA Monitor — {{ title }}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
<style>
body { background: #f0f2f5; font-family: 'Segoe UI', sans-serif; }
.sidebar { background: #1e3c72; min-height: 100vh; padding-top: 20px; }
.sidebar a { color: #adc8ff; text-decoration: none; display: block;
             padding: 10px 20px; border-radius: 6px; margin: 2px 8px; }
.sidebar a:hover, .sidebar a.active { background: #2e5fa3; color: white; }
.sidebar .brand { color: white; font-size: 1.1em; font-weight: 700;
                  padding: 10px 20px 20px; border-bottom: 1px solid #2e5fa3; margin-bottom: 10px; }
.main { padding: 24px; }
.status-badge { font-size: 0.85em; padding: 4px 12px; border-radius: 20px; }
.card { border: none; box-shadow: 0 1px 4px rgba(0,0,0,0.1); border-radius: 10px; }
.card-header { border-radius: 10px 10px 0 0 !important; font-weight: 600; }
.btn-run { background: #28a745; color: white; border: none; }
.btn-run:hover { background: #218838; color: white; }
.btn-stop { background: #dc3545; color: white; border: none; }
.btn-stop:hover { background: #c82333; color: white; }
.btn-restart { background: #fd7e14; color: white; border: none; }
.btn-restart:hover { background: #e8690b; color: white; }
.region-card { border-left: 4px solid #1e3c72; margin-bottom: 16px; }
.log-box { background: #1a1a2e; color: #a8d8a8; font-family: monospace;
           font-size: 0.78em; height: 400px; overflow-y: auto; padding: 12px;
           border-radius: 8px; }
.log-error { color: #ff6b6b; }
.log-warn  { color: #ffa726; }
.log-info  { color: #a8d8a8; }
input[type=number], input[type=text], select, textarea {
    border-radius: 6px; border: 1px solid #ced4da; padding: 6px 10px; width: 100%; }
.form-label { font-weight: 600; font-size: 0.88em; color: #555; margin-bottom: 4px; }
.section-title { font-size: 1em; font-weight: 700; color: #1e3c72;
                 border-bottom: 2px solid #1e3c72; padding-bottom: 6px; margin: 20px 0 16px; }
.toggle-switch { display: flex; align-items: center; gap: 10px; }
</style>
</head>
<body>
<div class="d-flex">
  <!-- Sidebar -->
  <div class="sidebar" style="width:220px;min-width:220px">
    <div class="brand">🤖 RTA Monitor</div>
    <a href="/" class="{{ 'active' if page=='dashboard' else '' }}">📊 Dashboard</a>
    <a href="/regions" class="{{ 'active' if page=='regions' else '' }}">🌍 Regions</a>
    <a href="/agents" class="{{ 'active' if page=='agents' else '' }}">⚙️ Agent Settings</a>
    <a href="/skills" class="{{ 'active' if page=='skills' else '' }}">📋 Skill Thresholds</a>
    <a href="/logs" class="{{ 'active' if page=='logs' else '' }}">📜 Live Logs</a>
    <a href="/chat" class="{{ 'active' if page=='chat' else '' }}">💬 Chatbot</a>
  </div>

  <!-- Main -->
  <div class="main flex-grow-1">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <div class="alert alert-{{ 'success' if cat=='success' else 'danger' }} alert-dismissible fade show">
          {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
      {% endfor %}
    {% endwith %}
    {{ content }}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
{{ extra_js }}
</body>
</html>"""


# -- Dashboard page ------------------------------------------------------------

DASHBOARD_CONTENT = """
<h4 class="mb-4">📊 Dashboard</h4>

<div class="card mb-4">
  <div class="card-header bg-primary text-white">System Status</div>
  <div class="card-body">
    <div class="d-flex align-items-center gap-3 mb-3">
      <span class="fs-5 fw-bold">Status:</span>
      {% if status == 'running' %}
        <span class="badge bg-success status-badge fs-6">● RUNNING — {{ run_mode_label }}</span>
      {% else %}
        <span class="badge bg-danger status-badge fs-6">● STOPPED</span>
      {% endif %}
      <span class="text-muted small">Last checked: {{ now }}</span>
    </div>

    <!-- Mode selector -->
    <div class="mb-3">
      <span class="fw-semibold me-3">Mode:</span>
      <div class="form-check form-check-inline">
        <input class="form-check-input" type="radio" name="modeSelect" id="modeFull" value="full" checked>
        <label class="form-check-label fw-semibold text-success" for="modeFull">
          📊 Scrape &amp; Monitor <small class="text-muted fw-normal">(alerts + levers)</small>
        </label>
      </div>
      <div class="form-check form-check-inline">
        <input class="form-check-input" type="radio" name="modeSelect" id="modeScrape" value="scrape">
        <label class="form-check-label fw-semibold text-primary" for="modeScrape">
          🔍 Scrape Only <small class="text-muted fw-normal">(data collection, no alerts)</small>
        </label>
      </div>
    </div>

    <div class="d-flex gap-2">
      <form method="POST" action="/control" id="startForm">
        <input type="hidden" name="action" value="start"/>
        <input type="hidden" name="mode" value="full" id="startMode"/>
        <button class="btn btn-run px-4" {{ 'disabled' if status=='running' }}
                onclick="document.getElementById('startMode').value=document.querySelector('input[name=modeSelect]:checked').value">
          ▶ Start
        </button>
      </form>
      <form method="POST" action="/control">
        <input type="hidden" name="action" value="stop"/>
        <button class="btn btn-stop px-4" {{ 'disabled' if status=='stopped' }}>⏹ Stop</button>
      </form>
      <form method="POST" action="/control" id="restartForm">
        <input type="hidden" name="action" value="restart"/>
        <input type="hidden" name="mode" value="full" id="restartMode"/>
        <button class="btn btn-restart px-4"
                onclick="document.getElementById('restartMode').value=document.querySelector('input[name=modeSelect]:checked').value">
          🔄 Restart
        </button>
      </form>
    </div>
  </div>
</div>

<div class="row">
  {% for r in regions %}
  <div class="col-md-6 mb-3">
    <div class="card region-card">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <div class="fw-bold">{{ r.display }}</div>
            <div class="text-muted small">{{ r.name }} | {{ r.dashboard }}</div>
          </div>
          {% if r.active %}
            <span class="badge bg-success">Active</span>
          {% else %}
            <span class="badge bg-secondary">Inactive</span>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
"""


@app.route("/legacy/dashboard")
def dashboard():
    cfg     = load_cfg()
    regions = cfg.get("regions", [])
    inner   = render_template_string(
        DASHBOARD_CONTENT,
        status=get_status(),
        regions=regions,
        now=datetime.now().strftime("%I:%M:%S %p"),
        run_mode_label="Scrape Only" if _run_mode == "scrape" else "Scrape & Monitor",
    )
    return render_template_string(
        BASE_HTML, title="Dashboard", page="dashboard",
        content=Markup(inner), extra_js=Markup("")
    )


@app.route("/legacy/control", methods=["POST"])
def control():
    action = request.form.get("action")
    mode   = request.form.get("mode", "full")
    if action == "start":
        ok, msg = start_system(mode)
    elif action == "stop":
        ok, msg = stop_system()
    elif action == "restart":
        ok, msg = restart_system(mode)
    else:
        ok, msg = False, "Unknown action"
    from flask import flash
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("dashboard"))


# -- Regions page --------------------------------------------------------------

REGIONS_CONTENT = """
<div class="d-flex justify-content-between align-items-center mb-4">
  <h4>🌍 Regions</h4>
</div>

<form method="POST" action="/regions/save">
{% for i, r in enumerate(regions) %}
<div class="card mb-3 region-card">
  <div class="card-header bg-light d-flex justify-content-between">
    <span>Region {{ i+1 }} — {{ r.display }}</span>
    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" name="active_{{ i }}"
             {{ 'checked' if r.get('active', True) }}>
      <label class="form-check-label">Active</label>
    </div>
  </div>
  <div class="card-body">
    <div class="row g-3">
      <div class="col-md-3">
        <label class="form-label">Region Name</label>
        <input type="text" name="name_{{ i }}" value="{{ r.name }}" class="form-control"/>
      </div>
      <div class="col-md-4">
        <label class="form-label">Display Name</label>
        <input type="text" name="display_{{ i }}" value="{{ r.display }}" class="form-control"/>
      </div>
      <div class="col-md-3">
        <label class="form-label">Dashboard File</label>
        <input type="text" name="dashboard_{{ i }}" value="{{ r.dashboard }}" class="form-control"/>
      </div>
      <div class="col-md-2">
        <label class="form-label">&nbsp;</label>
        <div class="d-flex gap-2">
          <a href="/dashboard/view/{{ i }}" target="_blank"
             class="btn btn-outline-primary w-100" title="Open dashboard in browser">
             👁 View
          </a>
          <button type="button" class="btn btn-outline-danger w-100"
                  onclick="this.closest('.card').remove()">?</button>
        </div>
      </div>
      <div class="col-12">
        <label class="form-label">Teams Webhook URL</label>
        <input type="text" name="webhook_{{ i }}" value="{{ r.webhook }}" class="form-control"/>
      </div>
    </div>
  </div>
</div>
{% endfor %}
<input type="hidden" name="count" value="{{ regions|length }}"/>
<div class="d-flex gap-2 mt-2">
  <button type="submit" class="btn btn-primary px-4">💾 Save Regions</button>
  <a href="/" class="btn btn-outline-secondary">Cancel</a>
</div>
</form>
"""


@app.route("/legacy/regions")
def regions_page():
    cfg     = load_cfg()
    regions = cfg.get("regions", [])
    inner = render_template_string(
        REGIONS_CONTENT,
        regions=regions,
        enumerate=enumerate
    )
    return render_template_string(
        BASE_HTML, title="Regions", page="regions",
        content=Markup(inner), extra_js=Markup("")
    )


@app.route("/dashboard/view/<int:region_index>")
def view_dashboard(region_index):
    """Open the dashboard HTML file in browser."""
    cfg     = load_cfg()
    regions = cfg.get("regions", [])
    if region_index >= len(regions):
        return "Region not found", 404
    region      = regions[region_index]
    dashboard   = region.get("dashboard", "")
    dashboard_path = os.path.join(BASE_DIR, dashboard)
    if not os.path.isfile(dashboard_path):
        return f"Dashboard file not found: {dashboard_path}", 404
    with open(dashboard_path, "r", encoding="utf-8") as f:
        html = f.read()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


def _serve_ui_file(filename):
    """Helper: read and return an HTML file from the ui/ folder."""
    fp = os.path.join(BASE_DIR, "ui", filename)
    if not os.path.isfile(fp):
        return f"File not found: {filename}", 404
    with open(fp, "r", encoding="utf-8") as f:
        html = f.read()
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/portal/cms")
def portal_cms():
    return _serve_ui_file("CMS.html")

@app.route("/portal/rta")
def portal_rta():
    return _serve_ui_file("RTA.html")

@app.route("/portal/cn")
def portal_cn():
    return _serve_ui_file("RTA_CN.html")

@app.route("/portal/au")
def portal_au():
    return _serve_ui_file("RTA_AU.html")

@app.route("/portal/emea")
def portal_emea():
    return _serve_ui_file("RTA_EMEA.html")

@app.route("/portal/hk")
def portal_hk():
    return _serve_ui_file("RTA_HK.html")

@app.route("/portal/my")
def portal_my():
    return _serve_ui_file("RTA_MY.html")

@app.route("/portal/kr")
def portal_kr():
    return _serve_ui_file("RTA_KR.html")

@app.route("/portal/th")
def portal_th():
    return _serve_ui_file("RTA_TH.html")

@app.route("/portal/br")
def portal_br():
    return _serve_ui_file("RTA_BR.html")

@app.route("/portal/tw")
def portal_tw():
    return _serve_ui_file("RTA_TW.html")


@app.route("/legacy/regions/save", methods=["POST"])
def regions_save():
    cfg   = load_cfg()
    count = int(request.form.get("count", 0))
    regs  = []
    for i in range(count):
        name = request.form.get(f"name_{i}", "").strip()
        if not name:
            continue
        regs.append({
            "name":      name,
            "display":   request.form.get(f"display_{i}", name),
            "dashboard": request.form.get(f"dashboard_{i}", f"{name}.html"),
            "webhook":   request.form.get(f"webhook_{i}", ""),
            "active":    f"active_{i}" in request.form,
        })
    cfg["regions"] = regs
    save_cfg(cfg)
    from flask import flash
    flash("Regions saved. Restart system to apply.", "success")
    return redirect(url_for("regions_page"))


# -- Agent Settings page -------------------------------------------------------

AGENTS_CONTENT = """
<h4 class="mb-4">⚙️ Agent Settings</h4>
<form method="POST" action="/agents/save">

  <!-- Agent 1 -->
  <div class="section-title">Agent 1 — Dashboard Scraper</div>
  <div class="row g-3 mb-3">
    <div class="col-md-3">
      <label class="form-label">Scraping Interval (seconds)</label>
      <input type="number" name="a1_scrape" value="{{ a1.get('scrape_interval_sec', 60) }}" class="form-control"/>
    </div>
    <div class="col-md-3">
      <label class="form-label">Band Drop Email</label>
      <select name="a1_email" class="form-control">
        <option value="true" {{ 'selected' if a1.get('band_drop_email_enabled', True) }}>Enabled</option>
        <option value="false" {{ 'selected' if not a1.get('band_drop_email_enabled', True) }}>Disabled</option>
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label">Band Drop Teams Alert</label>
      <select name="a1_teams" class="form-control">
        <option value="true" {{ 'selected' if a1.get('band_drop_teams_enabled', True) }}>Enabled</option>
        <option value="false" {{ 'selected' if not a1.get('band_drop_teams_enabled', True) }}>Disabled</option>
      </select>
    </div>
  </div>

  <!-- Agent 2 -->
  <div class="section-title">Agent 2 — CMS Analyst + LLM</div>
  <div class="row g-3 mb-3">
    <div class="col-md-3">
      <label class="form-label">OCW Threshold (seconds)</label>
      <input type="number" name="a2_ocw" value="{{ a2.get('ocw_threshold_sec', 60) }}" class="form-control"/>
    </div>
    <div class="col-md-3">
      <label class="form-label">Queue Minimum (calls)</label>
      <input type="number" name="a2_queue_min" value="{{ a2.get('queue_min', 1) }}" class="form-control"/>
    </div>
    <div class="col-md-3">
      <label class="form-label">Cooldown (seconds)</label>
      <input type="number" name="a2_cooldown" value="{{ a2.get('cooldown_sec', 300) }}" class="form-control"/>
    </div>
    <div class="col-md-3">
      <label class="form-label">LLM Enabled</label>
      <select name="a2_llm" class="form-control">
        <option value="true" {{ 'selected' if a2.get('llm_enabled', True) }}>Enabled</option>
        <option value="false" {{ 'selected' if not a2.get('llm_enabled', True) }}>Disabled (rule-based)</option>
      </select>
    </div>
  </div>

  <!-- Agent 3 -->
  <div class="section-title">Agent 3 — Lever Generator</div>
  <div class="row g-3 mb-3">
    <div class="col-md-2">
      <label class="form-label">Amber Lever (%)</label>
      <input type="number" step="0.1" name="a3_amber" value="{{ a3.get('amber_threshold', 90.0) }}" class="form-control"/>
    </div>
    <div class="col-md-2">
      <label class="form-label">Red Lever (%)</label>
      <input type="number" step="0.1" name="a3_red" value="{{ a3.get('red_threshold', 80.0) }}" class="form-control"/>
    </div>
    <div class="col-md-2">
      <label class="form-label">Black Lever (%)</label>
      <input type="number" step="0.1" name="a3_black" value="{{ a3.get('black_threshold', 70.0) }}" class="form-control"/>
    </div>
    <div class="col-md-6">
      <label class="form-label">Excel Path</label>
      <input type="text" name="a3_excel" value="{{ a3.get('excel_path', '') }}" class="form-control"/>
    </div>
    <div class="col-12">
      <label class="form-label">Email Recipients (comma separated)</label>
      <input type="text" name="a3_emails" value="{{ a3.get('email_recipients', []) | join(', ') }}" class="form-control"/>
    </div>
  </div>

  <!-- Agent 4 -->
  <div class="section-title">Agent 4 — CMS Monitor</div>
  <div class="row g-3 mb-3">
    <div class="col-md-3">
      <label class="form-label">Scraping Interval (seconds)</label>
      <input type="number" name="a4_scrape" value="{{ a4.get('scrape_interval_sec', 60) }}" class="form-control"/>
    </div>
    <div class="col-md-3">
      <label class="form-label">Avg AHT Target (minutes)</label>
      <input type="number" name="a4_aht" value="{{ a4.get('aht_target_min', 24) }}" class="form-control"/>
    </div>
    <div class="col-md-3">
      <label class="form-label">Avg ACW Target (minutes)</label>
      <input type="number" name="a4_acw" value="{{ a4.get('acw_target_min', 5) }}" class="form-control"/>
    </div>
  </div>

  <!-- AUX Thresholds -->
  <div class="section-title">Agent 4 — AUX Thresholds</div>
  <p class="text-muted small mb-3">Set max time per AUX code. Alert fires if agent exceeds this time. Set 0 to disable monitoring for that AUX.</p>
  <div class="table-responsive mb-3">
    <table class="table table-bordered table-hover align-middle">
      <thead class="table-light">
        <tr>
          <th>AUX Code</th>
          <th>Name</th>
          <th>Max Time (min)</th>
          <th>Monitor</th>
        </tr>
      </thead>
      <tbody>
        {% for aux_code, aux_cfg in a4.get('aux_thresholds', {}).items() %}
        <tr>
          <td class="fw-bold text-primary">{{ aux_code }}</td>
          <td>{{ aux_cfg.get('name', '') }}</td>
          <td style="width:160px">
            <input type="number" name="aux_time_{{ aux_code }}"
                   value="{{ aux_cfg.get('max_time_min', 0) }}"
                   min="0" max="480"
                   class="form-control form-control-sm"/>
          </td>
          <td style="width:100px">
            <div class="form-check form-switch">
              <input class="form-check-input" type="checkbox"
                     name="aux_enabled_{{ aux_code }}"
                     {{ 'checked' if aux_cfg.get('enabled', False) }}>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="d-flex gap-2 mt-2">
    <button type="submit" class="btn btn-primary px-4">💾 Save Agent Settings</button>
    <a href="/" class="btn btn-outline-secondary">Cancel</a>
  </div>
</form>
"""


@app.route("/legacy/agents")
def agents_page():
    cfg     = load_cfg()
    inner = render_template_string(
        AGENTS_CONTENT,
        a1=cfg.get("agent1", {}),
        a2=cfg.get("agent2", {}),
        a3=cfg.get("agent3", {}),
        a4=cfg.get("agent4", {})
    )
    return render_template_string(
        BASE_HTML, title="Agent Settings", page="agents",
        content=Markup(inner), extra_js=Markup("")
    )


@app.route("/legacy/agents/save", methods=["POST"])
def agents_save():
    cfg = load_cfg()
    f   = request.form

    cfg["agent1"] = {
        "scrape_interval_sec":      int(f.get("a1_scrape", 60)),
        "band_drop_email_enabled":  f.get("a1_email") == "true",
        "band_drop_teams_enabled":  f.get("a1_teams") == "true",
    }
    cfg["agent2"] = {
        "ocw_threshold_sec":  int(f.get("a2_ocw", 60)),
        "queue_min":          int(f.get("a2_queue_min", 1)),
        "cooldown_sec":       int(f.get("a2_cooldown", 300)),
        "llm_enabled":        f.get("a2_llm") == "true",
    }
    emails = [e.strip() for e in f.get("a3_emails", "").split(",") if e.strip()]
    cfg["agent3"] = {
        "amber_threshold":  float(f.get("a3_amber", 90)),
        "red_threshold":    float(f.get("a3_red", 80)),
        "black_threshold":  float(f.get("a3_black", 70)),
        "excel_path":       f.get("a3_excel", ""),
        "email_recipients": emails,
    }

    # Build AUX thresholds from form
    aux_codes = {
        "AUX1": "IT Issue",    "AUX2": "Break",
        "AUX3": "Lunch",       "AUX4": "Meeting",
        "AUX5": "Training",    "AUX6": "Case Mgmt",
        "AUX7": "Project",     "AUX8": "Alt Channel",
        "AUX9": "Outbound"
    }
    aux_thresholds = {}
    for code, name in aux_codes.items():
        aux_thresholds[code] = {
            "name":         name,
            "max_time_min": int(f.get(f"aux_time_{code}", 0)),
            "enabled":      f"aux_enabled_{code}" in f,
        }

    cfg["agent4"] = {
        "scrape_interval_sec": int(f.get("a4_scrape", 60)),
        "aht_target_min":      int(f.get("a4_aht", 24)),
        "acw_target_min":      int(f.get("a4_acw", 5)),
        "aux_thresholds":      aux_thresholds,
    }
    save_cfg(cfg)
    from flask import flash
    flash("Agent settings saved. Restart system to apply.", "success")
    return redirect(url_for("agents_page"))


# -- Skill Thresholds page -----------------------------------------------------

SKILLS_CONTENT = """
<h4 class="mb-4">📋 Skill Thresholds</h4>
<form method="POST" action="/skills/save">
<div class="card">
  <div class="card-body">
    <table class="table table-hover align-middle">
      <thead class="table-light">
        <tr>
          <th>Skill Name</th>
          <th>Region</th>
          <th>AHT Target (min)</th>
          <th>OCW Threshold (sec)</th>
          <th>Active</th>
        </tr>
      </thead>
      <tbody>
        {% for skill, cfg in skills.items() %}
        <tr>
          <td class="fw-bold">{{ skill }}</td>
          <td class="text-muted small">{{ regions.get(skill, '--') }}</td>
          <td>
            <input type="number" name="aht_{{ skill }}"
                   value="{{ cfg.aht_target_min }}"
                   style="width:80px" class="form-control form-control-sm"/>
          </td>
          <td>
            <input type="number" name="ocw_{{ skill }}"
                   value="{{ cfg.ocw_threshold_sec }}"
                   style="width:80px" class="form-control form-control-sm"/>
          </td>
          <td>
            <input type="checkbox" name="active_{{ skill }}"
                   {{ 'checked' if cfg.active }} class="form-check-input"/>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
<div class="d-flex gap-2 mt-3">
  <button type="submit" class="btn btn-primary px-4">💾 Save Skill Thresholds</button>
  <a href="/" class="btn btn-outline-secondary">Cancel</a>
</div>
</form>
"""

SKILL_REGION_MAP = {
    # APJ-IN (India)
    "TS_CSTCE": "APJ-IN", "TS_CSTElite": "APJ-IN", "TS_LicKeys": "APJ-IN",
    "TS_VICHW": "APJ-IN", "TS_CSTVCE": "APJ-IN", "TS_CSTCritAcct": "APJ-IN",
    # APJ-CN (China)
    "TS_CN_ProDB": "APJ-CN", "TS_CN_ProCNX": "APJ-CN", "TS_CN_Elite": "APJ-CN",
    "TS_CN_LicKeys": "APJ-CN", "TS_CN_VICHW": "APJ-CN", "TS_CN_CritAcct": "APJ-CN",
    # APJ-AU (Australia)
    "TS_AU_ProDB": "APJ-AU", "TS_AU_ProCNX": "APJ-AU", "TS_AU_Elite": "APJ-AU",
    "TS_AU_LicKeys": "APJ-AU", "TS_AU_VICHW": "APJ-AU", "TS_AU_CritAcct": "APJ-AU",
    # EMEA
    "TS_MLSCST_GER": "EMEA", "TS_MLSCST_SPA": "EMEA", "TS_MLSCST_FRA": "EMEA",
    "TS_MLSCST_ITA": "EMEA", "TS_MLSCST_NLD": "EMEA", "TS_MLSCST_POL": "EMEA",
    # APJ-HK (Hong Kong)
    "TS_HK_ProDB": "APJ-HK", "TS_HK_ProCNX": "APJ-HK", "TS_HK_Elite": "APJ-HK",
    "TS_HK_LicKeys": "APJ-HK", "TS_HK_VICHW": "APJ-HK", "TS_HK_CritAcct": "APJ-HK",
    # APJ-MY (Malaysia)
    "TS_MY_ProDB": "APJ-MY", "TS_MY_ProCNX": "APJ-MY", "TS_MY_Elite": "APJ-MY",
    "TS_MY_LicKeys": "APJ-MY", "TS_MY_VICHW": "APJ-MY", "TS_MY_CritAcct": "APJ-MY",
    # APJ-KR (Korea)
    "TS_KR_ProDB": "APJ-KR", "TS_KR_ProCNX": "APJ-KR", "TS_KR_Elite": "APJ-KR",
    "TS_KR_LicKeys": "APJ-KR", "TS_KR_VICHW": "APJ-KR", "TS_KR_CritAcct": "APJ-KR",
    # APJ-TH (Thailand)
    "TS_TH_ProDB": "APJ-TH", "TS_TH_ProCNX": "APJ-TH", "TS_TH_Elite": "APJ-TH",
    "TS_TH_LicKeys": "APJ-TH", "TS_TH_VICHW": "APJ-TH", "TS_TH_CritAcct": "APJ-TH",
    # LATAM-BR (Brazil)
    "TS_BR_ProDB": "LATAM-BR", "TS_BR_ProCNX": "LATAM-BR", "TS_BR_Elite": "LATAM-BR",
    "TS_BR_LicKeys": "LATAM-BR", "TS_BR_VICHW": "LATAM-BR", "TS_BR_CritAcct": "LATAM-BR",
    # APJ-TW (Taiwan)
    "TS_TW_ProDB": "APJ-TW", "TS_TW_ProCNX": "APJ-TW", "TS_TW_Elite": "APJ-TW",
    "TS_TW_LicKeys": "APJ-TW", "TS_TW_VICHW": "APJ-TW", "TS_TW_CritAcct": "APJ-TW",
}


@app.route("/legacy/skills")
def skills_page():
    cfg    = load_cfg()
    skills = cfg.get("skill_thresholds", {})
    inner = render_template_string(
        SKILLS_CONTENT,
        skills=skills,
        regions=SKILL_REGION_MAP
    )
    return render_template_string(
        BASE_HTML, title="Skill Thresholds", page="skills",
        content=Markup(inner), extra_js=Markup("")
    )


@app.route("/legacy/skills/save", methods=["POST"])
def skills_save():
    cfg    = load_cfg()
    skills = cfg.get("skill_thresholds", {})
    f      = request.form
    for skill in skills:
        skills[skill]["aht_target_min"]    = int(f.get(f"aht_{skill}", 24))
        skills[skill]["ocw_threshold_sec"] = int(f.get(f"ocw_{skill}", 60))
        skills[skill]["active"]            = f"active_{skill}" in f
    cfg["skill_thresholds"] = skills
    save_cfg(cfg)
    from flask import flash
    flash("Skill thresholds saved. Restart system to apply.", "success")
    return redirect(url_for("skills_page"))


# -- Logs page -----------------------------------------------------------------

LOGS_CONTENT = """
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>📜 Live Logs</h4>
  <div class="d-flex gap-2">
    <button class="btn btn-sm btn-outline-secondary" onclick="clearLogs()">🗑 Clear</button>
    <button class="btn btn-sm btn-outline-primary" onclick="toggleAuto()">⏸ Pause</button>
  </div>
</div>
<div class="log-box" id="logBox">Loading...</div>
"""

LOGS_JS = """
<script>
let autoRefresh = true;
let interval;

function loadLogs() {
  fetch('/api/logs')
    .then(r => r.json())
    .then(data => {
      const box = document.getElementById('logBox');
      box.innerHTML = data.lines.map(line => {
        let cls = 'log-info';
        if (line.includes(' ERROR ')) cls = 'log-error';
        else if (line.includes(' WARNING ')) cls = 'log-warn';
        return `<div class="${cls}">${line}</div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    });
}

function clearLogs() {
  fetch('/api/logs/clear', {method:'POST'}).then(loadLogs);
}

function toggleAuto() {
  autoRefresh = !autoRefresh;
  document.querySelector('[onclick="toggleAuto()"]').textContent =
    autoRefresh ? '⏸ Pause' : '▶ Resume';
}

loadLogs();
interval = setInterval(() => { if (autoRefresh) loadLogs(); }, 2000);
</script>
"""


@app.route("/legacy/logs")
def logs_page():
    return render_template_string(
        BASE_HTML, title="Live Logs", page="logs",
        content=Markup(LOGS_CONTENT), extra_js=Markup(LOGS_JS)
    )


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    global _log_lines
    _log_lines = []
    return jsonify({"ok": True})


# -- Chatbot -------------------------------------------------------------------

LIVE_STATE_PATH  = os.path.join(BASE_DIR, "db", "live_state.json")
CMS_AGENTS_PATH  = os.path.join(BASE_DIR, "db", "cms_agents.json")

CHAT_CONTENT = """
<div class="d-flex flex-column" style="height: calc(100vh - 120px);">
  <h4 class="mb-3">&#x1F4AC; RTA Chatbot</h4>
  <div class="d-flex gap-2 mb-3">
    <button type="button" id="modeLive" class="btn btn-success btn-sm px-3" onclick="setMode('live')">&#x1F7E2; Live Data</button>
    <button type="button" id="modeHistory" class="btn btn-outline-secondary btn-sm px-3" onclick="setMode('history')">&#x1F4C5; History</button>
    <span id="modeLabel" class="text-muted small align-self-center">Currently: Live Data</span>
  </div>
  <div class="text-muted small mb-3">
    Ask anything about live queue data &mdash; e.g. Which skills are breached?, What levers fired?
  </div>

  <div id="chatMessages" class="flex-grow-1 overflow-auto mb-3"
       style="background:#fff;border-radius:10px;padding:16px;
              border:1px solid #e0e0e0;min-height:200px;">
    <div id="chatPlaceholder" class="text-muted small text-center mt-4">
      Ask a question about your live RTA data...
    </div>
  </div>

  <div class="d-flex gap-2">
    <input type="text" id="chatInput" class="form-control"
           placeholder="e.g. What is happening in India right now?" />
    <button type="button" id="sendBtn" class="btn btn-primary px-4">Send</button>
    <button type="button" id="clearBtn" class="btn btn-outline-secondary">Clear</button>
  </div>
</div>
<script src="/chat-js"></script>
"""

CHAT_JS = """
<script>
let chatHistory = [];

function sendChat() {
  const input = document.getElementById('chatInput');
  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  appendMessage('user', question);
  appendMessage('bot', '? Thinking...');

  fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: question})
  })
  .then(function(r) {
    if (!r.ok) throw new Error('Server error ' + r.status);
    return r.json();
  })
  .then(function(data) {
    const msgs = document.querySelectorAll('.chat-msg-bot');
    const last = msgs[msgs.length - 1];
    if (last) last.innerHTML = formatAnswer(data.answer || 'No response.');
  })
  .catch(function(err) {
    const msgs = document.querySelectorAll('.chat-msg-bot');
    const last = msgs[msgs.length - 1];
    if (last) last.textContent = 'Error: ' + err.message;
  });
}

function formatAnswer(text) {
  return text.replace(/\n/g, '<br>');
}

function appendMessage(role, text) {
  const box = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = role === 'user' ? 'chat-msg-user' : 'chat-msg-bot';
  div.style.cssText = role === 'user'
    ? 'background:#e3f2fd;border-radius:10px;padding:10px 14px;margin:8px 0;margin-left:20%'
    : 'background:#f5f5f5;border-radius:10px;padding:10px 14px;margin:8px 0;margin-right:20%';
  div.innerHTML = (role === 'user' ? '<strong>You:</strong> ' : '<strong>RTA Bot:</strong> ') + text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function clearChat() {
  document.getElementById('chatMessages').innerHTML =
    '<div class="text-muted small text-center mt-4">Ask a question about your live RTA data...</div>';
}
</script>
"""


def _load_live_state() -> dict:
    """Read live_state.json written by run_all.py after every poll."""
    try:
        with open(LIVE_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"live_state.json read error: {e}")
        return {}


def _load_cms_agents() -> dict:
    """
    Read cms_agents.json written by Agent 4 after every CMS poll.
    Returns {region_tag: {skill_name: [agent_dicts]}} or {} if not available.
    Each agent_dict has: name, state, aux_reason, aux_key, aux_name, time_minutes, skill.
    """
    try:
        with open(CMS_AGENTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"cms_agents.json read error: {e}")
        return {}


def _build_context(question: str, live_state: dict, cms_agents: dict = None) -> str:
    """
    Build LLM context from live_state filtered by what the question is asking.
    Only sends relevant data -- not the entire state -- to save tokens.
    """
    if not live_state:
        return "No live data available -- system may not be running yet."

    q = question.lower()

    # -- Detect specific skill name in question (e.g. "TS_AU_Elite") -----------
    import re as _re
    skill_match = _re.search(r'ts_[a-z0-9_]+', q)
    specific_skill = skill_match.group(0).upper() if skill_match else None

    # -- Detect region intent --------------------------------------------------
    # Pad question with spaces so word-boundary checks work on first/last word
    _q = f" {q} "

    if specific_skill:
        # Auto-detect region from skill name prefix
        s = specific_skill.lower()
        if "_cn_" in s:
            region_filter = ["cn"]
        elif "_au_" in s:
            region_filter = ["au"]
        elif "_hk_" in s:
            region_filter = ["hk"]
        elif "_my_" in s:
            region_filter = ["my"]
        elif "_kr_" in s:
            region_filter = ["kr"]
        elif "_th_" in s:
            region_filter = ["th"]
        elif "_br_" in s:
            region_filter = ["br"]
        elif "_tw_" in s:
            region_filter = ["tw"]
        elif any(x in s for x in ["_ger_","_spa_","_fra_","_ita_","_nld_","_pol_","mlscst"]):
            region_filter = ["emea"]
        else:
            region_filter = ["rta"]
    # ── "all regions / all dashboards" — must come BEFORE any single-region check ──
    elif any(x in _q for x in [" all region", " all dashboard", " all 10", " every region",
                                 " all skill", " across all", " from all"]):
        region_filter = list(live_state.keys())
    # ── Single-region checks — use full names OR padded abbreviations only ──────
    # RULE: 2-3 char codes MUST be padded with spaces to avoid false-matching
    # common English words (e.g. "tha"→"that", "ind"→"individual", "au"→"because")
    elif any(x in _q for x in ["india", " rta "]):
        region_filter = ["rta"]
    elif any(x in _q for x in ["china", "chinese", " cn "]):
        region_filter = ["cn"]
    elif any(x in _q for x in ["australia", " aus ", " au "]):
        region_filter = ["au"]
    elif any(x in _q for x in ["emea", "europe", "germany", "france", "spain",
                                 "italy", "netherlands", "poland"]):
        region_filter = ["emea"]
    elif any(x in _q for x in ["hong kong", "hongkong", "hkg", " hk "]):
        region_filter = ["hk"]
    elif any(x in _q for x in ["malaysia", " mys ", " my "]):
        region_filter = ["my"]
    elif any(x in _q for x in ["korea", "korean", " kor ", " kr "]):
        region_filter = ["kr"]
    elif any(x in _q for x in ["thailand", "thai", " tha ", " th "]):
        region_filter = ["th"]
    elif any(x in _q for x in ["brazil", "brazilian", " bra ", " br "]):
        region_filter = ["br"]
    elif any(x in _q for x in ["taiwan", " twn ", " tw "]):
        region_filter = ["tw"]
    else:
        region_filter = list(live_state.keys())  # all regions

    # -- Parse SLA threshold from question (e.g. "90+", ">90", "above 90") ----
    import re as _re_sla
    _sla_threshold = None
    _sla_m = _re_sla.search(r'(\d+)\s*\+|(?:above|over|greater than|>=?)\s*(\d+)', q)
    if _sla_m:
        _sla_threshold = float(_sla_m.group(1) or _sla_m.group(2))

    # -- Detect topic intent ---------------------------------------------------
    if specific_skill:
        topic = "skill_detail"   # show full detail for that one skill
    elif any(x in q for x in ["lever", "escalat"]):
        topic = "levers"
    elif any(x in q for x in ["breach", "critical", "severe", "worst", "bad"]):
        topic = "breached"
    elif any(x in q for x in ["aux", "break", "lunch", "move", "agent"]):
        topic = "agents"
    elif any(x in q for x in ["queue", "waiting", "ciq", "ocw"]):
        topic = "queue"
    elif any(x in q for x in ["compare", "which region", "all region"]):
        topic = "summary"
    elif any(x in q for x in ["improve", "fix", "action", "recommendation", "suggest",
                                "how to", "what to do",
                                "what can we", "what can i",
                                "what should we", "what should i"]):
        topic = "improvement"
    elif any(x in q for x in ["project", "projected", "forecast", "what if", "if agents",
                                "if we add", "scenario", "predict"]):
        topic = "all"   # projection questions need full SLA data for all skills
    else:
        topic = "all"

    # Region tag → friendly name legend so LLM understands the data
    tag_names = {
        "rta":  "India (Client ProSupport IND)",
        "cn":   "China (Client ProSupport CHN)",
        "au":   "Australia (Client ProSupport AUS)",
        "emea": "EMEA (Europe / Germany / France / Spain)",
    }
    # Add any extra tags from live_state not in the hardcoded map
    for t in live_state:
        if t not in tag_names:
            tag_names[t] = live_state[t].get("region_display", t.upper())

    lines = ["LIVE RTA DATA (current poll only — no history):"]
    lines.append("Region key: " + " | ".join(f"{t}={n}" for t, n in tag_names.items()))
    lines.append(f"Showing: {[tag_names.get(r, r) for r in region_filter]}")
    lines.append("")

    for tag, region in live_state.items():
        if tag not in region_filter:
            continue

        display   = region.get("region_display", tag.upper())
        poll_time = region.get("last_poll_time", "unknown")

        skills = region.get("skills", {})

        # Apply SLA threshold filter if user asked for "90+", ">= 85", etc.
        if _sla_threshold is not None:
            skills = {s: d for s, d in skills.items()
                      if d.get("sla") is not None and float(d["sla"]) >= _sla_threshold}
            if not skills:
                continue   # skip this region entirely — no skills meet the threshold

        lines.append(f"=== {display} (last updated: {poll_time}) ===")

        if topic == "skill_detail":
            # Show full data for the specific skill
            data = skills.get(specific_skill)
            if data:
                lines.append(f"  {specific_skill} full detail:")
                lines.append(f"    SLA      : {data.get('sla')}% ({data.get('band')})")
                lines.append(f"    Queue    : {data.get('queue')} calls waiting")
                lines.append(f"    OCW      : {data.get('ocw')}")
                lines.append(f"    Available: {data.get('avail')} agents")
                lines.append(f"    On AUX   : {data.get('on_aux')} agents")
                lines.append(f"    Lever    : {data.get('lever_fired', 'none')}")
                lines.append(f"    Breached : {data.get('breached', False)}")
                if data.get('breach_reasons'):
                    lines.append(f"    Reasons  : {data['breach_reasons']}")
                if data.get('root_cause'):
                    lines.append(f"    Root cause: {data['root_cause']}")
                if data.get('a2_note'):
                    lines.append(f"    AI note  : {data['a2_note']}")
            else:
                available = list(skills.keys())
                lines.append(f"  Skill '{specific_skill}' not found in this region.")
                lines.append(f"  Available skills: {available}")

        elif topic == "levers":
            # Only show lever info
            levers = region.get("levers_fired", {})
            if levers:
                lines.append(f"Levers fired: {list(levers.keys())}")
            else:
                lines.append("No levers fired -- all skills above threshold.")
            for skill, data in skills.items():
                if data.get("lever_fired"):
                    lines.append(
                        f"  {skill}: {data['lever_fired']} Lever | "
                        f"SLA={data['sla']}% | Queue={data['queue']}"
                    )

        elif topic == "breached":
            # Only show breached/critical skills
            breached = {s: d for s, d in skills.items() if d.get("breached") or d.get("band") in ["CRITICAL","SEVERE"]}
            if breached:
                for skill, data in breached.items():
                    lines.append(
                        f"  {skill}: SLA={data['sla']}% ({data['band']}) | "
                        f"Queue={data['queue']} | OCW={data['ocw']} | "
                        f"Avail={data['avail']} | AUX={data['on_aux']} | "
                        f"Reasons={data.get('breach_reasons', [])}"
                    )
            else:
                lines.append("  No breached skills -- all healthy.")

        elif topic == "queue":
            # Queue and OCW focused
            for skill, data in skills.items():
                if data["queue"] > 0 or data["ocw"] != "00:00":
                    lines.append(
                        f"  {skill}: Queue={data['queue']} | "
                        f"OCW={data['ocw']} | Avail={data['avail']}"
                    )
            if not any(d["queue"] > 0 for d in skills.values()):
                lines.append("  No calls in queue currently.")

        elif topic == "agents":
            # AUX agents — use cms_agents.json for full per-agent detail
            region_cms  = (cms_agents or {}).get(tag, {})
            cms_present = bool(region_cms)   # False = agent4 hasn't written yet
            any_agents  = False

            for skill, data in skills.items():
                skill_agents = region_cms.get(skill, [])
                aux_agents   = [a for a in skill_agents
                                if a.get("state", "").upper() in ("AUX", "AUX ")]
                acw_agents   = [a for a in skill_agents
                                if a.get("state", "").upper() == "ACW"]

                if data["on_aux"] > 0 or aux_agents or data.get("last_move") or data.get("last_ask"):
                    any_agents = True
                    lines.append(f"  {skill}: {data['on_aux']} on AUX | "
                                 f"{data['avail']} available | {data['on_calls']} on calls")

                    if not cms_present:
                        # cms_agents.json doesn't exist yet (agent4 not started or scrape-only mode)
                        # Tell LLM not to invent names — show count only
                        lines.append(
                            f"    ⚠ Individual agent names NOT available — "
                            f"CMS data not yet loaded. Show count ({data['on_aux']}) only. "
                            f"Do NOT invent agent names or durations."
                        )
                    elif not aux_agents:
                        # cms_agents.json exists but no AUX agents found for this skill
                        lines.append(f"    (No agents in AUX state in current CMS snapshot)")
                    else:
                        # Full per-agent detail available
                        for a in aux_agents:
                            aux_label = a.get("aux_name") or a.get("aux_reason") or "AUX"
                            aux_key   = a.get("aux_key", "")
                            mins      = a.get("time_minutes", 0)
                            duration  = f"{mins:.0f} min" if mins else "< 1 min"
                            lines.append(
                                f"    [AUX] {a['name']} — {aux_label}"
                                f"{' (' + aux_key + ')' if aux_key else ''} — {duration}"
                            )
                    for a in acw_agents:
                        mins     = a.get("time_minutes", 0)
                        duration = f"{mins:.0f} min" if mins else "< 1 min"
                        lines.append(f"    [ACW] {a['name']} — {duration}")
                    if data.get("last_move"):
                        lines.append(f"    A2 move recommendation: {data['last_move']}")
                    if data.get("last_ask"):
                        lines.append(f"    A2 ask recommendation: {data['last_ask']}")
                    if data.get("a2_note"):
                        lines.append(f"    AI note: {data['a2_note']}")
            if not any_agents:
                lines.append("  ✅ No agents currently on AUX.")

        elif topic == "improvement":
            # Breached skills with full detail — actionable improvement advice
            region_cms = (cms_agents or {}).get(tag, {})
            breached   = {s: d for s, d in skills.items()
                          if d.get("breached") or d.get("band") in ("CRITICAL", "SEVERE")}
            if not breached:
                # Include WARNING too as lower-priority items
                warning = {s: d for s, d in skills.items() if d.get("band") == "WARNING"}
                if warning:
                    lines.append("  No CRITICAL/SEVERE breaches. WARNING skills (at risk):")
                    breached = warning
                else:
                    lines.append("  ✅ All skills healthy — no improvements needed right now.")

            for skill, data in breached.items():
                lines.append(
                    f"  {skill}: SLA={data['sla']}% ({data['band']}) | "
                    f"Queue={data['queue']} calls | OCW={data['ocw']} | "
                    f"Avail={data['avail']} agents available | "
                    f"AUX={data['on_aux']} on AUX | OnCalls={data['on_calls']}"
                )
                if data.get("breach_reasons"):
                    lines.append(f"    Breach triggers: {data['breach_reasons']}")
                if data.get("root_cause"):
                    lines.append(f"    Root cause: {data['root_cause']}")
                if data.get("a2_note"):
                    lines.append(f"    A2 analysis: {data['a2_note']}")
                if data.get("last_move"):
                    lines.append(f"    A2 move recommendation: {data['last_move']}")
                if data.get("last_ask"):
                    lines.append(f"    A2 ask recommendation: {data['last_ask']}")
                if data.get("lever_fired"):
                    lines.append(f"    Lever already fired: {data['lever_fired']}")

                # AUX agents for this skill — the main lever for immediate SLA recovery
                skill_agents = region_cms.get(skill, [])
                aux_agents   = [a for a in skill_agents
                                if a.get("state", "").upper() in ("AUX", "AUX ")]
                if aux_agents:
                    lines.append(f"    AUX agents who can be pulled back immediately:")
                    for a in aux_agents:
                        aux_label = a.get("aux_name") or a.get("aux_reason") or "AUX"
                        mins      = a.get("time_minutes", 0)
                        duration  = f"{mins:.0f} min" if mins else "< 1 min"
                        lines.append(
                            f"      → {a['name']} — {aux_label} — {duration}"
                        )
                elif data["on_aux"] > 0:
                    lines.append(
                        f"    {data['on_aux']} agent(s) on AUX — names unavailable "
                        f"(CMS data pending). Consider pulling back from AUX."
                    )

        elif topic == "summary":
            # One line per skill -- all regions comparison
            for skill, data in skills.items():
                lines.append(
                    f"  {skill}: SLA={data['sla']}% ({data['band']}) | "
                    f"Queue={data['queue']}"
                )

        else:
            # Full snapshot for the region
            for skill, data in skills.items():
                lines.append(
                    f"  {skill}: SLA={data['sla']}% ({data['band']}) | "
                    f"Queue={data['queue']} | OCW={data['ocw']} | "
                    f"Avail={data['avail']} | AUX={data['on_aux']} | "
                    f"Lever={data.get('lever_fired','none')} | "
                    f"RootCause={data.get('root_cause','')}"
                )
            breached_count = region.get("breached_count", 0)
            lines.append(f"  Breached skills: {breached_count}")

        lines.append("")

    context = "\n".join(lines)

    # ── Guard against 413 "Request too large" on Groq 8k-context models ───────
    # llama-3.1-8b-instant: 8,192 token context. Rules (~600 tok) + question (~50 tok)
    # + safety = ~1,500 tokens overhead → ~6,700 tokens left for context = ~26,800 chars.
    # Cap at 22,000 chars to leave headroom.
    _MAX_CONTEXT_CHARS = 22_000
    if len(context) > _MAX_CONTEXT_CHARS:
        context = context[:_MAX_CONTEXT_CHARS] + "\n\n...[context truncated — too large for model]"
        logger.warning(f"_build_context: truncated to {_MAX_CONTEXT_CHARS} chars")

    return context


def _build_history_context(question: str) -> str:
    """
    For history mode: use LLM to generate SQL, run it on history.db,
    return results as context string for the answer LLM.
    """
    try:
        from core.history import get_schema, query as db_query
    except Exception as e:
        return f"History database not available: {e}"

    schema = get_schema()
    now = datetime.now()

    # ── Normalise synonyms so the LLM sees clean keywords ────────────────────
    import re as _re
    from datetime import timedelta as _td
    _synonyms = [
        (r'\b(last day|prior day|previous day|day before)\b', 'yesterday'),
        (r'\b(last week)\b',                                  'past 7 days'),
        (r'\b(this morning)\b',                               'today before 12pm'),
        (r'\b(this afternoon)\b',                             'today after 12pm'),
    ]
    q_normalised = question
    for pattern, replacement in _synonyms:
        q_normalised = _re.sub(pattern, replacement, q_normalised, flags=_re.IGNORECASE)
    question = q_normalised

    today_str     = now.strftime("%Y-%m-%d")
    yesterday_str = (now - _td(days=1)).strftime("%Y-%m-%d")
    now_str       = now.strftime("%Y-%m-%d %H:%M:%S")

    # ── Python resolves the date range — LLM must NOT guess dates ─────────────
    # Inject an explicit DATE CONSTRAINT line so the LLM just copies it verbatim.
    _q_lower = question.lower()
    if "yesterday" in _q_lower:
        _date_constraint = (
            f"MANDATORY DATE CONSTRAINT (copy this exactly into WHERE clause): "
            f"date(timestamp) = '{yesterday_str}'"
        )
    elif "today" in _q_lower:
        _date_constraint = (
            f"MANDATORY DATE CONSTRAINT (copy this exactly into WHERE clause): "
            f"date(timestamp) = '{today_str}'"
        )
    elif _re.search(r'\bpast (\d+) days?\b', _q_lower):
        _days = int(_re.search(r'\bpast (\d+) days?\b', _q_lower).group(1))
        _since = (now - _td(days=_days)).strftime("%Y-%m-%d")
        _date_constraint = (
            f"MANDATORY DATE CONSTRAINT (copy this exactly into WHERE clause): "
            f"date(timestamp) >= '{_since}'"
        )
    else:
        _date_constraint = (
            f"No date constraint required — use only filters implied by the question."
        )

    # Step 1: LLM generates SQL
    from core.prompt_loader import load_prompt, clear_cache
    clear_cache()   # always reload prompt files — no stale templates
    sql_prompt = load_prompt(
        "chatbot_sql_gen",
        now_str=now_str,
        today_str=today_str,
        yesterday_str=yesterday_str,
        date_constraint=_date_constraint,
        schema=schema,
        question=question,
    )

    sql = _call_llm_raw(sql_prompt, max_tokens=200, is_sql=True)
    # Strip markdown fences the LLM sometimes adds anyway
    sql = sql.strip()
    for prefix in ("```sql", "```sqlite", "```", "sql\n", "sqlite\n"):
        if sql.lower().startswith(prefix):
            sql = sql[len(prefix):].strip()
    if sql.endswith("```"):
        sql = sql[:-3].strip()

    logger.info(f"[chat/history] Generated SQL: {sql}")

    # Guardrail — validate SQL before running
    from core.guardrails import validate_sql
    ok, result = validate_sql(sql)
    if not ok:
        logger.warning(f"[chat/history] SQL guardrail blocked: {result}")
        return f"Could not generate a safe SQL query: {result}"

    # Step 2: Run the SQL
    try:
        rows = db_query(sql)
    except Exception as e:
        return f"SQL query failed: {e}\nSQL was: {sql}"

    if not rows:
        # Give a helpful reason if it looks like a future-time query
        current_hour = now.hour
        time_match = __import__('re').search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', question.lower())
        hint = ""
        if time_match:
            h = int(time_match.group(1))
            ampm = time_match.group(3)
            if not ampm and 1 <= h <= 8:
                h += 12  # business hours assumption
            if h > current_hour:
                hint = f" (Note: {h}:00 hasn't happened yet today — current time is {now.strftime('%I:%M %p')})"
        return (
            f"No historical data found for this query.{hint}\n"
            f"Try rephrasing — e.g. use 'yesterday' for past data, or check the region/skill name."
        )

    # Step 3: Format rows — use smart aggregation for range queries to save tokens
    import re as _re2
    from datetime import datetime as _dt

    _is_range_q = bool(_re2.search(
        r'\b(yesterday|today|last day|past \d|last \d|all day|entire day|full day|'
        r'morning|afternoon|how did|performance|summary|overview|trend)\b',
        question, _re2.IGNORECASE
    ))

    region_map = {
        "rta":  "India",
        "cn":   "China",
        "au":   "Australia",
        "emea": "EMEA",
        "hk":   "Hong Kong",
        "my":   "Malaysia",
        "kr":   "Korea",
        "th":   "Thailand",
        "br":   "Brazil",
        "tw":   "Taiwan",
    }

    def _fmt_ts(ts):
        try:
            return _dt.strptime(str(ts), "%Y-%m-%d %H:%M:%S").strftime("%b %d %I:%M %p")
        except Exception:
            return str(ts)

    if _is_range_q and len(rows) > 5:
        # ── Aggregate into a compact summary (saves ~80% tokens vs raw rows) ──
        sla_vals   = [float(r["sla"]) for r in rows if r.get("sla") is not None]
        queue_vals = [int(r["queue"]) for r in rows if r.get("queue") is not None]

        band_counts = {}
        for r in rows:
            b = r.get("band") or "UNKNOWN"
            band_counts[b] = band_counts.get(b, 0) + 1

        lever_fires = [
            f'{r.get("lever_fired")} on {r.get("skill","?")} at {_fmt_ts(r.get("timestamp",""))}'
            for r in rows if r.get("lever_fired") and r["lever_fired"] not in ("None", "", None)
        ]

        root_causes = list({r.get("root_cause") for r in rows
                            if r.get("root_cause") and r["root_cause"] not in ("", None)})

        # Worst 5 readings (lowest SLA)
        sorted_by_sla = sorted(
            [r for r in rows if r.get("sla") is not None],
            key=lambda r: float(r["sla"])
        )
        worst_5 = sorted_by_sla[:5]

        # Best 3 readings (highest SLA — shows recovery)
        best_3 = sorted_by_sla[-3:]

        region_tag = rows[0].get("region_tag", "")
        region     = region_map.get(region_tag, region_tag.upper())
        skill_name = rows[0].get("skill", "")
        date_label = _fmt_ts(rows[0].get("timestamp", ""))[:6]  # "Jun 08"

        lines = [
            f"REGION KEY: rta=India | cn=China | au=Australia | emea=EMEA | hk=Hong Kong | my=Malaysia | kr=Korea | th=Thailand | br=Brazil | tw=Taiwan",
            f"",
            f"AGGREGATED DAY SUMMARY — {region} / {skill_name} — {date_label}",
            f"Total readings: {len(rows)}",
            f"SLA min: {min(sla_vals):.1f}%  |  SLA max: {max(sla_vals):.1f}%  |  SLA avg: {sum(sla_vals)/len(sla_vals):.1f}%",
            f"Queue peak: {max(queue_vals) if queue_vals else 'N/A'}",
            f"Time in bands: " + " | ".join(f"{b}={c} readings" for b, c in sorted(band_counts.items())),
            f"",
            f"LEVER FIRES ({len(lever_fires)} total):",
        ] + (lever_fires if lever_fires else ["  None recorded"]) + [
            f"",
            f"ROOT CAUSES: {', '.join(root_causes) if root_causes else 'None recorded'}",
            f"",
            f"WORST 5 READINGS (lowest SLA):",
        ]
        for r in worst_5:
            region_r = region_map.get(r.get("region_tag",""), r.get("region_tag","").upper())
            lines.append(
                f"  [{_fmt_ts(r.get('timestamp',''))}] SLA={r.get('sla')}% ({r.get('band','')}) "
                f"Queue={r.get('queue','')} Lever={r.get('lever_fired') or 'None'}"
            )
        lines += ["", "BEST 3 READINGS (highest SLA — shows recovery):"]
        for r in best_3:
            lines.append(
                f"  [{_fmt_ts(r.get('timestamp',''))}] SLA={r.get('sla')}% ({r.get('band','')}) "
                f"Queue={r.get('queue','')} Lever={r.get('lever_fired') or 'None'}"
            )

        context = "\n".join(lines)
        if len(context) > 4000:
            context = context[:4000] + "\n...[truncated]"
        return context

    # ── Point query: list individual rows (unchanged) ─────────────────────────
    MAX_ROWS = 15
    lines = [
        "REGION KEY: rta=India | cn=China | au=Australia | emea=EMEA | hk=Hong Kong | my=Malaysia | kr=Korea | th=Thailand | br=Brazil | tw=Taiwan",
        "",
        "HISTORICAL RTA DATA from database:",
        f"Total matching records: {len(rows)} (showing top {min(len(rows), MAX_ROWS)})",
        "",
    ]

    for row in rows[:MAX_ROWS]:
        region_tag = row.get("region_tag", "")
        region     = region_map.get(region_tag, region_tag.upper())
        skill      = row.get("skill", "")
        sla        = row.get("sla", "")
        band       = row.get("band", "")
        queue      = row.get("queue", "")
        lever      = row.get("lever_fired") or "None"
        root_cause = row.get("root_cause") or ""
        breach     = "YES" if row.get("breached") else "no"

        line = (
            f"[{_fmt_ts(row.get('timestamp',''))}] {region} / {skill}: "
            f"SLA={sla}% ({band}) | Queue={queue} | "
            f"Lever={lever} | Breached={breach}"
        )
        if root_cause:
            line += f" | Cause={root_cause}"
        lines.append(line)

    context = "\n".join(lines)
    if len(context) > 3000:
        context = context[:3000] + "\n...[truncated]"
    return context


def _get_nvidia_keys() -> list:
    """Return list of (api_key, base_url, model) tuples — one per configured NVIDIA key."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, "config.env"), override=True)
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
    model    = os.getenv("NVIDIA_MODEL",    "meta/llama-3.3-70b-instruct").strip()
    keys = []
    for i in range(1, 10):   # supports NVIDIA_API_KEY_1 through _9
        k = os.getenv(f"NVIDIA_API_KEY_{i}", "").strip()
        if k and len(k) > 20:
            keys.append((k, base_url, model))
    # Backward-compat: also check legacy NVIDIA_API_KEY (no suffix)
    legacy = os.getenv("NVIDIA_API_KEY", "").strip()
    if legacy and len(legacy) > 20 and not any(legacy == t[0] for t in keys):
        keys.append((legacy, base_url, model))
    return keys


def _get_groq_keys() -> list:
    """Groq keys — primary for chat."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, "config.env"), override=True)
    keys = []
    for i in range(1, 10):   # supports GROQ_API_KEY_1 through _9
        k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if k and not k.startswith("gsk_...") and len(k) > 20:
            keys.append(k)
    return keys


def _call_llm_raw(prompt: str, max_tokens: int = 1200, is_sql: bool = False) -> str:
    """
    PRIMARY  : Groq round-robin across all configured keys (fast, ~1-3s).
    FALLBACK : NVIDIA NIM if every Groq key is rate-limited (429).
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, "config.env"), override=True)

    temp         = 0.1 if is_sql else 0.2
    import requests as req

    # ── Primary: Groq round-robin ─────────────────────────────────────────
    keys = _get_groq_keys()
    # SQL generation: use fast 8b model (short prompt, fits 8k context easily)
    # Chat answer:    use large-context model — chat prompt includes rules.yaml +
    #                 full region context which can exceed 8k tokens on 8b-instant.
    # Override via GROQ_MODEL_CHAT in config.env. Default: llama-3.3-70b-versatile (32k ctx).
    model_sql    = os.getenv("GROQ_MODEL",      "llama-3.1-8b-instant")
    model_answer = os.getenv("GROQ_MODEL_CHAT", "llama-3.3-70b-versatile")
    model        = model_sql if is_sql else model_answer

    groq_errors = []
    if keys:
        for idx, api_key in enumerate(keys):
            try:
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}",
                             "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temp,
                    },
                    timeout=30,
                )
                if resp.status_code == 429:
                    groq_errors.append(f"key{idx+1}:429")
                    logger.warning(f"Groq key {idx+1} rate-limited, rotating")
                    time.sleep(0.5)
                    continue
                if not resp.ok:
                    groq_errors.append(f"key{idx+1}:HTTP{resp.status_code}")
                    logger.error(f"Groq key {idx+1} HTTP {resp.status_code}: {resp.text[:120]}")
                    continue
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                groq_errors.append(f"key{idx+1}:{type(e).__name__}")
                logger.error(f"Groq key {idx+1} exception: {e}")
                if "429" in str(e):
                    time.sleep(0.5)
                continue
        logger.warning(f"All Groq keys exhausted ({groq_errors}) — trying NVIDIA NIM fallback")
    else:
        logger.warning("No Groq keys configured — trying NVIDIA NIM")

    # ── Fallback: NVIDIA NIM (rotate through all configured keys) ────────────
    nvidia_keys  = _get_nvidia_keys()
    nvidia_errors = []

    if nvidia_keys:
        for nidx, (nvidia_key, nvidia_base_url, nvidia_model) in enumerate(nvidia_keys):
            try:
                resp = req.post(
                    f"{nvidia_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {nvidia_key}",
                             "Content-Type": "application/json"},
                    json={
                        "model":       nvidia_model,
                        "messages":    [{"role": "user", "content": prompt}],
                        "max_tokens":  max_tokens,
                        "temperature": temp,
                        "top_p":       0.7,
                        "stream":      False,
                    },
                    timeout=30,
                )
                if resp.status_code == 429:
                    nvidia_errors.append(f"nvkey{nidx+1}:429")
                    logger.warning(f"NVIDIA key {nidx+1} rate-limited, rotating")
                    time.sleep(0.5)
                    continue
                if resp.status_code == 401:
                    nvidia_errors.append(f"nvkey{nidx+1}:401-auth")
                    logger.error(f"NVIDIA key {nidx+1} auth error (401) — skipping")
                    continue
                if not resp.ok:
                    nvidia_errors.append(f"nvkey{nidx+1}:HTTP{resp.status_code}")
                    logger.error(f"NVIDIA key {nidx+1} HTTP {resp.status_code}")
                    continue
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                nvidia_errors.append(f"nvkey{nidx+1}:{type(e).__name__}")
                logger.error(f"NVIDIA key {nidx+1} exception: {e}")
                continue
        logger.error(f"All NVIDIA keys failed: {nvidia_errors}")
    else:
        nvidia_errors = ["no NVIDIA keys configured"]

    logger.error(f"All providers failed. Groq: {groq_errors} | NVIDIA: {nvidia_errors}")
    return (f"⚠️ All LLM providers unavailable.\n"
            f"Groq ({len(keys)} keys): {', '.join(groq_errors) or 'no keys tried'}\n"
            f"NVIDIA ({len(nvidia_keys)} keys): {', '.join(nvidia_errors)}")


def _call_llm_for_chat(question: str, context: str) -> str:
    """Call LLM for final answer generation (quality model)."""
    from core.prompt_loader import load_prompt, clear_cache
    prompt = load_prompt("chatbot_answer", context=context, question=question)
    return _call_llm_raw(prompt, max_tokens=1500, is_sql=False)


import re as _re_intent

# Words/patterns that mean the user is asking about the PAST (needs history DB).
# Includes same-day-past-hours phrasing ("an hour ago", "at 11am", "earlier today").
_PAST_PATTERNS = [
    r'\byesterday\b', r'\blast night\b', r'\bearlier\b', r'\bago\b',
    r'\bprevious(ly)?\b', r'\bprior\b', r'\bpast\b', r'\bhistor(y|ical)\b',
    r'\bover the (day|week|month|hour)\b', r'\bsince\b', r'\btrend(s|ing|ed)?\b',
    r'\bused to\b', r'\bback then\b', r'\bso far today\b',
    r'\bthis morning\b', r'\bthis afternoon\b', r'\bearlier today\b',
    r'\blast (week|month|hour|\d+\s*(hours?|hrs?|days?|minutes?|mins?))\b',
    r'\b(was|were|had|did)\b',                       # past-tense verbs
    r'\bat \d{1,2}\s*(?::\d{2})?\s*(am|pm)\b',        # "at 11am", "at 9:30 pm"
    r'\b\d+\s*(hours?|hrs?|minutes?|mins?|days?)\s+ago\b',
    r'\b(mon|tues|wednes|thurs|fri|satur|sun)day\b',  # day names
    r'\b\d{4}-\d{2}-\d{2}\b',                          # ISO date
]

# Words/patterns that mean the user is asking about the PRESENT (live data only).
_PRESENT_PATTERNS = [
    r'\b(right )?now\b', r'\bcurrent(ly)?\b', r'\blive\b',
    r'\bat (the |this )?moment\b', r'\bas of now\b', r'\bat present\b',
    r'\bat the moment\b', r'\bthis (second|instant)\b',
]


def _detect_temporal_intent(question: str) -> str:
    """
    Classify whether a question is about the past, the present, or neither.
    Used to route the chatbot: live mode can't answer past questions, and
    history mode can't answer live ones. Returns 'past' | 'present' | 'neutral'.
    Past signals win ties (e.g. "what was the SLA right now" → past).
    """
    q = (question or "").lower()
    if any(_re_intent.search(p, q) for p in _PAST_PATTERNS):
        return "past"
    if any(_re_intent.search(p, q) for p in _PRESENT_PATTERNS):
        return "present"
    return "neutral"


def _suggest_followups(question: str, mode: str) -> list:
    """
    Generate up to 3 deeper follow-up questions for the given question/mode.
    Best-effort — returns [] on any failure so it never blocks the answer.
    """
    try:
        from core.prompt_loader import load_prompt
        mode_desc = ("answers from current real-time dashboard data only"
                     if mode == "live"
                     else "answers from the 7-day historical SQLite database")
        prompt = load_prompt("chatbot_suggest", mode=mode, mode_desc=mode_desc,
                             question=question)
        raw = _call_llm_raw(prompt, max_tokens=120, is_sql=True)
        if not raw or raw.startswith("⚠️"):
            return []
        out = []
        for line in raw.splitlines():
            # Strip leading numbering / bullets / quotes the model may add
            line = _re_intent.sub(r'^\s*(\d+[\.\)]|[-*•])\s*', '', line).strip()
            line = line.strip('"').strip("'").strip()
            if line and len(line) > 5:
                out.append(line)
        return out[:3]
    except Exception as e:
        logger.warning(f"suggestion generation failed: {e}")
        return []


@app.route("/legacy/chat")
def chat_page():
    return render_template_string(
        BASE_HTML, title="RTA Chatbot", page="chat",
        content=Markup(CHAT_CONTENT), extra_js=Markup("")
    )


@app.route("/legacy/chat-js")
def chat_js():
    js = (
        "var STORAGE_KEY = 'rta_chat_history';\n"
        "\n"
        "var chatMode = sessionStorage.getItem('chatMode') || 'live';\n"
        "\n"
        "function setMode(mode) {\n"
        "  chatMode = mode;\n"
        "  sessionStorage.setItem('chatMode', mode);\n"
        "  if (mode === 'live') {\n"
        "    document.getElementById('modeLive').className = 'btn btn-success btn-sm px-3';\n"
        "    document.getElementById('modeHistory').className = 'btn btn-outline-secondary btn-sm px-3';\n"
        "    document.getElementById('modeLabel').textContent = 'Currently: Live Data';\n"
        "  } else {\n"
        "    document.getElementById('modeLive').className = 'btn btn-outline-secondary btn-sm px-3';\n"
        "    document.getElementById('modeHistory').className = 'btn btn-primary btn-sm px-3';\n"
        "    document.getElementById('modeLabel').textContent = 'Currently: History (7 days)';\n"
        "  }\n"
        "}\n"
        "setMode(chatMode);\n"
        "\n"
        "function saveHistory() {\n"
        "  var box = document.getElementById('chatMessages');\n"
        "  sessionStorage.setItem(STORAGE_KEY, box.innerHTML);\n"
        "}\n"
        "\n"
        "function loadHistory() {\n"
        "  var saved = sessionStorage.getItem(STORAGE_KEY);\n"
        "  if (saved) {\n"
        "    document.getElementById('chatMessages').innerHTML = saved;\n"
        "    var box = document.getElementById('chatMessages');\n"
        "    box.scrollTop = box.scrollHeight;\n"
        "  }\n"
        "}\n"
        "\n"
        "loadHistory();\n"
        "\n"
        "document.getElementById('sendBtn').addEventListener('click', sendChat);\n"
        "document.getElementById('chatInput').addEventListener('keydown', function(e) {\n"
        "  if (e.key === 'Enter') sendChat();\n"
        "});\n"
        "document.getElementById('clearBtn').addEventListener('click', function() {\n"
        "  sessionStorage.removeItem(STORAGE_KEY);\n"
        "  document.getElementById('chatMessages').innerHTML ="
        "    '<div class=\"text-muted small text-center mt-4\">Ask a question about your live RTA data...</div>';\n"
        "});\n"
        "\n"
        "function sendChat() {\n"
        "  var input = document.getElementById('chatInput');\n"
        "  var question = input.value.trim();\n"
        "  if (!question) return;\n"
        "  input.value = '';\n"
        "  var ph = document.getElementById('chatPlaceholder');\n"
        "  if (ph) ph.remove();\n"
        "  appendMessage('user', question);\n"
        "  var thinkDiv = appendMessage('bot', '⏳ Thinking...');\n"
        "  fetch('/api/chat', {\n"
        "    method: 'POST',\n"
        "    headers: {'Content-Type': 'application/json'},\n"
        "    body: JSON.stringify({question: question, mode: chatMode})\n"
        "  })\n"
        "  .then(function(r) {\n"
        "    if (!r.ok) throw new Error('Server error ' + r.status);\n"
        "    return r.json();\n"
        "  })\n"
        "  .then(function(data) {\n"
        "    thinkDiv.innerHTML = '<strong>RTA Bot:</strong> ' + (data.answer || 'No response.').replace(/\\n/g, '<br>');\n"
        "    saveHistory();\n"
        "  })\n"
        "  .catch(function(err) {\n"
        "    thinkDiv.innerHTML = '<strong>RTA Bot:</strong> Error: ' + err.message;\n"
        "    thinkDiv.style.background = '#fff3cd';\n"
        "    saveHistory();\n"
        "  });\n"
        "}\n"
        "\n"
        "function appendMessage(role, text) {\n"
        "  var box = document.getElementById('chatMessages');\n"
        "  var div = document.createElement('div');\n"
        "  if (role === 'user') {\n"
        "    div.style.cssText = 'background:#e3f2fd;border-radius:10px;padding:10px 14px;margin:8px 0;margin-left:20%';\n"
        "    div.innerHTML = '<strong>You:</strong> ' + text;\n"
        "  } else {\n"
        "    div.style.cssText = 'background:#f5f5f5;border-radius:10px;padding:10px 14px;margin:8px 0;margin-right:20%';\n"
        "    div.innerHTML = '<strong>RTA Bot:</strong> ' + text;\n"
        "  }\n"
        "  box.appendChild(div);\n"
        "  box.scrollTop = box.scrollHeight;\n"
        "  return div;\n"
        "}\n"
    )
    from flask import Response
    return Response(js, mimetype="application/javascript")


# ── React SPA ─────────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path):
    """Serve React SPA — static assets served directly, everything else gets index.html."""
    dist = os.path.join(BASE_DIR, "ui", "dist")

    # Build not ready yet
    if not os.path.isdir(dist) or not os.path.isfile(os.path.join(dist, "index.html")):
        return (
            "<h2 style='font-family:monospace;padding:40px;color:#e74c3c'>"
            "React app not built yet.<br><br>"
            "Run inside RTA_Final/frontend/:<br>"
            "<code>npm run build</code></h2>",
            503,
        )

    # Serve real files (JS/CSS/assets) directly
    if path:
        candidate = os.path.join(dist, path)
        if os.path.isfile(candidate):
            return send_from_directory(dist, path)

    # All other paths → SPA entry point (React Router handles routing)
    return send_from_directory(dist, "index.html")


# ── REST API routes ────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    global _run_mode, _process
    state = get_status()
    return jsonify({
        "state":        state,
        "mode":         _run_mode,
        "last_checked": datetime.now().strftime("%I:%M:%S %p"),
    })


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(force=True) or {}
    mode = data.get("mode", "full")
    ok, msg = start_system(mode)
    _emit_status()
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    ok, msg = stop_system()
    _emit_status()
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/restart", methods=["POST"])
def api_restart():
    data = request.get_json(force=True) or {}
    mode = data.get("mode", None)
    ok, msg = restart_system(mode)
    _emit_status()
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/live")
def api_live():
    """Return the current live_state.json as JSON."""
    try:
        p = LIVE_STATE_PATH
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
    except Exception:
        pass
    return jsonify({})


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": list(_log_lines)})


@app.route("/api/regions", methods=["GET", "POST"])
def api_regions():
    cfg = load_cfg()
    if request.method == "GET":
        return jsonify({"regions": cfg.get("regions", [])})
    data = request.get_json(force=True) or {}
    cfg["regions"] = data.get("regions", [])
    save_cfg(cfg)
    return jsonify({"ok": True})


@app.route("/api/agents", methods=["GET", "POST"])
def api_agents():
    cfg = load_cfg()
    if request.method == "GET":
        return jsonify({
            "agent1": cfg.get("agent1", {}),
            "agent2": cfg.get("agent2", {}),
            "agent3": cfg.get("agent3", {}),
            "agent4": cfg.get("agent4", {}),
        })
    data = request.get_json(force=True) or {}
    for key in ["agent1", "agent2", "agent3", "agent4"]:
        if key in data:
            cfg[key] = data[key]
    save_cfg(cfg)
    return jsonify({"ok": True})


@app.route("/api/cms_agents")
def api_cms_agents():
    """Return cms_agents.json enriched with per-agent breach flags."""
    raw = _load_cms_agents()
    if not raw:
        return jsonify({})

    cfg            = load_cfg()
    aux_thresholds = cfg.get("agent4", {}).get("aux_thresholds", {})
    acw_target_min = cfg.get("agent4", {}).get("acw_target_min", 5)
    a4_aht_global  = cfg.get("agent4", {}).get("aht_target_min", 0)
    skill_thresh   = cfg.get("skill_thresholds", {})

    result = {}
    for region_tag, skills_data in raw.items():
        result[region_tag] = {}
        for skill_name, agents in skills_data.items():
            sk_cfg         = skill_thresh.get(skill_name, {})
            aht_target_min = sk_cfg.get("aht_target_min") or a4_aht_global or 24
            aht_breach_min = aht_target_min * 1.10

            enriched = []
            for a in agents:
                d     = dict(a)
                state = a.get("state", "")
                t_min = a.get("time_minutes", 0)
                d["breach"] = False

                if state == "AUX":
                    ax_cfg   = aux_thresholds.get(a.get("aux_key", ""), {})
                    max_time = ax_cfg.get("max_time_min", 0)
                    if ax_cfg.get("enabled", False) and max_time > 0 and t_min > max_time:
                        d["breach"] = True
                elif state == "ACD" and aht_breach_min > 0 and t_min > aht_breach_min:
                    d["breach"] = True
                elif state == "ACW" and acw_target_min > 0 and t_min > acw_target_min:
                    d["breach"] = True

                enriched.append(d)
            result[region_tag][skill_name] = enriched

    return jsonify(result)


@app.route("/api/skills", methods=["GET", "POST"])
def api_skills():
    cfg = load_cfg()
    if request.method == "GET":
        return jsonify({
            "skills": cfg.get("skill_thresholds", {}),
            "region_map": SKILL_REGION_MAP,
        })
    data = request.get_json(force=True) or {}
    cfg["skill_thresholds"] = data.get("skills", cfg.get("skill_thresholds", {}))
    save_cfg(cfg)
    return jsonify({"ok": True})


@app.route("/api/env", methods=["GET", "POST"])
def api_env():
    """GET: return config.env as dict (keys visible, values masked for keys).
       POST: save new values to config.env."""
    if request.method == "GET":
        env = load_env()
        # Mask secret values
        masked = {}
        for k, v in env.items():
            if any(s in k.upper() for s in ("KEY", "SECRET", "PASS", "WEBHOOK")):
                masked[k] = v  # send actual value so form can edit it
            else:
                masked[k] = v
        return jsonify({"env": masked})

    data = request.get_json(force=True) or {}
    new_env = data.get("env", {})
    try:
        existing = load_env()
        existing.update({k: v for k, v in new_env.items() if v})
        lines_out = []
        for k, v in existing.items():
            lines_out.append(f"{k}={v}")
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines_out) + "\n")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/thresholds", methods=["GET", "POST"])
def api_thresholds():
    """GET/POST skill threshold config from config.json."""
    cfg = load_cfg()
    skills_cfg = cfg.get("skills", {})

    if request.method == "GET":
        return jsonify({"thresholds": skills_cfg})

    data = request.get_json(force=True) or {}
    cfg["skills"] = data.get("thresholds", skills_cfg)
    save_cfg(cfg)
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Unified chat endpoint for React frontend (same logic as /chat POST)."""
    data     = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    mode     = data.get("mode", "live")
    if not question:
        return jsonify({"answer": "Please enter a question.", "suggestions": []})

    intent = _detect_temporal_intent(question)

    # ── Live mode + question about the past → don't guess, send them to History ──
    if mode == "live" and intent == "past":
        answer = (
            "🕑 That looks like a question about **past data**, but I'm in **Live mode** — "
            "I only have the current poll, not history.\n\n"
            "👉 Switch to **History mode** (toggle at the top-right) and ask again to get accurate "
            "past data."
        )
        return jsonify({
            "answer": answer,
            "suggestions": _suggest_followups(question, "history"),
            "notice": "switch_to_history",
        })

    if mode == "history":
        context = _build_history_context(question)
        answer  = _call_llm_for_chat(question, context)
        # ── History mode + question about the live/current situation → caveat ────
        if intent == "present":
            answer = (
                "⚠️ I don't have **current live data** in History mode, so this may not reflect "
                "the real-time situation — but based on the **latest available past data**, this "
                "may help:\n\n" + answer
            )
    else:
        live_state = _load_live_state()
        cms_agents = _load_cms_agents()
        context    = _build_context(question, live_state, cms_agents)
        answer     = _call_llm_for_chat(question, context)

    return jsonify({
        "answer": answer,
        "suggestions": _suggest_followups(question, mode),
    })


# ── SocketIO events ────────────────────────────────────────────────────────────

def _emit_status():
    socketio.emit("status_update", {
        "state":        get_status(),
        "mode":         _run_mode,
        "last_checked": datetime.now().strftime("%I:%M:%S %p"),
    })


def _background_push():
    """Push live_state + new log lines to all connected clients every 5s."""
    last_log_count = 0
    while True:
        socketio.sleep(5)
        try:
            # Push live state
            if os.path.exists(LIVE_STATE_PATH):
                with open(LIVE_STATE_PATH, "r", encoding="utf-8") as f:
                    socketio.emit("live_update", json.load(f))
            # Push new log lines since last push
            current = list(_log_lines)
            if len(current) > last_log_count:
                for line in current[last_log_count:]:
                    socketio.emit("log_line", line)
                last_log_count = len(current)
            elif len(current) < last_log_count:
                last_log_count = len(current)  # reset on clear
        except Exception:
            pass


@socketio.on("connect")
def on_connect():
    # Send current state immediately on connect
    try:
        if os.path.exists(LIVE_STATE_PATH):
            with open(LIVE_STATE_PATH, "r", encoding="utf-8") as f:
                emit("live_update", json.load(f))
    except Exception:
        pass
    emit("status_update", {
        "state":        get_status(),
        "mode":         _run_mode,
        "last_checked": datetime.now().strftime("%I:%M:%S %p"),
    })


# -- Run -----------------------------------------------------------------------

if __name__ == "__main__":
    # Start background push thread
    socketio.start_background_task(_background_push)
    print("=" * 50)
    print("  RTA Monitor UI  (React + Dark Theme)")
    print("  Open: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)