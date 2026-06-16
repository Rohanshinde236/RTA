"""
agents/agent2_analyst.py
Agent 2 — CMS scraper + LLM analyst

Sequential processing — ONE LLM call PER skill (not all at once).
Flow per breached skill:
  1. Scrape CMS for that skill
  2. Build prompt
  3. LLM call
  4. Send Teams message immediately
  5. Move to next skill

Teams message format (exact):
  🚨 [RTA] SLA Alert — TS_CSTCE — 78.2% (CRITICAL)
  📊 Skill Snapshot SLA: 78.2% | Queue: 6 | OCW: 01:00 | Avail: 0
  ✅ MOVE 3 AGENTS — Priority Order:
  1. AgentAlpha — Break — 00:28 on AUX
     Exceeded 15 min break — move first
  2. AgentBravo — Break — 00:30 on AUX
     Exceeded 15 min break — move first
  💬 POLITE ASK — Case Management:
  • AgentGolf is on case management, can you please jump to calls?
  ⏸ DO NOT MOVE:
  • AgentHotel — Only 8 min into lunch — do not disturb
  🤖 AI Analysis: <root cause and action summary>
  📈 SLA expected to recover to ~88% within 2 minutes
"""

import importlib.util
import json
import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import threading
logger = logging.getLogger(__name__)

def _get_a2_config():
    """Load agent2 config from config.json. Falls back to defaults."""
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader_a2", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_agent2()
    except Exception:
        return {
            "ocw_threshold_sec": 60,
            "queue_min":         1,
            "cooldown_sec":      300,
            "llm_enabled":       True,
        }

# Global LLM lock — stored in sys.modules so ALL region module copies share ONE lock
# importlib loads this module as rta_agent2_rta / rta_agent2_usa / rta_agent2_asia
# each gets its own module namespace — so a module-level lock would NOT be shared
# Solution: store the lock in sys.modules under a fixed key so all copies share it
_LOCK_KEY = '__rta_llm_global_lock__'
if _LOCK_KEY not in sys.modules:
    sys.modules[_LOCK_KEY] = threading.Lock()
_LLM_LOCK = sys.modules[_LOCK_KEY]

def _get_aux_config() -> dict:
    """
    Load agent4.aux_thresholds from config.json.
    This is the single source of truth for all AUX rules —
    values come from the UI (Agent 4 AUX Thresholds table).
    """
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader_a2_aux", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_agent4().get("aux_thresholds", {})
    except Exception:
        # Fallback defaults match config.json defaults in config_loader.py
        return {
            "AUX1": {"name": "IT Issue",    "max_time_min": 0,  "enabled": False},
            "AUX2": {"name": "Break",       "max_time_min": 15, "enabled": True},
            "AUX3": {"name": "Lunch",       "max_time_min": 30, "enabled": True},
            "AUX4": {"name": "Meeting",     "max_time_min": 0,  "enabled": False},
            "AUX5": {"name": "Training",    "max_time_min": 0,  "enabled": False},
            "AUX6": {"name": "Case Mgmt",   "max_time_min": 45, "enabled": True},
            "AUX7": {"name": "Project",     "max_time_min": 0,  "enabled": False},
            "AUX8": {"name": "Alt Channel", "max_time_min": 0,  "enabled": False},
            "AUX9": {"name": "Outbound",    "max_time_min": 0,  "enabled": False},
        }


