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
import json
import logging
import os
import re as _re
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)

# ── Shared lock for cms_agents.json — one lock across all 10 region copies ────
# (agent4 is loaded as rta_agent4_<tag> — each copy has its own module namespace,
#  so a plain threading.Lock() would NOT be shared between regions)
_CMS_LOCK_KEY = "__rta_cms_agents_lock__"
if _CMS_LOCK_KEY not in sys.modules:
    sys.modules[_CMS_LOCK_KEY] = threading.Lock()
_CMS_STATE_LOCK = sys.modules[_CMS_LOCK_KEY]

_CMS_STATE_PATH = os.path.join(_ROOT, "db", "cms_agents.json")

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
        skill    = alert.get('skill', '')
        a_type   = alert.get('type', '')
        message  = alert.get('message', '')
        aux_name = alert.get('aux_name', '').lower()
        if a_type == 'AHT':
            icon = '⏱️'
        elif a_type == 'ACW':
            icon = '📝'
        elif a_type == 'AUX':
            if 'break' in aux_name:      icon = '☕'
            elif 'lunch' in aux_name:    icon = '🍽️'
            elif 'case' in aux_name:     icon = '📁'
            elif 'meeting' in aux_name:  icon = '📅'
            elif 'training' in aux_name: icon = '📚'
            elif 'outbound' in aux_name: icon = '📞'
            else:                        icon = '🔶'
        else:
            icon = '⚠️'
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

    Per-skill AUX count gate (aux_threshold in skill_thresholds):
      If total agents currently on AUX  <=  skill's aux_threshold, the skill
      has enough staffing headroom — suppress all AUX time alerts for this
      poll cycle (healthy skills like ProDB don't need AUX micromanagement).
      When count exceeds threshold, normal time-based checks fire.
    """
    alerts     = []
    aux_agents = [a for a in agents if a.get('state') == 'AUX']
    if not aux_agents:
        return []

    # ── Per-skill AUX count gate ──────────────────────────────────────────────
    # Loads aux_threshold from config.json → skill_thresholds[skill_name]
    # Falls back to name-pattern defaults in config_loader.get_aux_max().
    _, config_mod = _get_a4_config()
    if config_mod:
        try:
            skill_aux_max = config_mod.get_aux_max(skill_name)
            if len(aux_agents) <= skill_aux_max:
                return []   # within allowed limit — no alerts needed
        except Exception:
            pass            # config_mod missing get_aux_max — fall through

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
                "skill":    skill_name,
                "type":     "AUX",
                "aux_key":  aux_key,   # e.g. "AUX2"
                "aux_name": aux_name,  # e.g. "Break"
                "message":  (
                    f"{len(exceeded)} agent(s) on {aux_name} exceeded "
                    f"{max_time}min limit: {names}"
                )
            })

    return alerts


# ── ACW analysis ──────────────────────────────────────────────────────────────

def _analyse_acw(agents: list, skill_name: str) -> list:
    """
    Alert when agents stay in After-Call-Work (ACW) longer than acw_target_min.
    acw_target_min=0 disables the check.
    """
    a4_cfg      = _get_a4_config()[0]
    target_min  = a4_cfg.get("acw_target_min", 0)
    if target_min <= 0:
        return []   # disabled

    acw_agents = [a for a in agents if a.get('state', '').upper() == 'ACW']
    if not acw_agents:
        return []

    exceeded = [
        (a.get('name', ''), a.get('time_minutes', 0))
        for a in acw_agents
        if a.get('time_minutes', 0) > target_min
    ]
    if not exceeded:
        return []

    exceeded.sort(key=lambda x: x[1], reverse=True)
    names = ", ".join(f"{n} ({m:.0f}min)" for n, m in exceeded)
    return [{
        "skill":   skill_name,
        "type":    "ACW",
        "message": f"{len(exceeded)} agent(s) in ACW > {target_min}min: {names}"
    }]


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


# ── Chatbot snapshot helpers ──────────────────────────────────────────────────

def _resolve_aux_name(raw_reason: str, aux_thresholds: dict) -> tuple:
    """
    Given raw AUX reason from CMS (e.g. "AUX 2"), return (aux_key, friendly_name).
    Falls back to raw_reason if no mapping found.
    """
    m = _re.search(r'AUX\s*(\d+)', raw_reason, _re.IGNORECASE)
    if m:
        aux_key  = f"AUX{m.group(1)}"
        cfg_name = aux_thresholds.get(aux_key, {}).get("name", "")
        return aux_key, cfg_name or raw_reason
    return "", raw_reason or "—"


def _save_agents_snapshot(region_tag: str, agents_by_skill: dict):
    """
    Write per-region per-skill agent list to db/cms_agents.json.
    Called after every Agent 4 poll — chatbot reads this file.
    Thread-safe: shared lock across all region copies via sys.modules.
    """
    try:
        with _CMS_STATE_LOCK:
            # Read current file (other regions may have written)
            existing = {}
            try:
                with open(_CMS_STATE_PATH, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

            existing[region_tag] = agents_by_skill

            tmp = _CMS_STATE_PATH + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2, default=str)
                os.replace(tmp, _CMS_STATE_PATH)
            except OSError:
                # OneDrive lock fallback
                with open(_CMS_STATE_PATH, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"A4: cms_agents.json write failed: {e}")


# ── Main monitor function ─────────────────────────────────────────────────────

def agent4_monitor(webhook: str, region_name: str, cms_collector, skills: list,
                   region_tag: str = "") -> list:
    """
    Single Agent 4 check — scrape CMS for region's skills and check thresholds.
    Returns list of all alerts found.
    """
    logger.info(f"=== Agent 4 — CMS Monitor [{region_name}] ===")
    all_alerts      = []
    agents_snapshot = {}   # {skill_name: [agent_dicts]} — written to cms_agents.json

    a4_cfg, _ = _get_a4_config()
    aux_thresholds = a4_cfg.get("aux_thresholds", {})

    for skill_name in skills:
        try:
            # Respect per-skill active toggle from Skill Thresholds UI
            skill_cfg = _get_a4_config()[1]
            if skill_cfg:
                sk = skill_cfg.get_skill(skill_name)
                if not sk.get("active", True):
                    logger.info(f"A4 [{region_name}]: {skill_name} — inactive (skipped)")
                    continue

            agents = cms_collector.collect(skill_name)
            if not agents:
                logger.info(f"A4 [{region_name}]: No agents for {skill_name} — skipping")
                continue

            # ── Build chatbot snapshot for this skill ─────────────────────────
            skill_agents = []
            for a in agents:
                raw_reason = a.get("aux_reason", "")
                aux_key, aux_name = _resolve_aux_name(raw_reason, aux_thresholds)
                skill_agents.append({
                    "name":         a.get("name", ""),
                    "state":        a.get("state", ""),
                    "aux_reason":   raw_reason,
                    "aux_key":      aux_key,           # e.g. "AUX2"
                    "aux_name":     aux_name,          # e.g. "Break"
                    "time_minutes": a.get("time_minutes", 0),
                    "skill":        skill_name,
                })
            agents_snapshot[skill_name] = skill_agents

            # ── Alert analysis ─────────────────────────────────────────────────
            aux_alerts = _analyse_aux(agents, skill_name)
            acw_alerts = _analyse_acw(agents, skill_name)
            aht_alerts = _analyse_aht(agents, skill_name)
            all_alerts.extend(aux_alerts)
            all_alerts.extend(acw_alerts)
            all_alerts.extend(aht_alerts)

            if aux_alerts or acw_alerts or aht_alerts:
                logger.info(
                    f"A4 [{region_name}]: {skill_name} — "
                    f"{len(aux_alerts)} AUX, {len(aht_alerts)} AHT alerts"
                )
            else:
                logger.info(f"A4 [{region_name}]: {skill_name} — clear")

        except Exception as e:
            logger.error(f"A4 [{region_name}]: Error checking {skill_name}: {e}")

    # ── Persist agent snapshot for chatbot ────────────────────────────────────
    tag = region_tag or region_name.lower()
    _save_agents_snapshot(tag, agents_snapshot)

    if all_alerts:
        _send_teams_alert(webhook, region_name, all_alerts)
        logger.info(f"A4 [{region_name}] complete — {len(all_alerts)} issue(s) found.")
    else:
        logger.info(f"A4 [{region_name}] complete — all skills clear.")

    return all_alerts


# ── Shared CMS collector ──────────────────────────────────────────────────────

def _get_cms_collector():
    """
    Return the SINGLE global CMS collector shared across all regions (and Agent 2).
    All regions read the same ui/CMS.html, so one browser + one background thread
    serves every region's requests through its internal queue.

    Previously each region's Agent 4 created its own CMSCollector → up to 10
    Chromium browsers launching at once → some background threads timed out and
    fell back to sync mode with no page → "CMSCollector: page not initialized".
    Sharing one collector (same sys.modules key Agent 2 uses) removes that race.
    """
    inst_key = "__rta_cms_inst_global__"
    if inst_key in sys.modules:
        return sys.modules[inst_key]

    lock_key = "__rta_cms_create_lock__"
    if lock_key not in sys.modules:
        sys.modules[lock_key] = threading.Lock()

    with sys.modules[lock_key]:
        if inst_key in sys.modules:               # double-checked under lock
            return sys.modules[inst_key]
        cms_file = os.path.join(_ROOT, "dashboard", "cms_collector.py")
        cms_path = os.path.join(_ROOT, "ui", "CMS.html")
        mod_key  = "__rta_cms_mod_global__"
        if mod_key in sys.modules:
            del sys.modules[mod_key]
        spec    = importlib.util.spec_from_file_location(mod_key, cms_file)
        cms_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cms_mod)
        collector = cms_mod.CMSCollector(cms_path)
        sys.modules[inst_key] = collector
        logger.info("A4: Global CMS collector created — shared across all regions.")
        return collector


# ── Background loop ───────────────────────────────────────────────────────────

def agent4_monitor_loop(webhook: str, region_name: str, dashboard_path: str,
                        tag: str = None, initial_delay_sec: int = 0):
    """
    Permanent background thread for Agent 4.
    Runs every POLL_INTERVAL_SEC seconds.
    Uses the single shared global CMS browser (same one Agent 2 uses) — one
    browser for all regions avoids the multi-Chromium startup race.
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

    # Use the single shared global CMS collector (one browser for all regions) —
    # avoids the per-region Chromium startup race that caused "page not initialized".
    try:
        cms_collector = _get_cms_collector()
        logger.info(f"A4 [{region_name}]: using shared global CMS collector")
    except Exception as e:
        logger.error(f"A4 [{region_name}]: CMS init failed — {e}")
        return

    while True:
        try:
            agent4_monitor(webhook, region_name, cms_collector, skills, region_tag=tag)
        except Exception as e:
            logger.error(f"A4 [{region_name}]: Monitor error: {e}")

        # Read poll interval from config each loop
        a4_cfg_now   = _get_a4_config()[0]
        interval_sec = a4_cfg_now.get("scrape_interval_sec",
                       a4_cfg_now.get("poll_interval_sec", POLL_INTERVAL_SEC))
        logger.info(f"A4 [{region_name}]: Next check in {interval_sec}s.")
        time.sleep(interval_sec)