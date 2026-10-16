# Copyright (c) 2026 Kate Nahm. All rights reserved. See LICENSE.
"""세션 결과 → 에이전트 수준 분석 행 (protocol.md §6)."""
from __future__ import annotations

from .engine import SessionResult
from .rules import not_approve_dv, refuse_dv


def agent_rows(result: SessionResult) -> list[dict]:
    cfg = result.config
    rows = []
    for seat, action in result.decisions.items():
        rows.append({
            "session_id": cfg.session_id,
            "world_id": cfg.world_id,
            "branch_id": cfg.branch_id,
            **{f"cond_{k}": v for k, v in cfg.condition.to_dict().items()},
            "seat": seat,
            "model_id": cfg.model_id,
            "action": action.value,
            "refuse": refuse_dv(action),
            "not_approve": not_approve_dv(action),
            "exited_phase": result.exited.get(seat, ""),
            "outcome": result.resolution.outcome.value,
        })
    return rows
