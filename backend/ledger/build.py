"""대사 결과 → 수입·지출 구분, 사업번호, 수입/지출내역서·총거래장부 행, 규칙 검사(RuleCheck).

근거: 3부 12·16조(구분), 37·38조(사업번호), 49~55조(내역서), 56~59조(장부), 29~36조(증빙), 5~17·27조(회계총칙).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from reconcile import hungarian, subset

FIXED = {"학생회비": 0, "관리운영비": 97, "소모품비": 98, "사업무관거래": 99, "감사비용": 100}
EXPENSE_CLASS = {"관리운영비": "관리운영비", "소모품비": "소모품비", "감사비용": "감사비용", "사업무관거래": "기타"}

# 수입 분류 규칙(전진법). 통장내역 키워드 → (사업, 구분). 질의·답변(Q-2026-1-01)에 따라 과잠은 사업수익금.
INCOME_RULES = [
    ("학생회비통장", None, "내부 이체"), ("축제통장", None, "내부 이체"),
    ("학생회비", "학생회비", "학생회비"),
    ("과잠", "과잠 공동구매", "사업수익금"),
    ("MT", "MT", "참가비"),
    ("이자", "사업무관거래", "예금결산이자"),
    ("매출", "축제 부스", "사업수익금"),
    ("학생회", "@공동 사업", "기타"),   # 학내 단체 → 단체간거래 수입(3부 30조의 2)
]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def classify_income(t: dict, ds: dict, overrides: dict) -> dict:
    if t["id"] in overrides:
        return {**overrides[t["id"]], "source": "감사인·집행부 지정"}
    if t.get("internal"):
        proj = "축제 부스" if t["account"] == "fest" or "축제" in t["desc"] else None
        return {"project": proj, "class": "내부 이체", "source": "규칙"}
    # 환불: 같은 업체·같은 금액의 이전 출금이 있으면 그 사업의 '취소'
    if "환불" in t["desc"]:
        vendor = t["desc"].replace("환불", "").strip()
        for o in ds["transactions"]:
            if o["out"] == t["in"] and vendor and vendor in o["desc"] and o["date"] <= t["date"]:
                return {"project": None, "class": "취소", "refund_of": o["id"], "source": "규칙"}
    for kw, proj, cls in INCOME_RULES:
        if kw in t["desc"]:
            if proj == "@공동 사업":
                ev = [e for e in ds["schedule"] if e["type"] == "공동 사업"]
                proj = min(ev, key=lambda e: abs((_d(e["date"]) - _d(t["date"])).days))["name"] if ev else None
            if kw == "매출" and t["account"] == "fest":
                proj = next((e["name"] for e in ds["schedule"] if e["type"] == "축제 부스"), proj)
            return {"project": proj, "class": cls, "source": "규칙"}
    return {"project": None, "class": "미분류", "source": "규칙"}


def reconcile(ds: dict, st: dict) -> dict:
    receipts = [{**r, **st.get("receipt_edits", {}).get(r["id"], {})} for r in ds["receipts"]]
    outs = [t for t in ds["transactions"] if t["out"] > 0 and not t.get("internal")]
    res = hungarian.match(receipts, outs)
    rc_by = {r["id"]: r for r in receipts}
    tx_by = {t["id"]: t for t in ds["transactions"]}
    decided = st.get("pair_decisions", {})   # "rc|tx" -> "확정"|"거절"

    pairs, un_r, un_t = [], set(res["unmatched_rc"]), set(res["unmatched_tx"])
    for p in res["pairs"]:
        key = f"{p['rc']}|{p['tx']}"
        dec = decided.get(key)
        if dec == "거절":
            un_r.add(p["rc"]); un_t.add(p["tx"])
            continue
        if dec == "확정":
            p = {**p, "status": "확정(감사인)"}
        pairs.append({**p, "kind": "1:1", "rc": [p["rc"]], "tx": [p["tx"]]})
    groups = subset.find([rc_by[i] for i in sorted(un_r)], [tx_by[i] for i in sorted(un_t)])
    for g in groups:
        key = "+".join(g["rc"]) + "|" + "+".join(g["tx"])
        dec = decided.get(key)
        g["key"] = key
        if dec == "거절":
            continue
        if dec == "확정":
            g["status"] = "확정(감사인)"
            un_r -= set(g["rc"]); un_t -= set(g["tx"])
        pairs.append({**g, "s": None, "parts": None})
    pending_group_tx = {t for g in groups if g["status"] == "확인 필요" for t in g["tx"]}
    pending_group_rc = {r for g in groups if g["status"] == "확인 필요" for r in g["rc"]}

    incomes = []
    for t in ds["transactions"]:
        if t["in"] > 0:
            incomes.append({"tx": t["id"], **classify_income(t, ds, st.get("income_overrides", {}))})
    for p in pairs:
        if "key" not in p:
            p["key"] = f"{p['rc'][0]}|{p['tx'][0]}"
    return {
        "pairs": pairs,
        "no_evidence": sorted(un_t - pending_group_tx),        # 증빙 없음 (역진법)
        "pending_group_tx": sorted(pending_group_tx),
        "not_in_bank": sorted(un_r - pending_group_rc),         # 통장에 없는 영수증
        "incomes": incomes,
        "unclassified": [i["tx"] for i in incomes if i["class"] == "미분류"],
        "total_cost": res["total_cost"],
        "counts": {
            "자동 확정": sum(1 for p in pairs if p["status"] == "자동 확정"),
            "확인 필요": sum(1 for p in pairs if p["status"] == "확인 필요"),
            "확정(감사인)": sum(1 for p in pairs if p["status"] == "확정(감사인)"),
            "증빙 없음": len(un_t - pending_group_tx),
            "미분류 수입": sum(1 for i in incomes if i["class"] == "미분류"),
            "통장에 없는 영수증": len(un_r - pending_group_rc),
        },
    }


def pay_method(r: dict | None, t: dict) -> str:
    if r:
        return r["pay"]
    if "자동이체" in t["desc"]:
        return "계좌이체"
    return "계좌이체" if t["in"] or t["out"] else "-"


def evidence_kinds(r: dict | None) -> list[str]:
    if not r:
        return []
    k = [r["kind"]]
    k += [a for a in r.get("attachments", []) if a not in k]
    return k


def build(ds: dict, st: dict) -> dict:
    rec = reconcile(ds, st)
    rc_by = {r["id"]: {**r, **st.get("receipt_edits", {}).get(r["id"], {})} for r in ds["receipts"]}
    tx_by = {t["id"]: t for t in ds["transactions"]}
    inc_by = {i["tx"]: i for i in rec["incomes"]}

    # 출금 → 증빙 (확인 필요 쌍도 잠정 연결, 상태로 구분)
    tx_rc: dict[str, list[str]] = {}
    tx_state: dict[str, str] = {}
    for p in rec["pairs"]:
        for t in p["tx"]:
            tx_rc[t] = p["rc"]
            tx_state[t] = p["status"]

    # 사업 귀속
    def project_of(t: dict) -> str | None:
        if t["in"] > 0:
            i = inc_by[t["id"]]
            if i.get("refund_of"):
                o = tx_by[i["refund_of"]]
                return project_of(o)
            return i["project"]
        rids = tx_rc.get(t["id"])
        if rids:
            return rc_by[rids[0]]["project"]
        if t.get("internal"):
            return "축제 부스"
        return None

    # 사업번호: 고정 번호 + 발생 순서대로 1부터 (3부 37·38조)
    first: dict[str, str] = {}
    for t in sorted(ds["transactions"], key=lambda x: (x["date"], x["id"])):
        pj = project_of(t)
        if pj and pj not in FIXED and pj not in first:
            first[pj] = t["date"]
    numbering = dict(FIXED)
    for k, (pj, _) in enumerate(sorted(first.items(), key=lambda kv: kv[1]), start=1):
        numbering[pj] = k
    projects_meta = {p["name"]: p for p in ds["projects"]}

    ledgers: dict[str, list[dict]] = {}
    for acc in ds["accounts"]:
        rows = []
        carry = ds["meta"]["carry_over"] if acc["id"] == "main" else 0
        rows.append({"seq": 1, "date": ds["meta"]["period"]["start"], "project_no": 0, "project": "학생회비",
                     "bank_desc": "전기 이월", "content": "전기 이월", "in": carry, "out": 0, "method": "-",
                     "class": "학생회비" if acc["id"] == "main" else "-", "items": "", "evidence": [], "note": "전기 이월", "tx": None})
        for t in sorted([x for x in ds["transactions"] if x["account"] == acc["id"]], key=lambda x: (x["date"], x["id"])):
            pj = project_of(t)
            rids = tx_rc.get(t["id"], [])
            r = rc_by[rids[0]] if rids else None
            note = ""
            if t["in"] > 0:
                inc = inc_by[t["id"]]
                cls = inc["class"]
                content = {"학생회비": "학생회비 납부", "참가비": f"{pj} 참가비", "사업수익금": f"{pj} 판매 수입",
                           "예금결산이자": "예금 결산 이자", "취소": "예약금 환불(지출 취소)", "기타": f"{pj} 수입",
                           "내부 이체": "통장 간 이체", "미분류": "출처 미확인 입금"}.get(cls, cls)
                items = ""
                if t.get("fee"):
                    items = f"순액 {t['in']:,} (매출 {t['gross']:,} − 수수료 {t['fee']:,})"
                    note = "수수료 차감 순액(3부 14·53조)"
                if cls == "기타" and "학생회" in t["desc"]:
                    note = "단체간거래(3부 30조의 2)"
                if cls == "내부 이체":
                    note = "통장 간 이체 · 현금의 유입과 유출이 없는 거래(학생회 기준)"
                method = "계좌이체" if "현금" not in t["desc"] else "현금"
                ev = ["과거거래내역서"] + (["단체간거래확인서", "이체내역서"] if cls == "기타" and "학생회" in t["desc"] else [])
                if "현금" in t["desc"]:
                    ev.append("판매 영수증철")
            else:
                cls = EXPENSE_CLASS.get(pj, "사업수행비") if pj else "미확인"
                if t.get("internal"):
                    cls = "내부 이체"
                    note = "통장 간 이체 · 현금의 유입과 유출이 없는 거래(학생회 기준)"
                content = (f"{r['vendor']} " + ", ".join(i["name"] for i in r["items"])).strip() if r else ("통장 간 이체" if t.get("internal") else "증빙 없음")
                items = ", ".join(f"{i['name']}" for i in r["items"]) if r and r["items"] else ("(세목 없음)" if r else "")
                method = pay_method(r, t)
                ev = evidence_kinds(r)
                if tx_state.get(t["id"]) == "확인 필요":
                    note = (note + " · " if note else "") + "대사 확인 필요"
            rows.append({"seq": len(rows) + 1, "date": t["date"], "project_no": numbering.get(pj) if pj else None, "project": pj,
                         "bank_desc": t["desc"], "content": content, "in": t["in"], "out": t["out"], "method": method,
                         "class": cls, "items": items, "evidence": ev, "note": note, "tx": t["id"], "rc": rids})
        # 전용 (현금흐름 없음, 3부 24~27조, 58조 ③)
        if acc["id"] == "main":
            for tr in ds["transfers"]:
                for pj, sign in ((tr["from"], -1), (tr["to"], 1)):
                    rows.append({"seq": len(rows) + 1, "date": tr["date"], "project_no": numbering.get(pj), "project": pj,
                                 "bank_desc": "-", "content": f"전용: {tr['content']}", "in": 0, "out": sign * tr["amount"],
                                 "method": "-", "class": "사업수행비", "items": tr["content"], "evidence": [],
                                 "note": "현금의 유입과 유출이 없는 거래" + (f" · 산출 근거: {tr['note']}" if tr["note"] else ""),
                                 "tx": None, "transfer": True})
        for row in rows:
            row["account"] = acc["id"]
            row["code"] = f"{row['project_no']}-{row['seq']}" if row["project_no"] is not None else f"?-{row['seq']}"
        ledgers[acc["id"]] = rows

    # 사업목록 + 사업개요서 자동 칸 (교비 제외 지출 총액)
    plist = []
    for pj, no in sorted(numbering.items(), key=lambda kv: kv[1]):
        ins = outs = 0
        for acc_rows in ledgers.values():
            for row in acc_rows:
                if row["project"] == pj and row["class"] not in ("내부 이체",) and row["tx"]:
                    if row["class"] == "취소":
                        outs -= row["in"]
                    else:
                        ins += row["in"]
                        outs += row["out"]
                elif row["project"] == pj and row.get("transfer"):
                    outs += row["out"]
        if pj == "학생회비":
            pass
        plist.append({"no": no, "name": pj, "fixed": pj in FIXED, "income": ins, "expense": outs,
                      "overview": projects_meta.get(pj, {}).get("overview")})

    checks = rule_checks(ds, st, rec, ledgers, rc_by, tx_by, numbering, plist)
    return {"reconcile": rec, "ledgers": ledgers, "projects": plist, "numbering": numbering, "checks": checks}


def rule_checks(ds, st, rec, ledgers, rc_by, tx_by, numbering, plist) -> list[dict]:
    """결정적 코드로 확인하는 기준안 규칙. 결과는 감사 패킷의 '숫자 사실'이 된다."""
    out: list[dict] = []
    audited = {a["evidence"] for a in ds.get("audited_evidence", [])}

    def add(clause, project, result, message, target=None, facts=None, item=None):
        out.append({"id": f"RC{len(out)+1:02d}", "clause": clause, "item": item, "project": project, "result": result,
                    "message": message, "target": target, "facts": facts or {}})

    for acc_rows in ledgers.values():
        for row in acc_rows:
            for rid in row.get("rc") or []:
                r = rc_by[rid]
                if rid in audited:
                    add("2부 7", row["project"], "제외", f"{r['vendor']} 증빙은 비정기감사에서 수검됨", row["code"])
                    continue
                kind, pay = r["kind"], r["pay"]
                if kind == "계산서":
                    missing = [k for k, v in (r.get("invoice") or {}).items() if not v]
                    if missing:
                        add("3부 35조", row["project"], "위반", f"{r['vendor']} 계산서 {'·'.join(missing)} 항목 누락", row["code"],
                            {"missing": missing, "amount": r["amount"]}, item=missing[0])
                    else:
                        add("3부 35조", row["project"], "충족", f"{r['vendor']} 계산서 6항목 모두 있음", row["code"])
                elif kind == "이체내역서":
                    ok = "이체내역서" in evidence_kinds(r) and "과거거래내역서" in evidence_kinds(r)
                    add("3부 32조의 2", row["project"], "충족" if ok else "위반",
                        f"{r['vendor']} 예약금 증빙: 과거거래내역서·이체내역서 " + ("있음" if ok else "부족"), row["code"])
                elif pay == "카드":
                    add("3부 31조", row["project"], "충족" if r["has_items"] else "위반",
                        f"{r['vendor']} 카드 전표 세목 " + ("표기됨" if r["has_items"] else "없음"), row["code"])
                elif pay == "계좌이체":
                    ok = kind == "현금영수증" and r["has_items"]
                    add("3부 32조", row["project"], "충족" if ok else "위반",
                        f"{r['vendor']} 계좌이체 증빙: {kind}" + (" (세목 있음)" if r["has_items"] else " (세목 없음)"), row["code"])
                if r.get("installment"):
                    add("3부 8조", row["project"], "위반", f"{r['vendor']} 카드 할부 {r['installment']}개월", row["code"],
                        {"installment": r["installment"], "amount": r["amount"]})
                if r.get("points"):
                    add("3부 9조", row["project"], "위반", f"{r['vendor']} 결제로 포인트 {r['points']:,}P 적립", row["code"],
                        {"points": r["points"]})
            if row.get("transfer") and row["out"] > 0 and "산출 근거" not in row["note"]:
                add("3부 27조", row["project"], "위반", f"전용 {row['out']:,}원에 산출 근거 비고 없음", row["code"],
                    {"amount": row["out"]})
    for t in rec["no_evidence"]:
        tx = tx_by[t]
        add("3부 31조", None, "위반", f"{tx['date']} {tx['desc']} {tx['out']:,}원 출금에 증빙 없음", t, {"amount": tx["out"]})
    for t in rec["unclassified"]:
        tx = tx_by[t]
        add("3부 12조", None, "확인 필요", f"{tx['date']} 입금 {tx['in']:,}원의 사업·수입 구분 미확인", t, {"amount": tx["in"]})
    # 참가비 ≤ 해당 사업 지출 (3부 13조)
    fee_by = defaultdict(int)
    for i in rec["incomes"]:
        if i["class"] == "참가비":
            fee_by[i["project"]] += tx_by[i["tx"]]["in"]
    for pj, fee in fee_by.items():
        spend = next((p["expense"] for p in plist if p["name"] == pj), 0)
        add("3부 13조", pj, "위반" if fee > spend else "충족",
            f"{pj} 참가비 {fee:,}원 {'>' if fee > spend else '≤'} 지출 {spend:,}원", None, {"참가비": fee, "지출": spend})
    # 축제 별도 통장 사전 승인 (3부 18조)
    for acc in ds["accounts"]:
        if acc.get("festival"):
            first_tx = min((t["date"] for t in ds["transactions"] if t["account"] == acc["id"]), default=None)
            ok = acc.get("approved") and first_tx and acc["approved"] <= first_tx
            add("3부 18조", "축제 부스", "충족" if ok else "위반",
                f"축제 통장 승인 {acc.get('approved') or '없음'} · 첫 거래 {first_tx}", None,
                {"approved": acc.get("approved"), "first_tx": first_tx})
    # 수수료 처리 (3부 14조)
    for t in ds["transactions"]:
        if t.get("fee"):
            add("3부 14조", "축제 부스", "충족", f"카드 매출 수수료 {t['fee']:,}원 차감한 순액 {t['in']:,}원으로 기록", t["id"])
    return out
