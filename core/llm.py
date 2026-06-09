import os
import time
import threading
import itertools
import requests
from dotenv import load_dotenv

load_dotenv("config.env")

# ─── Build unified key pool ────────────────────────────────────
# Each entry: (provider, api_key, model)
_key_pool = []

# Groq keys
groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
for i in range(1, 9):  # supports up to 8 Groq keys
    k = os.getenv(f"GROQ_API_KEY_{i}")
    if k and k.strip() and not k.strip().startswith("gsk_..."):
        _key_pool.append(("groq", k.strip(), groq_model))

# Gemini keys (uncomment in config.env to activate)
gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
for i in range(1, 9):  # supports up to 8 Gemini keys
    k = os.getenv(f"GEMINI_API_KEY_{i}")
    if k and k.strip():
        _key_pool.append(("gemini", k.strip(), gemini_model))

if not _key_pool:
    raise RuntimeError("No LLM API keys found in config.env")

_pool_cycle = itertools.cycle(range(len(_key_pool)))
_pool_lock  = threading.Lock()  # protects the shared cycle iterator

# ─── Per-region locks ──────────────────────────────────────────
# Stored in sys.modules so importlib copies all share the same lock
import sys
_REGION_LOCK_PREFIX = "__rta_llm_lock_"

def get_region_lock(region_tag: str) -> threading.Lock:
    key = f"{_REGION_LOCK_PREFIX}{region_tag}__"
    if key not in sys.modules:
        sys.modules[key] = threading.Lock()
    return sys.modules[key]

# ─── Unified call ──────────────────────────────────────────────
def call_llm(prompt: str, region_tag: str = "global",
             max_tokens: int = 1024, retries: int = None) -> str:
    """
    Call LLM using the shared key pool with round-robin rotation.
    Per-region lock ensures one LLM call at a time per region.
    Rotates to next key on 429 with exponential backoff.
    """
    if retries is None:
        retries = len(_key_pool) * 2  # two full passes through all keys

    lock = get_region_lock(region_tag)
    with lock:
        rate_limit_count = 0
        for attempt in range(retries):
            with _pool_lock:
                idx = next(_pool_cycle)
            provider, api_key, model = _key_pool[idx]
            key_label = f"{provider}_key_{idx+1}"

            print(f"  LLM call attempt {attempt+1} ({key_label}, model={model})...")
            try:
                if provider == "groq":
                    response = _call_groq(prompt, api_key, model, max_tokens)
                elif provider == "gemini":
                    response = _call_gemini(prompt, api_key, model, max_tokens)
                else:
                    continue

                print(f"  LLM responded successfully ({key_label})")
                return response

            except RateLimitError:
                rate_limit_count += 1
                # After cycling through all keys once, wait before trying again
                if rate_limit_count % len(_key_pool) == 0:
                    wait = min(30, 5 * (rate_limit_count // len(_key_pool)))
                    print(f"  All keys rate-limited — waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    time.sleep(1)  # brief pause between individual key rotations
                print(f"  429 on {key_label} — rotating to next key")
                continue
            except Exception as e:
                print(f"  LLM error on {key_label}: {e}")
                continue

        return "LLM unavailable — all keys exhausted"


# ─── Provider implementations ─────────────────────────────────

class RateLimitError(Exception):
    pass

def _call_groq(prompt: str, api_key: str, model: str, max_tokens: int) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3
        },
        timeout=60
    )
    if resp.status_code == 429:
        raise RateLimitError()
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()

def _call_gemini(prompt: str, api_key: str, model: str, max_tokens: int) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    resp = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}
        },
        timeout=60
    )
    if resp.status_code == 429:
        raise RateLimitError()
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()