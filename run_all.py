"""
run_all.py
Multi-region RTA monitoring — v3 with LangGraph

Each region runs in its own permanent thread.
LangGraph workflow handles agent routing per poll.
Agent 4 runs in its own background thread (every 60s).
"""

import argparse
import importlib.util
import logging
import os
import sys
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

# Fix Windows Unicode encoding for terminal output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rta_v3.log', encoding='utf-8')
    ]
)
logger     = logging.getLogger(__name__)
script_dir = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(script_dir, 'config.env'), override=True)

POLL_INTERVAL_SEC = 60

# Parse --mode argument (set by app.py when launching this process)
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--mode", default="full", choices=["full", "scrape"])
_args, _ = _parser.parse_known_args()
RUN_MODE = _args.mode  # "full" = Scrape & Monitor | "scrape" = Scrape Only

def _load_regions() -> list:
    """Load regions from config.json. Falls back to config.env if not found."""
    cfg_path = os.path.join(script_dir, "config.json")
    try:
        import json
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        regions = [r for r in cfg.get("regions", []) if r.get("active", True)]
        if regions:
            logger.info(f"Loaded {len(regions)} regions from config.json")
            return regions
    except Exception as e:
        logger.warning(f"config.json not found or invalid — using config.env: {e}")

    # Fallback to config.env
    return [
        {
            "name":      os.getenv("REGION_1_NAME",    "RTA"),
            "display":   os.getenv("REGION_1_DISPLAY", "Client ProSupport IND"),
            "dashboard": os.getenv("REGION_1_DASHBOARD", "RTA.html"),
            "webhook":   os.getenv("REGION_1_TEAMS_WEBHOOK", ""),
            "active":    True,
        },
        {
            "name":      os.getenv("REGION_2_NAME",    "CN"),
            "display":   os.getenv("REGION_2_DISPLAY", "Client ProSupport CHN"),
            "dashboard": os.getenv("REGION_2_DASHBOARD", "RTA_CN.html"),
            "webhook":   os.getenv("REGION_2_TEAMS_WEBHOOK", ""),
            "active":    True,
        },
        {
            "name":      os.getenv("REGION_3_NAME",    "AU"),
            "display":   os.getenv("REGION_3_DISPLAY", "Client ProSupport AUS"),
            "dashboard": os.getenv("REGION_3_DASHBOARD", "RTA_AU.html"),
            "webhook":   os.getenv("REGION_3_TEAMS_WEBHOOK", ""),
            "active":    True,
        },
        {
            "name":      os.getenv("REGION_4_NAME",    "EMEA"),
            "display":   os.getenv("REGION_4_DISPLAY", "Client ProSupport EMEA"),
            "dashboard": os.getenv("REGION_4_DASHBOARD", "RTA_EMEA.html"),
            "webhook":   os.getenv("REGION_4_TEAMS_WEBHOOK", ""),
            "active":    True,
        },
    ]

REGIONS = _load_regions()

# ── Live State — shared dict written after every poll ─────────────────────────
# app.py reads live_state.json for the chatbot.
# Each region writes its own key — 4 regions never conflict.
# JSON file is completely overwritten every poll — no history kept.
LIVE_STATE      = {}
_LIVE_STATE_LOCK = threading.Lock()
_LIVE_STATE_PATH = os.path.join(script_dir, "db", "live_state.json")


def _update_live_state(tag: str, name: str, display: str, state: dict):
    """
    Extract chatbot-relevant fields from agent state and write to live_state.json.
    Called after every poll. Only keeps latest data — previous poll is overwritten.
    Atomic write: writes to .tmp first then renames to avoid partial reads by app.py.
    """
    metrics   = state.get("skill_metrics", [])
    breached  = state.get("breached_skills", {})
    levers    = state.get("a3_fired_levers", {})
    decisions = state.get("analyst_decisions", {})

    skills_data = {}
    for m in metrics:
        skill = m.skill_name
        # Get last A2 decision for this skill if available
        decision = decisions.get(skill, {})
        move_list = decision.get("move_list", [])
        ask_list  = decision.get("ask_list",  [])
        hold_list = decision.get("hold_list", [])

        # Which lever has fired for this skill
        fired_lever = None
        for lvl in ["Black", "Red", "Amber"]:
            if levers.get(f"{skill}_{lvl}"):
                fired_lever = lvl
                break

        skills_data[skill] = {
            "sla":          round(m.service_level, 1),
            "band":         m.band,
            "queue":        m.calls_waiting,
            "ocw":          m.ocw,
            "avail":        m.agents_available,
            "on_calls":     m.agents_on_calls,
            "on_aux":       m.agents_on_aux,
            "headcount":    m.headcount,
            "breached":     skill in breached,
            "breach_reasons": breached.get(skill, []),
            "lever_fired":  fired_lever,
            "last_move":    [a.get("name","") for a in move_list],
            "last_ask":     [a.get("name","") for a in ask_list],
            "last_hold":    [a.get("name","") for a in hold_list],
            "a2_note":      decision.get("analyst_note", ""),
            "root_cause":   decision.get("root_cause", ""),
        }

    # Save to history DB
    try:
        from core.history import save_skill_snapshot, cleanup_old_data
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_skill_snapshot(tag, display, skills_data, ts)
        cleanup_old_data()  # remove data older than 7 days
    except Exception as e:
        logger.warning(f"History DB write failed: {e}")

    region_data = {
        "region_name":    name,
        "region_display": display,
        "last_poll_time": state.get("last_poll_time", "").strftime("%H:%M:%S")
                          if hasattr(state.get("last_poll_time",""), "strftime")
                          else str(state.get("last_poll_time", "")),
        "poll_number":    state.get("poll_number", 0),
        "skills":         skills_data,
        "breached_count": len(breached),
        "levers_fired":   {k: v for k, v in levers.items() if v},
    }

    with _LIVE_STATE_LOCK:
        LIVE_STATE[tag] = region_data
        # Atomic write — write to .tmp then rename so app.py never reads partial file
        tmp_path  = _LIVE_STATE_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                import json as _j
                _j.dump(LIVE_STATE, f, indent=2, default=str)
            os.replace(tmp_path, _LIVE_STATE_PATH)
        except Exception as e:
            logger.warning(f"live_state.json write failed: {e}")


