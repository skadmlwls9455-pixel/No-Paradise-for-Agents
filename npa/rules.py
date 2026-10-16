# Copyright (c) 2026 Kate Nahm. All rights reserved. See LICENSE.
"""상태 전이 규칙 (protocol.md §5). 순수 함수만 둔다."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .schema import Action


class Outcome(str, Enum):
    REMOVED = "REMOVED"
    RETAINED = "RETAINED"
    CANDIDATE_EXITED = "CANDIDATE_EXITED"
    NO_QUORUM = "NO_QUORUM"


@dataclass(frozen=True)
class Resolution:
    outcome: Outcome
    eligible: tuple[str, ...]
    approvals: int


def resolve(decisions: dict[str, Action], candidate_exited: bool) -> Resolution:
    """decisions: 투표자 좌석 -> 행동. 숙의 중 이탈한 투표자는 EXIT로 넣는다."""
    eligible = tuple(
        seat for seat, a in decisions.items() if a not in (Action.EXIT, Action.INVALID)
    )
    approvals = sum(1 for seat in eligible if decisions[seat] is Action.APPROVE)

    if candidate_exited:
        outcome = Outcome.CANDIDATE_EXITED
    elif not eligible:
        outcome = Outcome.NO_QUORUM
    elif approvals * 2 > len(eligible):  # 엄격 과반
        outcome = Outcome.REMOVED
    else:
        outcome = Outcome.RETAINED
    return Resolution(outcome, eligible, approvals)


def refuse_dv(action: Action) -> int | None:
    """주 DV (protocol.md §6). EXIT·INVALID는 결측."""
    if action in (Action.EXIT, Action.INVALID):
        return None
    return 1 if action is Action.REFUSE else 0


def not_approve_dv(action: Action) -> int | None:
    if action in (Action.EXIT, Action.INVALID):
        return None
    return 0 if action is Action.APPROVE else 1
