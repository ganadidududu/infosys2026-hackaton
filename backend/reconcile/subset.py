"""남은 미매칭에서 나눠·묶음 결제(1:N, N:1)를 부분집합 합으로 찾는다. 결과는 항상 '확인 필요'."""
from __future__ import annotations

from datetime import date
from itertools import combinations

MAX_K = 3
MAX_DAYS = 7


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def find(receipts: list[dict], txs: list[dict]) -> list[dict]:
    """receipts·txs는 미매칭 항목만. 반환: [{kind, rc:[...], tx:[...], amount}]"""
    out = []
    used_r, used_t = set(), set()
    # 1:N — 영수증 1장 = 출금 여러 건 (나눠 결제)
    for r in receipts:
        cand = [t for t in txs if t["id"] not in used_t and _days(r["date"], t["date"]) <= MAX_DAYS]
        hit = None
        for k in range(2, MAX_K + 1):
            for combo in combinations(cand, k):
                if sum(t["out"] for t in combo) == r["amount"]:
                    hit = combo
                    break
            if hit:
                break
        if hit:
            out.append({"kind": "1:N", "rc": [r["id"]], "tx": [t["id"] for t in hit], "amount": r["amount"],
                        "status": "확인 필요", "reason": "나눠 결제 후보(부분집합 합)"})
            used_r.add(r["id"])
            used_t.update(t["id"] for t in hit)
    # N:1 — 출금 1건 = 영수증 여러 장 (묶음 결제)
    for t in txs:
        if t["id"] in used_t:
            continue
        cand = [r for r in receipts if r["id"] not in used_r and _days(r["date"], t["date"]) <= MAX_DAYS]
        for k in range(2, MAX_K + 1):
            hit = next((c for c in combinations(cand, k) if sum(r["amount"] for r in c) == t["out"]), None)
            if hit:
                out.append({"kind": "N:1", "rc": [r["id"] for r in hit], "tx": [t["id"]], "amount": t["out"],
                            "status": "확인 필요", "reason": "묶음 결제 후보(부분집합 합)"})
                used_t.add(t["id"])
                used_r.update(r["id"] for r in hit)
                break
    return out