def _load(name, rel):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(script_dir, rel)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def region_loop(region: dict):
    """Permanent thread for one region."""
    name      = region["name"]
    display   = region["display"]
    dashboard = os.path.join(script_dir, region["dashboard"])
    webhook   = region["webhook"]
    tag       = name.lower()

    scrape_only = (RUN_MODE == "scrape")
    logger.info(f"[{name}] Starting permanent thread... mode={'SCRAPE ONLY' if scrape_only else 'SCRAPE & MONITOR'}")

    # Load core modules with unique names per region
    _load(f"rta_core_models_{tag}",  "core/models.py")
    _load(f"rta_core_llm_{tag}",     "core/llm.py")
    if not scrape_only:
        _load(f"rta_alerts_teams_{tag}", "alerts/teams.py")
        _load(f"rta_alerts_email_{tag}", "alerts/email.py")
    _load(f"rta_dashboard_{tag}",    "dashboard/collector.py")

    # Load state module
    _state_mod = _load(f"rta_core_state_{tag}", "core/state.py")

    # Build LangGraph workflow for this region
    from workflow import build_workflow
    app = build_workflow(tag, scrape_only=scrape_only)

    # Agent 4 (CMS monitor) — only in full mode
    if not scrape_only:
        agent4 = _load(f"rta_agent4_{tag}", "agents/agent4_cms_monitor.py")
        a4_thread = threading.Thread(
            target=agent4.agent4_monitor_loop,
            args=(webhook, name, dashboard, tag),
            name=f"A4-{name}",
            daemon=True
        )
        a4_thread.start()
        logger.info(f"[{name}] Agent 4 CMS monitor thread started.")
    else:
        logger.info(f"[{name}] Scrape-only mode — Agent 4 (CMS monitor) skipped.")

    # Create initial state — pass region_tag and region_display
    state = _state_mod.initial_state(
        region_name    = name,
        dashboard_path = dashboard,
        webhook        = webhook,
        region_tag     = tag,       # ← short slug for module namespacing
        region_display = display,   # ← label for Teams/email headers
    )

    logger.info(f"[{name}] LangGraph workflow ready. Starting poll loop...")

    try:
        while True:
            poll_start = time.time()
            logger.info(f"[{name}] Poll #{state['poll_number']}")

            try:
                state = app.invoke(state)
            except Exception as e:
                logger.error(f"[{name}] Workflow error: {e}")
                state['error_count'] = state.get('error_count', 0) + 1

            state['poll_number'] += 1
            poll_time  = time.time() - poll_start

            # Update live state for chatbot — after every poll
            try:
                _update_live_state(tag, name, display, state)
            except Exception as e:
                logger.warning(f"[{name}] live_state update failed: {e}")

            # Read scrape interval from config each poll
            try:
                import json as _json
                with open(os.path.join(script_dir, 'config.json'), 'r') as _f:
                    _cfg = _json.load(_f)
                poll_interval = _cfg.get('agent1', {}).get('scrape_interval_sec', POLL_INTERVAL_SEC)
            except Exception:
                poll_interval = POLL_INTERVAL_SEC
            sleep_time = max(0, poll_interval - poll_time)

            logger.info(
                f"[{name}] Poll done in {poll_time:.1f}s | "
                f"Skills: {len(state.get('skill_metrics', []))} | "
                f"Breached: {list(state.get('breached_skills', {}).keys())} | "
                f"Route: A2={state.get('_invoke_a2', False)} "
                f"A3={state.get('_invoke_a3', False)} | "
                f"Next in {sleep_time:.1f}s"
            )
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info(f"[{name}] Stopped.")
    finally:
        try:
            agent1_mod = sys.modules.get(f"rta_agent1_{tag}")
            if agent1_mod:
                agent1_mod.cleanup_collector()
            logger.info(f"[{name}] Browser closed.")
        except Exception as e:
            logger.warning(f"[{name}] Cleanup error: {e}")


def main():
    logger.info("=" * 60)
    logger.info("RTA MULTI-REGION MONITORING SYSTEM — v3 (LangGraph)")
    logger.info(f"MODE: {'SCRAPE ONLY (no alerts/levers)' if RUN_MODE == 'scrape' else 'SCRAPE & MONITOR (full)'}")
    logger.info("=" * 60)
    for r in REGIONS:
        logger.info(f"Region: {r['name']} | Display: {r['display']} | Dashboard: {r['dashboard']}")
    logger.info("=" * 60)

    threads = []
    for i, region in enumerate(REGIONS):
        t = threading.Thread(
            target=region_loop,
            args=(region,),
            name=f"RTA-{region['name']}",
            daemon=True
        )
        threads.append(t)
        t.start()
        logger.info(f"Started thread for {region['name']}")
        time.sleep(15)  # stagger browser starts — 15s between regions

    logger.info("All regions running! Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping all regions...")


if __name__ == "__main__":
    main()