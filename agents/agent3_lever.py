"""
agents/agent3_lever.py
Agent 3 — Lever Generator

Triggered by Agent 1 when SLA crosses threshold:
  91% → below 90% = Amber Lever
  80% → below 80% = Red Lever
  70% → below 70% = Black Lever

Flow:
  1. Receives skill name + current metrics from state
  2. Reads Excel KPI sheet for that skill (today's 30-min intervals)
  3. Sends context to LLM
  4. LLM generates:
     - Root cause
     - Business callouts
     - Mitigation actions
  5. Sends Lever email to managers

Fires ONCE per threshold crossing — cooldown tracked in state.
"""

import importlib.util
import json
import logging
import os
import sys
import threading
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

# Global Excel read lock — shared across ALL region module copies via sys.modules.
# When 3 regions fire A3 simultaneously they all try to open the same xlsx file.
# Windows locks the file on first open → other regions get [Errno 13] Permission denied.
# This lock serialises Excel reads so only one region reads at a time.
_EXCEL_LOCK_KEY = '__rta_excel_lock__'
if _EXCEL_LOCK_KEY not in sys.modules:
    sys.modules[_EXCEL_LOCK_KEY] = threading.Lock()
_EXCEL_LOCK = sys.modules[_EXCEL_LOCK_KEY]

def _get_a3_config():
    """Load agent3 config from config.json."""
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader_a3", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_agent3()
    except Exception:
        return {
            "amber_threshold": 90.0,
            "red_threshold":   80.0,
            "black_threshold": 70.0,
            "excel_path":      "",
            "email_recipients": [],
        }

def _get_lever_thresholds():
    """Get lever thresholds from config.json."""
    cfg = _get_a3_config()
    return [
        {"name": "Black", "below": cfg.get("black_threshold", 70.0), "color": "⚫"},
        {"name": "Red",   "below": cfg.get("red_threshold",   80.0), "color": "🔴"},
        {"name": "Amber", "below": cfg.get("amber_threshold", 90.0), "color": "🟡"},
    ]

# ── Lever threshold definitions — fallback defaults ───────────────────────────
LEVER_THRESHOLDS = [
    {"name": "Amber", "below": 90, "color": "🟡"},
    {"name": "Red",   "below": 80, "color": "🔴"},
    {"name": "Black", "below": 70, "color": "⚫"},
]

# ── AUX code reference for LLM context ───────────────────────────────────────
AUX_REFERENCE = """
AUX CODES REFERENCE:
AUX0=Available · AUX1=IT Issue · AUX2=Break(target≤15min)
AUX3=Lunch(target≤30min) · AUX4=Meeting · AUX5=Training
AUX6=Case Management · AUX7=Project · AUX8=Alt Channel · AUX9=Outbound
"""


# ── module loader ─────────────────────────────────────────────────────────────

def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    path = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Excel reader ──────────────────────────────────────────────────────────────

# ── Region → Combined Queue Name mapping ─────────────────────────────────────
REGION_TO_QUEUE = {
    "rta":  "Client ProSupport IND",
    "cn":   "Client ProSupport CHN",
    "au":   "Client ProSupport AUS",
    "emea": "Client ProSupport EMEA",
    "hk":   "Client ProSupport HKG",
    "my":   "Client ProSupport MYS",
    "kr":   "Client ProSupport KOR",
    "th":   "Client ProSupport THA",
    "br":   "Client ProSupport BRA",
    "tw":   "Client ProSupport TWN",
}


