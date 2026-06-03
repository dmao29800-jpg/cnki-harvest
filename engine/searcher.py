"""
CNKI advanced search + metadata extraction.
Uses requests + BeautifulSoup against kns.cnki.net.
"""
import re
import time
import logging
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CNKI_BASE = "https://kns.cnki.net"
SEARCH_URL = f"{CNKI_BASE}/kns8s/Brief/Result"

# Session management
SESSION = None


def _get_session() -> requests.Session:
    global SESSION
    if SESSION is None:
        SESSION = requests.Session()
        SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        # Prime the session with a GET to the search page
        try:
            SESSION.get(f"{CNKI_BASE}/kns8s/AdvSearch", timeout=15)
        except Exception:
            pass
    return SESSION


def search(
    keywords: list[str],
    from_year: int = 2010,
    to_year: int = 2026,
    core_only: bool = False,
    core_journals: Optional[list[str]] = None,
    max_results: int = 300,
    page_size: int = 50,
) -> list[dict]:
    """
    Search CNKI and return paper metadata.

    Args:
        keywords: List of Chinese keywords (AND logic within group, OR between groups).
        from_year: Start year.
        to_year: End year.
        core_only: If True, only return papers from core journals.
        core_journals: List of core journal names to filter by.
        max_results: Max papers to return.
        page_size: Results per page (max 50).

    Returns:
        List of dicts with keys: title, authors, journal, year, abstract,
                                 keywords, download_url, detail_url, is_core
    """
    session = _get_session()
    papers = []
    kw_str = " + ".join(keywords[:5])  # CNKI limits keyword length

    for page in range(1, (max_results // page_size) + 2):
        if len(papers) >= max_results:
            break

        params = _build_search_params(kw_str, from_year, to_year, page, page_size)
        try:
            resp = session.post(SEARCH_URL, data=params, timeout=30)
            resp.encoding = "utf-8"
        except requests.RequestException as e:
            logger.error(f"Search failed page {page}: {e}")
            break

        page_papers = _parse_search_results(resp.text, core_journals if core_only else None)
        if not page_papers:
            break

        papers.extend(page_papers)
        logger.info(f"  Page {page}: found {len(page_papers)} papers (total: {len(papers)})")

        if len(page_papers) < page_size:
            break  # last page

        time.sleep(2)  # Be polite to CNKI

    return papers[:max_results]


def _build_search_params(
    kw_str: str, from_year: int, to_year: int, page: int, page_size: int
) -> dict:
    """Build CNKI advanced search POST params."""
    # CNKI's internal search parameter format
    return {
        "boolSearch": "true",
        "QueryJson": str({
            "Platform": "",
            "Resource": "CJFQ,CDFD,CMFD,CPFD",  # Journal, Doctoral, Master, Conference
            "Classid": "YSTT4HG0",
            "SearchType": "Advanced",
            "QNode": {
                "SearchType": 2,
                "SearchNodeList": [{
                    "NodeID": 1,
                    "Field": "SU$%=|''",
                    "Logic": 1,
                    "FieldName": "主题",
                    "SearchType": "2",
                    "KeyType": "keyword",
                    "SearchWord": kw_str,
                    "IsAdvancedSearch": "1",
                }]
            },
            "SearchCondition": [
                {"Field": "CF", "FieldName": "年份", "SearchType": "2",
                 "Logic": "1", "SearchWord": f"{from_year}-{to_year}"}
            ],
            "Page": page,
            "PageSize": page_size,
            "Sort": "RELEVANCE",
        }).replace("'", '"'),
    }


def _parse_search_results(html: str, core_journals: Optional[list[str]]) -> list[dict]:
    """Parse CNKI search result HTML into paper metadata list."""
    soup = BeautifulSoup(html, "html.parser")
    papers = []

    # Find result rows
    rows = soup.select("tr.result, table.result-table tr, .result-item, .result-table-list tr")
    if not rows:
        rows = soup.find_all("tr", attrs={"class": re.compile(r".*result.*|.*list.*")})
    if not rows:
        # Fallback: look for title links
        rows = soup.select("a[href*='Detail'], a.fz14, td.name a")

    for row in rows:
        title_el = row.select_one("a.fz14, a[href*='Detail'], td.name a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        href = title_el.get("href", "")
        detail_url = href if href.startswith("http") else f"{CNKI_BASE}{href}"

        # Extract other fields from nearby cells
        cells = row.find_all("td") if row.name == "tr" else []
        # Authors usually in 2nd cell, journal in 3rd
        authors = ""
        journal = ""
        year = ""
        if len(cells) >= 3:
            authors = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            journal = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        if len(cells) >= 4:
            year_text = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            year_match = re.search(r"(\d{4})", year_text)
            year = year_match.group(1) if year_match else ""

        # Core journal check
        is_core = False
        if core_journals and journal:
            is_core = any(j in journal for j in core_journals)

        papers.append({
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "detail_url": detail_url,
            "is_core": is_core,
        })

    return papers


def get_download_url(detail_url: str) -> Optional[str]:
    """Visit paper detail page and extract PDF download URL."""
    session = _get_session()
    try:
        resp = session.get(detail_url, timeout=20)
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        logger.warning(f"Failed to load detail page: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    # CNKI download links
    patterns = [
        "a[onclick*='download']",
        "a.downloadlink",
        "a[href*='download']",
        "a[href$='.pdf']",
        "a[href*='DownLoad']",
    ]
    for pat in patterns:
        link = soup.select_one(pat)
        if link:
            href = link.get("href", "")
            if href:
                return href if href.startswith("http") else f"{CNKI_BASE}{href}"

    # Try regex fallback
    m = re.search(r'(/kns8[^"\']*?down[^"\']*?\.(?:pdf|aspx)[^"\']*?)', resp.text, re.I)
    if m:
        path = m.group(1)
        return path if path.startswith("http") else f"{CNKI_BASE}{path}"

    return None
