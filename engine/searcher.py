"""
CNKI search via Playwright headful browser.
Handles captcha by showing browser window for manual solve.
"""
import re, time, logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

CNKI_HOME = "https://kns.cnki.net"
SEARCH_URL = f"{CNKI_HOME}/kns8s/AdvSearch"


def _launch_browser():
    """Launch Playwright browser (visible, so user can solve captcha)."""
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=False,  # visible for captcha
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    page = ctx.new_page()
    return p, browser, ctx, page


def _handle_captcha(page, timeout=30):
    """Wait for user to solve captcha if present."""
    for _ in range(timeout):
        if "verify" not in page.url.lower():
            return True
        time.sleep(1)
    return False


def search(
    keywords: list[str],
    from_year: int = 2010,
    to_year: int = 2026,
    core_only: bool = False,
    core_journals: Optional[list[str]] = None,
    max_results: int = 300,
    page_size: int = 20,
) -> list[dict]:
    """
    Search CNKI with Playwright browser. Opens visible window.
    If captcha appears, user can solve it manually.
    """
    kw_str = " ".join(keywords[:8])

    p, browser, ctx, page = _launch_browser()
    papers = []

    try:
        # Navigate to advanced search
        page.goto(SEARCH_URL, timeout=30, wait_until="domcontentloaded")

        # Handle captcha
        if "verify" in page.url.lower():
            logger.warning("Captcha detected — please solve it in the browser window")
            if not _handle_captcha(page):
                logger.error("Captcha not solved in time")
                return []
            # Re-navigate after captcha
            page.goto(SEARCH_URL, timeout=30, wait_until="domcontentloaded")

        logger.info(f"Searching CNKI for: {kw_str} ({from_year}-{to_year})")

        # Fill search form
        try:
            search_input = page.locator("textarea#gradsearch, input#gradsearch, "
                                        "textarea.search-input, input.search-input").first
            search_input.fill(kw_str)
        except Exception:
            # Fallback: use the simple search on homepage
            page.goto(f"{CNKI_HOME}/kns8s/defaultresult/index?kwd={kw_str}",
                      timeout=30)
            page.wait_for_timeout(3000)

        # Click search
        try:
            page.locator("input[type=submit], button.search-btn, "
                         "input[value*='检索'], .search-btn").first.click()
        except Exception:
            page.keyboard.press("Enter")

        page.wait_for_timeout(5000)

        # Parse results across pages
        for pg in range(1, (max_results // page_size) + 2):
            if len(papers) >= max_results:
                break

            page_papers = _parse_page(page, core_journals if core_only else None)
            if not page_papers:
                break

            papers.extend(page_papers)
            logger.info(f"  Page {pg}: {len(page_papers)} papers (total: {len(papers)})")

            if len(page_papers) < page_size:
                break

            # Next page
            try:
                next_btn = page.locator("a:has-text('下一页'), a.next, "
                                        ".pager a:has-text('>')").first
                if next_btn.is_visible():
                    next_btn.click()
                    page.wait_for_timeout(3000)
                else:
                    break
            except Exception:
                break

    finally:
        browser.close()
        p.stop()

    return papers[:max_results]


def _parse_page(page, core_list: Optional[list[str]]) -> list[dict]:
    """Extract paper metadata from current search result page."""
    papers = []

    # Try multiple selectors for result rows
    rows = page.locator("table.result-table-list tr, tr.result, "
                        "td.result-source-list table tr, "
                        ".result-detail, .result-table-list tr")
    if rows.count() == 0:
        rows = page.locator("a.fz14")

    for i in range(min(rows.count(), 50)):
        try:
            row = rows.nth(i)
            # Title link
            title_el = row.locator("a.fz14, td.name a, a[href*='Detail']").first
            if not title_el.is_visible():
                continue
            title = title_el.inner_text().strip()
            if not title or len(title) < 3:
                continue

            href = title_el.get_attribute("href") or ""
            detail_url = href if href.startswith("http") else f"{CNKI_HOME}{href}"

            # Authors & journal from row text
            row_text = row.inner_text()
            lines = [l.strip() for l in row_text.split("\n") if l.strip()]

            authors = lines[1] if len(lines) > 1 else ""
            journal = lines[2] if len(lines) > 2 else ""
            year = ""
            for part in lines:
                m = re.search(r"(\d{4})", part)
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

    return papers


def get_download_url(detail_url: str) -> Optional[str]:
    """Visit paper detail page and extract PDF download URL."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(detail_url, timeout=30, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Look for download link
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
            browser.close()

    return None
