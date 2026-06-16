import os
import time
import threading
import itertools
import requests
from dotenv import load_dotenv

load_dotenv("config.env", override=True)

# ─── Build unified key pool ────────────────────────────────────
# Each entry: (provider, api_key, model)
# Order matters — pool is cycled round-robin.
# ── TEMPORARY: Groq only ──────────────────────────────────────
# To re-enable NVIDIA/Gemini, uncomment those blocks below.
_key_pool = []

# ── NVIDIA keys — disabled temporarily ───────────────────────
# nvidia_model    = os.getenv("NVIDIA_MODEL",    "meta/llama-3.3-70b-instruct")
# nvidia_base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
# for i in range(1, 10):
#     k = os.getenv(f"NVIDIA_API_KEY_{i}")
#     if k and k.strip():
#         _key_pool.append(("nvidia", k.strip(), nvidia_model))

# ── Groq keys (active) ────────────────────────────────────────
groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
for i in range(1, 10):  # supports up to 9 Groq keys
    k = os.getenv(f"GROQ_API_KEY_{i}")
    if k and k.strip() and not k.strip().startswith("gsk_..."):
        _key_pool.append(("groq", k.strip(), groq_model))

# ── Gemini keys — disabled temporarily ───────────────────────
# gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
# for i in range(1, 10):
#     k = os.getenv(f"GEMINI_API_KEY_{i}")
#     if k and k.strip():
#         _key_pool.append(("gemini", k.strip(), gemini_model))

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
             max_tokens: int = 1024, retries: int = None,
             max_wall_sec: float = 45.0) -> str:
    """
    Call LLM using the shared key pool with round-robin rotation.
    Per-region lock ensures one LLM call at a time per region.
    Rotates to next key on 429 with exponential backoff.

    max_wall_sec bounds the TOTAL time spent retrying. Without it, a large key
    pool (len*2 retries × 30–60s timeouts) could block a region's poll loop for
    minutes when providers are slow/exhausted — which froze breached regions'
    dashboards. Once the deadline passes we stop retrying and return gracefully.
    """
    if retries is None:
        retries = len(_key_pool) * 2  # two full passes through all keys

    lock = get_region_lock(region_tag)
    with lock:
        deadline = time.monotonic() + max_wall_sec
        rate_limit_count = 0
        for attempt in range(retries):
            if time.monotonic() >= deadline:
                print(f"  LLM wall-clock deadline ({max_wall_sec}s) hit — giving up")
                return "LLM unavailable — timed out"
            with _pool_lock:
                idx = next(_pool_cycle)
            provider, api_key, model = _key_pool[idx]
            key_label = f"{provider}_key_{idx+1}"

            print(f"  LLM call attempt {attempt+1} ({key_label}, model={model})...")
            try:
                if provider == "nvidia":
                    response = _call_nvidia(prompt, api_key, model, max_tokens)
                elif provider == "groq":
                    response = _call_groq(prompt, api_key, model, max_tokens)
                elif provider == "gemini":
                    response = _call_gemini(prompt, api_key, model, max_tokens)
                else:
                    continue

                print(f"  LLM responded successfully ({key_label})")
                return response

            except RateLimitError:
                rate_limit_count += 1
                # After cycling through all keys once, wait before trying again —
                # but never sleep past the wall-clock deadline.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print(f"  LLM wall-clock deadline ({max_wall_sec}s) hit — giving up")
                    return "LLM unavailable — timed out"
                if rate_limit_count % len(_key_pool) == 0:
                    wait = min(30, 5 * (rate_limit_count // len(_key_pool)), remaining)
                    print(f"  All keys rate-limited — waiting {wait:.0f}s before retry...")
                    time.sleep(max(0, wait))
                else:
                    time.sleep(min(1, remaining))  # brief pause between key rotations
                print(f"  429 on {key_label} — rotating to next key")
                continue
            except Exception as e:
                print(f"  LLM error on {key_label}: {e}")
                continue

        return "LLM unavailable — all keys exhausted"


# ─── Provider implementations ─────────────────────────────────

class RateLimitError(Exception):
    pass


def _call_nvidia(prompt: str, api_key: str, model: str, max_tokens: int) -> str:
    """Call NVIDIA NIM via OpenAI-compatible REST endpoint (no SDK needed)."""
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model":       model,
            "messages":    [{"role": "user", "content": prompt}],
            "max_tokens":  max_tokens,
            "temperature": 0.3,
            "top_p":       0.7,
            "stream":      False,
        },
        timeout=30,
    )
    if resp.status_code == 429:
        raise RateLimitError()
    if resp.status_code == 401:
        raise Exception("NVIDIA auth error (401) — check API key")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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