def _get_aux_reference() -> str:
    """
    Build AUX move-rules string for the LLM prompt.
    Reads ALL 9 AUX codes from agent4.aux_thresholds in config.json
    (set via the Agent 4 AUX Thresholds table in the UI).

    Move logic per AUX code:
      - max_time_min == 0 or enabled == False → NEVER move
      - AUX6 (Case Mgmt) → ASK POLITELY only (never force)
      - All others with max_time_min > 0 → MOVE if exceeded, LOW PRIORITY / HOLD if within limit
    """
    aux_cfg = _get_aux_config()

    lines = ["AUX CODES AND MOVE RULES — apply these exactly:"]

    # AUX code → number for matching (AUX1 → 1, etc.)
    for code, cfg in aux_cfg.items():
        num      = code.replace("AUX", "")   # "1" .. "9"
        name     = cfg.get("name", code)
        max_min  = cfg.get("max_time_min", 0)
        enabled  = cfg.get("enabled", False)

        aux_label = f"Aux{num} = {name}"

        if not enabled or max_min == 0:
            lines.append(f"{aux_label:<30} → NEVER move")
        elif code == "AUX6":
            lines.append(
                f"{aux_label:<30} → ASK POLITELY only — never force move\n"
                f"{'':30}   Use the agent's ACTUAL NAME from the table above.\n"
                f"{'':30}   Message format: \"<actual_agent_name> is on {name}, can you please jump to calls?\"\n"
                f"{'':30}   Example: \"Sharma_D is on {name}, can you please jump to calls?\""
            )
        else:
            lines.append(
                f"{aux_label} (target ≤{max_min}min)"
                f"{'':>{max(1, 20 - len(aux_label) - len(str(max_min)) - 10)}}"
                f"→ MOVE if time > {max_min}min (exceeded limit)\n"
                f"{'':30}   LOW PRIORITY / HOLD if time ≤ {max_min}min"
            )

    lines.append("DEFAULT / Unknown              → NEVER move")
    lines.append("")

    # Build priority order dynamically from moveable AUX codes
    moveable = [
        (code, cfg) for code, cfg in aux_cfg.items()
        if cfg.get("enabled", False)
        and cfg.get("max_time_min", 0) > 0
        and code != "AUX6"
    ]
    if moveable:
        lines.append("PRIORITY ORDER for move_list (longest time on AUX first within each group):")
        for i, (code, cfg) in enumerate(moveable, 1):
            num     = code.replace("AUX", "")
            name    = cfg.get("name", code)
            max_min = cfg.get("max_time_min", 0)
            lines.append(f"{i}. Aux{num} agents who exceeded {max_min}min — longest time first")
        lines.append(
            f"{len(moveable)+1}. Aux codes within their limit — only if absolutely no one else available"
        )

    lines.append("Only move as many agents as needed to cover the queue.")

    return "\n".join(lines)


# ── module loader ─────────────────────────────────────────────────────────────

def _load_file(name, abs_path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, abs_path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load(name, rel):
    path = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)
    return _load_file(name, path)


# ── Teams sender ──────────────────────────────────────────────────────────────

def _send_teams_text(webhook, text):
    """
    Send message via Adaptive Card format — required for Power Automate webhooks.
    Plain {"text": ...} returns 202 but renders nothing in Teams.
    Each line becomes its own TextBlock so formatting is preserved.
    """
    if not webhook:
        logger.warning("No webhook set!")
        return
    import requests

    # Split into lines — each line is a separate TextBlock for clean rendering
    lines = [l for l in text.split('\n') if l.strip()]

    body = []
    for line in lines:
        # First line (header) — bold and large
        if line.startswith('🚨'):
            body.append({
                "type": "TextBlock",
                "text": line,
                "weight": "Bolder",
                "size": "Large",
                "wrap": True
            })
        # Snapshot line — medium bold
        elif line.startswith('📊'):
            body.append({
                "type": "TextBlock",
                "text": line,
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
                "spacing": "Small"
            })
        # Section headers
        elif line.startswith(('✅', '💬', '⏸', '🤖', '⚠️')):
            body.append({
                "type": "TextBlock",
                "text": line,
                "weight": "Bolder",
                "wrap": True,
                "spacing": "Medium"
            })
        # All other lines — normal wrap
        else:
            body.append({
                "type": "TextBlock",
                "text": line,
                "wrap": True,
                "spacing": "None"
            })

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": body,
                "msteams": {"width": "Full"}
            }
        }]
    }

    try:
        r = requests.post(webhook, json=card, timeout=10)
        logger.info(f"Teams sent — {r.status_code}")
    except Exception as e:
        logger.error(f"Teams failed: {e}")


