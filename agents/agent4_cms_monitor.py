"""
agents/agent4_cms_monitor.py
Agent 4 — CMS Monitor

Runs independently every 60 seconds (not tied to A1 poll cycle).
Scrapes CMS for ALL skills across ALL regions and checks:
  1. AHT (Average Handle Time) vs target
  2. AUX usage patterns — too many agents on extended breaks

Sends Teams alert if thresholds breached.
No LLM — pure rule-based fast checks.

Run from run_all.py in a separate thread:
  threading.Thread(target=agent4_monitor_loop, args=(webhook, region_name, dashboard_path, tag), daemon=True)
"""

import importlib.util
import logging
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

# ── Thresholds — loaded from config.json via config_loader ──────────────────
POLL_INTERVAL_SEC = 60   # default — overridden by config.json

def _get_a4_config():
    """Load agent4 config from config.json."""
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader_a4", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_agent4(), mod
    except Exception:
        return {
            "scrape_interval_sec": 60,
            "aht_target_min":      24,
            "acw_target_min":      5,
            "aux_thresholds": {
                "AUX2": {"name": "Break",     "max_time_min": 15, "enabled": True},
                "AUX3": {"name": "Lunch",     "max_time_min": 30, "enabled": True},
                "AUX6": {"name": "Case Mgmt", "max_time_min": 45, "enabled": True},
            }
        }, None

