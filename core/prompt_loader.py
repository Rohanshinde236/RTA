"""
core/prompt_loader.py
Loads prompt templates from the prompts/ folder and fills in variables.

Usage:
    from core.prompt_loader import load_prompt

    text = load_prompt("agent2_analyst", region="India", context="...", ...)
"""

import os

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
_cache: dict = {}


def load_prompt(name: str, **kwargs) -> str:
    """
    Load a prompt template from prompts/<name>.txt and fill in variables.

    Args:
        name:   filename without extension, e.g. "agent2_analyst"
        kwargs: variables to substitute into the template

    Returns:
        Filled prompt string ready to send to LLM.

    Raises:
        FileNotFoundError if the prompt file does not exist.
    """
    if name not in _cache:
        path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Prompt file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            _cache[name] = f.read()

    template = _cache[name]

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise KeyError(f"Prompt '{name}' is missing variable: {e}")

    return template


def clear_cache():
    """Clear the in-memory prompt cache (useful after editing prompt files)."""
    _cache.clear()