# ── CMS collector initialiser ─────────────────────────────────────────────────

def _get_cms_collector(tag, dashboard_path):
    """
    Return the single global CMS collector shared across all regions.
    All regions use the same ui/CMS.html — no need for 10 separate browsers.
    One browser + one BG thread handles all regions sequentially via queue.

    Previously: 10 per-region collectors → 10 Chromium instances → resource
    exhaustion → BG thread timeouts + sync-mode "page not initialized" errors.
    Now: 1 collector → 1 browser → no startup race under load.
    """
    cms_file = os.path.join(_ROOT, "dashboard", "cms_collector.py")
    cms_path = os.path.join(_ROOT, 'ui', 'CMS.html')

    inst_key = "__rta_cms_inst_global__"
    if inst_key in sys.modules:
        return sys.modules[inst_key]

    # Double-checked locking — prevents 10 regions racing to create separate collectors
    lock_key = "__rta_cms_create_lock__"
    if lock_key not in sys.modules:
        sys.modules[lock_key] = threading.Lock()

    with sys.modules[lock_key]:
        if inst_key in sys.modules:
            return sys.modules[inst_key]
        try:
            mod_key = "__rta_cms_mod_global__"
            if mod_key in sys.modules:
                del sys.modules[mod_key]
            cms_mod = _load_file(mod_key, cms_file)
            collector = cms_mod.CMSCollector(cms_path)
            sys.modules[inst_key] = collector
            logger.info("Global CMS collector created — shared across all regions.")
            return collector
        except Exception as e:
            logger.warning(f"Global CMS collector init failed: {e}")
            return None


# ── agent table builder (for LLM prompt) ─────────────────────────────────────

def _build_agent_table(agents):
    """
    Build raw agent table string for LLM.
    No pre-processing — LLM applies move rules itself.
    """
    if not agents:
        return "No agent data available from CMS."

    lines = []

    # AUX agents first
    aux_agents = [a for a in agents if a.get('state') == 'AUX']
    other      = [a for a in agents if a.get('state') != 'AUX']

    if aux_agents:
        lines.append(f"{'Name':<20} {'AUX Reason':<20} {'Time on AUX':<14} {'Time (min)'}")
        lines.append("─" * 65)
        for a in aux_agents:
            name     = a.get('name', '')
            reason   = a.get('aux_reason', '—')
            time_str = a.get('time', '0:00')
            time_min = a.get('time_minutes', 0)
            lines.append(f"{name:<20} {reason:<20} {time_str:<14} {time_min:.1f} min")

    if other:
        lines.append("")
        lines.append(f"{'Name':<20} {'State':<10} {'Time'}")
        lines.append("─" * 40)
        for a in other:
            lines.append(
                f"{a.get('name',''):<20} "
                f"{a.get('state',''):<10} "
                f"{a.get('time','')}"
            )

    return "\n".join(lines)


# ── Teams message builder (exact format) ─────────────────────────────────────

