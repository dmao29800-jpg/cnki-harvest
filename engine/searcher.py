"""
CNKI search via Playwright with persistent browser state.
First run: captcha appears → user solves manually → state saved.
Subsequent runs: no captcha (cookies reused).
"""
import re, time, json, logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

CNKI_HOME = "https://kns.cnki.net"
STATE_DIR = Path.home() / ".cnki-harvest"
STATE_FILE = STATE_DIR / "browser_state.json"


def _browser_state():
    """Load saved browser state if exists."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return str(STATE_FILE)
        except Exception:
            pass
    return None


def _save_state(context):
    """Save browser state (cookies, storage) for next session."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        context.storage_state(path=str(STATE_FILE))
    except Exception:
        pass


def search(
    keywords: list[str],
    from_year: int = 2010,
    to_year: int = 2026,
    core_only: bool = False,
    core_journals: Optional[list[str]] = None,
    max_results: int = 300,
    page_size: int = 20,
) -> list[dict]:
    """Search CNKI with Playwright. On first run, user solves captcha in visible browser."""

    from playwright.sync_api import sync_playwright

    kw_str = " ".join(keywords[:6])

    p = sync_playwright().start()
    state_path = _browser_state()

    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )

    context_kwargs = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1280, "height": 800},
    }
    if state_path:
        context_kwargs["storage_state"] = state_path

    ctx = browser.new_context(**context_kwargs)
    page = ctx.new_page()
    papers = []

    try:
        # Use simple search URL — more reliable than advanced search
        from urllib.parse import quote
        search_url = (
            f"{CNKI_HOME}/kns8s/defaultresult/index"
            f"?kwd={quote(kw_str)}"
            f"&dbcode=CJFD"
        )
        page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Handle captcha
        if "verify" in page.url.lower():
            logger.info("Captcha detected — please solve it in the browser window")
            page.locator("body").wait_for(state="visible", timeout=120000)
            # Wait for user to solve captcha (up to 2 min)
            for _ in range(120):
                if "verify" not in page.url.lower():
                    logger.info("Captcha solved!")
                    page.wait_for_timeout(3000)
                    break
                time.sleep(1)
            else:
                logger.error("Captcha not solved, returning empty")
                _save_state(ctx)
                return []

        # Save state after potential captcha solve
        _save_state(ctx)

        # Now we should be on the search results page
        logger.info(f"Searching CNKI for: {kw_str}")

        # Parse results
        for pg in range(1, (max_results // page_size) + 2):
            if len(papers) >= max_results:
                break

            page_papers = _parse_page(page, core_journals if core_only else None)
            papers.extend(page_papers)
            logger.info(f"  Page {pg}: {len(page_papers)} papers (total: {len(papers)})")

            if not page_papers or len(page_papers) < page_size:
                break

            # Next page
            try:
                next_btn = page.locator(
                    "a:has-text('下一页'), .next, .pager a:has-text('>')"
                ).first
                if next_btn.is_visible(timeout=2000):
                    next_btn.click()
                    page.wait_for_timeout(3000)
                else:
                    break
            except Exception:
                break

    finally:
        _save_state(ctx)
        browser.close()
        p.stop()

    return papers[:max_results]


def _parse_page(page, core_list: Optional[list[str]]) -> list[dict]:
    """Extract paper metadata from search results page."""
    papers = []

    # Try multiple approaches
    # Approach 1: CNKI's standard result table
    rows = page.locator("table.result-table-list tr").all()
    if not rows:
        rows = page.locator("tr:has(td.name)").all()

    for row in rows:
        try:
            # Title
            title_el = row.locator("td.name a, a.fz14").first
            title = title_el.inner_text().strip() if title_el.is_visible() else ""
            if not title or len(title) < 3:
                continue

            href = title_el.get_attribute("href") or ""
            detail_url = href if href.startswith("http") else f"{CNKI_HOME}{href}"

            # Get all text cells
            cells = row.locator("td").all()
            cell_texts = [c.inner_text().strip() for c in cells if c.is_visible()]

            authors = cell_texts[1] if len(cell_texts) > 1 else ""
            journal = cell_texts[2] if len(cell_texts) > 2 else ""
            year = ""
            for ct in cell_texts:
                m = re.search(r"(\d{4})", ct)
                if m:
                    year = m.group(1)
                    break

            is_core = any(j in journal for j in core_list) if core_list else False

            papers.append({
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "detail_url": detail_url,
                "is_core": is_core,
            })
        except Exception:
            continue

    # Approach 2: if table rows didn't work, try direct link extraction
    if not papers:
        links = page.locator("a.fz14, td.name a").all()
        for link in links:
            try:
                title = link.inner_text().strip()
                if not title or len(title) < 5:
                    continue
                href = link.get_attribute("href") or ""
                detail_url = href if href.startswith("http") else f"{CNKI_HOME}{href}"
                papers.append({
                    "title": title,
                    "authors": "",
                    "journal": "",
                    "year": "",
                    "detail_url": detail_url,
                    "is_core": False,
                })
            except Exception:
                continue

    return papers


def get_download_url(detail_url: str) -> Optional[str]:
    """Extract PDF download URL from detail page."""
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    state_path = _browser_state()
    context_kwargs = {}
    if state_path:
        context_kwargs["storage_state"] = state_path

    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(**context_kwargs)
    page = ctx.new_page()

    try:
        page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        dl = page.locator(
            "a[onclick*='download'], a.downloadlink, "
            "a[href*='download'], a[href$='.pdf'], "
            "a:has-text('PDF'), a:has-text('下载')"
        ).first
        if dl.is_visible():
            return dl.get_attribute("href") or ""
    except Exception:
        pass
    finally:
        _save_state(ctx)
        browser.close()
        p.stop()

    return None
