"""
core/config_loader.py
Central config loader — reads config.json for all agents.

Usage in any agent:
    from core.config_loader import get_config, get_agent1, get_agent2, get_agent3, get_agent4, get_skill

All agents call these functions — no hardcoded values.
config.json is read fresh every call so UI changes take effect on restart.
"""

import json
import logging
import os

logger    = logging.getLogger(__name__)
_ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG_PATH = os.path.join(_ROOT, "config.json")

# ── Defaults (fallback if config.json missing) ────────────────────────────────
_DEFAULTS = {
    "regions": [],
    "agent1": {
        "scrape_interval_sec":      60,
        "band_drop_email_enabled":  True,
        "band_drop_teams_enabled":  True,
    },
    "agent2": {
        "ocw_threshold_sec":  60,
        "queue_min":          1,
        "cooldown_sec":       300,
        "llm_enabled":        True,
    },
    "agent3": {
        "amber_threshold":    90.0,
        "red_threshold":      80.0,
        "black_threshold":    70.0,
        "excel_path":         "",
        "email_recipients":   [],
    },
    "agent4": {
        "scrape_interval_sec": 60,
        "aht_target_min":      24,
        "acw_target_min":      5,
        "aux_thresholds": {
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
    },
    "skill_thresholds": {}
}


def get_config() -> dict:
    """Load and return full config.json. Falls back to defaults if file missing."""
    try:
        with open(_CFG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Merge with defaults so missing keys don't cause KeyErrors
        merged = dict(_DEFAULTS)
        for key in _DEFAULTS:
            if key in cfg:
                if isinstance(_DEFAULTS[key], dict):
                    merged[key] = {**_DEFAULTS[key], **cfg[key]}
                else:
                    merged[key] = cfg[key]
        return merged
    except FileNotFoundError:
        logger.warning(f"config.json not found at {_CFG_PATH} — using defaults")
        return dict(_DEFAULTS)
    except Exception as e:
        logger.error(f"config.json load error: {e} — using defaults")
        return dict(_DEFAULTS)


def save_config(cfg: dict) -> bool:
    """Save config dict to config.json. Returns True on success."""
    try:
        with open(_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        logger.info("config.json saved successfully.")
        return True
    except Exception as e:
        logger.error(f"config.json save error: {e}")
        return False


# ── Convenience getters ───────────────────────────────────────────────────────

def get_regions() -> list:
    """Return list of active region dicts."""
    cfg = get_config()
    return [r for r in cfg.get("regions", []) if r.get("active", True)]


def get_agent1() -> dict:
    return get_config().get("agent1", _DEFAULTS["agent1"])


def get_agent2() -> dict:
    return get_config().get("agent2", _DEFAULTS["agent2"])


def get_agent3() -> dict:
    cfg = get_config().get("agent3", _DEFAULTS["agent3"])
    # Also check config.env KPI_EXCEL_PATH as fallback
    if not cfg.get("excel_path"):
        cfg["excel_path"] = os.getenv("KPI_EXCEL_PATH", "")
    return cfg


def get_agent4() -> dict:
    return get_config().get("agent4", _DEFAULTS["agent4"])


def get_skill(skill_name: str) -> dict:
    """
    Return threshold config for a specific skill.
    Falls back to defaults if skill not in config.
    """
    cfg    = get_config()
    skills = cfg.get("skill_thresholds", {})
    return skills.get(skill_name, {
        "aht_target_min":    24,
        "ocw_threshold_sec": 60,
        "active":            True,
    })


def get_aht_target_sec(skill_name: str) -> int:
    """Return AHT target in seconds for a skill."""
    sk = get_skill(skill_name)
    return sk.get("aht_target_min", 24) * 60


def get_ocw_threshold(skill_name: str = None) -> int:
    """
    Return OCW threshold in seconds.
    If skill_name provided — returns skill-specific override.
    Falls back to agent1 global threshold.
    """
    if skill_name:
        sk = get_skill(skill_name)
        if "ocw_threshold_sec" in sk:
            return sk["ocw_threshold_sec"]
    return get_agent1().get("ocw_threshold_sec", 60)