def _build_teams_message(region, skill_name, metric, result):
    """
    Build the exact Teams message format:

    🚨 [RTA] SLA Alert — TS_CSTCE — 78.2% (CRITICAL)
    📊 Skill Snapshot SLA: 78.2% | Queue: 6 | OCW: 01:00 | Avail: 0
    ✅ MOVE N AGENTS — Priority Order:
    1. AgentAlpha — Break — 00:28 on AUX
       Exceeded 15 min break — move first
    💬 POLITE ASK — Case Management:
    • AgentGolf is on case management, can you please jump to calls?
    ⏸ DO NOT MOVE:
    • AgentHotel — Only 8 min into lunch — do not disturb
    🤖 AI Analysis: <analyst_note>
    📈 <sla_recovery_estimate>
    """
    move_list = result.get('move_list', [])
    hold_list = result.get('hold_list', [])
    ask_list  = result.get('ask_list',  [])
    recovery  = result.get('sla_recovery_estimate', '')
    note      = result.get('analyst_note', '')

    sl   = metric.service_level
    band = metric.band
    q    = metric.calls_waiting
    ocw  = metric.ocw
    avail = metric.agents_available

    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"🚨 [{region}] SLA Alert — {skill_name} — {sl:.1f}% ({band})")

    # ── Snapshot ──────────────────────────────────────────────────────────────
    lines.append(
        f"📊 Skill Snapshot  SLA: {sl:.1f}% | Queue: {q} | OCW: {ocw} | Avail: {avail}"
    )

    # ── Move list ─────────────────────────────────────────────────────────────
    if move_list:
        agent_word = "AGENT" if len(move_list) == 1 else "AGENTS"
        lines.append(f"✅ MOVE {len(move_list)} {agent_word} — Priority Order:")
        for i, a in enumerate(move_list):
            p        = i + 1          # sequential — LLM decides order, Python fixes numbering
            name     = a.get('name', '')
            reason   = a.get('aux_reason', '')
            time_aux = a.get('time_on_aux', '')
            note_txt = a.get('note', '')
            lines.append(f"{p}. {name} — {reason} — {time_aux} on AUX")
            if note_txt:
                lines.append(f"   {note_txt}")
    else:
        if not ask_list:
            # Truly no AUX agents at all
            lines.append("⚠️ No AUX agents available to move")
        # If ask_list is non-empty, Case Mgmt agents exist — don't say "no AUX agents"

    # ── Polite ask ────────────────────────────────────────────────────────────
    if ask_list:
        lines.append("💬 POLITE ASK — Case Management:")
        for a in ask_list:
            lines.append(f"• {a.get('message', '')}")

    # ── Do not move ───────────────────────────────────────────────────────────
    if hold_list:
        lines.append("⏸ DO NOT MOVE:")
        for a in hold_list:
            name   = a.get('name', '')
            reason = a.get('reason_to_hold', '')
            lines.append(f"• {name} — {reason}")

    # ── AI analysis ───────────────────────────────────────────────────────────
    ai_parts = []
    if note:
        ai_parts.append(note)
    if recovery:
        ai_parts.append(f"📈 {recovery}")

    if ai_parts:
        lines.append(f"🤖 AI Analysis: {' '.join(ai_parts)}")

    return "\n".join(lines)


# ── LLM prompt builder (single skill) ────────────────────────────────────────

# ── Recovery estimate calculator (deterministic — no LLM guessing) ───────────

def _calc_recovery_estimate(metric, agents: list) -> str:
    """
    Calculate realistic SLA recovery using projected SL formula.
    Injected into LLM prompt so it cannot hallucinate the number.
    """
    offered    = getattr(metric, 'calls_offered',    0) or 0
    acceptable = getattr(metric, 'calls_acceptable', 0) or 0
    queue      = getattr(metric, 'calls_waiting',    0) or 0
    ocw        = getattr(metric, 'ocw', '00:00')        or '00:00'

    if offered == 0:
        return "insufficient data to estimate recovery"

    # Count agents that can realistically be moved
    moveable_count = sum(
        1 for a in agents
        if a.get('moveable') in ('yes', 'conditional')
    )

    # OCW seconds — remaining window within 120s SL threshold
    try:
        ocw_parts = str(ocw).split(':')
        ocw_sec   = int(ocw_parts[0]) * 60 + int(ocw_parts[1])
    except Exception:
        ocw_sec = 0

    remaining_sec = max(0, 120 - ocw_sec)
    probability   = min(0.9, remaining_sec / 120) if remaining_sec > 0 else 0

    # Expected saves
    potential_saves = min(moveable_count, queue)
    expected_saves  = round(potential_saves * probability)

    # Projected SL
    proj_offered    = offered + queue
    proj_acceptable = acceptable + expected_saves
    proj_sl         = (proj_acceptable / proj_offered * 100) if proj_offered > 0 else 0
    current_sl      = metric.service_level
    diff            = proj_sl - current_sl

    if moveable_count == 0:
        return (
            f"No moveable AUX agents — SLA will stay at ~{current_sl:.0f}% "
            f"or worsen. Escalate to supervisor immediately."
        )
    elif diff >= 1:
        return (
            f"Moving {expected_saves} agent(s) → projected SLA ~{proj_sl:.0f}% "
            f"(+{diff:.0f}% from current {current_sl:.0f}%) within 2 minutes."
        )
    else:
        return (
            f"Moving {expected_saves} agent(s) → SLA stabilises at ~{proj_sl:.0f}% "
            f"(queue pressure limits recovery). Supervisor review recommended."
        )