def _read_excel_for_skill(excel_path: str, skill_name: str,
                           region_tag: str = "rta") -> list:
    """
    Read today's 30-min interval rows for a region from Excel.
    Filters by Combined_Queue_Name (mapped from region_tag).
    Returns list of dicts with interval data.

    Uses temp-copy strategy to bypass OneDrive file locking:
      1. _EXCEL_LOCK acquired (serialises multi-region access)
      2. File copied to system temp folder (<100ms)
      3. _EXCEL_LOCK released immediately after copy
      4. pd.read_excel() runs on temp copy — OneDrive never touches temp files
      5. Temp file deleted after read

    This fixes [Errno 13] Permission denied caused by OneDrive holding
    the original file open during cloud sync.
    """
    import os
    import shutil
    import tempfile
    import pandas as pd

    tmp_path = None
    try:
        # Step 1+2+3: copy under lock — fast (<100ms), releases lock immediately
        logger.info(f"A3 [{region_tag}]: Waiting for Excel lock — {skill_name}")
        with _EXCEL_LOCK:
            logger.info(f"A3 [{region_tag}]: Copying Excel to temp — {skill_name}")
            tmp_path = tempfile.mktemp(suffix=".xlsx", prefix="rta_kpi_")
            shutil.copy2(excel_path, tmp_path)
        logger.info(f"A3 [{region_tag}]: Reading temp copy — lock released")

        # Step 4: read temp copy — no OneDrive, no lock contention
        df = pd.read_excel(tmp_path, sheet_name="Daily", header=2, dtype=str)

        # Map region tag to Combined_Queue_Name
        queue_name = REGION_TO_QUEUE.get(region_tag, skill_name)
        queue_col  = df.columns[0]   # first column = Combined_Queue_Name

        df_skill = df[df[queue_col].str.strip() == queue_name].copy()

        if df_skill.empty:
            logger.warning(
                f"A3: No Excel data found for queue '{queue_name}' "
                f"(region={region_tag}, skill={skill_name})"
            )
            return []

        # Convert to list of dicts — clean up NaN
        rows = []
        for _, row in df_skill.iterrows():
            row_dict = {}
            for col in df.columns:
                val = row[col]
                if str(val).lower() in ('nan', 'none', ''):
                    val = '—'
                row_dict[col] = str(val).strip()
            rows.append(row_dict)

        logger.info(f"A3: Read {len(rows)} interval rows for {skill_name} from Excel")
        return rows

    except Exception as e:
        logger.error(f"A3: Excel read failed for {skill_name}: {e}")
        return []

    finally:
        # Step 5: always delete temp file — even if read failed
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# ── Build Excel context string for LLM ───────────────────────────────────────

def _build_excel_context(rows: list, skill_name: str) -> str:
    """Build Excel context using actual column names from Voice_Queue_Intraday.xlsx"""
    if not rows:
        return f"No interval data available for {skill_name} today."

    lines = [f"TODAY\'S 30-MIN INTERVAL DATA FOR {skill_name}:"]
    lines.append(
        f"{'Interval':<10} {'SL':<8} {'Offered':<8} {'Offered%':<10} "
        f"{'AHT':<10} {'Avail%':<8} {'AUX2(Brk)':<12} "
        f"{'AUX3(Lunch)':<13} {'AUX6(CaseMgt)':<14} {'maxOCW'}"
    )
    lines.append("-" * 105)

    for row in rows:
        lines.append(
            f"{row.get('Starting','—'):<10} "
            f"{row.get('SL','—'):<8} "
            f"{row.get('callsoffered','—'):<8} "
            f"{row.get('Offered%','—'):<10} "
            f"{row.get('AHT','—'):<10} "
            f"{row.get('Avail%','—'):<8} "
            f"{row.get('i_auxtime2','—'):<12} "
            f"{row.get('i_auxtime3','—'):<13} "
            f"{row.get('i_auxtime6','—'):<14} "
            f"{row.get('maxocwtime','—')}"
        )

    return "\n".join(lines)


# ── Determine lever level ─────────────────────────────────────────────────────

def _get_lever_level(sla: float) -> dict | None:
    """Returns the highest (worst) lever threshold crossed — from config.json."""
    thresholds = _get_lever_thresholds()  # loads from config each time
    crossed    = None
    for threshold in thresholds:  # Black first (sorted worst→best)
        if sla < threshold["below"]:
            crossed = threshold
            break
    return crossed


# ── Check if this threshold was already fired ─────────────────────────────────

