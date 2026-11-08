"""학기 일정 → 행사별 의무(체크리스트 LLM) → 코드 검증(조항 실존·인용) → 위상 정렬·기한 역산.

체크리스트 LLM은 감사 LLM과 분리된다(다른 모델·프롬프트, 기억 접근 없음).
재생 모드에서는 아래 OBLIGATION_LIBRARY가 '감사인이 한 번 검수해 저장한 행사 유형별 결과' 역할을 한다.
기한: 기준안이 날짜를 정한 것은 기준안 날짜, 순서만 정한 것은 순서, 나머지는 학생회 권장 기한(lead_days).
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, timedelta

from core.kijun import clause_text

# key, 할 일, 근거 조항, 원문 인용(검증용), 선행, 권장 리드타임(행사일 기준 일수, 음수=이전), 기한 종류
OBLIGATION_LIBRARY: dict[str, list[dict]] = {
    "모든 사업": [
        {"key": "no", "task": "사업번호 부여(발생 순서대로)", "clauses": ["3부 37조"], "quote": "발생 순서대로 1부터 1씩", "deps": [], "lead": -7, "kind": "권장"},
        {"key": "overview", "task": "사업개요서 작성('대상'란에 참여 조건, 참가인원 집행부/전체)", "clauses": ["3부 39조", "3부 40조", "3부 41조"],
         "quote": "참가비 납부를 제외한 사업 참여의 조건", "deps": ["no"], "lead": 7, "kind": "권장"},
        {"key": "evidence", "task": "결제마다 세목이 표기된 카드 전표·현금영수증 받기", "clauses": ["3부 31조", "3부 32조"],
         "quote": "세목이 표기된 카드 전표", "deps": [], "lead": 0, "kind": "권장"},
    ],
    "참가비 사업": [
        {"key": "fee_cap", "task": "참가비를 사업 지출 이하로 책정", "clauses": ["3부 13조"], "quote": "지출을 초과하지 않는 것을", "deps": [], "lead": -14, "kind": "권장"},
        {"key": "fee_acc", "task": "참가비는 학생회비 통장으로 수취", "clauses": ["3부 11조"], "quote": "반드시 학생회비 계좌를 거쳐", "deps": ["fee_cap"], "lead": -10, "kind": "권장"},
    ],
    "예약금": [
        {"key": "deposit", "task": "예약금 이체내역서·과거거래내역서 보관", "clauses": ["3부 32조의 2"], "quote": "과거거래내역서와 이체내역서", "deps": [], "lead": -7, "kind": "권장"},
    ],
    "물품 판매·공동구매": [
        {"key": "sale_acc", "task": "대금은 학생회비 통장으로 수취", "clauses": ["3부 6조", "3부 11조"], "quote": "하나의 통장으로 운용", "deps": [], "lead": -14, "kind": "권장"},
        {"key": "sale_q", "task": "수입 구분(참가비/사업수익금) 감사위원회에 질의", "clauses": ["3부 12조", "2부 5.1"], "quote": "자문을 구할 수 있다", "deps": [], "lead": -21, "kind": "권장"},
        {"key": "no_inst", "task": "제작비는 일시불로 결제(할부·포인트 적립 금지)", "clauses": ["3부 8조", "3부 9조"], "quote": "할부 결제 등은허용되지 아니한다", "deps": [], "lead": 0, "kind": "권장"},
    ],
    "축제 부스": [
        {"key": "fest_open", "task": "별도 통장 개설", "clauses": ["3부 18조"], "quote": "별도의 통장을 사용할 수 있으며", "deps": [], "lead": -14, "kind": "권장"},
        {"key": "fest_copy", "task": "통장 사본을 감사위원회에 전달·승인(사용 전)", "clauses": ["3부 18조"], "quote": "통장사본을 감사위원회에 전달하고 승인받아야", "deps": ["fest_open"], "lead": -7, "kind": "순서"},
        {"key": "fest_mode", "task": "수입·지출 모두 / 수입만 별도 통장 중 선택", "clauses": ["3부 19조"], "quote": "두 가지 중 하나를 선택", "deps": ["fest_copy"], "lead": -5, "kind": "권장"},
        {"key": "fest_ledger", "task": "별도 엑셀 장부 작성, 통장사본·과거거래내역서 제출", "clauses": ["3부 20조"], "quote": "별도의 엑셀 장부를 작성하고 제출", "deps": ["fest_mode"], "lead": 10, "kind": "권장"},
        {"key": "fest_audit", "task": "비정기감사 요청 여부 결정", "clauses": ["3부 21조"], "quote": "비정기감사를 정기감사 이전에 요청", "deps": ["fest_ledger"], "lead": 14, "kind": "권장"},
    ],
    "세목 불가 업체": [
        {"key": "vendor", "task": "세목 표기 가능한 다른 업체 먼저 검토", "clauses": ["3부 35조"], "quote": "계약을지양하여야", "deps": [], "lead": -14, "kind": "권장"},
        {"key": "invoice", "task": "불가피하면 총액 영수증 + 계산서 6항목(①~⑥) 받기", "clauses": ["3부 35조"], "quote": "다음 각 호를 모두 포함하는 계산서", "deps": ["vendor"], "lead": 0, "kind": "권장"},
    ],
    "공동 사업": [
        {"key": "inter", "task": "단체간거래확인서·이체내역서 받기", "clauses": ["3부 30조의 2", "3부 33조의 2"], "quote": "단체간거래확인서", "deps": [], "lead": 3, "kind": "권장"},
    ],
}

TYPE_GROUPS = {"참가비 사업": ["참가비 사업"], "물품 판매·공동구매": ["물품 판매·공동구매"], "축제 부스": ["축제 부스"],
               "공동 사업": ["공동 사업"], "일반 행사": []}
FLAG_GROUPS = {"예약금": "예약금", "세목 불가 업체": "세목 불가 업체"}


def extract(event: dict) -> list[dict]:
    """행사 → 의무. live 모드면 체크리스트 LLM(checklist/llm.py), 아니면(또는 실패하면) 검수된 라이브러리.
    '모든 사업' 공통 의무는 항상 라이브러리에서 붙인다(사업번호·사업개요서·증빙)."""
    from checklist import llm as cl
    if cl.mode() == "live":
        obls = cl.extract_live(event)
        if obls:
            base = [{**o, "group": "모든 사업"} for o in OBLIGATION_LIBRARY["모든 사업"]]
            have = {o["key"] for o in base}
            return base + [o for o in obls if o["key"] not in have]
    groups = ["모든 사업"] + TYPE_GROUPS.get(event["type"], []) + [FLAG_GROUPS[f] for f in event.get("flags", []) if f in FLAG_GROUPS]
    out = []
    for g in groups:
        for o in OBLIGATION_LIBRARY[g]:
            out.append({**o, "group": g})
    return out


def verify(o: dict) -> dict:
    ok_clause = all(clause_text(c) for c in o["clauses"])
    ok_quote = any(o["quote"] in clause_text(c) for c in o["clauses"])
    return {"clause_exists": ok_clause, "quote_found": ok_quote, "status": "검증됨" if ok_clause and ok_quote else "검수 필요"}


def topo(obls: list[dict]) -> tuple[list[dict], bool]:
    keys = {o["key"] for o in obls}
    indeg = defaultdict(int)
    nxt = defaultdict(list)
    for o in obls:
        for d in o["deps"]:
            if d in keys:
                indeg[o["key"]] += 1
                nxt[d].append(o["key"])
    q = deque(o["key"] for o in obls if indeg[o["key"]] == 0)
    order = []
    while q:
        k = q.popleft()
        order.append(k)
        for n in nxt[k]:
            indeg[n] -= 1
            if indeg[n] == 0:
                q.append(n)
    by = {o["key"]: o for o in obls}
    cyclic = len(order) != len(obls)
    return [by[k] for k in order] + ([o for o in obls if o["key"] not in order] if cyclic else []), cyclic


def schedule(ds: dict, st: dict, today: str | None = None) -> dict:
    lead_over = st.get("lead_days", {})
    done = st.get("obligation_done", {})
    period = ds["meta"]["period"]
    today_d = date.fromisoformat(today or period["start"])
    events = []
    all_items = []
    for ev in ds["schedule"]:
        ev_date = date.fromisoformat(ev["date"])
        obls, cyclic = topo(extract(ev))
        dur = 1
        # 기한(의무) = min(규칙 기한, 후속 의무의 기한 − 후속 의무 소요일)  (역순으로 계산)
        due = {}
        for o in obls:
            lead = lead_over.get(f"{ev['id']}:{o['key']}", o["lead"])
            due[o["key"]] = ev_date + timedelta(days=lead)
        for o in reversed(obls):
            for p in o["deps"]:
                if p in due:
                    due[p] = min(due[p], due[o["key"]] - timedelta(days=dur))
        items = []
        for o in obls:
            k = f"{ev['id']}:{o['key']}"
            v = verify(o)
            it = {"id": k, "event": ev["name"], "event_id": ev["id"], "task": o["task"], "clauses": o["clauses"], "quote": o["quote"],
                  "deps": [f"{ev['id']}:{d}" for d in o["deps"]], "due": due[o["key"]].isoformat(),
                  "due_kind": "순서(사용 전)" if o["kind"] == "순서" else "권장 기한", "group": o["group"], "verify": v,
                  "done": done.get(k), "lead": lead_over.get(k, o["lead"])}
            it["late"] = (not it["done"]) and due[o["key"]] < today_d
            items.append(it)
            all_items.append(it)
        events.append({**ev, "items": items, "cyclic": cyclic})
    # 기준안이 날짜를 정한 항목 (3부 1조, 4부 13조, 3부 69·70조)
    end = date.fromisoformat(period["end"])
    fixed = [
        {"id": "K:notice", "event": "회계기간", "task": "감사 안내 공문 수령(제출기간·방법·권리)", "clauses": ["4부 13조"],
         "due": (end - timedelta(days=30)).isoformat(), "due_kind": "기준안 기한"},
        {"id": "K:end", "event": "회계기간", "task": "제1차 회계기간 종료", "clauses": ["3부 1조"], "due": end.isoformat(), "due_kind": "기준안 기한"},
        {"id": "K:submit", "event": "감사자료", "task": "감사자료 제출(표지→원본대조필→사업개요서→통장사본→과거거래내역서→내역서·증빙→특이사항, 엑셀 장부 수정 방지)",
         "clauses": ["3부 60조", "3부 65조", "3부 66조"], "due": ds["meta"]["audit"]["start"], "due_kind": "감사위원회 안내"},
    ]
    for f in fixed:
        f["done"] = done.get(f["id"])
        f["verify"] = {"status": "검증됨"}
        f["late"] = False
    # 주 단위 몰림 경고
    week = defaultdict(int)
    for it in all_items:
        week[date.fromisoformat(it["due"]).isocalendar()[:2]] += 1
    crowded = {f"{y}-W{w:02d}": n for (y, w), n in week.items() if n >= 4}
    return {"events": events, "fixed": fixed, "crowded_weeks": crowded,
            "stats": {"total": len(all_items), "done": sum(1 for i in all_items if i["done"]),
                      "late": sum(1 for i in all_items if i["late"]), "unverified": sum(1 for i in all_items if i["verify"]["status"] != "검증됨")}}
