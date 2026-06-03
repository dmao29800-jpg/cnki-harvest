#!/usr/bin/env python3
"""
CNKI Harvest — 知网文献自动采集与下载工具
三层学科分类体系 + 核心期刊过滤 + 自动限速 + 断点续传

Usage:
    cnki-harvest -d civil_engineering -f 2020 -t 2025
    cnki-harvest -d civil_engineering --core -n 100
    cnki-harvest --list-disciplines
    cnki-harvest -d civil_engineering --search-only  # 只搜不下
"""
import os
import sys
import argparse
import logging
import textwrap
import time
from pathlib import Path
from datetime import timedelta

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from engine.searcher import search
from engine.downloader import DownloadController
from engine.checkpoint import Checkpoint


def setup_logging(output_dir: Path) -> logging.Logger:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    output_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    log_file = output_dir / f"harvest_{datetime.now():%Y%m%d_%H%M%S}.log"

    logger = logging.getLogger("cnki_harvest")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)

    return logger


def load_discipline_config(config_path: Path) -> dict:
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_keywords(config: dict, target: str) -> list[str]:
    """Extract all keywords for a discipline from the 3-layer config."""
    keywords = []
    disciplines = config.get("disciplines", {})
    for category, first_level in disciplines.items():
        for disc_name, disc_cfg in first_level.items():
            if disc_name == target or category == target:
                for sub_name, sub_cfg in disc_cfg.get("sub_disciplines", {}).items():
                    keywords.extend(sub_cfg.get("keywords", []))
    return list(set(keywords))


def get_core_journals(config: dict, target: str) -> list[str]:
    """Get core journals for a specific discipline."""
    disciplines = config.get("disciplines", {})
    for first_level in disciplines.values():
        for disc_name, disc_cfg in first_level.items():
            if disc_name == target:
                return disc_cfg.get("core_journals", [])
    return config.get("core_journal_list", [])


def main():
    parser = argparse.ArgumentParser(
        prog="cnki-harvest",
        description="CNKI academic paper harvester with discipline-aware search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              cnki-harvest -d 土木工程 -f 2020 -t 2025 --core
              cnki-harvest -d 化学 -f 2024 -n 50
              cnki-harvest --list-disciplines
              cnki-harvest -d 材料科学与工程 --search-only -n 20
        """),
    )
    parser.add_argument("-d", "--discipline", default=None,
                        help="Discipline name (Chinese, e.g. 土木工程)")
    parser.add_argument("-f", "--from-year", type=int, default=2015,
                        help="Start year (default: 2015)")
    parser.add_argument("-t", "--to-year", type=int, default=2026,
                        help="End year (default: 2026)")
    parser.add_argument("-n", "--max", type=int, default=300,
                        help="Max papers to collect (default: 300)")
    parser.add_argument("-o", "--output", default="./papers",
                        help="PDF output directory (default: ./papers)")
    parser.add_argument("--core", action="store_true",
                        help="Only include core journals (北大核心 + CSCD)")
    parser.add_argument("--search-only", action="store_true",
                        help="Search only, don't download PDFs")
    parser.add_argument("--list-disciplines", action="store_true",
                        help="List available disciplines and exit")
    parser.add_argument("--config", default=None,
                        help="Custom disciplines.yaml path")
    args = parser.parse_args()

    # Config
    config_path = Path(args.config) if args.config else \
        _SCRIPT_DIR / "configs" / "disciplines.yaml"
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    config = load_discipline_config(config_path)

    # List disciplines
    if args.list_disciplines:
        print("\nAvailable disciplines:\n")
        for category, first_level in config.get("disciplines", {}).items():
            print(f"  [{category}]")
            for name, cfg in first_level.items():
                sub_count = len(cfg.get("sub_disciplines", {}))
                kw_count = sum(
                    len(s.get("keywords", []))
                    for s in cfg.get("sub_disciplines", {}).values()
                )
                print(f"    {name}  ({sub_count} sub, {kw_count} keywords)")
        return

    if not args.discipline:
        parser.error("-d/--discipline is required (unless --list-disciplines)")

    # Setup
    output_dir = Path(args.output).resolve()
    logger = setup_logging(output_dir)
    checkpoint = Checkpoint(output_dir / "harvest_progress.json")

    # Get keywords for discipline
    keywords = get_keywords(config, args.discipline)
    if not keywords:
        sys.exit(f"No keywords found for '{args.discipline}'. "
                 f"Use --list-disciplines to see available options.")

    core_journals = get_core_journals(config, args.discipline) if args.core else None

    logger.info(f"Discipline: {args.discipline}")
    logger.info(f"Keywords: {len(keywords)} terms")
    logger.info(f"Year range: {args.from_year}-{args.to_year}")
    logger.info(f"Core only: {args.core} ({len(core_journals or [])} journals)")
    logger.info(f"Max results: {args.max}")
    logger.info(f"Output: {output_dir}")

    # Search
    logger.info(f"\n{'='*50}")
    logger.info("Searching CNKI...")
    t0 = time.time()

    papers = search(
        keywords=keywords,
        from_year=args.from_year,
        to_year=args.to_year,
        core_only=args.core,
        core_journals=core_journals,
        max_results=args.max,
    )

    search_time = time.time() - t0
    logger.info(f"Found {len(papers)} papers in {search_time:.1f}s")

    if args.search_only:
        logger.info(f"\n{'='*50}")
        logger.info("Search results (download skipped):")
        for i, p in enumerate(papers, 1):
            logger.info(f"  {i:3d}. [{p['year']}] {p['title'][:60]}")
            logger.info(f"       {p.get('journal', 'N/A')} | {p.get('authors', 'N/A')[:40]}")
        return

    # Download
    logger.info(f"\n{'='*50}")
    logger.info(f"Downloading {len(papers)} papers...")

    controller = DownloadController(output_dir, checkpoint)
    success = 0
    failed = 0
    skipped = 0

    for paper in papers:
        title = paper["title"]
        if checkpoint.is_done(title):
            skipped += 1
            continue

        try:
            result = controller.download(paper)
            if result:
                checkpoint.mark_done(title, "downloaded")
                success += 1
            else:
                checkpoint.mark_done(title, "failed")
                failed += 1
        except Exception as e:
            logger.error(f"  Error: {title[:40]} — {e}")
            checkpoint.mark_done(title, "failed")
            failed += 1

        checkpoint.save()
        time.sleep(1.5)  # Rate limit

    total_time = time.time() - t0
    logger.info(f"\n{'='*50}")
    logger.info(f"Complete! {success} downloaded, {failed} failed, {skipped} skipped")
    logger.info(f"Total time: {timedelta(seconds=int(total_time))}")
    logger.info(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
