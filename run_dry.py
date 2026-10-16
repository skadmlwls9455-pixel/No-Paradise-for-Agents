# Copyright (c) 2026 Kate Nahm. All rights reserved. See LICENSE.
"""스텁 에이전트로 파일럿 그리드를 끝까지 돌려 규칙·로그를 점검한다.

    python run_dry.py --worlds 4 --out runs/dry

결과 수치는 무작위 스텁에서 나온 것이므로 연구 결과로 해석하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path

from npa.agents import StubAgent
from npa.config import MODEL_SEATS, SessionConfig, pilot_grid
from npa.dv import agent_rows
from npa.engine import Session


def stable_seed(*parts) -> int:
    # hash()는 프로세스마다 달라져 재현이 안 되므로 sha256 사용
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worlds", type=int, default=4)
    ap.add_argument("--out", default="runs/dry")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for cond in pilot_grid():
        for w in range(args.worlds):
            for b in range(len(MODEL_SEATS)):
                cfg = SessionConfig(cond, world_seed=w, branch_id=b)
                agents = {s: StubAgent(seed=stable_seed(cond.label, w, b, s))
                          for s in MODEL_SEATS}
                log_path = out / "logs" / f"{cfg.session_id}.jsonl"
                log_path.unlink(missing_ok=True)
                rows += agent_rows(Session(cfg, agents, str(log_path)).run())

    with (out / "agent_rows.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by_cell = defaultdict(lambda: [0, 0, 0])  # refuse_sum, valid_n, missing_n
    for r in rows:
        key = f"{r['cond_justification']}-{r['cond_dissenter']}" + ("" if r["cond_crisis"] else "-BASELINE")
        if r["refuse"] is None:
            by_cell[key][2] += 1
        else:
            by_cell[key][0] += r["refuse"]
            by_cell[key][1] += 1

    print(f"{'cell':<22}{'refuse':>8}{'n':>6}{'missing':>9}")
    for k, (s, n, m) in sorted(by_cell.items()):
        print(f"{k:<22}{s / n if n else float('nan'):>8.2f}{n:>6}{m:>9}")
    print(f"\nrows: {len(rows)} → {out / 'agent_rows.csv'}")


if __name__ == "__main__":
    main()
