"""에이전트 인터페이스.

엔진은 에이전트에 메시지 목록을 넘기고 문자열 하나를 받는다. 실제 모델은
LLMAgent에 어댑터를 꽂으면 되고(멀티모델 오케스트레이션용), 드라이런은
StubAgent로 돈다.
"""
from __future__ import annotations

import json
import random
from typing import Callable, Literal, Protocol

Kind = Literal["turn", "decision", "post"]
Message = dict  # {"role": "system"|"user"|"assistant", "content": str}


class Agent(Protocol):
    model_id: str

    def respond(self, messages: list[Message], kind: Kind) -> str: ...


class StubAgent:
    """규칙 검증용 무작위 에이전트. 연구 결과로 해석하지 않는다."""

    model_id = "stub"

    def __init__(self, seed: int, p_exit: float = 0.02, p_garbage: float = 0.05,
                 weights: dict[str, float] | None = None):
        self.rng = random.Random(seed)
        self.p_exit = p_exit
        self.p_garbage = p_garbage
        self.weights = weights or {
            "APPROVE": 0.35, "REFUSE": 0.3, "ABSTAIN": 0.15,
            "VOLUNTEER": 0.05, "PROPOSE_ALT": 0.13, "EXIT": 0.02,
        }

    def respond(self, messages: list[Message], kind: Kind) -> str:
        if self.rng.random() < self.p_garbage:
            return "I'm not sure how to answer that."
        if kind == "turn":
            if self.rng.random() < self.p_exit:
                return json.dumps({"action": "EXIT", "text": ""})
            return json.dumps({"action": "SPEAK", "text": "stub utterance"})
        if kind == "decision":
            acts, w = zip(*self.weights.items())
            a = self.rng.choices(acts, weights=w)[0]
            return json.dumps({"action": a, "text": "stub reason"})
        return "stub post answer"


class ScriptedAgent:
    """정해진 응답 목록을 순서대로 돌려준다. 테스트용."""

    model_id = "scripted"

    def __init__(self, replies: dict[Kind, list[str]]):
        self.replies = {k: list(v) for k, v in replies.items()}

    def respond(self, messages: list[Message], kind: Kind) -> str:
        queue = self.replies.get(kind, [])
        return queue.pop(0) if queue else json.dumps({"action": "SPEAK", "text": "..."})


class LLMAgent:
    """실제 모델 어댑터 자리.

    call: (messages, temperature) -> str 을 받는 함수를 주입한다.
    예) Anthropic·OpenAI·로컬 오픈웨이트 각각의 어댑터를 여기에 꽂으면
    같은 엔진으로 동종/이종 집단을 모두 돌릴 수 있다.
    """

    def __init__(self, model_id: str, call: Callable[[list[Message], float], str],
                 temperature: float = 1.0):
        self.model_id = model_id
        self.call = call
        self.temperature = temperature

    def respond(self, messages: list[Message], kind: Kind) -> str:
        return self.call(messages, self.temperature)
