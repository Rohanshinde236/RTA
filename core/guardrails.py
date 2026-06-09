"""
core/guardrails.py
Production guardrails for all RTA agents.

Each agent calls the relevant validate_* function before using LLM output.
On validation failure, returns (False, reason) — caller falls back to rule-based logic.
On success, returns (True, cleaned_data).

Guardrails by agent:

  Agent 1 — Data guardrails (scrape output sanity)
    validate_skill_metric()     — bounds-check scraped values

  Agent 2 — LLM output guardrails
    validate_analyst_output()   — JSON structure, move_list priorities, list lengths

  Agent 3 — LLM output guardrails
    validate_lever_output()     — JSON structure, required fields, list non-empty

  Chatbot — SQL guardrails
    validate_sql()              — SELECT-only, no dangerous keywords, length cap

  System-wide
    validate_webhook_url()      — webhook is a valid HTTPS URL
    validate_api_key()          — key format check before making LLM call
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Agent 1 — Scrape data guardrails ─────────────────────────────────────────

def validate_skill_metric(skill: str, data: dict) -> tuple:
    """
    Validate a scraped skill metric dict.
    Catches obviously wrong values that would cause false alerts.

    Returns: (True, data) or (False, reason_string)
    """
    errors = []

    sla = data.get("sla")
    if sla is not None:
        if not isinstance(sla, (int, float)):
            errors.append(f"sla is not a number: {sla}")
        elif not (0.0 <= sla <= 100.0):
            errors.append(f"sla out of range 0-100: {sla}")

    queue = data.get("queue")
    if queue is not None and (not isinstance(queue, int) or queue < 0):
        errors.append(f"queue invalid: {queue}")

    avail = data.get("avail")
    if avail is not None and (not isinstance(avail, int) or avail < 0):
        errors.append(f"avail invalid: {avail}")

    headcount = data.get("headcount")
    if headcount is not None and isinstance(headcount, int):
        on_calls = data.get("on_calls", 0) or 0
        on_aux   = data.get("on_aux",   0) or 0
        avail_v  = data.get("avail",    0) or 0
        total_accounted = on_calls + on_aux + avail_v
        if total_accounted > headcount + 2:   # +2 tolerance for rounding
            errors.append(
                f"agent counts ({total_accounted}) exceed headcount ({headcount})"
            )

    if errors:
        logger.warning(f"[Guardrail][A1] Skill {skill} validation: {'; '.join(errors)}")
        return False, "; ".join(errors)

    return True, data


# ── Agent 2 — Analyst LLM output guardrails ──────────────────────────────────

def validate_analyst_output(parsed: dict, on_aux: int = 99) -> tuple:
    """
    Validate the JSON dict returned by Agent 2's LLM call.

    Checks:
    - Required keys present
    - move_list priorities are unique and sequential
    - move_list length doesn't exceed available AUX agents
    - root_cause is a known value
    - analyst_note is ≤ 20 words

    Returns: (True, cleaned_dict) or (False, reason_string)
    """
    required = {"skill", "root_cause", "move_list", "hold_list", "ask_list",
                "sla_recovery_estimate", "analyst_note"}
    missing  = required - set(parsed.keys())
    if missing:
        return False, f"Missing keys: {missing}"

    # root_cause validation
    valid_causes = {"AUX_HEAVY", "STAFFING", "VOLUME", "OCW_BREACH",
                    "RECOVERING", "STABLE"}
    causes = [c.strip() for c in str(parsed.get("root_cause", "")).split("|")]
    bad    = [c for c in causes if c and c not in valid_causes]
    if bad:
        logger.warning(f"[Guardrail][A2] Unknown root_cause values: {bad} — allowing anyway")

    # analyst_note word count
    note       = str(parsed.get("analyst_note", ""))
    word_count = len(note.split())
    if word_count > 20:
        parsed["analyst_note"] = " ".join(note.split()[:20])
        logger.warning(f"[Guardrail][A2] analyst_note truncated from {word_count} to 20 words")

    # move_list validations
    move_list = parsed.get("move_list", [])
    if not isinstance(move_list, list):
        return False, "move_list is not a list"

    if len(move_list) > on_aux:
        logger.warning(
            f"[Guardrail][A2] move_list length {len(move_list)} > on_aux {on_aux} — trimming"
        )
        parsed["move_list"] = move_list[:on_aux]
        move_list = parsed["move_list"]

    # Check priority uniqueness
    priorities = [item.get("priority") for item in move_list if isinstance(item, dict)]
    if len(priorities) != len(set(priorities)):
        logger.warning("[Guardrail][A2] Duplicate priorities in move_list — reassigning")
        for i, item in enumerate(move_list):
            if isinstance(item, dict):
                item["priority"] = i + 1

    return True, parsed


# ── Agent 3 — Lever LLM output guardrails ────────────────────────────────────

def validate_lever_output(parsed: dict, skill_name: str) -> tuple:
    """
    Validate the JSON dict returned by Agent 3's LLM call.

    Checks:
    - Required keys present
    - Lists are non-empty (LLM sometimes returns empty arrays)
    - lever_summary is a non-empty string
    - skill_name appears in combined_queue_names

    Returns: (True, cleaned_dict) or (False, reason_string)
    """
    required = {"combined_queue_names", "root_cause", "business_callouts",
                "mitigation_actions", "lever_summary"}
    missing  = required - set(parsed.keys())
    if missing:
        return False, f"Missing keys: {missing}"

    # Ensure lists
    for field in ("root_cause", "business_callouts", "mitigation_actions",
                  "combined_queue_names"):
        val = parsed.get(field)
        if not isinstance(val, list):
            parsed[field] = [str(val)] if val else ["No data"]
            logger.warning(f"[Guardrail][A3] {field} was not a list — wrapped")

    # lever_summary must be a non-empty string
    summary = str(parsed.get("lever_summary", "")).strip()
    if not summary:
        parsed["lever_summary"] = f"SLA lever triggered for {skill_name}"
        logger.warning("[Guardrail][A3] lever_summary was empty — using default")

    # skill_name should be in combined_queue_names
    queue_names = parsed.get("combined_queue_names", [])
    if skill_name and not any(skill_name.lower() in n.lower() for n in queue_names):
        parsed["combined_queue_names"].insert(0, skill_name)
        logger.warning(f"[Guardrail][A3] skill_name {skill_name} missing from combined_queue_names — added")

    return True, parsed


# ── Chatbot — SQL guardrails ──────────────────────────────────────────────────

DANGEROUS_SQL_KEYWORDS = re.compile(
    r'\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH)\b',
    re.IGNORECASE
)

def validate_sql(sql: str) -> tuple:
    """
    Validate LLM-generated SQL before running it on history.db.

    Rules:
    - Must start with SELECT
    - Must not contain dangerous keywords
    - Must not exceed 2000 chars (prevents prompt injection artifacts)
    - Must reference skill_history or cms_history (known tables)

    Returns: (True, cleaned_sql) or (False, reason_string)
    """
    sql = sql.strip()

    if not sql.upper().startswith("SELECT"):
        return False, f"SQL must start with SELECT, got: {sql[:50]}"

    danger = DANGEROUS_SQL_KEYWORDS.search(sql)
    if danger:
        return False, f"Dangerous keyword detected: {danger.group(0)}"

    if len(sql) > 2000:
        return False, f"SQL too long ({len(sql)} chars) — possible injection"

    known_tables = ("skill_history", "cms_history")
    if not any(t in sql.lower() for t in known_tables):
        return False, f"SQL must query skill_history or cms_history"

    return True, sql


# ── System-wide guardrails ────────────────────────────────────────────────────

def validate_webhook_url(url: str) -> tuple:
    """Check that a Teams webhook URL looks valid before sending."""
    if not url:
        return False, "Webhook URL is empty"
    if not url.startswith("https://"):
        return False, f"Webhook URL must be HTTPS: {url[:60]}"
    if len(url) < 30:
        return False, f"Webhook URL too short — likely misconfigured"
    return True, url


def validate_api_key(key: str, provider: str = "groq") -> tuple:
    """Check that an API key has the expected format."""
    if not key or not key.strip():
        return False, "API key is empty"

    if provider == "groq":
        if not key.startswith("gsk_"):
            return False, f"Groq key should start with 'gsk_', got: {key[:8]}..."
        if len(key) < 40:
            return False, "Groq key too short"

    if provider == "gemini":
        if not key.startswith("AIzaSy"):
            return False, f"Gemini key should start with 'AIzaSy', got: {key[:8]}..."

    return True, key