def _already_fired(state: dict, skill_name: str, lever_name: str) -> bool:
    """Returns True if this lever was already sent for this skill."""
    fired = state.get('a3_fired_levers', {})
    key   = f"{skill_name}_{lever_name}"
    return fired.get(key, False)


def _mark_fired(state: dict, skill_name: str, lever_name: str):
    """Mark this lever as fired so it doesn't repeat."""
    if 'a3_fired_levers' not in state:
        state['a3_fired_levers'] = {}
    state['a3_fired_levers'][f"{skill_name}_{lever_name}"] = True


def _reset_fired(state: dict, skill_name: str):
    """
    Reset fired levers for a skill when it recovers above 90%.
    So next time it drops, levers fire again.
    """
    fired = state.get('a3_fired_levers', {})
    keys_to_reset = [k for k in fired if k.startswith(f"{skill_name}_")]
    for k in keys_to_reset:
        del fired[k]
    logger.info(f"A3: Reset lever history for {skill_name} (recovered)")


# ── LLM prompt builder ────────────────────────────────────────────────────────

def _build_lever_prompt(
    region: str,
    skill_name: str,
    lever: dict,
    metric,
    excel_context: str,
    snapshot_table: str
) -> str:

    current_time = datetime.now().strftime("%I:%M %p IST")

    from core.prompt_loader import load_prompt
    return load_prompt(
        "agent3_lever",
        lever_name=lever['name'],
        lever_color=lever['color'],
        lever_below=lever['below'],
        region=region,
        skill_name=skill_name,
        sla=metric.service_level,
        current_time=current_time,
        aux_reference=AUX_REFERENCE,
        snapshot_table=snapshot_table,
        excel_context=excel_context,
    )


# ── Build snapshot table string ───────────────────────────────────────────────

def _build_snapshot_table(metric, region: str) -> str:
    return (
        f"{'Queue':<20} {'CIQ':<6} {'OCW':<8} {'Avail':<7} "
        f"{'OnCalls':<9} {'OnAUX':<7} {'SL%'}\n"
        f"{'─'*70}\n"
        f"{metric.skill_name:<20} {metric.calls_waiting:<6} {metric.ocw:<8} "
        f"{metric.agents_available:<7} {metric.agents_on_calls:<9} "
        f"{metric.agents_on_aux:<7} {metric.service_level:.1f}%"
    )


# ── KPI parsing + day aggregation for the rich HTML email ────────────────────
import re as _re3


def _to_int(s) -> int:
    try:
        return int(float(_re3.sub(r'[^\d.\-]', '', str(s)) or 0))
    except Exception:
        return 0


def _pct_val(s):
    v = _re3.sub(r'[^\d.\-]', '', str(s))
    try:
        return float(v) if v not in ('', '.', '-') else None
    except Exception:
        return None


def _hms_to_sec(s) -> int:
    try:
        parts = [int(p) for p in str(s).strip().split(':')]
    except Exception:
        return 0
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0


