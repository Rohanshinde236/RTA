# RTA Monitoring System — Full Documentation

**Version:** v3 (LangGraph Multi-Region)
**Path:** `D:\OneDrive - Aligned Automation Services Private Limited\Desktop\RTA_Final`
**Last Updated:** June 2026

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [How to Run](#2-how-to-run)
3. [Architecture](#3-architecture)
4. [File Structure](#4-file-structure)
5. [Regions & Skills](#5-regions--skills)
6. [Agents](#6-agents)
7. [LangGraph Workflow](#7-langgraph-workflow)
8. [Flask Web UI](#8-flask-web-ui)
9. [Chatbot (AI Assistant)](#9-chatbot-ai-assistant)
10. [SQLite History Database](#10-sqlite-history-database)
11. [Run Modes — Scrape Only vs Scrape & Monitor](#11-run-modes--scrape-only-vs-scrape--monitor)
12. [API Keys & LLM Configuration](#12-api-keys--llm-configuration)
13. [Alerts — Teams & Email](#13-alerts--teams--email)
14. [Configuration Files](#14-configuration-files)
15. [Known Issues & Fixes Applied](#15-known-issues--fixes-applied)
16. [Data Flow Diagram](#16-data-flow-diagram)

---

## 1. System Overview

The RTA (Real-Time Analyst) Monitoring System is a Flask web application that monitors contact center SLA metrics in real-time across **4 regions**:

| Region Tag | Region Name | Display Name |
|---|---|---|
| `rta` | RTA | Client ProSupport IND (India) |
| `cn` | CN | Client ProSupport CHN (China) |
| `au` | AU | Client ProSupport AUS (Australia) |
| `emea` | EMEA | Client ProSupport EMEA (Europe) |

**What it does:**
- Scrapes live SLA/queue data from HTML dashboards every 60 seconds
- Detects SLA breaches per skill queue
- Fires escalation levers (Amber → Red → Black) when thresholds are crossed
- Sends alerts to Microsoft Teams via webhooks
- Sends email alerts via Gmail SMTP
- Saves all data to a 7-day SQLite history database
- Provides an AI chatbot for querying both live and historical data

---

## 2. How to Run

### Prerequisites
```
Python 3.10+
pip install -r requirements.txt
```

### Step 1 — Start the Flask UI
```bash
python app.py
```
Open browser: **http://localhost:5000**

### Step 2 — Start the monitoring system
- Go to the Dashboard page
- Select a **mode** (see Section 11)
- Click **▶ Start**

### Step 3 — Access the chatbot
- Click **💬 Chatbot** in the sidebar
- Use **Live Data** mode for current status
- Use **History** mode to query past data (last 7 days)

### Stop the system
- Click **⏹ Stop** on the dashboard, or
- Press `Ctrl+C` in the terminal

---

## 3. Architecture

```
app.py (Flask UI)
    │
    ├── Starts run_all.py as a subprocess
    │
run_all.py
    │
    ├── Thread per region (RTA / CN / AU / EMEA)
    │       │
    │       └── LangGraph Workflow (workflow.py)
    │               │
    │               ├── Agent 1 — Scrape HTML dashboard
    │               ├── Router  — Decide what to invoke
    │               ├── Agent 2 — Analyst (LLM decisions)
    │               └── Agent 3 — Lever firing
    │
    ├── Agent 4 — CMS monitor (separate thread per region)
    │
    └── history.db — SQLite, written after every poll
```

**Key design decisions:**
- Each region runs in its own permanent Python thread
- Browsers (Playwright) are kept open — one per region
- `live_state.json` is overwritten every poll (atomic write via `.tmp → rename`)
- `history.db` keeps 7 days of data, written via WAL mode (thread-safe)

---

## 4. File Structure

```
RTA_Final/
│
├── app.py                    # Flask web UI + chatbot routes
├── run_all.py                # Main runner — starts all region threads
├── workflow.py               # LangGraph graph builder
├── config.env                # API keys, credentials, region config
├── config.json               # Runtime config (regions, thresholds, intervals)
├── live_state.json           # Current live data (overwritten every poll)
├── history.db                # SQLite history — 7-day rolling window
├── requirements.txt          # Python dependencies
│
├── agents/
│   ├── agent1_collector.py   # Scrapes HTML dashboard, detects breaches
│   ├── agent2_analyst.py     # LLM analyst — decides moves/asks/holds
│   ├── agent3_lever.py       # Fires Amber/Red/Black levers, sends Teams alerts
│   └── agent4_cms_monitor.py # CMS scraper — per-agent state (AUX, calls, etc.)
│
├── core/
│   ├── state.py              # AgentState TypedDict — shared between agents
│   ├── models.py             # SkillMetric dataclass
│   ├── llm.py                # Groq LLM key rotation with exponential backoff
│   ├── config_loader.py      # Reads thresholds from config.json
│   └── history.py            # SQLite DB — save/query history data
│
├── dashboard/
│   ├── collector.py          # Playwright HTML dashboard scraper
│   └── cms_collector.py      # CMS agent-level data scraper
│
├── alerts/
│   ├── teams.py              # Microsoft Teams webhook alerts
│   └── email.py              # Gmail SMTP email alerts
│
└── dashboard HTML files:
    ├── RTA.html              # India dashboard
    ├── RTA_CN.html           # China dashboard
    ├── RTA_AU.html           # Australia dashboard
    └── RTA_EMEA.html         # EMEA dashboard
```

---

## 5. Regions & Skills

### India (`rta`) — Client ProSupport IND
| Skill | Description |
|---|---|
| TS_CSTCE | CST CE queue |
| TS_CSTElite | CST Elite queue |
| TS_LicKeys | License Keys queue |
| TS_VICHW | VIC HW queue |
| TS_CSTVCE | CST VCE queue |
| TS_CSTCritAcct | CST Critical Accounts |

### China (`cn`) — Client ProSupport CHN
| Skill | Description |
|---|---|
| TS_CN_ProDB | ProDB queue |
| TS_CN_ProCNX | ProCNX queue |
| TS_CN_Elite | Elite queue |
| TS_CN_LicKeys | License Keys queue |
| TS_CN_VICHW | VIC HW queue |
| TS_CN_CritAcct | Critical Accounts |

### Australia (`au`) — Client ProSupport AUS
| Skill | Description |
|---|---|
| TS_AU_ProDB | ProDB queue |
| TS_AU_ProCNX | ProCNX queue |
| TS_AU_Elite | Elite queue |
| TS_AU_LicKeys | License Keys queue |
| TS_AU_VICHW | VIC HW queue |
| TS_AU_CritAcct | Critical Accounts |

### EMEA (`emea`) — Client ProSupport EMEA
| Skill | Description |
|---|---|
| TS_MLSCST_GER | Germany queue |
| TS_MLSCST_SPA | Spain queue |
| TS_MLSCST_FRA | France queue |
| TS_MLSCST_ITA | Italy queue |
| TS_MLSCST_NLD | Netherlands queue |
| TS_MLSCST_POL | Poland queue |

---

## 6. Agents

### Agent 1 — Queue Data Collector (`agents/agent1_collector.py`)
- Scrapes the HTML dashboard using Playwright (browser kept open)
- Extracts per-skill: SLA%, band, queue depth, OCW, agents available, on-calls, on-AUX, headcount
- Detects breach conditions: band drops, queue doubled, falling 3 polls
- Populates `skill_metrics` and `breached_skills` in AgentState
- Runs every poll for all regions

**Breach detection rules:**
- `BAND_CHANGED` — SLA band dropped (e.g., HEALTHY → SEVERE)
- `FALLING_3_POLLS` — SLA fell 3 consecutive polls
- `QUEUE_DOUBLED` — Queue count doubled since last poll
- `LOW_AVAIL` — Agents available = 0

### Agent 2 — Analyst (`agents/agent2_analyst.py`)
- Only runs when Agent 1 detects queue/OCW pressure
- Uses Groq LLM to decide which agents to move/ask/hold
- Scrapes CMS data (per-agent state) to identify who is on AUX
- Saves CMS data to `cms_history` table in history.db
- Outputs `analyst_decisions` with `move_list`, `ask_list`, `hold_list`, `analyst_note`, `root_cause`

**Root cause codes:**
| Code | Meaning |
|---|---|
| `AUX_HEAVY` | Too many agents on break/AUX |
| `STAFFING` | Not enough agents logged in |
| `VOLUME` | Unexpected call volume spike |
| `OCW_BREACH` | Oldest call waiting too long |
| `RECOVERING` | SLA improving, still below threshold |
| `STABLE` | No issues detected |

### Agent 3 — Lever Generator (`agents/agent3_lever.py`)
- Fires escalation levers when SLA crosses thresholds
- Each lever fires once per breach episode (tracked in `a3_fired_levers`)
- Sends Microsoft Teams adaptive card alerts
- Sends email alerts for Black lever

**Lever thresholds (configurable in config.json):**
| Lever | Default SLA threshold |
|---|---|
| Amber | < 90% |
| Red | < 80% |
| Black | < 70% |

### Agent 4 — CMS Monitor (`agents/agent4_cms_monitor.py`)
- Runs in a separate background thread per region (not part of LangGraph graph)
- Scrapes CMS every ~60 seconds
- Monitors agent-level state: AUX reason, time in state, login status
- Triggers proactive alerts if agents are overdue on break

---

## 7. LangGraph Workflow

**Graph structure:**
```
START
  └── Agent1 (always runs)
        └── Router (inline logic)
              ├── A2 only    → Agent2 → END
              ├── A3 only    → Agent3 → END
              ├── Both       → Agent2 → Agent3 → END
              └── End        → END (all clear)
```

**Router logic (`workflow.py → router_node`):**
- Invokes A2 if: queue ≥ queue_min AND avail = 0, OR OCW > threshold
- Invokes A3 if: SLA < amber threshold AND that lever hasn't fired yet for this episode
- Sends recovery alerts if: skill was previously breached but now queue=0, avail>0, SLA≥amber

**Scrape-only mode:** Graph is simplified to just `Agent1 → END` (see Section 11)

---

## 8. Flask Web UI

**URL:** http://localhost:5000

### Pages

| Page | URL | Purpose |
|---|---|---|
| Dashboard | `/` | System status, Start/Stop/Restart, region overview |
| Regions | `/regions` | Configure region names, dashboard files, webhooks |
| Agent Settings | `/agents` | Configure LLM, CMS, alert settings per agent |
| Skill Thresholds | `/skills` | Configure SLA thresholds, OCW limits per skill |
| Live Logs | `/logs` | Real-time log viewer (last 200 lines) |
| Chatbot | `/chat` | AI assistant for live + historical queries |

### Routes

| Route | Method | Purpose |
|---|---|---|
| `/control` | POST | Start / Stop / Restart with mode selection |
| `/api/status` | GET | JSON — current running status |
| `/api/logs` | GET | JSON — latest log lines |
| `/api/chat` | POST | Chat API — accepts `{question, mode}` |
| `/chat-js` | GET | Serves chat JavaScript (bypasses Jinja2 templating) |

---

## 9. Chatbot (AI Assistant)

Located at `/chat`. Uses Groq LLM (llama-3.1-8b-instant) to answer questions.

### Two Modes

**🟢 Live Data mode** (default)
- Reads from `live_state.json` (last poll, ~60 seconds old)
- Answers questions like: "What is happening in India right now?"
- Automatically detects region and skill names in the question

**📅 History mode** (last 7 days)
- Two-LLM-call pipeline:
  1. LLM reads database schema → generates a SQLite SELECT query
  2. Python runs the query on `history.db`
  3. Results passed to LLM → explains findings in plain English
- Answers questions like: "Which skill was most impacted at 4:50 today?"
- Time conversion: `"4:50"` → `16:50` (business hours assumed)

### Chat features
- Chat history persists across page navigation (stored in `sessionStorage`)
- Mode selection (Live/History) also persists in `sessionStorage`
- Clear button wipes chat history

### Example questions

**Live mode:**
- "What is India's SLA right now?"
- "Which skills are breached?"
- "What is TS_CN_Elite's current status?"
- "Is any skill in critical band?"

**History mode:**
- "Which skill was most impacted at 4:50 today?"
- "What happened in Australia at 5pm today?"
- "Show me all lever fires today"
- "What was the SLA for TS_VICHW at 3pm?"
- "Which agents were on AUX the longest today?"
- "What caused the SLA drop in India at 4:40?"

---

## 10. SQLite History Database

**File:** `history.db` (in project root)
**Retention:** 7 days (auto-cleanup, runs at most once per hour)
**Thread safety:** WAL (Write-Ahead Logging) mode + Python threading.Lock for writes

### Table: `skill_history`

One row per skill per poll (~every 60 seconds).

| Column | Type | Description |
|---|---|---|
| id | INTEGER | Auto-increment primary key |
| timestamp | TEXT | `YYYY-MM-DD HH:MM:SS` (local time) |
| region_tag | TEXT | `rta` / `cn` / `au` / `emea` |
| region_display | TEXT | Full region name |
| skill | TEXT | Skill queue name (e.g., `TS_CSTCE`) |
| sla | REAL | Service level % (e.g., `85.2`) |
| band | TEXT | `EXCELLENT` / `HEALTHY` / `WARNING` / `CRITICAL` / `SEVERE` |
| queue | INTEGER | Calls waiting in queue |
| ocw | TEXT | Oldest call waiting (`MM:SS`) |
| avail | INTEGER | Agents available |
| on_calls | INTEGER | Agents on active calls |
| on_aux | INTEGER | Agents on AUX/break |
| headcount | INTEGER | Total agents logged in |
| breached | INTEGER | `1` = breached, `0` = not |
| breach_reasons | TEXT | JSON array of reason codes |
| lever_fired | TEXT | `Amber` / `Red` / `Black` / NULL |
| last_move | TEXT | JSON array of agent names moved |
| last_ask | TEXT | JSON array of agent names given polite ask |
| a2_note | TEXT | AI analyst note (≤15 words) |
| root_cause | TEXT | Root cause code(s) |

### Table: `cms_history`

One row per agent per skill per CMS scrape.

| Column | Type | Description |
|---|---|---|
| id | INTEGER | Auto-increment primary key |
| timestamp | TEXT | `YYYY-MM-DD HH:MM:SS` |
| region_tag | TEXT | `rta` / `cn` / `au` / `emea` |
| skill | TEXT | Skill queue name |
| agent_name | TEXT | Agent's full name |
| login_id | TEXT | Agent login ID / extension |
| role | TEXT | `Agent` / `Supervisor` |
| aux_reason | TEXT | AUX reason if in AUX state |
| state | TEXT | `AUX` / `AVAIL` / `ACW` / `TALKING` |
| direction | TEXT | `INBOUND` / `OUTBOUND` / NULL |
| time_in_state | TEXT | Time in current state (`HH:MM:SS`) |
| time_seconds | INTEGER | Time in current state (seconds) |

### Viewing the database
Use **DB Browser for SQLite**: https://sqlitebrowser.org/dl/
- Open `history.db` → Browse Data tab → select table
- **Note:** Close DB Browser before running queries via chatbot (file lock conflict)

### Example SQL queries
```sql
-- Most impacted skills today
SELECT timestamp, skill, region_tag, sla, band, queue
FROM skill_history
WHERE date(timestamp) = date('now')
ORDER BY sla ASC LIMIT 20;

-- All lever fires today
SELECT timestamp, region_tag, skill, lever_fired, sla, queue
FROM skill_history
WHERE lever_fired IS NOT NULL AND date(timestamp) = date('now')
ORDER BY timestamp DESC;

-- Agents on AUX in last 5 minutes
SELECT agent_name, aux_reason, time_in_state, skill, region_tag
FROM cms_history
WHERE timestamp >= datetime('now', '-5 minutes') AND state = 'AUX'
ORDER BY time_seconds DESC;

-- SLA history for a specific skill today
SELECT timestamp, sla, band, queue, lever_fired
FROM skill_history
WHERE skill = 'TS_VICHW' AND date(timestamp) = date('now')
ORDER BY timestamp;
```

---

## 11. Run Modes — Scrape Only vs Scrape & Monitor

Selected from the Dashboard page before clicking Start.

### 📊 Scrape & Monitor (Full mode)
- Runs all 4 agents per region
- Agent 2: LLM analyst decisions (move/ask/hold)
- Agent 3: Lever firing (Amber/Red/Black)
- Agent 4: CMS monitor with proactive alerts
- Teams webhook alerts sent
- Email alerts sent for Black lever
- **Use this for:** Normal operations during business hours

### 🔍 Scrape Only
- Runs Agent 1 only per region (no Agent 2, 3, or 4)
- No LLM calls → no Groq API usage
- No Teams alerts → no noise during testing
- Dashboard data scraped and saved to `live_state.json` and `history.db` as normal
- Chatbot still works (Live + History modes)
- **Use this for:** Testing, demos, after-hours data collection, or when you want to track data without firing alerts

### Switching mode
- Stop the system
- Select the new mode radio button
- Click Start
- The status badge shows current mode: `● RUNNING — Scrape Only`

---

## 12. API Keys & LLM Configuration

Configured in `config.env`.

### Groq (primary LLM)
```
GROQ_MODEL=llama-3.1-8b-instant
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...
GROQ_API_KEY_4=gsk_...
GROQ_API_KEY_5=gsk_...
```

**Model choice:** `llama-3.1-8b-instant` has 5× higher rate limits than `llama-3.3-70b-versatile` on the free tier. Use 8b-instant to avoid 429 errors when all 4 regions fire simultaneously.

**Key rotation:** `core/llm.py` rotates through all keys on 429 errors:
- 1 second delay between individual key attempts
- After full cycle exhausted: 5s → 10s → 15s → 30s (max) exponential backoff

### Gemini (backup — optional)
```
GEMINI_MODEL=gemini-1.5-flash
GEMINI_API_KEY_1=AIzaSy...
```
> Note: Keys starting with `AQ.` are OAuth tokens, not standard API keys. Only `AIzaSy...` format keys work with the Gemini REST API.

### Getting more Groq keys
- Register additional accounts at https://console.groq.com
- Add as `GROQ_API_KEY_6`, `GROQ_API_KEY_7`, etc. in `config.env`
- System auto-detects keys 1–8

---

## 13. Alerts — Teams & Email

### Microsoft Teams (via Power Automate webhooks)
- Each region has its own webhook URL in `config.env`
- Adaptive card format with color-coded severity
- Fired by Agent 3 when lever threshold is crossed
- Recovery alert sent when SLA returns to healthy

**Webhook URLs in `config.env`:**
```
REGION_1_TEAMS_WEBHOOK=https://...   # India
REGION_2_TEAMS_WEBHOOK=https://...   # China
REGION_3_TEAMS_WEBHOOK=https://...   # Australia
REGION_4_TEAMS_WEBHOOK=https://...   # EMEA
```

### Email (Gmail SMTP)
- Triggered on Black lever (most severe)
- Sent to managers list
- Config in `config.env`:
```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=busyperson517@gmail.com
SMTP_PASSWORD=<app password>
EMAIL_MANAGERS=manager1@company.com,manager2@company.com
```
> Use a Gmail App Password (not your account password). Generate at: https://myaccount.google.com/apppasswords

---

## 14. Configuration Files

### `config.env` — Secrets & static config
Contains API keys, credentials, region names, dashboard file paths, and webhook URLs.
Never commit this file to git.

### `config.json` — Runtime config (editable via UI)
```json
{
  "regions": [
    {
      "name": "RTA",
      "display": "Client ProSupport IND",
      "dashboard": "RTA.html",
      "webhook": "https://...",
      "active": true
    }
  ],
  "agent1": {
    "scrape_interval_sec": 60
  },
  "agent2": {
    "ocw_threshold_sec": 60,
    "queue_min": 1
  },
  "agent3": {
    "amber_threshold": 90.0,
    "red_threshold": 80.0,
    "black_threshold": 70.0
  }
}
```

Changes to `config.json` take effect on the next poll without restarting.

### `live_state.json` — Current live data
Written after every poll. Read by the chatbot for live-mode queries.
```json
{
  "rta": {
    "region_display": "Client ProSupport IND",
    "last_poll_time": "16:05:34",
    "poll_number": 4,
    "skills": {
      "TS_VICHW": {
        "sla": 78.1,
        "band": "CRITICAL",
        "queue": 3,
        "ocw": "00:44",
        "avail": 1,
        "on_calls": 8,
        "on_aux": 3,
        "headcount": 12,
        "breached": false,
        "lever_fired": "Red",
        "root_cause": "AUX_HEAVY | VOLUME"
      }
    }
  }
}
```

---

## 15. Known Issues & Fixes Applied

| Issue | Root Cause | Fix Applied |
|---|---|---|
| `/chat` page returning 404 | `app.run()` was called before route definitions | Moved `app.run()` to end of `app.py` |
| Send button not working | Jinja2 processed JavaScript `{{ }}` as template variables | Moved all JS to `/chat-js` route with `mimetype="application/javascript"` |
| 429 rate limit errors | No delay between key rotations, 4 regions firing simultaneously | Added 1s per-key delay + exponential backoff in `core/llm.py` |
| "No JSON found" warning | LLM returned "LLM unavailable..." and JSON parser tried to parse it | Added `"LLM unavailable" not in raw` guard in `agent3_lever.py` |
| Bot says "no info about India" | LLM didn't know `rta` tag = India | Added region legend to context preamble in `_build_context()` |
| Bot can't answer skill queries | No skill-name detection | Added regex `ts_[a-z0-9_]+` detection + `skill_detail` topic |
| Chat history lost on navigation | History stored in DOM only | Moved to `sessionStorage` — persists across page navigation |
| History query returning wrong time | LLM generating `04:50` for "4:50" (4am instead of 4pm) | Added business-hours time conversion rules to SQL prompt |
| SQLite "database is locked" | Multiple threads writing simultaneously | Enabled WAL (Write-Ahead Logging) mode; reads skip lock entirely |
| 413 Payload Too Large | Too many rows returned to Groq | Capped at 15 rows, stripped heavy fields, hard cap at 3000 chars |
| Cleanup running every poll | `cleanup_old_data()` called on every poll from every region | Added hourly throttle — runs at most once per 3600 seconds |

---

## 16. Data Flow Diagram

```
HTML Dashboards (RTA.html etc.)
        │
        │  Playwright browser scrape (every 60s)
        ▼
  Agent 1 — collector.py
        │  skill_metrics, breached_skills
        ▼
    Router (workflow.py)
        │
   ┌────┴────┐
   ▼         ▼
Agent 2    Agent 3
Analyst    Lever
  │           │
  │ CMS       │ Teams/Email
  │ scrape    │ alerts
  ▼           ▼
cms_history  Teams webhook
(history.db) Email SMTP
        │
        ▼
  live_state.json  ←── app.py reads this for chatbot
        │
        ▼
  history.db  ←── chatbot History mode queries this
  skill_history
  cms_history
        │
        ▼
  Flask /api/chat
        │
        ├── Live mode:  live_state.json → LLM → answer
        │
        └── History mode: question → LLM generates SQL
                              → Python runs SQL on history.db
                              → results → LLM explains → answer
```

---

## Quick Reference

### Start the system
```bash
python app.py          # Start Flask UI
# Then go to http://localhost:5000 and click Start
```

### Check if data is being saved
```bash
python -c "
from core.history import query
rows = query('SELECT COUNT(*) as c FROM skill_history')
print('Skill history rows:', rows[0]['c'])
rows = query('SELECT COUNT(*) as c FROM cms_history')
print('CMS history rows:', rows[0]['c'])
"
```

### View latest poll data
```bash
python -c "
import json
data = json.load(open('live_state.json'))
for region, info in data.items():
    print(f'{region}: {info[\"last_poll_time\"]} — {len(info[\"skills\"])} skills')
"
```

### Manually query history
```bash
python -c "
from core.history import query
rows = query('''
  SELECT timestamp, skill, sla, band, lever_fired
  FROM skill_history
  WHERE date(timestamp) = date(\"now\")
  ORDER BY sla ASC LIMIT 10
''')
for r in rows: print(r)
"
```
