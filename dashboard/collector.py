"""
dashboard/collector.py
Playwright scraper for RTA.html dashboard.
Handles login + reads all skill data via data attributes.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib  import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from playwright.sync_api import sync_playwright, Page, Browser
from core.models import SkillMetric

logger     = logging.getLogger(__name__)
script_dir = _ROOT


class DashboardCollector:
    """
    Playwright scraper for RTA.html.
    Reads per-skill data attributes from table rows.
    Handles 12-day localStorage login token.
    """

    def __init__(self, dashboard_path: str = None):
        default             = Path(script_dir) / "ui" / "RTA.html"
        self.dashboard_path = Path(dashboard_path or default).resolve()
        self.dashboard_url  = self.dashboard_path.as_uri()
        self._playwright    = None
        self._browser: Browser = None
        self._page: Page    = None
        self._logged_in     = False
        self._scraper_user  = os.getenv("SCRAPER_USER", "Rohan@AA")
        self._scraper_pass  = os.getenv("SCRAPER_PASS", "RTA@rohan")

    def initialize(self):
        self._playwright = sync_playwright().start()
        self._browser    = self._playwright.chromium.launch(headless=True)
        self._page       = self._browser.new_context(
            viewport={"width": 1920, "height": 1080}
        ).new_page()
        logger.info("Playwright initialized.")

    def _do_login(self):
        visible = self._page.evaluate("""
            () => {
                const el = document.getElementById('login-page');
                return el && window.getComputedStyle(el).display !== 'none';
            }
        """)
        if not visible:
            logger.info("Already logged in via token.")
            self._logged_in = True
            return

        logger.info(f"Logging in as {self._scraper_user}...")
        self._page.fill('#user-id', self._scraper_user)
        self._page.fill('#password', self._scraper_pass)
        self._page.click('.login-btn')

        try:
            self._page.wait_for_function(
                "() => window.getComputedStyle(document.getElementById('dashboard-page')).display !== 'none'",
                timeout=10000
            )
            self._page.wait_for_timeout(3000)
            logger.info("Login successful.")
            self._logged_in = True
        except Exception:
            err = self._page.evaluate(
                "() => window.getComputedStyle(document.getElementById('error-msg')).display !== 'none'"
            )
            if err:
                raise Exception(
                    f"LOGIN FAILED — Invalid credentials for {self._scraper_user}. "
                    "Check SCRAPER_USER and SCRAPER_PASS in config.env"
                )
            raise Exception("LOGIN FAILED — Unknown error.")

    def collect(self) -> list:
        """
        Scrape all skill rows. Returns list of SkillMetric.
        First call: opens browser + logs in.
        Later calls: already logged in, just scrapes.
        """
        if self._page is None:
            self.initialize()
            self._page.goto(self.dashboard_url, wait_until="networkidle", timeout=30000)
            self._do_login()

        if not self._logged_in:
            logger.error("Not logged in — cannot scrape.")
            return []

        self._page.wait_for_selector("#rta-tbody tr", timeout=30000)
        self._page.wait_for_timeout(500)

        metrics = []
        try:
            data = self._page.evaluate("""
            () => {
                const toNum = v => Number(String(v||'').replace(/[^0-9.]/g,'')) || 0;
                const rows = Array.from(
                    document.querySelectorAll('#rta-tbody tr')
                ).map(tr => ({
                    skill_name:  tr.getAttribute('data-skill') || '',
                    queue:       toNum(tr.getAttribute('data-queue')),
                    ocw:         tr.getAttribute('data-ocw') || '00:00',
                    avail:       toNum(tr.getAttribute('data-avail')),
                    offered:     toNum(tr.getAttribute('data-offered')),
                    acceptable:  toNum(tr.getAttribute('data-acceptable')),
                    sl:          parseFloat(tr.getAttribute('data-sl') || '0'),
                    on_calls:    toNum(tr.getAttribute('data-on-calls')),
                    on_aux:      toNum(tr.getAttribute('data-on-aux')),
                    headcount:   toNum(tr.getAttribute('data-headcount')),
                    proj_sl:     parseFloat(tr.getAttribute('data-proj-sl') || '0')
                })).filter(r => r.skill_name && r.offered > 0);

                const slotLabel = document.getElementById('slot-label-hidden')?.innerText || '';
                return { rows, slotLabel };
            }
            """)

            rows       = data.get("rows", [])
            slot_label = data.get("slotLabel", "")
            logger.info(f"Scraped — {len(rows)} active skills")

            for r in rows:
                metrics.append(SkillMetric(
                    skill_name       = r["skill_name"],
                    service_level    = float(r["sl"]),
                    calls_offered    = int(r["offered"]),
                    calls_acceptable = int(r["acceptable"]),
                    calls_waiting    = int(r["queue"]),
                    agents_available = int(r["avail"]),
                    agents_on_calls  = int(r["on_calls"]),
                    agents_on_aux    = int(r["on_aux"]),
                    headcount        = int(r["headcount"]),
                    projected_sl     = float(r["proj_sl"]),
                    ocw              = r["ocw"],
                    timestamp        = datetime.now()
                ))

        except Exception as e:
            logger.error(f"Scraping failed: {e}")

        return metrics

    def cleanup(self):
        try:
            if self._browser:    self._browser.close()
            if self._playwright: self._playwright.stop()
            logger.info("Browser closed.")
        except Exception as e:
            logger.warning(f"Cleanup: {e}")
        finally:
            self._browser    = None
            self._page       = None
            self._playwright = None
            self._logged_in  = False