def _build_prompt(region, skill_name, metric, hist, agents, breach_reasons):
    sla_hist    = " → ".join(f"{v:.1f}%" for v in hist.sla_history)
    q_hist      = " → ".join(str(v) for v in hist.queue_history)
    ocw_flag    = "⚠️ OCW BREACH!" if metric.is_ocw_critical else "OK"
    agent_table = _build_agent_table(agents)

    # Pre-calculate recovery with real formula — LLM must use this exactly
    recovery_calc = _calc_recovery_estimate(metric, agents)

    context = f"""
Skill: {skill_name}
SLA: {metric.service_level:.1f}% (Band: {metric.band})
SLA History (last polls): {sla_hist}
Queue History (last polls): {q_hist}
Queue: {metric.calls_waiting} | Avail: {metric.agents_available} | AUX: {metric.agents_on_aux} | OCW: {metric.ocw} [{ocw_flag}]
Breach reasons: {", ".join(breach_reasons)}
PRE-CALCULATED RECOVERY (use this exactly): {recovery_calc}

{agent_table}
"""

    aux_ref = _get_aux_reference()
    from core.prompt_loader import load_prompt
    return load_prompt(
        "agent2_analyst",
        region=region,
        aux_ref=aux_ref,
        context=context,
        skill_name=skill_name,
    )


# ── fallback (when LLM fails or times out) ───────────────────────────────────

def _fallback(skill_name, metric, agents, breach_reasons):
    """
    Rule-based fallback — uses actual agent data, not generic messages.
    All AUX thresholds read from config.json (agent4.aux_thresholds)
    so they stay in sync with the UI — no hardcoded values.
    """
    move_list = []
    hold_list = []
    ask_list  = []
    queue     = metric.calls_waiting if metric else 0
    priority  = 1

    # Load AUX thresholds from config — single source of truth
    aux_cfg = _get_aux_config()

    # Sort by time on AUX descending — longest first
    aux_agents = [
        a for a in (agents or [])
        if a.get('state') == 'AUX'
    ]
    aux_agents.sort(key=lambda x: x.get('time_seconds', 0), reverse=True)

    for a in aux_agents:
        name     = a.get('name', '')
        reason   = a.get('aux_reason', '—')
        time_str = a.get('time', '0:00')
        time_min = a.get('time_minutes', 0)

        # Match agent's AUX reason to an AUX code (e.g. "AUX 2" or "Aux2" → "AUX2")
        matched_code = None
        for i in range(1, 10):
            if f'AUX {i}' in reason or f'Aux{i}' in reason or f'AUX{i}' in reason:
                matched_code = f'AUX{i}'
                break

        cfg      = aux_cfg.get(matched_code, {}) if matched_code else {}
        enabled  = cfg.get("enabled", False)
        max_min  = cfg.get("max_time_min", 0)
        aux_name = cfg.get("name", reason)

        if not matched_code or not enabled or max_min == 0:
            # Unknown AUX or monitoring disabled — never move
            hold_list.append({
                "name":           name,
                "aux_reason":     reason,
                "reason_to_hold": f"On {aux_name} — do not interrupt",
            })

        elif matched_code == "AUX6":
            # Case Mgmt — always polite ask, never force move
            ask_list.append({
                "name":    name,
                "message": f"{name} is on {aux_name}, can you please jump to calls?",
            })

        elif time_min > max_min and priority <= max(queue, 1):
            # Exceeded threshold and queue needs coverage — move
            move_list.append({
                "priority":    priority,
                "name":        name,
                "aux_code":    matched_code,
                "aux_reason":  aux_name,
                "time_on_aux": time_str,
                "note":        f"Exceeded {max_min} min {aux_name} limit — move to calls",
            })
            priority += 1

        elif time_min > max_min:
            # Exceeded but queue already covered — still flag
            hold_list.append({
                "name":           name,
                "aux_reason":     aux_name,
                "reason_to_hold": f"Exceeded {max_min} min limit but queue covered — monitor",
            })

        else:
            # Within allowed time — hold
            hold_list.append({
                "name":           name,
                "aux_reason":     aux_name,
                "reason_to_hold": f"Only {int(time_min)} min into {aux_name} — under {max_min} min limit",
            })

    sla     = metric.service_level if metric else 0
    band    = metric.band if metric else ''
    on_aux  = metric.agents_on_aux if metric else 0
    avail   = metric.agents_available if metric else 0

    # CMS returned nothing but live scrape shows AUX agents — data gap
    no_cms_data = not agents and on_aux > 0

    return {
        "skill":      skill_name,
        "root_cause": "AUX_HEAVY" if on_aux > 0 else "STAFFING",
        "move_list":  move_list,
        "hold_list":  hold_list,
        "ask_list":   ask_list,
        "sla_recovery_estimate": (
            f"Moving {len(move_list)} agent(s) should recover SLA within 2-3 minutes."
            if move_list else "No moveable AUX agents — escalate to supervisor."
        ),
        "analyst_note": (
            f"SLA at {sla:.1f}% ({band}). {queue} calls waiting. "
            f"CMS data unavailable — {on_aux} agent(s) on AUX but names unknown. Escalate to supervisor."
            if no_cms_data else
            f"SLA at {sla:.1f}% ({band}). {queue} calls waiting. "
            f"{on_aux} on AUX. Avail: {avail}."
        ),
    }


