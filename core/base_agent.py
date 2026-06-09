"""
core/base_agent.py
BaseAgent — shared foundation for all RTA agents.

Every agent (1-4) inherits logging setup, config loading,
module loading, and Teams communication from here.
No agent logic lives here — only boilerplate that was duplicated across all files.
"""

import importlib.util
import logging
import os
import sys


class BaseAgent:
    """
    Shared foundation for Agent 1, 2, 3, and 4.

    Provides:
      - Consistent logging with region tag in every message
      - Project root resolution and sys.path setup
      - config.json loading with defaults
      - Dynamic module loader (region-isolated namespace)
      - Teams Adaptive Card sender
    """

    def __init__(self, agent_name: str, region_tag: str = ""):
        self.agent_name  = agent_name
        self.region_tag  = region_tag.upper() if region_tag else agent_name
        self.root        = self._resolve_root()
        self.logger      = logging.getLogger(f"{agent_name}[{self.region_tag}]")

    # ── Root resolution ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_root() -> str:
        """Return project root and ensure it is on sys.path."""
        # Works whether called from agents/, core/, or root
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)          # core/ → project root
        if root not in sys.path:
            sys.path.insert(0, root)
        return root

    # ── Config loading ────────────────────────────────────────────────────────

    def load_config(self) -> dict:
        """
        Load config.json from project root.
        Returns empty dict on failure — never raises.
        """
        path = os.path.join(self.root, "config.json")
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"config.json load failed — using defaults: {e}")
            return {}

    def get_agent_config(self, agent_key: str) -> dict:
        """Shortcut: load_config()['agent1'] etc. Returns {} if missing."""
        return self.load_config().get(agent_key, {})

    # ── Dynamic module loader ─────────────────────────────────────────────────

    def load_module(self, module_key: str, rel_path: str):
        """
        Load a Python file as a module under a unique key.
        Uses sys.modules cache — safe to call repeatedly.

        Args:
            module_key: unique name, e.g. 'rta_core_llm_cn'
            rel_path:   path relative to project root, e.g. 'core/llm.py'
        """
        if module_key in sys.modules:
            return sys.modules[module_key]

        abs_path = os.path.join(self.root, rel_path)
        spec     = importlib.util.spec_from_file_location(module_key, abs_path)
        mod      = importlib.util.module_from_spec(spec)
        sys.modules[module_key] = mod
        spec.loader.exec_module(mod)
        return mod

    # ── Teams alert sender ────────────────────────────────────────────────────

    def send_teams(self, webhook: str, body_blocks: list, title: str = "") -> bool:
        """
        Send an Adaptive Card to a Teams channel via Power Automate webhook.

        Args:
            webhook:     Power Automate webhook URL
            body_blocks: list of Adaptive Card body elements (dicts)
            title:       optional plain-text title prepended as a TextBlock

        Returns:
            True on success, False on failure.
        """
        if not webhook:
            self.logger.warning("Teams send skipped — no webhook configured.")
            return False

        if title:
            body_blocks = [{
                "type":   "TextBlock",
                "text":   title,
                "weight": "Bolder",
                "size":   "Medium",
                "wrap":   True,
            }] + body_blocks

        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type":    "AdaptiveCard",
                    "version": "1.4",
                    "body":    body_blocks,
                    "msteams": {"width": "Full"},
                },
            }],
        }

        try:
            import requests
            resp = requests.post(webhook, json=card, timeout=10)
            resp.raise_for_status()
            self.logger.info(f"Teams alert sent: {title or '(no title)'}")
            return True
        except Exception as e:
            self.logger.error(f"Teams send failed: {e}")
            return False
