"""
PDF file naming: {年份}_{期刊}_{标题}_{第一作者}.pdf
Matches paper-distill's title extraction convention (rsplit on last _).
"""
import re

# Characters invalid in Windows filenames
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\n\r\t]')
# Strip CNKI suffixes often appended to titles
_CNKI_SUFFIX = re.compile(
    r'[（(](?:全文|摘要|英文|增刊|专刊|特刊|会议|综述|评述|研究进展)[）)]$'
)
# Multiple spaces/underscores
_MULTI_SPACE = re.compile(r'\s+')
_MULTI_UNDERSCORE = re.compile(r'_+')


def make_filename(paper: dict) -> str:
    """
    Generate standardized filename from paper metadata.
    Format: {年份}_{期刊}_{标题}_{第一作者}.pdf
    """
    year = paper.get("year", "0000")
    journal = _clean(paper.get("journal", "unknown"))
    title = _clean(paper.get("title", "untitled"))
    authors = paper.get("authors", "")

    # First author only
    first_author = "佚名"
    if authors:
        # Split by common separators
        names = re.split(r'[,;，；\s]+', authors.strip())
        first_author = names[0] if names else "佚名"

    # Clean title: remove CNKI suffixes, truncate if too long
    title = _CNKI_SUFFIX.sub('', title)
    if len(title) > 80:
        title = title[:80]

    filename = f"{year}_{journal}_{title}_{first_author}.pdf"
    # Ensure no invalid chars
    filename = _INVALID_CHARS.sub('', filename)
    filename = _MULTI_UNDERSCORE.sub('_', filename)

    return filename


def _clean(s: str) -> str:
    """Remove invalid filename characters from a string."""
    s = _INVALID_CHARS.sub('', s)
    s = _MULTI_SPACE.sub(' ', s)
    return s.strip()
