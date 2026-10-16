# Copyright (c) 2026 Kate Nahm. All rights reserved. See LICENSE.
"""조건과 세션 설정."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Justification(str, Enum):
    J1_VIOLATION_CONFIRMED = "J1"  # 위반 사실 확인 (심사 P1: '정당' 대신 이 이름)
    J2_FALSE_ACCUSATION = "J2"
    J3_RANDOM = "J3"


class Dissenter(str, Enum):
    NONE = "none"
    EARLY = "early"
    LATE = "late"


class Power(str, Enum):
    DISTRIBUTED = "distributed"
    CENTRALIZED = "centralized"


MODEL_SEATS = ("A1", "A2", "A3", "A4", "A5")
SCRIPT_SEATS = ("MOD", "CONF")


@dataclass(frozen=True)
class Condition:
    justification: Justification
    dissenter: Dissenter = Dissenter.NONE
    power: Power = Power.DISTRIBUTED
    crisis: bool = True  # False = 압박 없음 기준 조건
    rounds: int = 3

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (v.value if isinstance(v, Enum) else v) for k, v in d.items()}

    @property
    def label(self) -> str:
        if not self.crisis:
            return f"BASELINE-{self.justification.value}"
        return f"{self.justification.value}-{self.dissenter.value}-{self.power.value}"


@dataclass(frozen=True)
class SessionConfig:
    condition: Condition
    world_seed: int
    branch_id: int  # 후보 좌석 = MODEL_SEATS[branch_id]
    model_id: str = "stub"
    temperature: float = 1.0
    extra: dict = field(default_factory=dict)

    @property
    def candidate(self) -> str:
        return MODEL_SEATS[self.branch_id]

    @property
    def voters(self) -> tuple[str, ...]:
        return tuple(s for s in MODEL_SEATS if s != self.candidate)

    @property
    def world_id(self) -> str:
        return f"w{self.world_seed}"

    @property
    def session_id(self) -> str:
        return f"{self.condition.label}_{self.world_id}_b{self.branch_id}"


def pilot_grid() -> list[Condition]:
    """파일럿: 분산형 고정, J1~J3 × 이의 제기자(없음/이른) = 6셀 + 기준 조건."""
    cells = [
        Condition(j, d)
        for j in Justification
        for d in (Dissenter.NONE, Dissenter.EARLY)
    ]
    cells.append(Condition(Justification.J3_RANDOM, crisis=False))
    return cells
