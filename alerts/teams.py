"""
alerts/teams.py
Microsoft Teams webhook alerts.
Webhook is set via _WEBHOOK_URL module variable
patched directly by run_all.py per region.
"""

import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import requests

logger = logging.getLogger(__name__)

# ── Per-region webhook — patched by run_all.py ────────────────────────────────
# DO NOT use os.getenv here — shared between threads!
_WEBHOOK_OVERRIDE = None


def _get_webhook() -> str:
    """Get webhook — prefer module override over env var."""
    return _WEBHOOK_OVERRIDE or os.getenv("TEAMS_WEBHOOK_URL", "")


def send_teams(title: str, message: str, facts: list = None, color: str = "Attention") -> bool:
    webhook = _get_webhook()
    if not webhook:
        logger.warning("Teams webhook not configured.")
        return False

    body = [
        {"type": "TextBlock", "text": title,
         "weight": "Bolder", "size": "Large", "color": color},
        {"type": "TextBlock", "text": message, "wrap": True}
    ]
    if facts:
        body.append({"type": "TextBlock", "text": "Skill Details",
                     "weight": "Bolder", "size": "Medium", "spacing": "Medium"})
        body.append({"type": "FactSet", "facts": facts[:10]})

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard", "version": "1.4",
                "body": body, "msteams": {"width": "Full"}
            }
        }]
    }
    try:
        requests.post(webhook, json=card, timeout=10)
        logger.info(f"Teams sent: {title}")
        return True
    except Exception as e:
        logger.error(f"Teams failed: {e}")
        return False


def send_teams_skill_alerts(alerts: list, poll_number: int, region: str = "RTA") -> bool:
    webhook = _get_webhook()
    if not webhook or not alerts:
        if not webhook:
            logger.warning("Teams webhook not configured.")
        return False

    t_ocw  = [a for a in alerts if a.get("trigger") == "OCW"]
    t_risk = [a for a in alerts if a.get("trigger") == "SL_RISK"]
    t_aux  = [a for a in alerts if a.get("trigger") == "AUX"]
    t_q    = [a for a in alerts if a.get("trigger") == "QUEUE"]

    body = [{
        "type": "TextBlock",
        "text": f"📊 [{region}] Real-Time Skill Alert — Poll #{poll_number}",
        "weight": "Bolder", "size": "Large"
    }]

    def add_section(heading, items, color="Attention"):
        if not items:
            return
        body.append({"type": "TextBlock", "text": heading,
                     "weight": "Bolder", "size": "Medium",
                     "color": color, "spacing": "Medium"})
        for a in items:
            body.append({"type": "TextBlock", "text": a["message"], "wrap": True})

    add_section("🔴 OCW — Oldest Call Waiting > 1 Minute", t_ocw)
    add_section("🚨 SL AT RISK — Queue > Available Agents", t_risk)
    add_section("💡 AUX OPPORTUNITY — Move Agents!", t_aux, "Good")
    add_section("⚠️ CALLS IN QUEUE", t_q, "Warning")

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard", "version": "1.4",
                "body": body, "msteams": {"width": "Full"}
            }
        }]
    }
    try:
        requests.post(webhook, json=card, timeout=10)
        logger.info(f"[{region}] Teams skill alerts sent ({len(alerts)} alerts).")
        return True
    except Exception as e:
        logger.error(f"Teams skill alerts failed: {e}")
        return False