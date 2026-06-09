"""
workflow.py
LangGraph workflow — RTA v3

Graph structure:
  START
    ↓
  agent1 (always runs — scrape + breach detection)
    ↓
  router_node (inline routing logic — no decision_engine.py)
    ↓
  ┌─────────────────────────────────────────┐
  │ a2_only  → agent2           → END       │
  │ a3_only  → agent3           → END       │
  │ both     → agent2 → agent3  → END       │
  │ end      → END                          │
  └─────────────────────────────────────────┘

Agent 4 runs in its own thread — not part of graph (time-based, not event-based)
"""

import importlib.util
import logging
import os
import sys

from langgraph.graph import StateGraph, END
from typing import Literal

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

# ── Routing thresholds — loaded from config.json via config_loader ───────────
# Fallback values used if config_loader not available
OCW_THRESHOLD_SEC   = 60
QUEUE_MIN           = 1
SLA_AMBER           = 90.0
SLA_RED             = 80.0
SLA_BLACK           = 70.0
SYSTEMIC_MIN_SKILLS = 3

def _get_thresholds():
    """Load thresholds from config.json. Falls back to defaults."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "config_loader", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        a2 = mod.get_agent2()   # OCW + queue_min now in agent2
        a3 = mod.get_agent3()
        return {
            "ocw_threshold_sec":   a2.get("ocw_threshold_sec",   60),
            "queue_min":            a2.get("queue_min",            1),
            "amber_threshold":      a3.get("amber_threshold",      90.0),
            "red_threshold":        a3.get("red_threshold",        80.0),
            "black_threshold":      a3.get("black_threshold",      70.0),
        }
    except Exception as e:
        logger.warning(f"config_loader not available — using defaults: {e}")
        return {
            "ocw_threshold_sec":  60,
            "queue_min":           1,
            "amber_threshold":     90.0,
            "red_threshold":       80.0,
            "black_threshold":     70.0,
        }


# ── Module loader ─────────────────────────────────────────────────────────────

def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    path = rel if os.path.isabs(rel) else os.path.join(_ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Recovery alert sender ─────────────────────────────────────────────────────

def _send_recovery_alerts(state: dict, recovering_skills: list):
    """Send RESOLVED Teams message for recovered skills."""
    webhook = state.get('teams_webhook', '')
    region  = state.get('region_display', state.get('region_name', 'RTA'))

    if not webhook or not recovering_skills:
        return

    import requests
    for r in recovering_skills:
        try:
            body = [{
                "type":   "TextBlock",
                "text":   (
                    f"✅ [{region}] RESOLVED — {r['skill']}\n"
                    f"SLA recovered to {r['sla']:.1f}% | "
                    f"Queue: 0 | Avail: {r['avail']}"
                ),
                "wrap":   True,
                "color":  "Good",
                "weight": "Bolder",
                "size":   "Medium"
            }]
            card = {
                "type": "message",
                "attachments": [{
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type":    "AdaptiveCard",
                        "version": "1.4",
                        "body":    body,
                        "msteams": {"width": "Full"}
                    }
                }]
            }
            requests.post(webhook, json=card, timeout=10)
            logger.info(f"[{region}] ✅ Recovery alert sent for {r['skill']}")

            # Reset lever history so levers re-fire if SLA drops again
            fired = state.get('a3_fired_levers', {})
            for k in [k for k in fired if k.startswith(f"{r['skill']}_")]:
                del fired[k]

        except Exception as e:
            logger.error(f"[{region}] Recovery alert failed: {e}")


# ── Router node ───────────────────────────────────────────────────────────────

def router_node(state: dict) -> dict:
    """
    Inline routing logic.

    Evaluates state after Agent 1 and:
      1. Decides whether to invoke A2 (queue/OCW pressure)
      2. Decides whether A2 should use LLM (AUX agents exist)
      3. Decides whether to invoke A3 (SLA threshold crossed, not yet fired)
      4. Detects recovered skills and sends RESOLVED alerts
      5. Detects systemic issues (3+ skills in crisis)
      6. Writes routing flags into state for conditional edge to read
    """
    region       = state.get('region_display', state.get('region_name', 'RTA'))
    metrics      = state.get('skill_metrics', [])
    fired_levers = state.get('a3_fired_levers', {})
    a2_alerted   = state.get('a2_last_alerted', {})

    # Load thresholds from config.json
    thresholds  = _get_thresholds()
    _OCW        = thresholds["ocw_threshold_sec"]
    _QUEUE_MIN  = thresholds["queue_min"]
    _SLA_AMBER  = thresholds["amber_threshold"]
    _SLA_RED    = thresholds["red_threshold"]
    _SLA_BLACK  = thresholds["black_threshold"]

    invoke_a2       = False
    use_llm         = False
    invoke_a3       = False
    critical_skills = []
    ocw_skills      = []
    lever_skills    = []
    recovering      = []
    reasons         = []

    for m in metrics:
        skill = m.skill_name
        sla   = m.service_level
        queue = m.calls_waiting
        avail = m.agents_available
        ocw   = m.ocw_seconds
        aux   = m.agents_on_aux

        # ── A2 trigger: queue with nobody available ───────────────────────────
        if queue >= _QUEUE_MIN and avail == 0:
            invoke_a2 = True
            critical_skills.append(skill)
            reasons.append(f"{skill}: queue={queue} avail=0")

        # ── A2 trigger: OCW breach ────────────────────────────────────────────
        if ocw > _OCW and queue > 0:
            invoke_a2 = True
            if skill not in ocw_skills:
                ocw_skills.append(skill)
            reasons.append(f"{skill}: OCW={m.ocw} > 60s")

        # ── LLM flag: only if AUX agents exist to move ───────────────────────
        if invoke_a2 and aux > 0:
            use_llm = True

        # ── A3 trigger: SLA threshold crossed for first time ─────────────────
        if sla < _SLA_AMBER:
            amber_fired = fired_levers.get(f"{skill}_Amber", False)
            red_fired   = fired_levers.get(f"{skill}_Red",   False)
            black_fired = fired_levers.get(f"{skill}_Black", False)

            should_fire = (
                (sla < _SLA_BLACK and not black_fired) or
                (sla < _SLA_RED   and not red_fired)   or
                (sla < _SLA_AMBER and not amber_fired)
            )

            if should_fire:
                invoke_a3 = True
                if skill not in lever_skills:
                    lever_skills.append(skill)
                reasons.append(f"{skill}: Lever — SLA={sla:.1f}%")

        # ── Recovery detection ────────────────────────────────────────────────
        was_breached = (
            f"{skill}_Amber" in fired_levers or
            skill in a2_alerted
        )
        is_now_clear = queue == 0 and avail > 0 and sla >= _SLA_AMBER

        if was_breached and is_now_clear:
            recovering.append({"skill": skill, "sla": sla, "avail": avail})
            reasons.append(f"{skill}: RECOVERED — SLA={sla:.1f}%")

    # ── Systemic check ────────────────────────────────────────────────────────
    is_systemic = (len(critical_skills) + len(ocw_skills)) >= SYSTEMIC_MIN_SKILLS

    # ── Write flags into state ────────────────────────────────────────────────
    state['_invoke_a2']       = invoke_a2
    state['_invoke_a3']       = invoke_a3
    state['use_llm']          = use_llm
    state['_critical_skills'] = critical_skills
    state['_ocw_skills']      = ocw_skills
    state['_lever_skills']    = lever_skills
    state['_is_systemic']     = is_systemic

    # ── Side effects ──────────────────────────────────────────────────────────
    if recovering:
        _send_recovery_alerts(state, recovering)

    if is_systemic:
        logger.warning(
            f"[{region}] ⚠️ SYSTEMIC — "
            f"{len(critical_skills) + len(ocw_skills)} skills in crisis: "
            f"{critical_skills + ocw_skills}"
        )

    # ── Logging ───────────────────────────────────────────────────────────────
    logger.info(
        f"[{region}] Router: "
        f"A2={invoke_a2} LLM={use_llm} A3={invoke_a3} "
        f"Systemic={is_systemic} | "
        f"Critical={critical_skills} OCW={ocw_skills} "
        f"Levers={lever_skills} "
        f"Recovering={[r['skill'] for r in recovering]}"
    )
    if reasons:
        logger.info(f"[{region}] Reasons: {' | '.join(reasons)}")
    else:
        logger.info(f"[{region}] All skills clear — no action needed")

    return state


# ── Conditional edge ──────────────────────────────────────────────────────────

def route_after_router(state: dict) -> Literal["a2_only", "a3_only", "both", "end"]:
    """Reads routing flags set by router_node and picks the graph path."""
    invoke_a2 = state.get('_invoke_a2', False)
    invoke_a3 = state.get('_invoke_a3', False)
    region    = state.get('region_display', state.get('region_name', 'RTA'))

    if invoke_a2 and invoke_a3:
        logger.info(f"[{region}] Route → BOTH (A2 + A3)")
        return "both"
    elif invoke_a2:
        logger.info(f"[{region}] Route → A2 only")
        return "a2_only"
    elif invoke_a3:
        logger.info(f"[{region}] Route → A3 only")
        return "a3_only"
    else:
        logger.info(f"[{region}] Route → END (all clear)")
        return "end"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_workflow(tag: str, scrape_only: bool = False):
    """
    Build and compile LangGraph workflow for a region.
    tag         = region name lowercase — 'rta', 'cn', 'au', 'emea'
    scrape_only = True  → Agent1 only (no analysis, no levers, no alerts)
                  False → Full pipeline (Agent1 → Router → Agent2/3)
    """
    agent1 = _load(f"rta_agent1_{tag}", "agents/agent1_collector.py")

    def agent1_node(state: dict) -> dict:
        try:
            return agent1.agent1_collector(state)
        except Exception as e:
            logger.error(f"[{tag.upper()}] Agent 1 error: {e}")
            state['error_count'] = state.get('error_count', 0) + 1
            return state

    if scrape_only:
        # Minimal graph — Agent1 only, straight to END
        workflow = StateGraph(dict)
        workflow.add_node("agent1", agent1_node)
        workflow.set_entry_point("agent1")
        workflow.add_edge("agent1", END)
        app = workflow.compile()
        logger.info(f"[{tag.upper()}] LangGraph workflow compiled (SCRAPE ONLY).")
        return app

    # Full pipeline
    agent2 = _load(f"rta_agent2_{tag}", "agents/agent2_analyst.py")
    agent3 = _load(f"rta_agent3_{tag}", "agents/agent3_lever.py")

    def agent2_node(state: dict) -> dict:
        if not state.get('breached_skills'):
            logger.info(f"[{tag.upper()}] A2: no breached skills — skipping.")
            return state
        try:
            return agent2.agent2_analyst(state)
        except Exception as e:
            logger.error(f"[{tag.upper()}] Agent 2 error: {e}")
            return state

    def agent3_node(state: dict) -> dict:
        try:
            return agent3.agent3_lever(state)
        except Exception as e:
            logger.error(f"[{tag.upper()}] Agent 3 error: {e}")
            return state

    workflow = StateGraph(dict)
    workflow.add_node("agent1", agent1_node)
    workflow.add_node("router", router_node)
    workflow.add_node("agent2", agent2_node)
    workflow.add_node("agent3", agent3_node)

    workflow.set_entry_point("agent1")
    workflow.add_edge("agent1", "router")
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"both": "agent2", "a2_only": "agent2", "a3_only": "agent3", "end": END}
    )
    workflow.add_conditional_edges(
        "agent2",
        lambda state: "agent3" if state.get('_invoke_a3') else END,
        {"agent3": "agent3", END: END}
    )
    workflow.add_edge("agent3", END)

    app = workflow.compile()
    logger.info(f"[{tag.upper()}] LangGraph workflow compiled (FULL).")
    return app