"""JSONL 이벤트 로거 (protocol.md §8)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class JsonlLogger:
    def __init__(self, path: str | Path | None, common: dict):
        self.path = Path(path) if path else None
        self.common = common
        self.events: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, phase: str, event: str, payload: dict,
            seat: str | None = None, round_: int | None = None) -> None:
        rec = {
            **self.common,
            "phase": phase,
            "round": round_,
            "seat": seat,
            "event": event,
            "payload": payload,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.events.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
