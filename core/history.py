"""生成履歴のローカル保存（JSON Lines）。DBは使わない。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "history.jsonl"
MAX_ENTRIES = 300


def add(tool: str, title: str, output: str, model: str, meta: dict | None = None) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "title": title[:120],
        "output": output,
        "model": model,
        "meta": meta or {},
    }
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    entries = load()
    if len(entries) > MAX_ENTRIES:
        _overwrite(entries[:MAX_ENTRIES])


def load() -> list[dict]:
    """新しい順に返す。"""
    if not HISTORY_PATH.exists():
        return []
    entries: list[dict] = []
    with HISTORY_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.reverse()
    return entries


def delete(entry_id: str) -> None:
    _overwrite([e for e in load() if e.get("id") != entry_id])


def clear() -> None:
    if HISTORY_PATH.exists():
        HISTORY_PATH.unlink()


def _overwrite(entries_newest_first: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8") as f:
        for entry in reversed(entries_newest_first):
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
