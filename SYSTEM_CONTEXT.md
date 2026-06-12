# RTA Monitor — Full System Context
**Version:** V3 | **Last Updated:** 2026-06-12
**Maintainer:** Aligned Automation Services Pvt. Ltd.
**Purpose of this document:** Complete technical context for any Claude session working on this codebase. Read this before making any changes.

---

## 1. What This System Does

**RTA Monitor** is a real-time SLA monitoring platform for a multi-region contact centre (10 regions, 60+ skill queues). Every 60 seconds it:

1. Scrapes live dashboard HTML pages (one per region) for queue metrics
2. Analyses SLA, queue depth, OCW (Oldest Call Waiting), and agent states
3. Fires escalation alerts (Teams webhooks) when thresholds are crossed
4. Updates a SQLite history database (7-day rolling window)
5. Exposes a React dashboard and AI chatbot for live + historical queries

**Scaling target:** The system is designed to scale from the current **10 regions / 60 skills** to **700+ queues** across many more regions with minimal code changes — only `config.json` needs new entries.

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask 3.1.x, Flask-SocketIO 5.6.x, eventlet |
| Agent Orchestration | LangGraph (StateGraph) |
| Database | SQLite (WAL mode), `db/history.db` |
| LLM Providers | NVIDIA NIM (primary, 70B), Groq (fallback), Gemini (fallback) |
| Frontend | React 18, Vite, Tailwind CSS, ReactMarkdown, remark-gfm |
| Alerting | Microsoft Teams via Power Automate webhooks |
| Reporting | openpyxl (lever reports to Excel) |
| Config | config.json (single source of truth) |
| Prompts | prompts/*.txt + prompts/rules.yaml |
| OS | Windows 11 (paths use forward slashes, OneDrive sync active) |

---

## 3. Repository Structure

```
RTA_Final/
├── app.py                        # Flask web server, API routes, chatbot handler
├── workflow.py                   # LangGraph state graph, router logic
├── run_all.py                    # Entry point, per-region threads, main loop
├── config.json                   # All thresholds, regions, webhooks
│
├── core/
│   ├── config_loader.py          # Centralised config access (no hardcoded values)
│   ├── llm.py                    # Multi-provider LLM router, rate-limit handling
│   ├── history.py                # SQLite read/write, 7-day rolling window
│   └── prompt_loader.py          # Template loader, auto-injects rules.yaml
│
├── agents/
│   └── agent4_cms_monitor.py     # AHT/AUX/ACW monitor, independent thread per region
│
├── prompts/
│   ├── chatbot_answer.txt        # Live chatbot system prompt
│   ├── chatbot_sql_gen.txt       # SQL generation prompt for history mode
│   └── rules.yaml                # Chatbot answer formatting rules (no code change needed)
│
├── ui/
│   ├── RTA.html                  # India region dashboard (scraped by agent1)
│   ├── RTA_CN.html               # China
│   ├── RTA_AU.html               # Australia
│   ├── RTA_EMEA.html             # EMEA
│   ├── RTA_HK.html               # Hong Kong (SLA locked 90–95%, never dips)
│   ├── RTA_MY.html               # Malaysia
│   ├── RTA_KR.html               # Korea
│   ├── RTA_TH.html               # Thailand
│   ├── RTA_BR.html               # Brazil
│   ├── RTA_TW.html               # Taiwan (SLA locked 90–95%, never dips)
│   └── CMS.html                  # Agent-level CMS portal (AUX/state view)
│
├── db/
│   ├── history.db                # SQLite (skill_history + cms_history tables)
│   ├── live_state.json           # Latest per-region poll snapshot (overwritten every 60s)
│   └── cms_agents.json           # Per-region per-skill agent state snapshot
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx     # Region overview cards, sparklines, control buttons
│   │   │   ├── Chatbot.jsx       # AI chatbot (live + history mode)
│   │   │   └── ...               # Regions, AgentSettings, SkillThresholds, Logs pages
│   │   └── components/
│   │       └── Sidebar.jsx       # Navigation, theme toggle
│   └── package.json
│
└── scripts/
    └── set_hk_tw_healthy.py      # Utility: force HK+TW to healthy state in JSON
```

---

## 4. Regions & Skills

### Region Tags (used everywhere in code, config, DB)

| Tag | Region Name | Display Name | Skills |
|---|---|---|---|
| `rta` | India | Client ProSupport IND | TS_CSTCE, TS_CSTElite, TS_LicKeys, TS_VICHW, TS_ProDB, TS_ProCNX |
| `cn` | China | Client ProSupport CHN | TS_CN_ProDB, TS_CN_ProCNX, TS_CN_CSTVCE, TS_CN_CSTElite, TS_CN_VICHW, TS_CN_LicKeys |
| `au` | Australia | Client ProSupport AUS | TS_AU_ProDB, TS_AU_ProCNX, TS_AU_Elite, TS_AU_LicKeys, TS_AU_VICHW, TS_AU_CritAcct |
| `emea` | EMEA | Client ProSupport EMEA | TS_EMEA_ProDB, TS_EMEA_ProCNX, TS_EMEA_MLSCST_EN, TS_EMEA_MLSCST_DE, TS_EMEA_MLSCST_FR, TS_EMEA_CritAcct |
| `hk` | Hong Kong | Client ProSupport HKG | TS_HK_ProDB, TS_HK_ProCNX, TS_HK_Elite, TS_HK_LicKeys, TS_HK_VICHW, TS_HK_CritAcct |
| `my` | Malaysia | Client ProSupport MYS | TS_MY_ProDB, TS_MY_ProCNX, TS_MY_Elite, TS_MY_LicKeys, TS_MY_VICHW, TS_MY_CritAcct |
| `kr` | Korea | Client ProSupport KOR | TS_KR_ProDB, TS_KR_ProCNX, TS_KR_Elite, TS_KR_LicKeys, TS_KR_VICHW, TS_KR_CritAcct |
| `th` | Thailand | Client ProSupport THA | TS_TH_ProDB, TS_TH_ProCNX, TS_TH_Elite, TS_TH_LicKeys, TS_TH_VICHW, TS_TH_CritAcct |
| `br` | Brazil | Client ProSupport BRA | TS_BR_ProDB, TS_BR_ProCNX, TS_BR_Elite, TS_BR_LicKeys, TS_BR_VICHW, TS_BR_CritAcct |
| `tw` | Taiwan | Client ProSupport TWN | TS_TW_ProDB, TS_TW_ProCNX, TS_TW_Elite, TS_TW_LicKeys, TS_TW_VICHW, TS_TW_CritAcct |

### Skill Types

| Skill Suffix | Meaning | Characteristics |
|---|---|---|
| `ProDB` | ProSupport Database | Large teams, high volume, `aux_threshold=3` |
| `ProCNX` | ProSupport Connectivity | High volume, `aux_threshold=3` |
| `Elite` | Elite/premium support | Moderate, `aux_threshold=2` |
| `LicKeys` | License & Keys | Smaller team, `aux_threshold=1` |
| `VICHW` | VIC Hardware | Consistently challenging, `aux_threshold=1` |
| `CritAcct` | Critical Accounts | High priority, `aux_threshold=2` |
| `CSTCE` | CST CE | India-specific |
| `CSTElite` | CST Elite | India/China-specific |
| `MLSCST_*` | Multi-language CST | EMEA only (EN, DE, FR) — small teams, `aux_threshold=1` |

---

## 5. SLA Bands

| Band | SLA Range | Color | Meaning |
|---|---|---|---|
| EXCELLENT | ≥ 95% | Blue | Ahead of target |
| HEALTHY | 90–94.9% | Green | On target |
| WARNING | 80–89.9% | Amber | Approaching breach |
| CRITICAL | 70–79.9% | Red/Orange | Active breach |
| SEVERE | < 70% | Black/Dark Red | Crisis — all levers fired |

---

## 6. Agent Pipeline (LangGraph)

The system runs **one LangGraph workflow per region**, each in its own Python thread.

```
A1 (Scraper) → Router → A2 (Analyst) ──┐
                      → A3 (Lever)  ────┴→ END
```

### Agent 1 — Scraper (`agent1_collector`)
- Opens `ui/RTA_<TAG>.html` in a headless browser (Selenium/Playwright)
- Waits for JavaScript to render (the HTML files generate simulated live data every 5s via JS)
- Parses the `<table>` rows: skill name, queue, OCW, avail, on_calls, on_aux, headcount, offered, acceptable, SLA%
- Returns a list of `SkillMetric` objects in LangGraph state

### Router (`workflow.py: router_node`)
Evaluates each skill after A1 and sets flags:

| Condition | Flag set | Trigger |
|---|---|---|
| queue ≥ queue_min AND avail = 0 | `_invoke_a2 = True` | Staffing pressure |
| ocw_sec > ocw_threshold_sec | `_invoke_a2 = True` | Calls waiting too long |
| SLA crossed amber/red/black (first time) | `_invoke_a3 = True` | Lever firing |
| Was breached, now queue=0 AND avail>0 AND SLA≥amber | Reset fired levers | Recovery |
| 3+ skills in trouble simultaneously | Systemic crisis log | `SYSTEMIC_MIN_SKILLS = 3` |

**One-shot lever logic:** Each lever fires only once per SLA band crossing. Stored in `a3_fired_levers[skill_Amber]`, `a3_fired_levers[skill_Red]`, etc. Recovery detection resets these so levers re-fire if SLA drops again after recovering.

### Agent 2 — Analyst (`agent2_analyst`)
- Fires when queue pressure or OCW breach detected
- If agents on AUX exist: calls LLM for recommendations (which agents to move)
- If no AUX data: rule-based recommendation (generic staffing advice)
- Cooldown: 300s per skill (throttle — won't alert same skill twice in 5 minutes)
- Sends Teams webhook with recommendations

### Agent 3 — Lever (`agent3_lever`)
- Fires when SLA crosses a band threshold for the first time
- Sends Teams alert with lever name (Amber/Red/Black), skill, SLA%, queue
- Updates Excel report file (path in config.json `agent3.excel_path`)
- Emails configured recipients
- Does NOT re-fire same lever unless recovery → re-breach

### Agent 4 — CMS Monitor (`agents/agent4_cms_monitor.py`)
- **Runs as a separate thread**, independent of the LangGraph workflow
- Starts staggered: `region_index × 6 seconds` delay (to spread Teams alerts)
- Every 60 seconds for each skill in the region:
  - Loads agent-level data from CMS (AUX reason, state, time in state)
  - Checks AHT vs per-skill `aht_target_min`
  - Checks AUX time vs `agent4.aux_thresholds[AUXn].max_time_min`
  - Checks ACW time vs `agent4.acw_target_min`
  - **AUX count gate:** if total agents on AUX ≤ skill's `aux_threshold`, suppress ALL time-based AUX alerts for that poll cycle
  - Sends Teams adaptive card if alerts exist
  - Saves snapshot to `db/cms_agents.json` (chatbot reads this)

---

## 7. Data Files

### `db/live_state.json`
Written every poll cycle by `run_all.py`. Structure:

```json
{
  "rta": {
    "region_name": "RTA",
    "region_display": "Client ProSupport IND",
    "last_poll_time": "14:32:10",
    "poll_number": 47,
    "breached_count": 2,
    "levers_fired": {"TS_CSTElite_Amber": true, "TS_LicKeys_Red": true},
    "skills": {
      "TS_CSTCE": {
        "sla": 81.9, "band": "WARNING", "queue": 2, "ocw": "00:34",
        "avail": 3, "on_calls": 10, "on_aux": 3, "headcount": 16,
        "breached": false, "breach_reasons": [],
        "lever_fired": "Black", "last_move": [], "last_ask": [], "last_hold": [],
        "a2_note": "", "root_cause": ""
      }
    }
  },
  "cn": { ... },
  ...
}
```

**Important:** This file is **overwritten every ~60 seconds** when the system is running. Any manual changes are lost on the next poll. To show specific values permanently, the source HTML files (`ui/RTA_<TAG>.html`) must be edited.

### `db/cms_agents.json`
Written by Agent 4. Structure:

```json
{
  "rta": {
    "TS_CSTCE": [
      {"name": "Sharma_R", "state": "AUX", "aux_reason": "AUX 2", "aux_key": "AUX2",
       "aux_name": "Break", "time_minutes": 12.5, "skill": "TS_CSTCE"}
    ]
  }
}
```

Used by chatbot to name agents in AUX recommendations.

### `db/history.db`
SQLite with two tables:

**`skill_history`** — one row per skill per poll:
```sql
CREATE TABLE skill_history (
  id INTEGER PRIMARY KEY,
  timestamp TEXT,        -- 'YYYY-MM-DD HH:MM:SS'
  region_tag TEXT,       -- 'rta', 'cn', 'hk', etc.
  region_display TEXT,
  skill TEXT,
  sla REAL,
  band TEXT,
  queue INTEGER,
  ocw TEXT,
  avail INTEGER,
  on_calls INTEGER,
  on_aux INTEGER,
  headcount INTEGER,
  breached INTEGER,      -- 0 or 1
  breach_reasons TEXT,   -- JSON array as text
  lever_fired TEXT,
  last_move TEXT,        -- JSON array
  last_ask TEXT,
  a2_note TEXT,
  root_cause TEXT
)
```

**`cms_history`** — one row per agent per poll:
```sql
CREATE TABLE cms_history (
  id INTEGER PRIMARY KEY,
  timestamp TEXT,
  region_tag TEXT,
  skill TEXT,
  agent_name TEXT,
  login_id TEXT,
  role TEXT,
  aux_reason TEXT,
  state TEXT,            -- 'ACD', 'AUX', 'AVAIL'
  direction TEXT,
  time_in_state TEXT,
  time_seconds INTEGER
)
```

**Retention:** 7-day rolling window. Cleanup runs max once per hour.
**WAL mode** enables concurrent reads during writes (critical for chatbot + scraper running simultaneously).

---

## 8. Configuration (`config.json`)

### Full Structure

```json
{
  "regions": [
    {
      "name": "RTA",
      "display": "Client ProSupport IND",
      "dashboard": "ui/RTA.html",
      "webhook": "https://...",
      "active": true
    }
  ],
  "agent1": {
    "scrape_interval_sec": 60
  },
  "agent2": {
    "ocw_threshold_sec": 60,
    "queue_min": 1,
    "cooldown_sec": 300,
    "llm_enabled": true
  },
  "agent3": {
    "amber_threshold": 90.0,
    "red_threshold": 80.0,
    "black_threshold": 70.0,
    "excel_path": "...",
    "email_recipients": []
  },
  "agent4": {
    "scrape_interval_sec": 60,
    "aht_target_min": 0,
    "acw_target_min": 5,
    "aux_thresholds": {
      "AUX1": {"name": "IT Issue",    "max_time_min": 0,  "enabled": false},
      "AUX2": {"name": "Break",       "max_time_min": 15, "enabled": true},
      "AUX3": {"name": "Lunch",       "max_time_min": 30, "enabled": true},
      "AUX4": {"name": "Coaching",    "max_time_min": 20, "enabled": true},
      "AUX5": {"name": "Case Mgmt",   "max_time_min": 20, "enabled": true},
      "AUX6": {"name": "Meeting",     "max_time_min": 60, "enabled": true},
      "AUX7": {"name": "Training",    "max_time_min": 120,"enabled": true},
      "AUX8": {"name": "Unavailable", "max_time_min": 10, "enabled": true},
      "AUX9": {"name": "Offline",     "max_time_min": 5,  "enabled": true}
    }
  },
  "skill_thresholds": {
    "TS_HK_ProDB": {
      "aht_target_min": 24,
      "ocw_threshold_sec": 60,
      "active": true,
      "aux_threshold": 3
    }
  }
}
```

### Key Config Rules
- Adding a new region: add to `regions[]` array + create `ui/RTA_<TAG>.html` + add skills to `skill_thresholds`
- `aht_target_min: 0` = disabled (use per-skill from `skill_thresholds`)
- `active: false` on a skill = Agent 4 skips it entirely
- Per-skill `ocw_threshold_sec` overrides global `agent2.ocw_threshold_sec`
- Config is re-read every poll cycle — no restart needed for threshold changes

---

## 9. `config_loader.py` — Key Functions

```python
get_aux_max(skill_name)   # Returns max concurrent AUX agents before alerts fire
                          # Defaults: ProDB/ProCNX=3, VICHW/LicKeys=1, MLSCST=1, others=2
                          # Override via skill_thresholds[skill]['aux_threshold']

get_aht_target_sec(skill) # Returns AHT target in seconds (converts from minutes)

get_ocw_threshold(skill)  # Per-skill OCW or global fallback

get_skill(skill_name)     # Returns full skill config dict
```

**Never hardcode thresholds in agents.** Always call `config_loader.get_*()`.

---

## 10. LLM Layer (`core/llm.py`)

### Providers (in priority order)
1. **NVIDIA NIM** — primary, 70B model (`meta/llama-3.1-70b-instruct`), best quality
2. **Groq** — fast fallback (`llama3-70b-8192`)
3. **Gemini** — secondary fallback (`gemini-1.5-flash`)

### Key Behaviour
- **Round-robin rotation** through all keys in the pool
- **Per-region lock** — only one LLM call per region at a time (thread-safe)
- **429 handling** — rotate key, exponential backoff (max 30s)
- **Retries** = 2 × pool size by default
- **Temperature** = 0.3 (low randomness, deterministic lever/analyst output)

---

## 11. Chatbot System

### Two Modes

**Live Mode:**
1. Load `db/live_state.json` + `db/cms_agents.json`
2. `_build_context()` — intelligent context builder:
   - Detects region mentions in question (filters to relevant region only)
   - Detects topic (lever/breach/queue/AUX/improvement/avail)
   - Applies SLA thresholds for band labels
   - Includes agent names if CMS data loaded
3. Render `chatbot_answer.txt` (injects `{rules}` + `{context}`)
4. Call LLM → return answer

**History Mode:**
1. Render `chatbot_sql_gen.txt` (schema + date constraints + routing rules)
2. Call LLM to generate SQL
3. Validate SQL (guardrails: no DROP/UPDATE/INSERT, only SELECT)
4. Execute on `db/history.db`
5. Aggregate if range query (min/max/avg SLA, peak queue, time-in-band counts)
6. Render `chatbot_answer.txt` with query results
7. Call LLM → return answer

### Anti-Hallucination Guards (in `rules.yaml`)
- Never invent agent names — if CMS pending, say "count only"
- Never invent SLA values — only use data from context
- No fabricated timestamps
- "⚠ Individual agent names NOT available" shown when CMS not loaded

---

## 12. Frontend (React)

### Dashboard Page (`Dashboard.jsx`)

**Region Cards show:**
- Region flag + name
- Average SLA across all skills (not worst-skill)
- Live band badge — computed from **average SLA** (not worst skill — prevents one SEVERE from painting entire card red)
- Worst skill shown in footer separately with its real band
- Sparkline (recharts) — 8-point history of top skills
- Breached skill count + lever fire count
- Portal dashboard button (opens `ui/RTA_<TAG>.html`)

**Badge logic (running state):**
- `avgSla ≥ 95` → EXCELLENT (blue)
- `avgSla ≥ 90` → HEALTHY (green)
- `avgSla ≥ 80` → WARNING (amber)
- `avgSla ≥ 70` → CRITICAL (orange)
- `avgSla < 70` → SEVERE (red)
- System stopped → ACTIVE / INACTIVE (from config, not live data)

**HealthSummaryBar** (top of page):
- Overall SLA % across all regions
- Count per band (colour-coded)
- Mini traffic-light dots per region

### Chatbot Page (`Chatbot.jsx`)
- Mode toggle: **Live** (current snapshot) / **History** (7-day DB)
- Markdown rendering with table support (remark-gfm)
- Persists last 40 messages to sessionStorage
- Suggestion buttons on empty state

---

## 13. Source HTML Files (`ui/RTA_*.html`)

These are the **source of truth for all live data**. Agent 1 opens and scrapes these files.

Each file contains:
- A `SKILLS` array (skill name, `sl_target`, `hc` headcount, `phase_offset`)
- A `getPhase()` JavaScript function that generates simulated live data every 5 seconds
- Table rendering + auto-refresh every 5 seconds

### Normal Behaviour (8 regions)
`getPhase()` runs a 240-second (4-minute) wave cycle:
- 0–25%: SLA near target, queue=0, agents available (healthy phase)
- 25–50%: SLA declining, queue building, agents going AUX (pressure phase)
- 50–65%: SLA at lowest (67–61%), queue=6–9, OCW rising (crisis phase)
- 65–82%: Recovery — queue draining, agents returning from AUX
- 82–100%: Healthy recovery, SLA back to target

### HK and TW — Locked Healthy (SPECIAL CASE)
`ui/RTA_HK.html` and `ui/RTA_TW.html` use a **modified `getPhase()`**:
```javascript
// SLA always stays 90-95% — sine wave oscillation only within this band
const sl = Math.round((90 + 2.5 + 2.5 * Math.sin(wave * 2 * Math.PI)) * 10) / 10;
// queue always = 0, OCW always = 00:00
```
This means HK and TW **always show 90–95% on every scrape**, permanently, even while the backend is running. This is intentional for demo/presentation purposes.

All `sl_target` values for HK and TW skills are set to `90` so SLA badges show green.

---

## 14. Edge Cases & Special Handling

### 1. OneDrive File Locking
Windows OneDrive can briefly lock `.tmp` files during sync.
- `live_state.json` and `cms_agents.json` use atomic write: write to `.tmp` first, then `os.rename()`
- If rename fails (OneDrive lock), retry up to 3 times with 0.1s sleep
- Final fallback: direct write (less atomic but always succeeds)

### 2. Per-Region Module Namespacing
Each region's agents are loaded as separate module instances:
- `rta_agent1_rta`, `rta_agent1_cn`, `rta_agent2_hk`, etc.
- Prevents cross-region state pollution in `sys.modules`
- Each region gets its own LLM lock, its own LangGraph compiled workflow

### 3. Agent 4 Stagger (Spread Teams Alerts)
10 regions × 6-second stagger = 0s, 6s, 12s, ..., 54s start delay.
This prevents all 10 regions from firing Teams alerts simultaneously on startup.
```python
# run_all.py
agent4_stagger = region_index * 6  # seconds
```

### 4. AUX Count Gate (Smart Alert Suppression)
The most important edge case in Agent 4:
- Each skill has `aux_threshold` — max concurrent AUX agents before time-based alerts fire
- If `len(aux_agents) <= skill.aux_threshold` → skip ALL time-based checks for this poll
- Rationale: ProDB with 3 agents on break isn't a problem. VICHW with 2 on AUX IS a problem.
- Configured per-skill in `config.json` skill_thresholds
- Defaults by pattern: ProDB/ProCNX→3, VICHW/LicKeys→1, MLSCST→1, others→2

### 5. Lever One-Shot + Recovery Reset
- Levers (Amber/Red/Black) fire only once per SLA crossing
- Stored per-skill in `a3_fired_levers`: `{skill_Amber: True}`
- Recovery: when SLA returns to ≥ amber AND queue=0 AND avail>0 → all fired levers for that skill are reset
- Next time SLA drops below amber again → lever fires again

### 6. History Query Aggregation (Token Efficiency)
- Range queries (yesterday, past week): aggregate to scorecard (min/max/avg SLA, peak queue, time-in-band minutes)
- Point queries (at 4:50 PM, at 3 PM): return individual rows (max 15)
- Saves ~80% tokens on range queries
- SQL generated by LLM is validated (no DROP/UPDATE/DELETE allowed)

### 7. Systemic Crisis Detection
- Router counts skills in trouble per region each poll
- If 3+ skills simultaneously have queue>0 AND avail=0 → systemic crisis log + flag
- `SYSTEMIC_MIN_SKILLS = 3` in workflow.py
- No auto-escalation yet — logged and visible in A2 recommendations

### 8. Dual-Mode Operation
```
--mode full   →  A1 → Router → A2/A3 (full alerting pipeline)
--mode scrape →  A1 → END    (data collection only, no alerts)
```
Mode set at startup via CLI. UI shows mode selector before start (disabled while running).

### 9. Per-Skill Active Flag
- `skill_thresholds[skill]['active'] = false` → Agent 4 skips that skill entirely
- Useful for skills that are temporarily offline or not yet staffed
- Does NOT affect Agent 1/2/3 scraping (those operate on whatever HTML provides)

### 10. SQL Guardrails (Chatbot Safety)
History chatbot SQL is generated by LLM but validated before execution:
- Only `SELECT` allowed — any `DROP`, `UPDATE`, `INSERT`, `DELETE` raises an error
- Region tag whitelist validation
- Date constraint injected server-side (Python calculates today's date, LLM copies verbatim)
- Max rows returned: 500 (prevents OOM on large queries)

### 11. Flask-SocketIO + Flask 3.x Compatibility
Flask 3.1+ removed the `session` property setter on `RequestContext`.
**Fix:** Upgrade to Flask-SocketIO ≥ 5.4.0 (currently 5.6.1).
Do not downgrade Flask — use 5.6.1+ of flask-socketio.

---

## 15. Scaling to 700 Queues

The system is architected to scale horizontally. Here is what changes vs what stays the same:

### What Scales Automatically (no code changes)
- Each new region = new entry in `config.json regions[]` array
- Each new skill = new entry in `config.json skill_thresholds`
- Thread-per-region model: 700 queues across ~70 regions = 70 threads (Python handles this fine)
- SQLite WAL handles concurrent writes from 70 threads without locking
- LLM pool rotates across all regions — more regions = more rotation pressure (add more API keys)

### What Needs Attention at Scale

| Area | Current | Needed for 700 queues |
|---|---|---|
| Regions | 10 | ~70–120 (depends on queue density) |
| `ui/*.html` files | 10 | One per region (can be templated) |
| Teams webhooks | 10 | One per region or shared by geography |
| LLM keys | 3–5 | 8–12+ (more parallel regions = more contention) |
| SQLite | 1 file, 10 regions | Recommend Postgres at 50+ regions (WAL helps but I/O becomes bottleneck) |
| `live_state.json` | 10-key JSON | 70-key JSON — still fine for REST/SocketIO |
| `cms_agents.json` | 10-key JSON | 70-key JSON — still fine |
| Agent 4 stagger | 10 × 6s | 70 × 2s = 140s startup spread (reduce multiplier) |
| React dashboard | 10 cards | Pagination or region groups needed (70 cards won't fit screen) |
| History DB | ~1M rows/month | ~7M rows/month at 70 regions — Postgres recommended |

### Recommended Changes for 700 Queues
1. **Migrate SQLite → PostgreSQL** in `core/history.py` (change connection string, adapt WAL logic)
2. **Template HTML generation**: script to generate `ui/RTA_<TAG>.html` from a template + `config.json` rather than maintaining 70 separate files
3. **Dashboard pagination**: group regions by geography (APJ / EMEA / AMER), paginate cards
4. **Add more LLM keys** in `core/llm.py` key pool (currently NVIDIA + Groq + Gemini)
5. **Reduce A4 stagger multiplier**: `region_index * 2` instead of `* 6` (2s × 70 = 140s spread)
6. **Connection pooling** for DB writes if moving to Postgres

---

## 16. Alert Flow (Teams)

### Agent 2 Alert (Staffing Pressure)
Triggered when: `queue ≥ queue_min` AND (`avail = 0` OR `ocw > threshold`)
Content: skill name, SLA, queue depth, OCW, recommended action (move agents from AUX)
Cooldown: 300s per skill (config: `agent2.cooldown_sec`)

### Agent 3 Alert (Lever Fire)
Triggered when: SLA crosses amber (90), red (80), or black (70) for the first time
Content: region, skill, lever name (Amber/Red/Black), current SLA, queue, recommended action
Also: updates Excel report + emails configured recipients

### Agent 4 Alert (AHT/AUX/ACW)
Triggered by: individual agent exceeding time thresholds
Content: Teams Adaptive Card with:
- AHT overrun: agent name, current AHT, target, % over
- AUX overrun: agent name, AUX code/name, time on AUX, max allowed
- ACW overrun: agent name, ACW duration, target
Suppressed when: `total AUX count ≤ skill.aux_threshold` (AUX count gate)

---

## 17. How to Run

```bash
# Full mode (scrape + analyse + alert)
python run_all.py --mode full

# Scrape only (no alerts, no levers)
python run_all.py --mode scrape

# Frontend (dev)
cd frontend && npm run dev

# Build frontend
cd frontend && npm run build
```

Backend runs on `http://localhost:5000`. React dev server on `http://localhost:5173`.

---

## 18. Key File Cross-Reference

| If you want to change... | Edit this file |
|---|---|
| Poll interval | `config.json → agent1.scrape_interval_sec` |
| SLA band thresholds | `config.json → agent3.*_threshold` |
| OCW alert threshold | `config.json → agent2.ocw_threshold_sec` (global) or `skill_thresholds[skill].ocw_threshold_sec` |
| AHT target per skill | `config.json → skill_thresholds[skill].aht_target_min` |
| AUX alert suppression | `config.json → skill_thresholds[skill].aux_threshold` |
| AUX code time limits | `config.json → agent4.aux_thresholds.AUX#.max_time_min` |
| Enable/disable a skill | `config.json → skill_thresholds[skill].active` |
| Add a region | `config.json → regions[]` + create `ui/RTA_<TAG>.html` |
| Chatbot answer style | `prompts/rules.yaml` |
| Chatbot system prompt | `prompts/chatbot_answer.txt` |
| SQL generation rules | `prompts/chatbot_sql_gen.txt` |
| Agent routing logic | `workflow.py → router_node()` |
| Agent 4 AUX count gate | `core/config_loader.py → get_aux_max()` |
| Dashboard card badge | `frontend/src/pages/Dashboard.jsx → liveBand` calculation |
| Live data display values | `ui/RTA_<TAG>.html → SKILLS array + getPhase()` |
| HK/TW healthy lock | `ui/RTA_HK.html` and `ui/RTA_TW.html → getPhase()` (sine wave 90–95%) |

---

## 19. Important Constraints & Gotchas

1. **Never push to `main` branch without explicit permission** from the user (Gaurav Khapekar). Always ask which branch and remote before any `git push`.

2. **live_state.json is volatile** — overwritten every 60s while backend runs. Editing it manually only works when backend is stopped. To permanently change what data shows, edit the source `ui/RTA_<TAG>.html` file.

3. **HK and TW HTML files are intentionally modified** to always return 90–95% SLA (for demo purposes). Do not "fix" this unless explicitly asked.

4. **Windows paths**: This runs on Windows 11 with OneDrive sync. Use forward slashes in Python paths. Quote paths with spaces. Atomic writes (.tmp rename) handle OneDrive locking.

5. **Python command**: On this machine use `python` not `python3`. Shell is PowerShell.

6. **Flask-SocketIO version**: Must be ≥ 5.6.1 for Flask 3.x compatibility. Do not downgrade Flask.

7. **Module namespacing**: Each region's agents are in separate `sys.modules` entries. If you add a new shared function to an agent file, test it doesn't cause import conflicts.

8. **config.json is hot-reloaded**: Most threshold changes take effect on the next poll without restart. Region adds/removes require restart.

9. **LLM keys rotation**: If adding new API keys, add to the pool in `core/llm.py`. The round-robin rotates across all keys in the pool.

10. **SQLite concurrent access**: WAL mode is enabled. Multiple threads can read while one writes. Do not switch to journal mode or use `check_same_thread=False` workarounds.