def _sec_to_hms(n: int) -> str:
    n = int(n)
    h, rem = divmod(n, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _sl_band_color(sla: float) -> str:
    """SL value → band colour, using the same thresholds as the levers (config.json)."""
    cfg = _get_a3_config()
    if sla >= cfg.get("amber_threshold", 90.0): return "#2e7d32"   # green
    if sla >= cfg.get("red_threshold",   80.0): return "#f9a825"   # amber
    if sla >= cfg.get("black_threshold", 70.0): return "#d32f2f"   # red
    return "#212121"                                               # black


def _aggregate_excel_day(rows: list) -> dict:
    """Aggregate today's 30-min interval rows into one day-total snapshot."""
    if not rows:
        return {}
    offered_total = sum(_to_int(r.get('callsoffered')) for r in rows)
    handled_total = sum(_to_int(r.get('acdcalls')) for r in rows)

    def _wavg_pct(col, weight_col='callsoffered'):
        num = den = 0.0
        for r in rows:
            v = _pct_val(r.get(col))
            if v is not None:
                w = _to_int(r.get(weight_col)) or 1
                num += v * w
                den += w
        return (num / den) if den else None

    def _wavg_sec(col, weight_col):
        num = den = 0.0
        for r in rows:
            sec = _hms_to_sec(r.get(col))
            if sec:
                w = _to_int(r.get(weight_col)) or 1
                num += sec * w
                den += w
        return int(num / den) if den else 0

    def _fp(v):
        return f"{v:.1f}%" if v is not None else "—"

    return {
        "sl":          _fp(_wavg_pct('SL')),
        "offered":     str(offered_total),
        "handled":     str(handled_total),
        "offered_pct": _fp(_wavg_pct('Offered%')),
        "ab":          _fp(_wavg_pct('AR%')),
        "aht":         _sec_to_hms(_wavg_sec('AHT', 'acdcalls')),
        "ibu":         _fp(_wavg_pct('IBU%')),
        "pdu":         _fp(_wavg_pct('PDU%')),
        "avail":       _fp(_wavg_pct('Avail%')),
        "maxocw":      _sec_to_hms(max((_hms_to_sec(r.get('maxocwtime')) for r in rows), default=0)),
        "aqt":         _sec_to_hms(_wavg_sec('AQT', 'callsoffered')),
        "aux":         [_fp(_wavg_pct(f'i_auxtime{i}')) for i in range(10)],
    }


def _lever_logos() -> dict:
    """Return {cid: path} for logo files that exist (silently skipped if absent)."""
    base = os.path.join(_ROOT, "documents")
    candidates = {
        "csg_logo":  os.path.join(base, "logo_csg.png"),
        "dell_logo": os.path.join(base, "logo_dell.png"),
    }
    return {cid: p for cid, p in candidates.items() if os.path.isfile(p)}


def _build_threshold_legend() -> str:
    """Static SL Lever Thresholds reference table (matches the standard definitions)."""
    rows = [
        ("Blue",  "#1565c0", ">85.6% / ≤100%", ">96.3% / ≤100%", "Actual SL > SL Goal × 107%"),
        ("Green", "#2e7d32", "≥80% / <85.6%",  "≥90% / <96.3%",  "Actual SL between 100%–107% of Goal"),
        ("Amber", "#f9a825", "≥72% / <80%",    ">81% / <90%",    "Actual SL between 90%–100% of Goal"),
        ("Red",   "#d32f2f", "≥64% / <72%",    "≥72% / <81%",    "Actual SL between 80%–90% of Goal"),
        ("Black", "#212121", "≥0% / <64%",     "≥0% / <72%",     "Actual SL below 80% of Goal"),
    ]
    body = ""
    for name, c, g80, g90, desc in rows:
        body += (
            f'<tr>'
            f'<td style="padding:4px 8px;background:{c};color:#fff;font-weight:700;">{name}</td>'
            f'<td style="padding:4px 8px;border:1px solid #ddd;" align="center">{g80}</td>'
            f'<td style="padding:4px 8px;border:1px solid #ddd;" align="center">{g90}</td>'
            f'<td style="padding:4px 8px;border:1px solid #ddd;">{desc}</td>'
            f'</tr>'
        )
    return (
        '<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:11px;border:1px solid #ddd;">'
        '<tr style="background:#37474f;color:#fff;">'
        '<th style="padding:5px 8px;" align="left">Lever</th>'
        '<th style="padding:5px 8px;">SL Goal 80%</th>'
        '<th style="padding:5px 8px;">SL Goal 90%</th>'
        '<th style="padding:5px 8px;" align="left">Description</th></tr>'
        f'{body}</table>'
    )


def _build_lever_html(region, queue_name, lever, metric, root_causes, callouts,
                      mitigations, agg, current_time, logos) -> str:
    """Build the email-client-safe HTML dashboard (inline styles + tables only)."""
    sl    = metric.service_level
    band  = _sl_band_color(sl)
    lname = lever['name'].upper()

    def _bullets(items, empty):
        items = items or [empty]
        return "".join(f'<li style="margin:3px 0;line-height:1.5;">{x}</li>' for x in items)

    csg = ('<img src="cid:csg_logo" alt="CSG" style="height:44px;">'
           if "csg_logo" in logos
           else '<span style="font-weight:700;color:#e23744;font-size:20px;">CSG</span>')
    dell = ('<img src="cid:dell_logo" alt="Dell" style="height:40px;margin-top:10px;">'
            if "dell_logo" in logos else '')

    aux    = agg.get('aux', ['—'] * 10)
    aux_th = "".join(f'<th style="padding:5px;">Aux{i}%</th>' for i in range(10))
    aux_td = "".join(f'<td align="center" style="padding:5px;border:1px solid #ddd;">{aux[i]}</td>' for i in range(10))

    return f"""
<html><body style="margin:0;padding:0;background:#f4f6f9;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:16px;">
<tr><td align="center">
<table width="860" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #d6dbe1;font-family:Arial,Helvetica,sans-serif;color:#2c3e50;">

  <!-- Logo strip + header banner -->
  <tr><td style="padding:10px 16px;border-bottom:1px solid #eee;">{csg}</td></tr>
  <tr><td style="background:{band};padding:14px 18px;">
      <span style="color:#fff;font-size:16px;font-weight:700;">
        APJ CSG | {region} | {queue_name} | {lname} Lever SL @ {sl:.1f}%
      </span>
  </td></tr>

  <!-- Two-column: analysis (left) + Aceyus snapshot (right) -->
  <tr><td style="padding:16px 18px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="56%" valign="top" style="font-size:13px;padding-right:14px;">
        <p style="margin:0 0 4px;font-weight:700;">Combined Queue Name:</p>
        <ul style="margin:0 0 12px;padding-left:18px;">{_bullets([queue_name], queue_name)}</ul>
        <p style="margin:0 0 4px;font-weight:700;">Root Cause:</p>
        <ul style="margin:0 0 12px;padding-left:18px;">{_bullets(root_causes, f"SLA dropped to {sl:.1f}%")}</ul>
        <p style="margin:0 0 4px;font-weight:700;">Business Callouts:</p>
        <ul style="margin:0 0 12px;padding-left:18px;">{_bullets(callouts, "No TCDs reported by Business")}</ul>
        <p style="margin:0 0 4px;font-weight:700;">Mitigation Actions:</p>
        <ul style="margin:0 0 4px;padding-left:18px;">{_bullets(mitigations, "Real-time load balancing in progress")}</ul>
      </td>
      <td width="44%" valign="top">
        <p style="margin:0 0 6px;font-weight:700;text-align:center;">Aceyus Real-Time Snapshot — {current_time}</p>
        <table width="100%" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:12px;border:1px solid #ddd;">
          <tr style="background:#eef2f7;color:#555;">
            <th align="left" style="padding:6px;">Queue</th><th>CIQ</th><th>OCW</th>
            <th>Avail</th><th>Offered</th><th>Handled</th><th>SL</th>
          </tr>
          <tr>
            <td style="padding:6px;border-top:1px solid #eee;">{queue_name}</td>
            <td align="center" style="border-top:1px solid #eee;">{metric.calls_waiting}</td>
            <td align="center" style="border-top:1px solid #eee;">{metric.ocw}</td>
            <td align="center" style="border-top:1px solid #eee;">{metric.agents_available}</td>
            <td align="center" style="border-top:1px solid #eee;">{agg.get('offered','—')}</td>
            <td align="center" style="border-top:1px solid #eee;">{agg.get('handled','—')}</td>
            <td align="center" style="background:{band};color:#fff;font-weight:700;">{sl:.1f}%</td>
          </tr>
        </table>
      </td>
    </tr></table>
  </td></tr>

  <!-- Full-width KPI table (day totals from Excel) -->
  <tr><td style="padding:0 18px 16px;">
    <p style="margin:0 0 6px;font-weight:700;">Combined Queue — Day Summary</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:11px;border:1px solid #ccc;">
      <tr style="background:#1f3a5f;color:#fff;">
        <th align="left" style="padding:5px;">Combined Queue</th>
        <th style="padding:5px;">SL</th><th style="padding:5px;">Offered#</th><th style="padding:5px;">Handled#</th>
        <th style="padding:5px;">Offered%</th><th style="padding:5px;">AB%</th><th style="padding:5px;">AHT</th>
        <th style="padding:5px;">IBU%</th><th style="padding:5px;">PDU%</th><th style="padding:5px;">Avail%</th>
        <th style="padding:5px;">maxOCW</th><th style="padding:5px;">AQT</th>{aux_th}
      </tr>
      <tr>
        <td align="left" style="padding:5px;border:1px solid #ddd;">{queue_name}</td>
        <td align="center" style="background:{band};color:#fff;font-weight:700;">{agg.get('sl','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('offered','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('handled','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('offered_pct','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('ab','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('aht','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('ibu','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('pdu','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('avail','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('maxocw','—')}</td>
        <td align="center" style="padding:5px;border:1px solid #ddd;">{agg.get('aqt','—')}</td>{aux_td}
      </tr>
    </table>
  </td></tr>

  <!-- SL Lever Thresholds legend -->
  <tr><td style="padding:0 18px 16px;">
    <p style="margin:0 0 6px;font-weight:700;">SL Lever Thresholds</p>
    {_build_threshold_legend()}
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:12px 18px;border-top:1px solid #eee;background:#fafbfc;">
    {dell}
    <p style="margin:6px 0 0;color:#888;font-size:11px;">Generated by RTA Agentic System | {current_time}</p>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


# ── Email sender ──────────────────────────────────────────────────────────────

def _send_lever_email(
    region: str,
    skill_name: str,
    lever: dict,
    metric,
    llm_result: dict,
    snapshot_table: str,
    email_mod,
    state: dict = None,
    excel_rows: list = None
):
    """Build and send the Lever email."""

    lever_name    = lever['name'].upper()
    lever_emoji   = lever['color']
    current_sl    = metric.service_level
    current_time  = datetime.now().strftime("%d %b %Y %I:%M %p IST")

    # Use real combined queue name — not skill name
    region_tag   = state.get('region_tag', 'rta') if isinstance(state, dict) else 'rta'
    queue_name   = REGION_TO_QUEUE.get(region_tag, skill_name)
    queues       = llm_result.get('combined_queue_names', [queue_name])
    # Always override with real queue name regardless of what LLM returned
    queues       = [queue_name]
    root_causes     = llm_result.get('root_cause', [])
    callouts        = llm_result.get('business_callouts', [])
    mitigations     = llm_result.get('mitigation_actions', [])
    lever_summary   = llm_result.get('lever_summary', '')

    # ── Subject ───────────────────────────────────────────────────────────────
    subject = (
        f"[{lever_name} LEVER] {region} | {queue_name} | "
        f"SL @ {current_sl:.1f}% | {current_time}"
    )

    # ── Body ──────────────────────────────────────────────────────────────────
    lines = []

    # Header
    lines.append(
        f"{lever_emoji} {region} | {queue_name} | "
        f"{lever_name} Lever SL @ {current_sl:.1f}%"
    )
    lines.append("=" * 70)
    lines.append(f"Aceyus Real-Time Snapshot as of {current_time}")
    lines.append("")

    # Combined queue names
    lines.append("Combined Queue Name:")
    for q in queues:
        lines.append(f"  • {q}")
    lines.append("")

    # Root cause
    lines.append("Root Cause:")
    if root_causes:
        for rc in root_causes:
            lines.append(f"  • {rc}")
    else:
        lines.append(f"  • SLA dropped to {current_sl:.1f}% below {lever['below']}% threshold")
    lines.append("")

    # Business callouts
    lines.append("Business Callouts:")
    if callouts:
        for bc in callouts:
            lines.append(f"  • {bc}")
    else:
        lines.append("  • No TCDs reported by Business")
    lines.append("")

    # Mitigation actions
    lines.append("Mitigation Actions:")
    if mitigations:
        for ma in mitigations:
            lines.append(f"  • {ma}")
    else:
        lines.append("  • Real-time load balancing in progress")
    lines.append("")

    # Snapshot table
    lines.append("Real-Time Snapshot:")
    lines.append("─" * 70)
    lines.append(snapshot_table)
    lines.append("─" * 70)
    lines.append("")

    # SL Lever thresholds
    lines.append("SL Lever Thresholds:")
    lines.append("  🟢 Green  → SL ≥ 90%")
    lines.append("  🟡 Amber  → SL 80–89%")
    lines.append("  🔴 Red    → SL 70–79%")
    lines.append("  ⚫ Black  → SL < 70%")
    lines.append("")

    # Footer
    if lever_summary:
        lines.append(f"Summary: {lever_summary}")
        lines.append("")
    lines.append(f"Generated by RTA Agentic System | {current_time}")

    body = "\n".join(lines)

    # ── Build the rich HTML dashboard (falls back to plain text inside email.py) ──
    try:
        agg   = _aggregate_excel_day(excel_rows or [])
        logos = _lever_logos()
        html  = _build_lever_html(
            region=region, queue_name=queue_name, lever=lever, metric=metric,
            root_causes=root_causes, callouts=callouts, mitigations=mitigations,
            agg=agg, current_time=current_time, logos=logos,
        )
    except Exception as e:
        logger.error(f"A3 [{region}]: HTML build failed ({e}) — sending plain text")
        html, logos = None, None

    # Send via existing email module
    try:
        email_mod.send_lever_email(
            subject=subject,
            body=body,
            skill_name=skill_name,
            lever_name=lever_name,
            region=region,
            html=html,
            inline_images=logos,
        )
        logger.info(f"A3 [{region}]: {lever_name} Lever email sent for {skill_name}")
    except Exception as e:
        logger.error(f"A3 [{region}]: Email send failed: {e}")
        # Fallback — try generic send
        try:
            email_mod.send_email_band_drop(
                skill_name=skill_name,
                old_band="HEALTHY",
                new_band=lever_name,
                metric=metric,
                message=body
            )
            logger.info(f"A3 [{region}]: Lever sent via fallback email method")
        except Exception as e2:
            logger.error(f"A3 [{region}]: Fallback email also failed: {e2}")


# ── Main Agent 3 entry point ──────────────────────────────────────────────────

def agent3_lever(state: dict) -> dict:
    """
    Agent 3 — Lever Generator.
    Called by run_all.py after Agent 1 detects SLA threshold crossing.
    Checks each skill metric and fires Lever if threshold crossed for first time.
    """
    logger.info("=== Agent 3 — Lever Generator ===")

    region_name = state.get('region_name', 'RTA')
    tag         = region_name.lower()
    metrics     = state.get('skill_metrics', [])
    a3_cfg      = _get_a3_config()
    excel_path  = a3_cfg.get("excel_path", "") or os.getenv("KPI_EXCEL_PATH", "")

    if not metrics:
        logger.info("A3: No metrics in state — skipping.")
        return state

    # Load modules
    _llm      = _load(f"rta_core_llm_{tag}",    os.path.join("core", "llm.py"))
    _email    = _load(f"rta_alerts_email_{tag}", os.path.join("alerts", "email.py"))

    levers_sent = 0

    for metric in metrics:
        skill_name = metric.skill_name
        sla        = metric.service_level

        # ── Check if SLA recovered above 90% → reset lever history ───────────
        if sla >= 90:
            if f"{skill_name}_Amber" in state.get('a3_fired_levers', {}):
                _reset_fired(state, skill_name)
            continue

        # ── Determine which lever applies ─────────────────────────────────────
        lever = _get_lever_level(sla)
        if not lever:
            continue

        # ── Check cooldown — fire once per threshold ───────────────────────────
        if _already_fired(state, skill_name, lever['name']):
            logger.info(
                f"A3 [{region_name}]: {lever['name']} Lever already sent for "
                f"{skill_name} (SLA={sla:.1f}%) — skipping"
            )
            continue

        logger.info(
            f"A3 [{region_name}]: {lever['name']} Lever triggered for "
            f"{skill_name} — SLA={sla:.1f}% (below {lever['below']}%)"
        )

        # ── Read Excel KPI data ───────────────────────────────────────────────
        excel_rows = []
        if excel_path and os.path.isfile(excel_path):
            excel_rows = _read_excel_for_skill(
                excel_path, skill_name,
                region_tag=state.get('region_tag', 'rta')
            )
        else:
            logger.warning(
                f"A3: Excel not found at '{excel_path}' — "
                f"proceeding without interval data"
            )

        excel_context  = _build_excel_context(excel_rows, skill_name)
        snapshot_table = _build_snapshot_table(metric, region_name)

        # ── Build LLM prompt ──────────────────────────────────────────────────
        prompt = _build_lever_prompt(
            region_name, skill_name, lever,
            metric, excel_context, snapshot_table
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        region_tag = state.get('region_tag', region_name.lower()) if isinstance(state, dict) else region_name.lower()
        raw    = _llm.call_llm(prompt, region_tag=region_tag)
        result = {}

        if raw and "LLM unavailable" not in raw:
            try:
                clean = raw.replace("```json", "").replace("```", "").strip()
                start = clean.find('{')
                end   = clean.rfind('}') + 1
                if start >= 0 and end > start:
                    result = json.loads(clean[start:end])
                    logger.info(f"A3 [{region_name}]: LLM parsed OK for {skill_name}")
                else:
                    logger.warning(f"A3: No JSON found in LLM response for {skill_name}. Raw: {raw[:200]}")
            except Exception as e:
                logger.error(f"A3: LLM JSON parse failed for {skill_name}: {e}. Raw: {raw[:200] if raw else 'empty'}")
        elif raw and "LLM unavailable" in raw:
            logger.warning(f"A3: LLM unavailable for {skill_name} — using fallback")
        else:
            logger.warning(f"A3: LLM returned empty/None for {skill_name}")

        # Fallback if LLM failed
        if not result:
            logger.warning(f"A3: Using fallback lever content for {skill_name}")
            result = {
                "combined_queue_names": [skill_name],
                "root_cause": [
                    f"SLA dropped to {sla:.1f}% below {lever['below']}% threshold",
                    f"Queue: {metric.calls_waiting} calls waiting | "
                    f"OCW: {metric.ocw} | Avail: {metric.agents_available}",
                    "Detailed interval analysis unavailable — LLM fallback"
                ],
                "business_callouts": ["No TCDs reported by Business"],
                "mitigation_actions": [
                    "Real-time load balancing in progress",
                    "AUX management — move overdue break agents",
                    "AHOD and supervisor support activated"
                ],
                "lever_summary": (
                    f"SLA at {sla:.1f}% ({lever['name']} Lever). "
                    f"Queue: {metric.calls_waiting} | OCW: {metric.ocw}"
                )
            }

        # ── Send Lever email ──────────────────────────────────────────────────
        _send_lever_email(
            region_name, skill_name, lever,
            metric, result, snapshot_table, _email,
            state=state, excel_rows=excel_rows
        )

        # ── Mark as fired ─────────────────────────────────────────────────────
        _mark_fired(state, skill_name, lever['name'])

        # If Red fired, also mark Amber as fired (Red > Amber)
        if lever['name'] == 'Red':
            _mark_fired(state, skill_name, 'Amber')

        # If Black fired, mark both Amber and Red as fired
        if lever['name'] == 'Black':
            _mark_fired(state, skill_name, 'Amber')
            _mark_fired(state, skill_name, 'Red')

        levers_sent += 1

    logger.info(
        f"A3 [{region_name}] complete — {levers_sent} lever(s) sent."
    )
    return state