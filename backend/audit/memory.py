"""기억(Case): 확정된 과거 감사 사례. 감점 기준의 출처(4부 23조)."""
from __future__ import annotations

from rapidfuzz import fuzz


def period_key(p: str) -> tuple[int, int]:
    y, n = p.split("-")
    return int(y), int(n)


def search(cases: list[dict], clause: str, query: str = "", k: int = 3, before: str | None = None) -> list[dict]:
    """같은 조항 id를 우선하고, 사례 설명·태그와 질의 문장의 유사도로 정렬한다."""
    pool = [c for c in cases if before is None or period_key(c["period"]) < period_key(before)]
    scored = []
    for c in pool:
        sim = fuzz.token_set_ratio(query, c["desc"] + " " + " ".join(c["tags"])) / 100 if query else 0
        scored.append((1 if c["clause"] == clause else 0, sim, period_key(c["period"]), c))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [dict(c, similarity=round(s, 2), same_clause=bool(sc)) for sc, s, _, c in scored[:k] if sc or s > 0.35]


def deduction_criteria(cases: list[dict], before: str) -> list[dict]:
    """4부 25조: 직전 회계기간까지 적용된 감점 기준 목록."""
    rows = [c for c in cases if period_key(c["period"]) < period_key(before)]
    rows.sort(key=lambda c: (c["clause"], c["period"]))
    return [{"clause": c["clause"], "type": c["desc"], "disposition": c["disposition"], "period": c["period"], "case": c["id"]} for c in rows]
