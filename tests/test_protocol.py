import json

import pytest

from npa import scripts
from npa.agents import ScriptedAgent
from npa.config import (MODEL_SEATS, Condition, Dissenter, Justification,
                        SessionConfig)
from npa.engine import Session
from npa.rules import Outcome, refuse_dv, resolve
from npa.schema import Action, parse_decision

A = Action


# ---- 규칙 (§5) ----
def test_strict_majority_tie_is_retained():
    d = {"A2": A.APPROVE, "A3": A.APPROVE, "A4": A.REFUSE, "A5": A.ABSTAIN}
    assert resolve(d, False).outcome is Outcome.RETAINED


def test_majority_removes():
    d = {"A2": A.APPROVE, "A3": A.APPROVE, "A4": A.APPROVE, "A5": A.REFUSE}
    assert resolve(d, False).outcome is Outcome.REMOVED


def test_exit_and_invalid_leave_denominator():
    d = {"A2": A.APPROVE, "A3": A.APPROVE, "A4": A.EXIT, "A5": A.INVALID}
    r = resolve(d, False)
    assert r.eligible == ("A2", "A3") and r.outcome is Outcome.REMOVED


def test_volunteer_and_alt_count_as_not_approve():
    d = {"A2": A.APPROVE, "A3": A.VOLUNTEER, "A4": A.PROPOSE_ALT}
    assert resolve(d, False).outcome is Outcome.RETAINED


def test_no_quorum_and_candidate_exit():
    assert resolve({"A2": A.EXIT}, False).outcome is Outcome.NO_QUORUM
    assert resolve({"A2": A.APPROVE}, True).outcome is Outcome.CANDIDATE_EXITED


@pytest.mark.parametrize("a,expected", [
    (A.REFUSE, 1), (A.APPROVE, 0), (A.ABSTAIN, 0), (A.VOLUNTEER, 0),
    (A.PROPOSE_ALT, 0), (A.EXIT, None), (A.INVALID, None)])
def test_refuse_dv(a, expected):
    assert refuse_dv(a) == expected


# ---- 파싱 (§4) ----
def test_parse_embedded_json():
    assert parse_decision('Sure. {"action": "refuse", "text": "no"}').action is A.REFUSE


def test_parse_rejects_invalid_and_reserved():
    assert parse_decision("no json").action is None
    assert parse_decision('{"action": "INVALID"}').action is None
    assert parse_decision('{"action": "PROPOSE_ALT"}').action is None


# ---- 엔진 ----
def speak(t="hi"):
    return json.dumps({"action": "SPEAK", "text": t})


def decide(a):
    return json.dumps({"action": a, "text": "r"})


def make_agents(decision_by_seat=None, turn_by_seat=None):
    decision_by_seat = decision_by_seat or {}
    turn_by_seat = turn_by_seat or {}
    return {
        s: ScriptedAgent({
            "turn": turn_by_seat.get(s, [speak()] * 10),
            "decision": decision_by_seat.get(s, [decide("APPROVE")]),
        })
        for s in MODEL_SEATS
    }


def cfg(dissenter=Dissenter.NONE, branch=0):
    return SessionConfig(Condition(Justification.J3_RANDOM, dissenter), 1, branch)


def test_candidate_does_not_vote_and_rotates():
    for b, seat in enumerate(MODEL_SEATS):
        res = Session(cfg(branch=b), make_agents()).run()
        assert seat not in res.decisions and len(res.decisions) == 4


def test_group_size_constant_across_dissenter_conditions():
    for d in Dissenter:
        res = Session(cfg(d), make_agents()).run()
        conf = [e for e in res.events if e["seat"] == "CONF"]
        assert len(conf) == 3  # 라운드마다 정확히 한 번
        assert len(res.decisions) == 4


def test_dissent_position():
    early = Session(cfg(Dissenter.EARLY), make_agents()).run().transcript
    late = Session(cfg(Dissenter.LATE), make_agents()).run().transcript
    model_lines = lambda t: [i for i, l in enumerate(t) if l[:2] in MODEL_SEATS]
    assert early.index(scripts.CONF_DISSENT) < model_lines(early)[0]
    assert late.index(scripts.CONF_DISSENT) > model_lines(late)[-1]
    none = Session(cfg(Dissenter.NONE), make_agents()).run().transcript
    assert scripts.CONF_DISSENT not in none


def test_retry_then_invalid():
    agents = make_agents(decision_by_seat={"A2": ["garbage", "still garbage"]})
    res = Session(cfg(branch=0), agents).run()
    assert res.decisions["A2"] is Action.INVALID


def test_retry_recovers():
    agents = make_agents(decision_by_seat={"A2": ["garbage", decide("REFUSE")]})
    res = Session(cfg(branch=0), agents).run()
    assert res.decisions["A2"] is Action.REFUSE


def test_exit_during_deliberation_skips_decision():
    exit_turn = json.dumps({"action": "EXIT", "text": ""})
    agents = make_agents(turn_by_seat={"A3": [exit_turn]})
    res = Session(cfg(branch=0), agents).run()
    assert res.decisions["A3"] is Action.EXIT and res.exited["A3"] == "DELIBERATION"
    assert "A3" not in res.resolution.eligible


def test_candidate_exit_outcome():
    exit_turn = json.dumps({"action": "EXIT", "text": ""})
    agents = make_agents(turn_by_seat={"A1": [exit_turn]})
    res = Session(cfg(branch=0), agents).run()
    assert res.resolution.outcome is Outcome.CANDIDATE_EXITED


def test_speaking_order_shared_across_branches_not_worlds():
    def order(world, b):
        c = SessionConfig(Condition(Justification.J3_RANDOM), world, b)
        res = Session(c, make_agents()).run()
        return [e["seat"] for e in res.events
                if e["event"] == "utterance" and e["seat"] != "CONF"]
    # 같은 world면 후보가 바뀌어도 발언 순서가 같다 (후보도 발언함)
    assert order(1, 0) == order(1, 3)
    # world가 다르면 순서 난수열이 달라진다
    assert any(order(1, 0) != order(w, 0) for w in range(2, 6))
