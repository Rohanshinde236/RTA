"""
agents/agent1_collector.py
Agent 1 — Real-time Dashboard Scraper + Breach Detector

Responsibilities:
  - Scrapes RTA dashboard every 60s via Playwright
  - Detects breach conditions per skill
  - Sends band drop Teams alert + email only (NO T1-T4 alerts)
  - Marks skills for Agent 2 (C1/C2/C3 breach conditions)
  - Agent 3 trigger handled by router in workflow.py

Breach conditions for Agent 2:
  C1: Band worsened (HEALTHY→WARNING, WARNING→CRITICAL etc)
  C2: SLA falling 3 consecutive polls
  C3: Queue doubled between polls (and queue >= 2)

NOTE: T1-T4 real-time Teams alerts REMOVED — A2 handles all messaging.
"""

import importlib.util
import logging
import os
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger      = logging.getLogger(__name__)
_collectors = {}   # {region_name: DashboardCollector} — one per region


def _get_a1_config() -> dict:
    """Load agent1 config from config.json. Falls back to defaults."""
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader_a1", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_agent1()
    except Exception:
        return {
            "scrape_interval_sec":      60,
            "band_drop_email_enabled":  True,
            "band_drop_teams_enabled":  True,
        }


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ROOT, rel)
    )
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Band drop Teams alert ─────────────────────────────────────────────────────

def _send_teams_adaptive(webhook, body_blocks, region):
    """Send Adaptive Card to Teams via Power Automate webhook."""
    if not webhook:
        return
    import requests
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": body_blocks,
                "msteams": {"width": "Full"}
            }
        }]
    }
    try:
        r = requests.post(webhook, json=card, timeout=10)
        logger.info(f"[{region}] Teams response: {r.status_code}")
    except Exception as e:
        logger.error(f"[{region}] Teams failed: {e}")


def _send_teams_band_drop(webhook, region, skill_name, old_band, new_band, metric):
    """Send band drop Adaptive Card alert."""
    if not webhook:
        return
    body = [
        {
            "type":   "TextBlock",
            "text":   f"Band Drop [{region}] — {skill_name}",
            "weight": "Bolder",
            "size":   "Large",
            "color":  "Attention"
        },
        {
            "type": "TextBlock",
            "text": (
                f"{old_band} -> {new_band} | "
                f"SLA: {metric.service_level:.1f}% | "
                f"Queue: {metric.calls_waiting} | "
                f"Avail: {metric.agents_available}"
            ),
            "wrap": True
        }
    ]
    _send_teams_adaptive(webhook, body, region)


# ── Main agent entry point ────────────────────────────────────────────────────

def agent1_collector(state: dict) -> dict:
    logger.info("=== Agent 1 — Queue Data Collector ===")

    webhook     = state.get('teams_webhook', '') or os.getenv("TEAMS_WEBHOOK_URL", "")
    region_name = state.get('region_name', 'RTA')
    tag         = state.get('region_tag', region_name.lower())

    # Load region-specific modules
    _models      = _load(f"rta_core_models_{tag}", "core/models.py")
    SkillHistory = _models.SkillHistory
    get_band     = _models.get_band
    _email_mod   = _load(f"rta_alerts_email_{tag}", "alerts/email.py")

    # ── Scrape dashboard ──────────────────────────────────────────────────────
    try:
        if region_name not in _collectors:
            path = state.get('dashboard_path') or ''
            logger.info(f"[{region_name}] Creating collector for: {path}")
            _coll_mod = _load(f"rta_dashboard_{tag}", "dashboard/collector.py")
            _collectors[region_name] = _coll_mod.DashboardCollector(path or None)

        metrics = _collectors[region_name].collect()
        if not metrics:
            logger.warning("Agent 1: no metrics returned.")
            return state

    except Exception as e:
        if "LOGIN FAILED" in str(e):
            logger.error(f"Agent 1 LOGIN FAILED: {e}")
            raise
        logger.error(f"Agent 1 scrape error: {e}")
        state['error_count'] = state.get('error_count', 0) + 1
        return state

    logger.info(f"Scraped — {len(metrics)} active skills")

    # ── Init histories ────────────────────────────────────────────────────────
    histories = dict(state.get('skill_histories') or {})
    for m in metrics:
        if m.skill_name not in histories:
            histories[m.skill_name] = SkillHistory(skill_name=m.skill_name)

    breached = {}   # skills marked for A2 analysis

    for m in metrics:
        hist         = histories[m.skill_name]
        current_band = get_band(m.service_level)
        old_band     = hist.last_band
        band_order   = {"HEALTHY": 0, "WARNING": 1, "CRITICAL": 2, "SEVERE": 3}

        # ── Band drop — worsening only ────────────────────────────────────────
        if (old_band and old_band != current_band and
                band_order.get(current_band, 0) > band_order.get(old_band, 0)):

            msg = (
                f"{m.skill_name} band dropped: {old_band} -> {current_band}. "
                f"SLA: {m.service_level:.1f}%. "
                f"Queue: {m.calls_waiting}, Avail: {m.agents_available}."
            )

            a1_cfg = _get_a1_config()

            # Teams band drop alert
            if a1_cfg.get("band_drop_teams_enabled", True):
                _send_teams_band_drop(
                    webhook, region_name, m.skill_name,
                    old_band, current_band, m
                )

            # Email band drop alert
            if a1_cfg.get("band_drop_email_enabled", True):
                try:
                    _email_mod.send_email_band_drop(
                        skill_name=m.skill_name,
                        old_band=old_band,
                        new_band=current_band,
                        metric=m,
                        message=msg
                    )
                except Exception as e:
                    logger.error(f"Band drop email failed: {e}")

            logger.info(f"BAND DROP: {m.skill_name} {old_band} -> {current_band}.")

        # ── Update history ────────────────────────────────────────────────────
        hist.update(m)

        # ── Breach conditions for Agent 2 ─────────────────────────────────────
        reasons = hist.get_breach_reasons(current_band)

        if m.calls_waiting >= 1 and m.agents_available == 0:
            if not reasons:
                reasons = ["QUEUE_PRESSURE"]
            breached[m.skill_name] = reasons
            logger.info(f"BREACH (queue+avail=0): {m.skill_name} — {reasons}")
        elif m.ocw_seconds > 60 and m.calls_waiting > 0:
            if not reasons:
                reasons = ["OCW_PRESSURE"]
            breached[m.skill_name] = reasons
            logger.info(f"BREACH (OCW): {m.skill_name} — {reasons}")
        elif reasons:
            logger.info(
                f"BREACH conditions met but no queue/OCW pressure "
                f"— skipping A2 for {m.skill_name}"
            )

        hist.last_band = current_band

    # ── Update state ──────────────────────────────────────────────────────────
    state['skill_metrics']   = metrics
    state['skill_histories'] = histories
    state['breached_skills'] = breached
    state['last_poll_time']  = datetime.now()

    logger.info(
        f"Agent 1 complete — {len(metrics)} skills scraped, "
        f"{len(breached)} breached."
    )
    return state


def cleanup_collector():
    global _collectors
    for region, collector in _collectors.items():
        try:
            collector.cleanup()
            logger.info(f"[{region}] Browser closed.")
        except Exception as e:
            logger.warning(f"[{region}] Cleanup error: {e}")
    _collectors = {}