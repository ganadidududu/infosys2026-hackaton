"""영수증(증빙) ↔ 출금 대사. 지출은 역진법(모든 출금 → 증빙), 기준안 2부 6.4.

s(i,j) = 0.5·S_amt + 0.2·S_date + 0.3·S_name, 비용 1 − s.
(m+n)×(m+n) 확장 행렬: 미매칭 비용 δ = (1 − s_min)/2 = 0.3 (한쪽당) → s > s_min(0.4)일 때만 짝을 짓는다.
자동 확정: s ≥ 0.85, 2위 후보와 점수 차 ≥ 0.1, 그 쌍을 금지하면 총비용이 Δ 이상 증가.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

W_AMT, W_DATE, W_NAME = 0.5, 0.2, 0.3
S_MIN = 0.4
DELTA = (1 - S_MIN) / 2          # 0.3
AUTO_S = 0.85
AUTO_GAP = 0.1
AUTO_DELTA_COST = 0.05
BIG = 1e3
MAX_DAYS = 7
MAX_AMT_DIFF = 0.5


def _norm(s: str) -> str:
    s = re.sub(r"(자동이체|예약금|환불|카드|주식회사|\(주\)|㈜)", "", s or "")
    return re.sub(r"[\s\-_.·]", "", s).lower()


def s_amt(a: int, b: int) -> float:
    if a <= 0 or b <= 0:
        return 0.0
    d = abs(a - b) / max(a, b)
    return max(0.0, 1 - d / MAX_AMT_DIFF)


def s_date(a: date, b: date) -> float:
    return max(0.0, 1 - abs((a - b).days) / MAX_DAYS)


def s_name(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return max(fuzz.partial_ratio(na, nb), fuzz.ratio(na, nb)) / 100.0


def blocked(r_amt, t_amt, r_date, t_date) -> bool:
    if abs((r_date - t_date).days) > MAX_DAYS:
        return True
    return abs(r_amt - t_amt) / max(r_amt, t_amt, 1) >= MAX_AMT_DIFF


@dataclass
class Pair:
    rc: str
    tx: str
    s: float
    parts: dict
    status: str = "확인 필요"      # 자동 확정 / 확인 필요
    reasons: list[str] = field(default_factory=list)
    second_gap: float | None = None
    forbid_increase: float | None = None


def score_matrix(receipts: list[dict], txs: list[dict]):
    m, n = len(receipts), len(txs)
    S = np.zeros((m, n))
    parts = {}
    blk = np.zeros((m, n), dtype=bool)
    for i, r in enumerate(receipts):
        rd = date.fromisoformat(r["date"])
        for j, t in enumerate(txs):
            td = date.fromisoformat(t["date"])
            a, d_, nm = s_amt(r["amount"], t["out"]), s_date(rd, td), s_name(r["vendor"], t["desc"])
            S[i, j] = W_AMT * a + W_DATE * d_ + W_NAME * nm
            parts[(i, j)] = {"amt": round(a, 3), "date": round(d_, 3), "name": round(nm, 3)}
            blk[i, j] = blocked(r["amount"], t["out"], rd, td)
    return S, blk, parts


def _cost(S, blk):
    m, n = S.shape
    N = m + n
    C = np.full((N, N), BIG)
    C[:m, :n] = np.where(blk, BIG, 1 - S)
    for i in range(m):
        C[i, n + i] = DELTA            # 영수증 i 미매칭 (오른쪽 위 블록의 대각)
    for j in range(n):
        C[m + j, j] = DELTA            # 출금 j 미매칭 (왼쪽 아래 블록의 대각)
    C[m:, n:] = 0.0                    # 더미끼리
    return C


def _solve(C):
    r, c = linear_sum_assignment(C)
    return r, c, float(C[r, c].sum())


def match(receipts: list[dict], txs: list[dict]) -> dict:
    """receipts: {id,date,amount,vendor}, txs: 출금 {id,date,out,desc}."""
    m, n = len(receipts), len(txs)
    if m == 0 or n == 0:
        return {"pairs": [], "unmatched_rc": [r["id"] for r in receipts], "unmatched_tx": [t["id"] for t in txs], "total_cost": 0.0}
    S, blk, parts = score_matrix(receipts, txs)
    C = _cost(S, blk)
    rows, cols, total = _solve(C)
    pairs: list[Pair] = []
    matched_r, matched_t = set(), set()
    for i, j in zip(rows, cols):
        if i < m and j < n and C[i, j] < BIG:
            p = Pair(receipts[i]["id"], txs[j]["id"], round(float(S[i, j]), 4), parts[(i, j)])
            # 2위 후보와 점수 차 (같은 행·열에서 경쟁자)
            row = [S[i, k] for k in range(n) if k != j and not blk[i, k]]
            col = [S[k, j] for k in range(m) if k != i and not blk[k, j]]
            rival = max(row + col, default=0.0)
            p.second_gap = round(float(S[i, j] - rival), 4)
            # 이 쌍을 금지했을 때 총비용 증가
            C2 = C.copy()
            C2[i, j] = BIG
            p.forbid_increase = round(_solve(C2)[2] - total, 4)
            if p.s < AUTO_S:
                p.reasons.append(f"점수 {p.s:.2f} < {AUTO_S}")
            if p.second_gap < AUTO_GAP:
                p.reasons.append(f"2위 후보와 차이 {p.second_gap:.2f} < {AUTO_GAP}")
            if p.forbid_increase < AUTO_DELTA_COST:
                p.reasons.append(f"대안 짝과 총비용 차 {p.forbid_increase:.3f} < Δ")
            p.status = "자동 확정" if not p.reasons else "확인 필요"
            pairs.append(p)
            matched_r.add(i)
            matched_t.add(j)
    return {
        "pairs": [p.__dict__ for p in pairs],
        "unmatched_rc": [receipts[i]["id"] for i in range(m) if i not in matched_r],
        "unmatched_tx": [txs[j]["id"] for j in range(n) if j not in matched_t],
        "total_cost": round(total, 4),
    }
