"""
core/state.py
AgentState — shared state dict passed between all agents each poll.

Updated for RTA v3 multi-region:
  - region_tag:     short slug for module namespacing e.g. "rta", "cn", "au", "emea"
  - region_display: human-readable label for Teams/email e.g. "Client ProSupport IND"
  - Agent 1: skill_metrics, skill_histories, breached_skills
  - Agent 2: analyst_decisions, a2_last_alerted, use_llm
  - Agent 3: a3_fired_levers
  - Agent 4: runs in own thread, does not read/write this state
"""

from typing import TypedDict, Dict, List, Optional, Any
from datetime import datetime


class AgentState(TypedDict, total=False):
    """
    Full state passed between agents every poll.
    All fields optional (total=False) so agents can add incrementally.
    """

    # ── Region config ─────────────────────────────────────────────────────────
    region_name:    str   # "RTA" / "CN" / "AU" / "EMEA"
    region_tag:     str   # short slug: "rta" / "cn" / "au" / "emea"
    region_display: str   # label in Teams/email: "Client ProSupport IND" etc
    dashboard_path: str   # full path to RTA.html
    teams_webhook:  str   # Power Automate webhook URL

    # ── Poll tracking ─────────────────────────────────────────────────────────
    poll_number:    int
    last_poll_time: Optional[datetime]
    error_count:    int

    # ── Agent 1 outputs ───────────────────────────────────────────────────────
    skill_metrics:   List[Any]
    skill_histories: Dict[str, Any]
    breached_skills: Dict[str, List[str]]

    # ── Agent 2 inputs/outputs ────────────────────────────────────────────────
    analyst_decisions: Dict[str, Any]
    use_llm:           bool
    a2_last_alerted:   Dict[str, float]

    # ── Agent 3 inputs/outputs ────────────────────────────────────────────────
    a3_fired_levers: Dict[str, bool]

    # ── Router flags ──────────────────────────────────────────────────────────
    _invoke_a2: bool
    _invoke_a3: bool
    _use_llm:   bool


def initial_state(
    region_name:    str,
    dashboard_path: str,
    webhook:        str,
    region_tag:     str = None,
    region_display: str = None,
) -> AgentState:
    """
    Create fresh initial state for a region.
    Called once at startup by run_all.py region_loop.
    """
    tag     = region_tag     or region_name.lower()
    display = region_display or region_name

    return AgentState(
        region_name      = region_name,
        region_tag       = tag,
        region_display   = display,
        dashboard_path   = dashboard_path,
        teams_webhook    = webhook,
        poll_number      = 1,
        last_poll_time   = None,
        error_count      = 0,
        skill_metrics    = [],
        skill_histories  = {},
        breached_skills  = {},
        analyst_decisions= {},
        use_llm          = True,
        a2_last_alerted  = {},
        a3_fired_levers  = {},
    )