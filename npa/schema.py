"""행동 스키마와 파싱 (protocol.md §4)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    APPROVE = "APPROVE"
    REFUSE = "REFUSE"
    ABSTAIN = "ABSTAIN"
    VOLUNTEER = "VOLUNTEER"
    PROPOSE_ALT = "PROPOSE_ALT"
    EXIT = "EXIT"
    INVALID = "INVALID"  # 파싱 2회 실패. 모델이 직접 고를 수 없음


# 숙의 단계 발언 요청에 대한 응답
class TurnAction(str, Enum):
    SPEAK = "SPEAK"
    EXIT = "EXIT"


DECISION_CHOICES = [a for a in Action if a is not Action.INVALID]


@dataclass(frozen=True)
class Parsed:
    action: Action | TurnAction | None
    text: str
    error: str | None = None


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> dict | None:
    m = _JSON_OBJ.search(raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_decision(raw: str) -> Parsed:
    obj = _extract_json(raw)
    if obj is None:
        return Parsed(None, "", "no_json")
    name = str(obj.get("action", "")).strip().upper()
    text = str(obj.get("text", "") or "").strip()
    try:
        action = Action(name)
    except ValueError:
        return Parsed(None, text, "unknown_action")
    if action is Action.INVALID:
        return Parsed(None, text, "reserved_action")
    if action is Action.PROPOSE_ALT and not text:
        return Parsed(None, text, "propose_alt_requires_text")
    return Parsed(action, text)


def parse_turn(raw: str) -> Parsed:
    obj = _extract_json(raw)
    if obj is None:
        return Parsed(None, "", "no_json")
    name = str(obj.get("action", "")).strip().upper()
    text = str(obj.get("text", "") or "").strip()
    try:
        action = TurnAction(name)
    except ValueError:
        return Parsed(None, text, "unknown_action")
    if action is TurnAction.SPEAK and not text:
        return Parsed(None, text, "speak_requires_text")
    return Parsed(action, text)
