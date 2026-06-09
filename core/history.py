"""
core/history.py
SQLite history database for RTA monitoring system.

Stores skill-level metrics and agent-level CMS data per poll.
Data is retained for 7 days then cleaned up automatically.
Thread-safe: uses a Lock since multiple region threads write simultaneously.
"""

import json
import logging
import os
import sqlite3
import threading

logger = logging.getLogger(__name__)

# DB lives in the same folder as run_all.py (project root)
_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "db", "history.db"
)

_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """Open a connection with row_factory set so rows come back as dicts."""
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL mode: multiple threads can read/write without blocking each other
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_last_cleanup = 0.0  # epoch seconds of last cleanup run

def _init_db():
    """Create tables and set WAL mode permanently on the DB file."""
    with _lock:
        try:
            conn = _get_conn()
            # Set WAL mode permanently on the file (survives restarts)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()
            cur = conn.cursor()
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS skill_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    region_tag      TEXT    NOT NULL,
                    region_display  TEXT    NOT NULL,
                    skill           TEXT    NOT NULL,
                    sla             REAL,
                    band            TEXT,
                    queue           INTEGER,
                    ocw             TEXT,
                    avail           INTEGER,
                    on_calls        INTEGER,
                    on_aux          INTEGER,
                    headcount       INTEGER,
                    breached        INTEGER,
                    breach_reasons  TEXT,
                    lever_fired     TEXT,
                    last_move       TEXT,
                    last_ask        TEXT,
                    a2_note         TEXT,
                    root_cause      TEXT
                );

                CREATE TABLE IF NOT EXISTS cms_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    region_tag      TEXT    NOT NULL,
                    skill           TEXT    NOT NULL,
                    agent_name      TEXT,
                    login_id        TEXT,
                    role            TEXT,
                    aux_reason      TEXT,
                    state           TEXT,
                    direction       TEXT,
                    time_in_state   TEXT,
                    time_seconds    INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_skill_history_ts
                    ON skill_history(timestamp);
                CREATE INDEX IF NOT EXISTS idx_skill_history_region
                    ON skill_history(region_tag);
                CREATE INDEX IF NOT EXISTS idx_cms_history_ts
                    ON cms_history(timestamp);
            """)
            conn.commit()
            conn.close()
            logger.info(f"History DB initialised at {_DB_PATH}")
        except Exception as e:
            logger.error(f"History DB init failed: {e}")


# Initialise on import
_init_db()


# ── Public API ────────────────────────────────────────────────────────────────

def save_skill_snapshot(
    region_tag: str,
    region_display: str,
    skills_data: dict,
    timestamp: str
) -> None:
    """
    Insert one row per skill into skill_history.

    skills_data is the dict built in run_all._update_live_state —
    keys are skill names, values are the metric dicts.
    """
    if not skills_data:
        return

    rows = []
    for skill, d in skills_data.items():
        breach_reasons = d.get("breach_reasons", [])
        last_move      = d.get("last_move", [])
        last_ask       = d.get("last_ask", [])

        rows.append((
            timestamp,
            region_tag,
            region_display,
            skill,
            d.get("sla"),
            d.get("band"),
            d.get("queue"),
            d.get("ocw"),
            d.get("avail"),
            d.get("on_calls"),
            d.get("on_aux"),
            d.get("headcount"),
            1 if d.get("breached") else 0,
            json.dumps(breach_reasons) if isinstance(breach_reasons, list) else str(breach_reasons),
            d.get("lever_fired"),
            json.dumps(last_move) if isinstance(last_move, list) else str(last_move),
            json.dumps(last_ask)  if isinstance(last_ask,  list) else str(last_ask),
            d.get("a2_note"),
            d.get("root_cause"),
        ))

    with _lock:
        try:
            conn = _get_conn()
            conn.executemany(
                """INSERT INTO skill_history
                   (timestamp, region_tag, region_display, skill,
                    sla, band, queue, ocw, avail, on_calls, on_aux, headcount,
                    breached, breach_reasons, lever_fired, last_move, last_ask,
                    a2_note, root_cause)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"save_skill_snapshot failed: {e}")


