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


# ── Email sender ──────────────────────────────────────────────────────────────

def _send_lever_email(
    region: str,
    skill_name: str,
    lever: dict,
    metric,
    llm_result: dict,
    snapshot_table: str,
    email_mod,
    state: dict = None
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

    # Send via existing email module
    try:
        email_mod.send_lever_email(
            subject=subject,
            body=body,
            skill_name=skill_name,
            lever_name=lever_name,
            region=region
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
            state=state
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