# ── Result sanitiser — runs after BOTH LLM and fallback ──────────────────────

def _sanitise_result(result: dict, agents: list) -> dict:
    """
    Post-process analyst result to fix common LLM hallucinations:
    1. Deduplicate: same agent cannot appear in more than one list.
       Priority order: move > ask > hold.
    2. Validate move_list: remove agents whose actual AUX time is below
       the configured threshold (LLM sometimes says "exceeded 15 min"
       for someone on break for 4 seconds).
    3. Strip trailing garbage chars (?  …) from text fields.
    """
    aux_cfg   = _get_aux_config()
    agents_map = {a.get('name', ''): a for a in (agents or [])}

    move_list = list(result.get('move_list', []) or [])
    ask_list  = list(result.get('ask_list',  []) or [])
    hold_list = list(result.get('hold_list', []) or [])

    # ── Step 1: validate move_list entries against real time data ─────────────
    valid_move   = []
    demoted_move = []   # names that failed validation

    for entry in move_list:
        name   = entry.get('name', '')
        actual = agents_map.get(name)

        if not actual or actual.get('state') != 'AUX':
            demoted_move.append(name)
            continue

        reason       = actual.get('aux_reason', '')
        time_min_act = actual.get('time_minutes', 0)

        # Find AUX code
        matched = None
        for i in range(1, 10):
            if f'AUX {i}' in reason or f'Aux{i}' in reason or f'AUX{i}' in reason:
                matched = f'AUX{i}'
                break

        # AUX6 (Case Mgmt) should never be in move_list
        if matched == 'AUX6':
            demoted_move.append(name)
            if not any(a.get('name') == name for a in ask_list):
                ask_list.append({
                    "name":    name,
                    "message": f"{name} is on Case Mgmt, can you please jump to calls?",
                })
            continue

        cfg     = aux_cfg.get(matched, {}) if matched else {}
        max_min = cfg.get('max_time_min', 0)
        # Reject if agent is under the threshold
        if max_min > 0 and time_min_act <= max_min:
            demoted_move.append(name)
            continue

        valid_move.append(entry)

    demoted_set = set(demoted_move)

    # ── Step 2: deduplicate ask/hold vs move ──────────────────────────────────
    move_names = {e.get('name', '') for e in valid_move}
    ask_list   = [a for a in ask_list  if a.get('name', '') not in move_names]

    ask_names  = {a.get('name', '') for a in ask_list}
    hold_list  = [
        h for h in hold_list
        if h.get('name', '') not in move_names
        and h.get('name', '') not in ask_names
    ]

    # ── Step 3: strip trailing junk from text fields ──────────────────────────
    _junk = '? \t'
    for key in ('analyst_note', 'sla_recovery_estimate', 'root_cause'):
        val = result.get(key, '')
        if val:
            result[key] = val.strip().rstrip(_junk).strip()

    # ── Step 4: remove ask_list entries with unresolved LLM placeholders ─────
    # LLM sometimes copies the template example literally ([Name], <agent_name>)
    # instead of substituting real names — strip these to avoid confusing output.
    _PLACEHOLDERS = {'[Name]', '<actual_agent_name>', '<agent_name>', '[agent_name]'}
    ask_list = [
        a for a in ask_list
        if a.get('name', '') not in _PLACEHOLDERS
        and not any(p in a.get('message', '') for p in _PLACEHOLDERS)
    ]

    result['move_list'] = valid_move
    result['ask_list']  = ask_list
    result['hold_list'] = hold_list
    return result


