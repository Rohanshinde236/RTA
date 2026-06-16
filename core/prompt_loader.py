"""
core/prompt_loader.py
Loads prompt templates from the prompts/ folder and fills in variables.

Rules are stored in prompts/rules.yaml — edit that file to change chatbot
behaviour without touching any code.  Any prompt template that contains
{rules} gets the rendered rulebook injected automatically.

Usage:
    from core.prompt_loader import load_prompt
    text = load_prompt("chatbot_answer", context="...", question="...")
"""

import os

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
_RULES_PATH  = os.path.join(_PROMPTS_DIR, "rules.yaml")
_cache: dict = {}


def _load_rules() -> str:
    """
    Read rules.yaml and render it as a clean text block for LLM injection.
    Cached after first load — call clear_cache() to reload after editing.
    """
    if "_rules" in _cache:
        return _cache["_rules"]

    if not os.path.exists(_RULES_PATH):
        _cache["_rules"] = ""
        return ""

    try:
        import yaml
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except ImportError:
        # yaml not installed — fall back to raw text injection
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            _cache["_rules"] = f.read()
        return _cache["_rules"]
    except Exception:
        _cache["_rules"] = ""
        return ""

    lines = []

    # Region key
    if "regions" in data:
        lines.append("REGION KEY:")
        for tag, name in data["regions"].items():
            lines.append(f"  {tag} = {name}")
        lines.append("")

    # SLA bands
    if "sla_bands" in data:
        lines.append("SLA BANDS:")
        for band, rng in data["sla_bands"].items():
            lines.append(f"  {band} = {rng}")
        lines.append("")

    # General rules
    if "general_rules" in data:
        lines.append("GENERAL RULES (always follow):")
        for i, rule in enumerate(data["general_rules"], 1):
            lines.append(f"  {i}. {rule}")
        lines.append("")

    # Output formats
    if "output_formats" in data:
        lines.append("OUTPUT FORMAT BY QUESTION TYPE:")
        for fmt_key, fmt in data["output_formats"].items():
            lines.append(f"\n  [{fmt_key.upper().replace('_', ' ')}]")
            lines.append(f"  Triggers: {fmt.get('trigger', '')}")
            lines.append(f"  Format:")
            for fline in fmt.get("format", "").strip().splitlines():
                lines.append(f"    {fline}")

    _cache["_rules"] = "\n".join(lines)
    return _cache["_rules"]


def load_prompt(name: str, **kwargs) -> str:
    """
    Load a prompt template from prompts/<name>.md and fill in variables.
    If the template contains {rules}, the YAML rulebook is injected automatically.

    Args:
        name:   filename without extension, e.g. "chatbot_answer"
        kwargs: variables to substitute into the template

    Returns:
        Filled prompt string ready to send to LLM.
    """
    if name not in _cache:
        path = os.path.join(_PROMPTS_DIR, f"{name}.md")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Prompt file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            _cache[name] = f.read()

    template = _cache[name]

    # Auto-inject rules if template uses {rules} placeholder
    if "{rules}" in template:
        kwargs.setdefault("rules", _load_rules())

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise KeyError(f"Prompt '{name}' is missing variable: {e}")

    return template


def clear_cache():
    """Clear the in-memory prompt cache — call after editing rules.yaml or any .md prompt."""
    _cache.clear()
