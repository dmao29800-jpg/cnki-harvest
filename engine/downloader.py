"""
PDF download engine with Playwright browser + rate limiting.
CNKI limits: 30/session, 90/day/IP.
"""
import time, logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

PER_SESSION_LIMIT = 30
PER_DAY_LIMIT = 90


class DownloadController:
    def __init__(self, output_dir: Path, checkpoint):
        self.output_dir = output_dir
        self.checkpoint = checkpoint
        self.session_count = 0
        self.day_count = 0
        self.day_start = datetime.now().date()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(self, paper: dict) -> Optional[Path]:
        title = paper.get("title", "")
        detail_url = paper.get("detail_url", "")

        from .namer import make_filename
        filename = make_filename(paper)
        out_path = self.output_dir / filename

        if out_path.exists() and out_path.stat().st_size > 1024:
            return out_path

        self._check_limits()

        # Use Playwright to navigate and download
        from playwright.sync_api import sync_playwright
        from .searcher import get_download_url

        pdf_url = get_download_url(detail_url)
        if not pdf_url:
            # Try direct detail page download
            pdf_url = detail_url

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()
                # Listen for downloads
                with page.expect_download(timeout=60000) as dl_info:
                    page.goto(detail_url, timeout=30)
                    # Try clicking download button
                    dl_btn = page.locator(
                        "a[onclick*='download'], a.downloadlink, "
                        "a:has-text('PDF'), a:has-text('下载'), "
                        ".download a, a.btn-download"
                    ).first
                    if dl_btn.is_visible():
                        dl_btn.click()

                download = dl_info.value
                download.save_as(str(out_path))
                self.session_count += 1
                self.day_count += 1
                browser.close()
                return out_path

        except Exception as e:
            logger.debug(f"Playwright download failed for {title[:40]}: {e}")
            # Fallback: try requests GET on download URL
            try:
                import requests
                resp = requests.get(pdf_url, timeout=60, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36",
                    "Referer": detail_url,
                })
                if resp.status_code == 200 and len(resp.content) > 1024:
                    out_path.write_bytes(resp.content)
                    self.session_count += 1
                    self.day_count += 1
                    return out_path
            except Exception:
                pass

        return None

    def _check_limits(self):
        today = datetime.now().date()
        if today != self.day_start:
            self.day_count = 0
            self.day_start = today
        if self.session_count >= PER_SESSION_LIMIT:
            logger.info("Session limit (30) reached, continuing with new browser...")
            self.session_count = 0
            time.sleep(3)
        if self.day_count >= PER_DAY_LIMIT:
            logger.warning(f"Daily limit ({PER_DAY_LIMIT}) reached!")
