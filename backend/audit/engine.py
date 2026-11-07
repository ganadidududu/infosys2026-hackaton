"""감사 판단 파이프라인: 패킷 → 감사 LLM 2회 → 코드 검증 → 선례 처분 + 경고 규칙 → 감사인 결정 반영."""
from __future__ import annotations

import re

from core.kijun import exists
from audit import llm, memory
from audit.packet import build_packets

NUMERIC_CLAUSES = {"3부 8조", "3부 9조", "3부 13조", "3부 27조", "3부 31조", "3부 32조", "3부 32조의 2", "3부 35조", "3부 14조", "3부 18조"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def warning_penalty(w: int) -> int:
    """4부 26조: 경고 3회째 1점, 이후 1건마다 1점 → max(0, w − 2). 회계기간마다 새로 센다."""
    return max(0, w - 2)


def verify(packet: dict, j: dict, cases_by: dict) -> dict:
    docs = {d["id"]: _norm(d["text"]) for d in packet["documents"]}
    v = {"quote": True, "clause": True, "case": True, "numeric": None, "notes": []}
    for e in j.get("evidence", []):
        if _norm(e.get("quote", "")) not in docs.get(e.get("doc"), ""):
            v["quote"] = False
            v["notes"].append(f"인용 불일치: \"{e.get('quote')}\"가 {e.get('doc')}에 없음")
    if not exists(j["clause"]) or j["clause"] not in {c["id"] for c in packet["clauses"]}:
        v["clause"] = False
        v["notes"].append("감사 대상 조항이 아님")
    sc = j.get("same_case")
    if sc:
        c = cases_by.get(sc.get("case_id"))
        if not c or c["clause"] != j["clause"]:
            v["case"] = False
            v["notes"].append("선례 id가 없거나 조항이 다름")
    return v


def run(ds: dict, led: dict, checklist_status: dict | None = None) -> dict:
    packets = build_packets(ds, led, checklist_status)
    cases_by = {c["id"]: c for c in ds["cases"]}
    findings = []
    raw = {}
    for p in packets:
        r1, r2 = llm.call(p, 1), llm.call(p, 2)
        raw[p["id"]] = {"call1": r1, "call2": r2}
        by2 = {j["clause"]: j for j in r2["judgments"]}
        for j1 in r1["judgments"]:
            j2 = by2.get(j1["clause"], {})
            v1, v2 = verify(p, j1, cases_by), (verify(p, j2, cases_by) if j2 else None)
            verdict = j1["verdict"]
            reasons = []
            # 코드 값 우선: 숫자로 판단되는 조항은 규칙 검사 결과를 쓴다
            cks = [c for c in p["checks"] if c["clause"] == j1["clause"]]
            code_verdict = None
            if j1["clause"] in NUMERIC_CLAUSES and cks:
                code_verdict = "미충족" if any(c["result"] == "위반" for c in cks) else "충족"
                if code_verdict != verdict:
                    reasons.append(f"숫자 판정은 코드 값 우선({verdict} → {code_verdict})")
                verdict = code_verdict
            if not v1["quote"] or (v2 and not v2["quote"]):
                verdict, reasons = "확인 필요", reasons + [n for n in v1["notes"] + (v2["notes"] if v2 else []) if n.startswith("인용")]
            if not v1["clause"]:
                verdict, reasons = "확인 필요", reasons + ["조항 검증 실패"]
            same1 = (j1.get("same_case") or {}).get("case_id") if v1["case"] else None
            same2 = (j2.get("same_case") or {}).get("case_id") if j2 and v2 and v2["case"] else None
            if j2 and j2.get("verdict") != j1["verdict"] and code_verdict is None:
                verdict, reasons = "확인 필요", reasons + [f"2회 판정 불일치({j1['verdict']} / {j2.get('verdict')})"]
            elif j2 and verdict == "미충족" and same1 != same2:
                verdict, reasons = "확인 필요", reasons + ["2회 동일 선례 불일치"]
            # 처분 (4부 23·24조)
            disp, source, alt = None, None, []
            new_type = bool(j1.get("is_new_type")) and verdict == "미충족"
            if verdict == "미충족":
                if same1:
                    c = cases_by[same1]
                    disp, source = c["disposition"], same1
                    others = [x for x in ds["cases"] if x["clause"] == c["clause"] and x["id"] != c["id"] and x["disposition"] != c["disposition"]]
                    if others:
                        latest = max([c] + others, key=lambda x: memory.period_key(x["period"]))
                        disp, source = latest["disposition"], latest["id"]
                        alt = [{"case": x["id"], "disposition": x["disposition"]} for x in [c] + others if x["id"] != latest["id"]]
                elif new_type:
                    disp, source = {"type": "신규 유형"}, "감사인단 전원 논의"
            fid = f"{p['id']}:{j1['clause']}"
            findings.append({
                "id": fid, "packet": p["id"], "project": p["title"], "clause": j1["clause"], "target": j1.get("target"),
                "verdict": verdict, "llm": [j1, j2], "verify": [v1, v2], "reasons": reasons,
                "evidence": j1.get("evidence", []), "missing": j1.get("missing", []), "question": j1.get("question") or (j2 or {}).get("question"),
                "same_case": same1, "same_case_alt": alt, "new_type": new_type, "disposition": disp, "disposition_source": source,
                "checks": [c["id"] for c in cks], "code_verdict": code_verdict,
            })
    return {"packets": packets, "raw": raw, "findings": findings, "mode": llm.mode()}


def apply_decisions(findings: list[dict], decisions: dict) -> list[dict]:
    out = []
    for f in findings:
        d = decisions.get(f["id"], {})
        g = dict(f)
        if d.get("verdict"):
            g["verdict"] = d["verdict"]
        if "disposition" in d:
            g["disposition"] = d["disposition"]
            g["disposition_source"] = d.get("source", "감사인 수정")
        g["confirmed"] = bool(d.get("confirmed"))
        g["note"] = d.get("note", "")
        g["public_text"] = d.get("public_text")
        out.append(g)
    return out


def totals(findings: list[dict]) -> dict:
    case_pts, warns, pending_new, pending_check = 0, 0, 0, 0
    for f in findings:
        d = f.get("disposition") or {}
        if f["verdict"] == "확인 필요":
            pending_check += 1
            continue
        if f["verdict"] != "미충족":
            continue
        if d.get("type") == "감점":
            case_pts += int(d.get("points", 0))
        elif d.get("type") == "경고":
            warns += 1
        elif d.get("type") == "신규 유형":
            pending_new += 1
    wp = warning_penalty(warns)
    by_verdict = {}
    for f in findings:
        by_verdict[f["verdict"]] = by_verdict.get(f["verdict"], 0) + 1
    return {"case_points": case_pts, "warnings": warns, "warning_points": wp, "total": case_pts + wp,
            "pending_new": pending_new, "pending_check": pending_check, "by_verdict": by_verdict,
            "clauses": len(findings)}


OPINION_KEYS = ["감사자료의 신뢰성", "회계관리 및 통제의 유효성", "수입 및 지출의 종합적 적절성", "회계 전반"]


def draft_opinions(findings: list[dict]) -> list[dict]:
    """4부 18조 4가지 평가 초안: 짧은 판정(양호/미흡) + 한두 문장. 감사인단이 고쳐 확정한다."""
    bad = [f for f in findings if f["verdict"] == "미충족"]
    groups = {
        0: [f for f in bad if f["clause"] in {"3부 31조", "3부 32조", "3부 32조의 2", "3부 35조"} or f["clause"].startswith("3부 4") or f["clause"].startswith("3부 5")],
        1: [f for f in bad if f["clause"] in {"3부 7조", "3부 8조", "3부 9조", "3부 18조", "3부 27조"}],
        2: [f for f in bad if f["clause"] in {"3부 10조", "3부 11조", "3부 12조", "3부 13조", "3부 14조", "3부 17조"}],
    }
    label = {"3부 35조": "계산서 산출 근거 누락", "3부 31조": "카드 전표 세목 누락", "3부 32조": "현금영수증 세목 누락",
             "3부 8조": "할부 결제", "3부 9조": "포인트 적립", "3부 27조": "전용 산출 근거 누락", "3부 18조": "축제 통장 미승인",
             "3부 13조": "참가비가 지출을 초과", "3부 12조": "수입 구분 미확인", "3부 40조": "사업개요서 대상란", "3부 42조": "사업내용 부실"}
    ops = []
    for i in range(3):
        g = groups[i]
        if g:
            txt = ", ".join(f"{f['project']} {label.get(f['clause'], '')}({f['clause']})".replace(" (", "(") for f in sorted(g, key=lambda x: x["clause"]))
            ops.append({"key": OPINION_KEYS[i], "grade": "미흡", "text": f"{txt}이(가) 확인되었습니다."})
        else:
            ops.append({"key": OPINION_KEYS[i], "grade": "양호", "text": "중요한 지적 사항이 없습니다."})
    n_bad = sum(1 for o in ops if o["grade"] == "미흡")
    ops.append({"key": OPINION_KEYS[3], "grade": "미흡" if n_bad >= 2 else "양호",
                "text": "세 영역 중 둘 이상에서 미흡 판정이 있습니다." if n_bad >= 2 else "증빙과 절차는 대체로 기준안을 따랐습니다."})
    return ops