def _get_aht_sec(skill_name: str) -> int:
    """Get AHT target in seconds from config.json for a skill."""
    try:
        spec = importlib.util.spec_from_file_location(
            "config_loader_aht", os.path.join(_ROOT, "core", "config_loader.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_aht_target_sec(skill_name)
    except Exception:
        return AHT_TARGETS.get(skill_name, AHT_TARGETS.get("DEFAULT", 24*60))

# AHT targets per skill (seconds) — fallback if config.json not available
AHT_TARGETS = {
    # APJ-IN
    "TS_CSTCE":         24 * 60,
    "TS_CSTElite":      22 * 60,
    "TS_LicKeys":       26 * 60,
    "TS_VICHW":         20 * 60,
    "TS_CSTVCE":        24 * 60,
    "TS_CSTCritAcct":   28 * 60,
    # APJ-CN
    "TS_CN_ProDB":      24 * 60,
    "TS_CN_ProCNX":     24 * 60,
    "TS_CN_Elite":      22 * 60,
    "TS_CN_LicKeys":    26 * 60,
    "TS_CN_VICHW":      20 * 60,
    "TS_CN_CritAcct":   28 * 60,
    # APJ-AU
    "TS_AU_ProDB":      24 * 60,
    "TS_AU_ProCNX":     24 * 60,
    "TS_AU_Elite":      22 * 60,
    "TS_AU_LicKeys":    26 * 60,
    "TS_AU_VICHW":      20 * 60,
    "TS_AU_CritAcct":   28 * 60,
    # EMEA
    "TS_MLSCST_GER":    22 * 60,
    "TS_MLSCST_SPA":    22 * 60,
    "TS_MLSCST_FRA":    22 * 60,
    "TS_MLSCST_ITA":    22 * 60,
    "TS_MLSCST_NLD":    22 * 60,
    "TS_MLSCST_POL":    22 * 60,
    # APJ-HK
    "TS_HK_ProDB":      24 * 60,
    "TS_HK_ProCNX":     24 * 60,
    "TS_HK_Elite":      22 * 60,
    "TS_HK_LicKeys":    26 * 60,
    "TS_HK_VICHW":      20 * 60,
    "TS_HK_CritAcct":   28 * 60,
    # APJ-MY
    "TS_MY_ProDB":      24 * 60,
    "TS_MY_ProCNX":     24 * 60,
    "TS_MY_Elite":      22 * 60,
    "TS_MY_LicKeys":    26 * 60,
    "TS_MY_VICHW":      20 * 60,
    "TS_MY_CritAcct":   28 * 60,
    # APJ-KR
    "TS_KR_ProDB":      24 * 60,
    "TS_KR_ProCNX":     24 * 60,
    "TS_KR_Elite":      22 * 60,
    "TS_KR_LicKeys":    26 * 60,
    "TS_KR_VICHW":      20 * 60,
    "TS_KR_CritAcct":   28 * 60,
    # APJ-TH
    "TS_TH_ProDB":      24 * 60,
    "TS_TH_ProCNX":     24 * 60,
    "TS_TH_Elite":      22 * 60,
    "TS_TH_LicKeys":    26 * 60,
    "TS_TH_VICHW":      20 * 60,
    "TS_TH_CritAcct":   28 * 60,
    # LATAM-BR
    "TS_BR_ProDB":      24 * 60,
    "TS_BR_ProCNX":     24 * 60,
    "TS_BR_Elite":      22 * 60,
    "TS_BR_LicKeys":    26 * 60,
    "TS_BR_VICHW":      20 * 60,
    "TS_BR_CritAcct":   28 * 60,
    # APJ-TW
    "TS_TW_ProDB":      24 * 60,
    "TS_TW_ProCNX":     24 * 60,
    "TS_TW_Elite":      22 * 60,
    "TS_TW_LicKeys":    26 * 60,
    "TS_TW_VICHW":      20 * 60,
    "TS_TW_CritAcct":   28 * 60,
    # Default fallback
    "DEFAULT":          24 * 60,
}

AHT_BREACH_THRESHOLD = 1.10   # alert if AHT > target × 110%

# AUX thresholds
MAX_AGENTS_ON_EXTENDED_BREAK = 2   # alert if > 2 agents on break > 15 min
MAX_AGENTS_ON_EXTENDED_LUNCH = 1   # alert if > 1 agent on lunch > 30 min
MAX_CASE_MGMT_AGENTS         = 3   # alert if > 3 agents on Aux6

# Skills to monitor per region tag
SKILLS_BY_REGION = {
    "rta": [
        "TS_CSTCE", "TS_CSTElite", "TS_LicKeys",
        "TS_VICHW", "TS_CSTVCE",   "TS_CSTCritAcct",
    ],
    "cn": [
        "TS_CN_ProDB",  "TS_CN_ProCNX", "TS_CN_Elite",
        "TS_CN_LicKeys","TS_CN_VICHW",  "TS_CN_CritAcct",
    ],
    "au": [
        "TS_AU_ProDB",  "TS_AU_ProCNX", "TS_AU_Elite",
        "TS_AU_LicKeys","TS_AU_VICHW",  "TS_AU_CritAcct",
    ],
    "emea": [
        "TS_MLSCST_GER", "TS_MLSCST_SPA", "TS_MLSCST_FRA",
        "TS_MLSCST_ITA", "TS_MLSCST_NLD", "TS_MLSCST_POL",
    ],
    "hk": [
        "TS_HK_ProDB",  "TS_HK_ProCNX", "TS_HK_Elite",
        "TS_HK_LicKeys","TS_HK_VICHW",  "TS_HK_CritAcct",
    ],
    "my": [
        "TS_MY_ProDB",  "TS_MY_ProCNX", "TS_MY_Elite",
        "TS_MY_LicKeys","TS_MY_VICHW",  "TS_MY_CritAcct",
    ],
    "kr": [
        "TS_KR_ProDB",  "TS_KR_ProCNX", "TS_KR_Elite",
        "TS_KR_LicKeys","TS_KR_VICHW",  "TS_KR_CritAcct",
    ],
    "th": [
        "TS_TH_ProDB",  "TS_TH_ProCNX", "TS_TH_Elite",
        "TS_TH_LicKeys","TS_TH_VICHW",  "TS_TH_CritAcct",
    ],
    "br": [
        "TS_BR_ProDB",  "TS_BR_ProCNX", "TS_BR_Elite",
        "TS_BR_LicKeys","TS_BR_VICHW",  "TS_BR_CritAcct",
    ],
    "tw": [
        "TS_TW_ProDB",  "TS_TW_ProCNX", "TS_TW_Elite",
        "TS_TW_LicKeys","TS_TW_VICHW",  "TS_TW_CritAcct",
    ],
}
# Default fallback — all skills
ALL_SKILLS = [s for skills in SKILLS_BY_REGION.values() for s in skills]


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


# ── Teams sender ──────────────────────────────────────────────────────────────

def _send_teams_alert(webhook, region, alerts):
    """Send Agent 4 CMS monitor alert as Adaptive Card."""
    if not webhook or not alerts:
        return
    import requests

    body = [
        {
            "type":    "TextBlock",
            "text":    f"📋 [{region}] CMS Monitor Alert",
            "weight":  "Bolder",
            "size":    "Large",
            "color":   "Attention"
        },
        {
            "type":    "TextBlock",
            "text":    "Agent 4 — CMS check detected issues:",
            "wrap":    True,
            "spacing": "Small"
        }
    ]

    for alert in alerts:
        skill   = alert.get('skill', '')
        a_type  = alert.get('type', '')
        message = alert.get('message', '')
        icon    = {"AHT":"⏱️","AUX_BREAK":"☕","AUX_LUNCH":"🍽️","AUX_CASE_MGMT":"📁"}.get(a_type,"⚠️")
        body.append({
            "type":    "TextBlock",
            "text":    f"{icon} **{skill}** — {message}",
            "wrap":    True,
            "spacing": "Small"
        })

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

    try:
        r = requests.post(webhook, json=card, timeout=10)
        logger.info(f"A4 [{region}]: Teams alert sent — {r.status_code}")
    except Exception as e:
        logger.error(f"A4 [{region}]: Teams failed: {e}")


# ── Time helpers ──────────────────────────────────────────────────────────────

def _parse_time_seconds(time_str: str) -> int:
    if not time_str or time_str in ('—', '-', ''):
        return 0
    parts = time_str.strip().split(':')
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0


def _seconds_to_str(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


# ── AUX analysis ──────────────────────────────────────────────────────────────

def _analyse_aux(agents: list, skill_name: str) -> list:
    """
    Check AUX patterns using config-driven thresholds.
    Each AUX code has its own max_time_min and enabled flag from config.
    """
    alerts     = []
    aux_agents = [a for a in agents if a.get('state') == 'AUX']
    if not aux_agents:
        return []

    # Load aux thresholds from config
    a4_cfg         = _get_a4_config()[0]
    aux_thresholds = a4_cfg.get("aux_thresholds", {})

    # Group agents by AUX code
    aux_groups = {}
    for a in aux_agents:
        reason   = a.get('aux_reason', '')
        time_min = a.get('time_minutes', 0)
        name     = a.get('name', '')

        # Extract AUX number from reason string e.g. "AUX 2" -> "AUX2"
        aux_key = None
        for i in range(1, 10):
            if f'AUX {i}' in reason or f'Aux{i}' in reason or f'AUX{i}' in reason:
                aux_key = f'AUX{i}'
                break

        if aux_key:
            if aux_key not in aux_groups:
                aux_groups[aux_key] = []
            aux_groups[aux_key].append((name, time_min))

    # Check each AUX group against its threshold
    for aux_key, agents_list in aux_groups.items():
        cfg = aux_thresholds.get(aux_key, {})
        if not cfg.get('enabled', False):
            continue

        max_time = cfg.get('max_time_min', 0)
        if max_time == 0:
            continue

        aux_name     = cfg.get('name', aux_key)
        exceeded     = [(n, m) for n, m in agents_list if m > max_time]

        if exceeded:
            names = ", ".join(f"{n} ({m:.0f}min)" for n, m in exceeded)
            alerts.append({
                "skill":   skill_name,
                "type":    f"AUX_{aux_key}",
                "message": (
                    f"{len(exceeded)} agent(s) on {aux_name} exceeded "
                    f"{max_time}min limit: {names}"
                )
            })

    return alerts


# ── AHT analysis ──────────────────────────────────────────────────────────────

def _analyse_aht(agents: list, skill_name: str) -> list:
    alerts     = []
    acd_agents = [a for a in agents if a.get('state') == 'ACD']
    if not acd_agents:
        return []

    # Per-skill target takes priority; global is only used as fallback when 0
    target_sec = _get_aht_sec(skill_name)
    a4_cfg     = _get_a4_config()[0]
    aht_global = a4_cfg.get("aht_target_min", 0)
    if target_sec <= 0 and aht_global > 0:
        target_sec = aht_global * 60
    if target_sec <= 0:
        target_sec = 24 * 60
    breach_sec = int(target_sec * 1.10)  # alert at 110% of target

    high = []
    for a in acd_agents:
        call_sec = a.get('time_seconds', 0)
        if call_sec > breach_sec:
            high.append((a.get('name', ''), _seconds_to_str(call_sec), call_sec))

    if high:
        # Sort by longest call first, show top 3 + overflow count
        high.sort(key=lambda x: x[2], reverse=True)
        shown   = high[:3]
        extra   = len(high) - 3
        names   = ", ".join(f"{n} ({t})" for n, t, _ in shown)
        if extra > 0:
            names += f" +{extra} more"
        alerts.append({"skill": skill_name, "type": "AHT",
            "message": (
                f"{len(high)} agent(s) > AHT "
                f"(target {_seconds_to_str(target_sec)}): {names}"
            )})
    return alerts


# ── Main monitor function ─────────────────────────────────────────────────────

def agent4_monitor(webhook: str, region_name: str, cms_collector, skills: list) -> list:
    """
    Single Agent 4 check — scrape CMS for region's skills and check thresholds.
    Returns list of all alerts found.
    """
    logger.info(f"=== Agent 4 — CMS Monitor [{region_name}] ===")
    all_alerts = []

    for skill_name in skills:
        try:
            agents = cms_collector.collect(skill_name)
            if not agents:
                logger.info(f"A4 [{region_name}]: No agents for {skill_name} — skipping")
                continue

            aux_alerts = _analyse_aux(agents, skill_name)
            aht_alerts = _analyse_aht(agents, skill_name)
            all_alerts.extend(aux_alerts)
            all_alerts.extend(aht_alerts)

            if aux_alerts or aht_alerts:
                logger.info(
                    f"A4 [{region_name}]: {skill_name} — "
                    f"{len(aux_alerts)} AUX, {len(aht_alerts)} AHT alerts"
                )
            else:
                logger.info(f"A4 [{region_name}]: {skill_name} — clear")

        except Exception as e:
            logger.error(f"A4 [{region_name}]: Error checking {skill_name}: {e}")

    if all_alerts:
        _send_teams_alert(webhook, region_name, all_alerts)
        logger.info(f"A4 [{region_name}] complete — {len(all_alerts)} issue(s) found.")
    else:
        logger.info(f"A4 [{region_name}] complete — all skills clear.")

    return all_alerts


# ── Background loop ───────────────────────────────────────────────────────────

def agent4_monitor_loop(webhook: str, region_name: str, dashboard_path: str,
                        tag: str = None, initial_delay_sec: int = 0):
    """
    Permanent background thread for Agent 4.
    Runs every POLL_INTERVAL_SEC seconds.
    Creates its own CMS browser — does NOT share A2's browser.
    initial_delay_sec: stagger offset so all 10 regions don't fire simultaneously.
    """
    if tag is None:
        tag = region_name.lower()

    if initial_delay_sec > 0:
        logger.info(f"A4 [{region_name}]: staggered start — waiting {initial_delay_sec}s")
        time.sleep(initial_delay_sec)

    logger.info(f"A4 [{region_name}]: Starting CMS monitor thread (every {POLL_INTERVAL_SEC}s)...")

    # Get skills for this region
    skills = SKILLS_BY_REGION.get(tag, ALL_SKILLS)
    logger.info(f"A4 [{region_name}]: Monitoring {len(skills)} skills: {skills}")

    # Load CMS collector
    cms_collector = None
    try:
        cms_file = os.path.join(_ROOT, "dashboard", "cms_collector.py")
        mod_key  = f"rta_cms_mod_a4_{tag}"
        spec     = importlib.util.spec_from_file_location(mod_key, cms_file)
        mod      = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        cms_path = os.path.join(
            os.path.dirname(dashboard_path), 'CMS.html'
        ) if dashboard_path else os.path.join(_ROOT, 'ui', 'CMS.html')

        cms_collector = mod.CMSCollector(cms_path)
        logger.info(f"A4 [{region_name}]: CMS browser ready — {cms_path}")

    except Exception as e:
        logger.error(f"A4 [{region_name}]: CMS init failed — {e}")
        return

    while True:
        try:
            agent4_monitor(webhook, region_name, cms_collector, skills)
        except Exception as e:
            logger.error(f"A4 [{region_name}]: Monitor error: {e}")

        # Read poll interval from config each loop
        a4_cfg_now   = _get_a4_config()[0]
        interval_sec = a4_cfg_now.get("scrape_interval_sec",
                       a4_cfg_now.get("poll_interval_sec", POLL_INTERVAL_SEC))
        logger.info(f"A4 [{region_name}]: Next check in {interval_sec}s.")
        time.sleep(interval_sec)