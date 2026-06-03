"""Checkpoint manager for resumable CNKI downloads."""
import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class Checkpoint:
    """Tracks downloaded paper titles to avoid re-download."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
                logger.warning("Corrupt checkpoint, starting fresh")

    def save(self):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False,
            suffix=".json", dir=self.path.parent,
        ) as tmp:
            json.dump(self._data, tmp, ensure_ascii=False, indent=2)
        Path(tmp.name).replace(self.path)

    def is_done(self, title: str) -> bool:
        return title in self._data

    def mark_done(self, title: str, status: str = "downloaded"):
        from datetime import datetime
        self._data[title] = {
            "status": status,
            "time": datetime.now().isoformat(),
        }

    @property
    def count(self) -> int:
        return len(self._data)

    @property
    def stats(self) -> dict:
        return {
            "total": len(self._data),
            "downloaded": sum(1 for v in self._data.values()
                              if v.get("status") == "downloaded"),
            "failed": sum(1 for v in self._data.values()
                          if v.get("status") == "failed"),
        }
