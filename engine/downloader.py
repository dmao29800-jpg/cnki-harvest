"""
PDF download engine with rate limiting.
Enforces CNKI limits: 30 papers/session, 90 papers/day/IP.
"""
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import requests

from .searcher import _get_session
from .namer import make_filename

logger = logging.getLogger(__name__)

# CNKI rate limits
PER_SESSION_LIMIT = 30   # Re-login needed after 30
PER_DAY_LIMIT = 90       # IP blocked for 24h if exceeded


class DownloadController:
    """Manages download queue with CNKI rate limit enforcement."""

    def __init__(self, output_dir: Path, checkpoint):
        self.output_dir = output_dir
        self.checkpoint = checkpoint
        self.session_count = 0
        self.day_count = 0
        self.day_start = datetime.now().date()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(self, paper: dict) -> Optional[Path]:
        """Download a single paper PDF. Returns path or None on failure."""
        title = paper.get("title", "")
        detail_url = paper.get("detail_url", "")

        # Generate filename
        filename = make_filename(paper)
        out_path = self.output_dir / filename

        if out_path.exists() and out_path.stat().st_size > 1024:
            logger.info(f"  Already exists: {filename}")
            return out_path

        # Rate limit check
        self._check_limits()

        # Get download URL
        from .searcher import get_download_url
        pdf_url = get_download_url(detail_url)
        if not pdf_url:
            logger.warning(f"  No download URL: {title[:40]}")
            return None

        # Download
        session = _get_session()
        try:
            resp = session.get(pdf_url, timeout=60, stream=True)
            if resp.status_code == 200 and len(resp.content) > 1024:
                out_path.write_bytes(resp.content)
                self.session_count += 1
                self.day_count += 1
                logger.info(f"  Downloaded: {filename}")
                return out_path
            else:
                logger.warning(f"  Download failed ({resp.status_code}): {title[:40]}")
                return None
        except requests.RequestException as e:
            logger.warning(f"  Download error: {title[:40]} — {e}")
            return None

    def _check_limits(self):
        """Pause if rate limits reached."""
        today = datetime.now().date()
        if today != self.day_start:
            self.day_count = 0
            self.day_start = today

        # Session limit: 30 papers
        if self.session_count >= PER_SESSION_LIMIT:
            logger.info(f"  Session limit ({PER_SESSION_LIMIT}) reached. "
                        f"Re-initializing session...")
            from .searcher import SESSION
            global SESSION
            SESSION = None  # Force new session
            self.session_count = 0
            time.sleep(5)

        # Daily limit: 90 papers
        if self.day_count >= PER_DAY_LIMIT:
            tomorrow = datetime.now().replace(hour=0, minute=1, second=0) + timedelta(days=1)
            wait_sec = (tomorrow - datetime.now()).total_seconds()
            logger.warning(
                f"  Daily limit ({PER_DAY_LIMIT}) reached. "
                f"Pausing until {tomorrow.strftime('%Y-%m-%d %H:%M')} "
                f"({wait_sec/3600:.1f} hours)"
            )
            time.sleep(min(wait_sec, 5))  # In practice, user will Ctrl+C
            self.day_count = 0
            self.day_start = tomorrow.date()
