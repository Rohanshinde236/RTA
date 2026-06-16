"""
dashboard/cms_collector.py
Pure CMS scraper — no business logic, no move decisions.

Responsibility:
  - Open CMS.html in Playwright
  - Select skill from dropdown
  - Read agent table raw
  - Return list of raw agent dicts

All move/hold/ask decisions are made by LLM in agent2_analyst.py
"""

import logging
import os
import sys
import threading
import queue as queue_mod

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger(__name__)


def parse_time_seconds(time_str: str) -> int:
    """Convert MM:SS or H:MM:SS to total seconds."""
    if not time_str or time_str in ('—', '-', ''):
        return 0
    parts = time_str.strip().split(':')
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0


def _is_asyncio_running() -> bool:
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        return loop.is_running()
    except Exception:
        return False


class CMSCollector:
    """
    Pure Playwright scraper for CMS.html.
    Returns raw agent data only — no business logic.
    """

    def __init__(self, cms_path: str = None):
        self.cms_path    = cms_path
        self._use_thread = False
        self._req_queue  = None
        self._bg_thread  = None
        self.browser     = None
        self.page        = None
        self._pw         = None
        self._init_playwright()

    def _init_playwright(self):
        # Always use background thread.
        # sync_playwright() raises inside eventlet/asyncio (used by Flask-SocketIO),
        # and _is_asyncio_running() was unreliable across threads — some regions
        # fell through to sync mode and got "page not initialized". BG thread is safe everywhere.
        self._use_thread = True
        self._start_bg_thread()

    def _init_sync(self):
        try:
            from playwright.sync_api import sync_playwright
            self._pw     = sync_playwright().start()
            self.browser = self._pw.chromium.launch(headless=True)
            self.page    = self.browser.new_page()
            logger.info("CMSCollector: Playwright initialized (sync).")
        except Exception as e:
            logger.error(f"CMSCollector: sync init failed: {e}")

    def _start_bg_thread(self):
        """Start background Playwright thread and wait for it to be ready."""
        self._req_queue = queue_mod.Queue()
        self._bg_thread = threading.Thread(
            target=self._bg_worker,
            name="CMS-Playwright-BG",
            daemon=True
        )
        self._bg_thread.start()
        try:
            ready = self._req_queue.get(timeout=45)
            if ready == "READY":
                logger.info("CMSCollector: background thread ready.")
            else:
                logger.error("CMSCollector: background thread failed to start.")
                self._use_thread = False
        except queue_mod.Empty:
            logger.error("CMSCollector: background thread timed out on startup.")
            self._use_thread = False

    def _bg_worker(self):
        """
        Background thread worker.
        Processes skill scrape requests from queue.
        Only accepts tuples of (skill_name, result_queue).
        """
        try:
            from playwright.sync_api import sync_playwright
            pw      = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            page    = browser.new_page()
            logger.info("CMSCollector: Playwright initialized (background thread).")
            # Signal ready
            self._req_queue.put("READY")
        except Exception as e:
            logger.error(f"CMSCollector BG: init failed: {e}")
            self._req_queue.put("READY")
            return

        url = self._get_url()
        # Open CMS page once
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # Wait for skill-select dropdown to be ready before accepting requests
            try:
                page.wait_for_selector('#skill-select', timeout=10000)
                logger.info(f"CMSCollector: opened {url} — skill-select ready")
            except Exception:
                logger.warning("CMSCollector: skill-select not found after page load — continuing anyway")
        except Exception as e:
            logger.error(f"CMSCollector BG: failed to open {url}: {e}")

        while True:
            try:
                item = self._req_queue.get(timeout=120)
            except queue_mod.Empty:
                continue

            # ── Stop signal ───────────────────────────────────────────────────
            if item == "STOP":
                try:
                    browser.close()
                    pw.stop()
                except Exception:
                    pass
                break

            # ── Startup handshake echo ────────────────────────────────────────
            # Race: BG thread puts "READY" then races through page.goto() and
            # enters this loop before _start_bg_thread consumes "READY" from the
            # shared queue. Safe to discard — _start_bg_thread will time out on
            # its own .get() but the thread is running fine.
            if item == "READY":
                continue

            # ── Validate item format ──────────────────────────────────────────
            # Must be a tuple of exactly (skill_name: str, result_q: Queue)
            if not isinstance(item, tuple) or len(item) != 2:
                logger.warning(
                    f"CMSCollector BG: unexpected item in queue "
                    f"(type={type(item)}, len={len(item) if isinstance(item, tuple) else 'N/A'}) — skipping"
                )
                continue

            skill_name, result_q = item

            # Validate result_q is actually a Queue
            if not isinstance(result_q, queue_mod.Queue):
                logger.warning(
                    f"CMSCollector BG: result_q is not a Queue (got {type(result_q)}) — skipping"
                )
                continue

            # ── Scrape ────────────────────────────────────────────────────────
            try:
                agents = self._scrape(page, skill_name)
                result_q.put(("ok", agents))
            except Exception as e:
                logger.error(
                    f"CMSCollector BG: scrape error for {skill_name}: {e}"
                )
                result_q.put(("err", []))

    def _get_url(self) -> str:
        path = self.cms_path or os.getenv("CMS_DASHBOARD_PATH", "")
        if path and os.path.isfile(path):
            return "file:///" + path.replace("\\", "/")
        default = os.path.join(_ROOT, "ui", "CMS.html")
        return "file:///" + default.replace("\\", "/")

    def _scrape(self, page, skill_name: str) -> list:
        """
        Scrape raw agent data for a skill.
        Returns list of dicts with raw values only.
        """
        try:
            # Wait for selector to be ready before selecting
            page.wait_for_selector('#skill-select', timeout=8000)
            # Set value + explicitly call render() in one atomic JS call.
            # Avoids two failure modes with select_option + change event:
            #   1. Same skill selected twice → change event doesn't fire → stale tbody
            #   2. Event fires but 600ms static wait races against JS execution
            page.evaluate(
                "(skillName) => { "
                "  document.getElementById('skill-select').value = skillName; "
                "  if (typeof render === 'function') render(); "
                "}",
                skill_name
            )
            page.wait_for_timeout(300)
        except Exception as e:
            logger.warning(f"CMSCollector: skill select failed for {skill_name} — reloading page: {e}")
            try:
                page.goto(self._get_url(), wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector('#skill-select', timeout=8000)
                page.evaluate(
                    "(skillName) => { "
                    "  document.getElementById('skill-select').value = skillName; "
                    "  if (typeof render === 'function') render(); "
                    "}",
                    skill_name
                )
                page.wait_for_timeout(300)
            except Exception as e2:
                logger.error(f"CMSCollector: skill select failed after reload for {skill_name}: {e2}")
                return []

        try:
            agents = page.evaluate("""() => {
                const rows = document.querySelectorAll('#agent-tbody tr');
                const result = [];
                rows.forEach(tr => {
                    const cells = tr.querySelectorAll('td');
                    if (cells.length >= 9) {
                        result.push({
                            name:       cells[0].innerText.trim(),
                            login_id:   cells[1].innerText.trim(),
                            role:       cells[2].innerText.trim(),
                            aux_reason: cells[3].innerText.trim(),
                            state:      cells[4].innerText.trim(),
                            direction:  cells[5].innerText.trim(),
                            skill:      cells[6].innerText.trim(),
                            level:      cells[7].innerText.trim(),
                            time:       cells[8].innerText.trim(),
                        });
                    }
                });
                return result;
            }""")
        except Exception as e:
            logger.error(f"CMSCollector: JS evaluate failed for {skill_name}: {e}")
            return []

        # Enrich with time in seconds/minutes — no business logic
        enriched = []
        for a in agents:
            a['time_seconds'] = parse_time_seconds(a.get('time', '0:00'))
            a['time_minutes'] = round(a['time_seconds'] / 60, 1)
            enriched.append(a)

        logger.info(
            f"CMSCollector: {len(enriched)} agents for {skill_name} (bg thread)"
        )
        return enriched

    def _restart_bg_thread(self):
        """Restart background thread if it crashed."""
        logger.warning("CMSCollector: restarting background thread...")
        self._req_queue = queue_mod.Queue()
        self._bg_thread = threading.Thread(
            target=self._bg_worker,
            name="CMS-Playwright-BG",
            daemon=True
        )
        self._bg_thread.start()
        try:
            ready = self._req_queue.get(timeout=45)
            if ready == "READY":
                logger.info("CMSCollector: background thread restarted successfully.")
                return True
        except queue_mod.Empty:
            pass
        logger.error("CMSCollector: background thread restart failed.")
        return False

    def collect(self, skill_name: str) -> list:
        """Public method — collect raw agent data for a skill."""
        if self._use_thread:
            # Check if BG thread is alive — restart if crashed
            if not self._bg_thread or not self._bg_thread.is_alive():
                logger.warning(
                    f"CMSCollector: BG thread dead — attempting restart..."
                )
                if not self._restart_bg_thread():
                    logger.error(
                        "CMSCollector: restart failed — returning empty."
                    )
                    return []

            result_q = queue_mod.Queue()
            self._req_queue.put((skill_name, result_q))
            try:
                status, agents = result_q.get(timeout=20)
                if status == "ok":
                    return agents
                return []
            except queue_mod.Empty:
                logger.error(
                    f"CMSCollector: BG thread timeout for {skill_name}"
                )
                return []
        else:
            # Sync mode
            if not self.page:
                logger.error("CMSCollector: page not initialized.")
                return []
            try:
                return self._scrape(self.page, skill_name)
            except Exception as e:
                logger.error(
                    f"CMSCollector: collect error for {skill_name}: {e}"
                )
                return []

    def cleanup(self):
        if self._use_thread and self._req_queue:
            try:
                self._req_queue.put("STOP")
                if self._bg_thread:
                    self._bg_thread.join(timeout=5)
            except Exception:
                pass
        else:
            try:
                if self.browser:
                    self.browser.close()
                if self._pw:
                    self._pw.stop()
            except Exception as e:
                logger.warning(f"CMSCollector: cleanup error: {e}")
        logger.info("CMSCollector: browser closed.")