# ── LLM call + JSON parse ─────────────────────────────────────────────────────

def _call_llm_for_skill(llm_mod, prompt, skill_name, region):
    """Call LLM, parse JSON object. Returns dict or None on failure."""
    raw = llm_mod.call_llm(prompt)
    if not raw:
        logger.warning(f"[{region}] LLM returned empty for {skill_name}")
        return None
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        # find outermost { }
        start = clean.find('{')
        end   = clean.rfind('}') + 1
        if start >= 0 and end > start:
            result = json.loads(clean[start:end])
            logger.info(f"[{region}] LLM parsed OK for {skill_name}")
            return result
    except Exception as e:
        logger.error(f"[{region}] LLM JSON parse failed for {skill_name}: {e}")
    return None


# ── main agent entry point ────────────────────────────────────────────────────

def agent2_analyst(state: dict) -> dict:
    logger.info("=== Agent 2 — Sequential CMS + LLM Analyst ===")

    webhook        = state.get('teams_webhook', '') or os.getenv("TEAMS_WEBHOOK_URL", "")
    region_name    = state.get('region_name', 'RTA')
    tag            = region_name.lower()
    dashboard_path = state.get('dashboard_path', '')

    _models = _load(f"rta_core_models_{tag}", os.path.join("core", "models.py"))
    _llm    = _load(f"rta_core_llm_{tag}",    os.path.join("core", "llm.py"))

    breached  = state.get('breached_skills', {})
    histories = state.get('skill_histories', {})
    metrics   = state.get('skill_metrics', [])
    decisions = {}

    if not breached:
        logger.info("Agent 2: no breached skills — skipping.")
        state['analyst_decisions'] = {}
        return state

    metrics_map   = {m.skill_name: m for m in metrics}
    cms_collector = _get_cms_collector(tag, dashboard_path)

    # ── Cooldown tracker — read from config ─────────────────────────────────
    import time
    a2_cfg       = _get_a2_config()
    cooldown_sec = a2_cfg.get("cooldown_sec", 300)
    last_alerted = state.get('a2_last_alerted', {})
    now          = time.time()

    logger.info(
        f"Agent 2 [{region_name}]: processing {len(breached)} breached skill(s) sequentially."
    )

    # ── Sequential loop — one skill at a time ─────────────────────────────────
    for skill_name, breach_reasons in breached.items():

        hist   = histories.get(skill_name)
        metric = metrics_map.get(skill_name)

        if not hist or not metric:
            logger.warning(f"[{region_name}] No history/metric for {skill_name} — skipping.")
            continue

        # Check cooldown — skip if alerted within last 5 minutes
        last_time = last_alerted.get(skill_name, 0)
        if now - last_time < cooldown_sec:
            remaining = int(cooldown_sec - (now - last_time))
            logger.info(
                f"[{region_name}] Skipping {skill_name} — cooldown active "
                f"({remaining}s remaining)"
            )
            continue

        logger.info(f"[{region_name}] Processing skill: {skill_name}")

        # 1. Scrape CMS for this skill
        agents = []
        if cms_collector:
            try:
                agents = cms_collector.collect(skill_name)
                logger.info(
                    f"[{region_name}] CMS: {len(agents)} agents for {skill_name}"
                )
            except Exception as e:
                logger.warning(f"[{region_name}] CMS collect failed for {skill_name}: {e}")

        # Save CMS snapshot to history DB
        try:
            from core.history import save_cms_snapshot
            from datetime import datetime as _dt
            _ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
            region_tag_for_history = state.get('region_tag', tag)
            save_cms_snapshot(region_tag_for_history, skill_name, agents, _ts)
        except Exception:
            pass  # never let history saving break the main flow

        # 2. Build prompt for this skill only
        prompt = _build_prompt(
            region_name, skill_name, metric, hist, agents, breach_reasons
        )

        # 3. LLM call — acquire global lock so regions don't call simultaneously
        logger.info(f"[{region_name}] Waiting for LLM lock — {skill_name}")
        with _LLM_LOCK:
            logger.info(f"[{region_name}] LLM lock acquired — {skill_name}")
            # LLM enabled check from config

        # Skip LLM when CMS returned no agents — LLM has no names to work with
        # and will hallucinate placeholders like [Name]. Fallback handles this cleanly.
        _llm_skipped = False
        if not agents:
            on_aux = metric.agents_on_aux if metric else 0
            logger.info(
                f"[{region_name}] No CMS data for {skill_name} "
                f"(metric shows {on_aux} on AUX) — using fallback directly"
            )
            result = None
            _llm_skipped = True
        elif not _get_a2_config().get("llm_enabled", True):
            logger.info(f"[{region_name}] LLM disabled in config — using fallback")
            result = None
            _llm_skipped = True
        else:
            result = _call_llm_for_skill(_llm, prompt, skill_name, region_name)

        # 4. Fallback if LLM failed or was skipped
        if not result:
            if not _llm_skipped:
                # LLM was called but failed — this is unexpected
                logger.warning(f"[{region_name}] LLM failed for {skill_name} — using fallback")
            result = _fallback(skill_name, metric, agents, breach_reasons)

        # 4b. Sanitise — deduplicate agents, validate move times, strip junk
        result = _sanitise_result(result, agents)

        # ensure skill key is correct
        result['skill'] = skill_name
        decisions[skill_name] = result

        # 5. Build and send Teams message immediately for this skill
        message = _build_teams_message(region_name, skill_name, metric, result)
        _send_teams_text(webhook, message)

        last_alerted[skill_name] = now   # update cooldown timestamp
        logger.info(
            f"[{region_name}] ✓ {skill_name} — Teams alert sent. "
            f"Move: {len(result.get('move_list',[]))} | "
            f"Ask: {len(result.get('ask_list',[]))} | "
            f"Hold: {len(result.get('hold_list',[]))}"
        )

    state['analyst_decisions']  = decisions
    state['a2_last_alerted']     = last_alerted   # persist cooldown across polls
    logger.info(
        f"Agent 2 [{region_name}] complete — "
        f"{len(decisions)}/{len(breached)} skills processed."
    )
    return state


# ── cleanup ───────────────────────────────────────────────────────────────────

def cleanup_cms(region_name: str = None):
    key = "__rta_cms_inst_global__"
    if key in sys.modules:
        try:
            sys.modules[key].cleanup()
            logger.info("Global CMS browser closed.")
        except Exception:
            pass
        del sys.modules[key]