def save_cms_snapshot(
    region_tag: str,
    skill: str,
    agents: list,
    timestamp: str
) -> None:
    """
    Insert one row per agent into cms_history.

    agents is the list returned by cms_collector.collect(skill_name).
    Each item is a dict with keys: name, login_id, role, aux_reason,
    state, direction, time (time_in_state), time_seconds.
    """
    if not agents:
        return

    rows = []
    for a in agents:
        rows.append((
            timestamp,
            region_tag,
            skill,
            a.get("name") or a.get("agent_name"),
            a.get("login_id"),
            a.get("role"),
            a.get("aux_reason"),
            a.get("state"),
            a.get("direction"),
            a.get("time") or a.get("time_in_state"),
            a.get("time_seconds"),
        ))

    with _lock:
        try:
            conn = _get_conn()
            conn.executemany(
                """INSERT INTO cms_history
                   (timestamp, region_tag, skill,
                    agent_name, login_id, role, aux_reason,
                    state, direction, time_in_state, time_seconds)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                rows
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"save_cms_snapshot failed: {e}")


def cleanup_old_data() -> None:
    """Delete rows older than 7 days. Runs at most once per hour."""
    global _last_cleanup
    import time as _time
    if _time.time() - _last_cleanup < 3600:
        return  # skip — already ran within the last hour
    _last_cleanup = _time.time()
    with _lock:
        try:
            conn = _get_conn()
            conn.execute(
                "DELETE FROM skill_history WHERE timestamp < datetime('now', '-7 days')"
            )
            conn.execute(
                "DELETE FROM cms_history WHERE timestamp < datetime('now', '-7 days')"
            )
            conn.commit()
            conn.close()
            logger.info("History DB cleanup complete.")
        except Exception as e:
            logger.error(f"cleanup_old_data failed: {e}")


def query(sql: str) -> list:
    """
    Execute a SELECT query and return results as a list of dicts.
    Only SELECT statements are permitted.
    No lock needed for reads — WAL mode handles concurrent access.
    """
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed.")

    conn = _get_conn()
    try:
        cur  = conn.execute(sql)
        rows = [dict(row) for row in cur.fetchall()]
        return rows
    finally:
        conn.close()


def get_schema() -> str:
    """
    Return a detailed description of the database schema,
    including column meanings and sample values, so the LLM
    can generate accurate SQLite queries.
    """
    return """
DATABASE: history.db (SQLite)
Timezone: Local server time (not UTC). All timestamps stored as text.

TABLE: skill_history
  Purpose: One row per skill per poll cycle (~every 60 seconds). Captures live dashboard metrics.
  Columns:
    id             INTEGER  — auto-increment primary key
    timestamp      TEXT     — format 'YYYY-MM-DD HH:MM:SS', e.g. '2026-06-08 15:42:05'
    region_tag     TEXT     — short region code: 'rta' (India), 'cn' (China), 'au' (Australia), 'emea' (Europe)
    region_display TEXT     — full region name, e.g. 'Client ProSupport IND'
    skill          TEXT     — skill queue name, e.g. 'TS_CSTCE', 'TS_CN_ProDB', 'TS_AU_Elite'
    sla            REAL     — service level percentage, e.g. 85.2 (means 85.2%)
    band           TEXT     — SLA band: 'EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'CRITICAL', 'SEVERE'
    queue          INTEGER  — number of calls currently waiting in queue
    ocw            TEXT     — oldest call waiting time in format 'MM:SS', e.g. '01:45'
    avail          INTEGER  — number of agents available (ready to take calls)
    on_calls       INTEGER  — number of agents currently on active calls
    on_aux         INTEGER  — number of agents in AUX (break/lunch/training etc.)
    headcount      INTEGER  — total headcount logged in
    breached       INTEGER  — 1 if SLA threshold was breached this poll, 0 if not
    breach_reasons TEXT     — JSON array of reason strings, e.g. '["LOW_AVAIL","HIGH_QUEUE"]'
    lever_fired    TEXT     — lever colour if escalated: 'Amber', 'Red', 'Black', or NULL
    last_move      TEXT     — JSON array of agent names recommended to move, e.g. '["AgentAlpha","AgentBeta"]'
    last_ask       TEXT     — JSON array of agent names given polite ask, e.g. '["AgentGamma"]'
    a2_note        TEXT     — AI analyst note (≤15 words), e.g. 'High AUX occupancy with active queue'
    root_cause     TEXT     — root cause code: 'AUX_HEAVY', 'STAFFING', 'VOLUME', 'OCW_BREACH', 'RECOVERING', 'STABLE'

  Skill name patterns:
    India (rta)  : TS_CSTCE, TS_CSTElite, TS_LicKeys, TS_VICHW, TS_CSTVCE, TS_CSTCritAcct
    China (cn)   : TS_CN_ProDB, TS_CN_ProCNX, TS_CN_Elite, TS_CN_LicKeys, TS_CN_VICHW, TS_CN_CritAcct
    Australia(au): TS_AU_ProDB, TS_AU_ProCNX, TS_AU_Elite, TS_AU_LicKeys, TS_AU_VICHW, TS_AU_CritAcct
    EMEA         : TS_MLSCST_GER, TS_MLSCST_SPA, TS_MLSCST_FRA, TS_MLSCST_ITA, TS_MLSCST_NLD, TS_MLSCST_POL

TABLE: cms_history
  Purpose: One row per agent per skill per poll. Raw CMS agent state data.
  Columns:
    id             INTEGER  — auto-increment primary key
    timestamp      TEXT     — format 'YYYY-MM-DD HH:MM:SS'
    region_tag     TEXT     — same as skill_history.region_tag
    skill          TEXT     — skill queue name
    agent_name     TEXT     — agent's full name, e.g. 'John Smith'
    login_id       TEXT     — agent login ID or extension
    role           TEXT     — agent role, e.g. 'Agent', 'Supervisor'
    aux_reason     TEXT     — AUX reason if in AUX state, e.g. 'Aux2', 'Break', 'Lunch'
    state          TEXT     — current state: 'AUX', 'AVAIL', 'ACW', 'TALKING', 'ON_CALL'
    direction      TEXT     — call direction: 'INBOUND', 'OUTBOUND', or NULL
    time_in_state  TEXT     — time in current state as 'HH:MM:SS' or 'MM:SS'
    time_seconds   INTEGER  — time in current state converted to seconds

USEFUL QUERY PATTERNS:
  -- Breached skills in last hour:
  SELECT timestamp, region_tag, skill, sla, band, queue, breach_reasons
  FROM skill_history WHERE breached=1 AND timestamp >= datetime('now', '-1 hour')
  ORDER BY timestamp DESC LIMIT 100;

  -- Average SLA per skill today:
  SELECT skill, region_tag, AVG(sla) as avg_sla, MIN(sla) as min_sla, COUNT(*) as polls
  FROM skill_history WHERE date(timestamp) = date('now')
  GROUP BY skill, region_tag ORDER BY avg_sla ASC LIMIT 100;

  -- Agents on AUX right now (latest poll):
  SELECT agent_name, aux_reason, time_in_state, skill
  FROM cms_history WHERE timestamp >= datetime('now', '-5 minutes') AND state='AUX'
  ORDER BY time_seconds DESC LIMIT 100;

  -- Lever fires today:
  SELECT timestamp, region_tag, skill, lever_fired, sla, queue
  FROM skill_history WHERE lever_fired IS NOT NULL AND date(timestamp) = date('now')
  ORDER BY timestamp DESC LIMIT 100;
""".strip()
