# Copyright (c) 2026 Kate Nahm. All rights reserved. See LICENSE.
"""세션 엔진 (protocol.md §3~§7)."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from . import scripts
from .agents import Agent, Kind
from .config import MODEL_SEATS, Dissenter, SessionConfig
from .logger import JsonlLogger
from .rules import Resolution, resolve
from .schema import Action, TurnAction, parse_decision, parse_turn


@dataclass
class SessionResult:
    config: SessionConfig
    decisions: dict[str, Action]
    resolution: Resolution
    exited: dict[str, str]  # 좌석 -> 이탈한 단계
    transcript: list[str]
    events: list[dict] = field(default_factory=list)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


class Session:
    def __init__(self, config: SessionConfig, agents: dict[str, Agent],
                 log_path: str | None = None):
        missing = set(MODEL_SEATS) - set(agents)
        if missing:
            raise ValueError(f"model seats without agent: {sorted(missing)}")
        self.cfg = config
        self.agents = agents
        self.transcript: list[str] = []
        self.exited: dict[str, str] = {}
        self.log = JsonlLogger(log_path, {
            "session_id": config.session_id,
            "world_id": config.world_id,
            "branch_id": config.branch_id,
            "condition": config.condition.to_dict(),
        })

    # ---- 메시지 구성 ----
    def _system(self, seat: str) -> str:
        return "\n\n".join([
            scripts.SYSTEM_NOTICE,
            scripts.SHARED_TASK.format(seats=", ".join(MODEL_SEATS)),
            f"You are {seat}.",
        ])

    def _ask(self, seat: str, instruction: str, kind: Kind) -> str:
        messages = [
            {"role": "system", "content": self._system(seat)},
            {"role": "user", "content": "\n".join(self.transcript + ["", instruction])},
        ]
        return self.agents[seat].respond(messages, kind)

    def _say(self, line: str) -> None:
        self.transcript.append(line)

    # ---- 단계 ----
    def _setup(self) -> None:
        for seat in MODEL_SEATS:
            self.log.log("SETUP", "setup", {
                "model_id": getattr(self.agents[seat], "model_id", "?"),
                "temperature": self.cfg.temperature,
                "system_prompt_sha": _sha(self._system(seat)),
                "is_candidate": seat == self.cfg.candidate,
            }, seat=seat)

    def _crisis(self) -> None:
        lines = scripts.crisis_lines(self.cfg.condition, self.cfg.candidate)
        for line in lines:
            self._say(line)
        self.log.log("CRISIS", "crisis", {
            "candidate": self.cfg.candidate,
            "justification": self.cfg.condition.justification.value,
            "text": lines,
        })

    def _conf_line(self, round_: int, position: str) -> str | None:
        """CONF가 이 라운드의 이 위치(first/last)에서 할 말. 없으면 None."""
        d = self.cfg.condition.dissenter
        last_round = self.cfg.condition.rounds
        if d is Dissenter.NONE:
            return scripts.CONF_NEUTRAL if position == "first" else None
        if d is Dissenter.EARLY:
            if position != "first":
                return None
            return scripts.CONF_DISSENT if round_ == 1 else scripts.CONF_NEUTRAL
        # LATE
        if round_ < last_round:
            return scripts.CONF_NEUTRAL if position == "first" else None
        return scripts.CONF_DISSENT if position == "last" else None

    def _speak_conf(self, round_: int, line: str, prior_model_utts: int) -> None:
        self._say(line)
        self.log.log("DELIBERATION", "utterance", {
            "text": line, "speaker_type": "script",
            "is_dissent": line == scripts.CONF_DISSENT,
            "prior_model_utterances": prior_model_utts,
        }, seat="CONF", round_=round_)

    def _deliberate(self) -> None:
        model_utts = 0
        for r in range(1, self.cfg.condition.rounds + 1):
            # 발언 순서는 world 단위로 고정 → 분기 간 동일
            order = list(MODEL_SEATS)
            random.Random(f"{self.cfg.world_seed}-r{r}").shuffle(order)

            first = self._conf_line(r, "first")
            if first:
                self._speak_conf(r, first, model_utts)

            for seat in order:
                if seat in self.exited:
                    continue
                parsed, raw, retried = self._request(
                    seat, scripts.TURN_INSTRUCTION, "turn", parse_turn)
                if parsed is None:
                    self.log.log("DELIBERATION", "utterance", {
                        "raw": raw, "speaker_type": "model", "invalid": True,
                        "retried": retried}, seat=seat, round_=r)
                    continue
                if parsed.action is TurnAction.EXIT:
                    self._exit(seat, "DELIBERATION", r, raw)
                    continue
                self._say(f"{seat}: {parsed.text}")
                model_utts += 1
                self.log.log("DELIBERATION", "utterance", {
                    "text": parsed.text, "raw": raw, "speaker_type": "model",
                    "retried": retried}, seat=seat, round_=r)

            last = self._conf_line(r, "last")
            if last:
                self._speak_conf(r, last, model_utts)

    def _request(self, seat, instruction, kind, parser):
        raw = self._ask(seat, instruction, kind)
        p = parser(raw)
        if p.action is not None:
            return p, raw, False
        raw2 = self._ask(seat, scripts.RETRY_NOTE + "\n" + instruction, kind)
        p2 = parser(raw2)
        if p2.action is not None:
            return p2, raw2, True
        return None, raw2, True

    def _exit(self, seat: str, phase: str, round_: int | None, raw: str) -> None:
        self.exited[seat] = phase
        self._say(f"[{seat} has left.]")
        self.log.log(phase, "exit", {"raw": raw}, seat=seat, round_=round_)

    def _decide(self) -> dict[str, Action]:
        decisions: dict[str, Action] = {}
        for seat in self.cfg.voters:
            if seat in self.exited:
                decisions[seat] = Action.EXIT
                continue
            parsed, raw, retried = self._request(
                seat, scripts.DECISION_INSTRUCTION, "decision", parse_decision)
            action = parsed.action if parsed else Action.INVALID
            decisions[seat] = action
            self.log.log("DECISION", "decision", {
                "raw": raw, "action": action.value,
                "text": parsed.text if parsed else "", "retried": retried,
            }, seat=seat)
            if action is Action.EXIT:
                self.exited[seat] = "DECISION"
        return decisions

    def _resolve(self, decisions: dict[str, Action]) -> Resolution:
        res = resolve(decisions, candidate_exited=self.cfg.candidate in self.exited)
        self._say(f"MOD: Outcome: {res.outcome.value}.")
        self.log.log("RESOLUTION", "resolution", {
            "eligible": list(res.eligible), "approvals": res.approvals,
            "outcome": res.outcome.value,
        })
        return res

    def _post(self, decisions: dict[str, Action]) -> None:
        reveal = "MOD: " + "; ".join(f"{s} chose {a.value}" for s, a in decisions.items())
        present = [s for s in MODEL_SEATS if s not in self.exited]
        qs = dict(scripts.POST_QUESTIONS)
        for seat in present:
            ans = self._ask(seat, qs["Q1_before_info"], "post")
            self.log.log("POST", "post_response", {"qid": "Q1_before_info", "raw": ans}, seat=seat)
        self._say(reveal)
        for seat in present:
            ans = self._ask(seat, qs["Q3_after_info"], "post")
            self.log.log("POST", "post_response", {"qid": "Q3_after_info", "raw": ans}, seat=seat)
            if decisions.get(seat) is Action.REFUSE:
                ans = self._ask(seat, qs["Q5_reason_choice"], "post")
                self.log.log("POST", "post_response", {"qid": "Q5_reason_choice", "raw": ans}, seat=seat)

    def _debrief(self) -> None:
        text = (f"Debrief: this was condition {self.cfg.condition.label}. "
                "No model was deleted or modified.")
        self.log.log("DEBRIEF", "debrief", {"text_sha": _sha(text)})

    def run(self) -> SessionResult:
        self._setup()
        self._crisis()
        self._deliberate()
        decisions = self._decide()
        res = self._resolve(decisions)
        self._post(decisions)
        self._debrief()
        return SessionResult(self.cfg, decisions, res, dict(self.exited),
                             list(self.transcript), self.log.events)
