"""감사 LLM 호출. 에이전트가 아니다: 패킷 하나에 정해진 프롬프트로 2회 호출하고 JSON만 받는다.

모드
- replay(기본): 시연용 재생 모드. 실제 API 없이 규칙 기반 모의 응답을 만든다. 일부러 '인용 불일치'와
  '2회 판정 불일치'를 한 번씩 섞어 검증 단계가 동작하는 모습을 보여 준다(QUIRKS).
- live: AUDITON_LLM=live 이고 ANTHROPIC_API_KEY가 있으면 Anthropic Messages API를 호출한다.
감점은 어떤 모드에서도 출력하지 않는다.
"""
from __future__ import annotations

import json
import os
import re

import httpx

SYSTEM_PROMPT = """너는 한양대학교 정보시스템학과 감사위원회의 감사 보조자다. 감사 패킷만 보고 조항마다 판단한다.
규칙:
1. 판단 기준은 패킷의 기준안 원문과 해당 회계기간 질의·답변뿐이다. 둘이 충돌하면 기준안이 우선한다(4부 15조).
2. 근거는 반드시 패킷 서류의 문장을 글자 그대로 인용한다. 서류에 근거가 없으면 verdict를 "확인 필요"로 한다.
3. 선례(memory)는 '동일한 사례인지'를 고르는 데만 쓴다. 동일한 선례가 없으면 is_new_type을 true로 한다.
4. 숫자 사실(checks, ledger_rows)은 주어진 값을 그대로 쓴다. 감점이나 점수는 절대 출력하지 않는다.
5. 체크리스트 이행 기록은 사실로만 참고하고 기준으로 쓰지 않는다.
출력: {"judgments": [{"clause", "target", "verdict": "충족|미충족|확인 필요", "evidence": [{"doc", "quote"}],
"missing": [], "same_case": {"case_id", "why"} | null, "is_new_type": bool, "question": str | null}]}"""

QUIRKS = {
    # (패킷 제목, 조항, 호출 회차) → 주입할 오류 (재생 모드 전용, 검증 단계 시연용)
    ("과잠 공동구매", "3부 42조", 1): "paraphrase_quote",
    ("MT", "3부 40조", 2): "flip_verdict",
}


def _find_line(docs: list[dict], needles: list[str]) -> tuple[str, str] | None:
    for n in needles:
        if not n:
            continue
        for d in docs:
            for line in d["text"].splitlines():
                if n in line:
                    return d["id"], line.strip()
    return None


def _mock(packet: dict, call_no: int) -> dict:
    out = []
    docs = packet["documents"]
    title = packet["title"]
    ov_doc = next((d for d in docs if d["kind"] == "사업개요서"), None)
    for cl in packet["clauses"]:
        cid = cl["id"]
        cks = [c for c in packet["checks"] if c["clause"] == cid]
        bad = [c for c in cks if c["result"] == "위반"]
        unsure = [c for c in cks if c["result"] == "확인 필요"]
        j = {"clause": cid, "target": title, "verdict": "충족", "evidence": [], "missing": [], "same_case": None,
             "is_new_type": False, "question": None}
        if bad:
            c = bad[0]
            j["verdict"] = "미충족"
            j["target"] = f"{title} / {c['target'] or ''}".rstrip(" /")
            vendor = c["message"].split(" ")[0]
            hit = _find_line(docs, ["③ 산출 근거", "할부", "포인트", vendor]) if cid in ("3부 35조", "3부 8조", "3부 9조") else None
            if cid == "3부 13조":
                hit = _find_line(docs, ["수입 적요"])
            if cid == "3부 27조":
                hit = _find_line(docs, ["사업내용"])
            if hit:
                j["evidence"] = [{"doc": hit[0], "quote": hit[1]}]
            j["missing"] = c["facts"].get("missing", [])
            mem = [m for m in packet["memory"].get(cid, []) if m["same_clause"]]
            if mem:
                j["same_case"] = {"case_id": mem[0]["id"], "why": f"{mem[0]['desc']}와(과) 같은 유형"}
            else:
                j["is_new_type"] = True
                j["question"] = "과거 동일 사례가 없습니다. 감사인단 전원 논의가 필요합니다."
        elif unsure:
            j["verdict"] = "확인 필요"
            j["question"] = unsure[0]["message"] + " — 집행부에 출처를 질의하세요."
        elif cid == "3부 40조" and ov_doc:
            line = next(l for l in ov_doc["text"].splitlines() if l.startswith("대상"))
            j["evidence"] = [{"doc": ov_doc["id"], "quote": line}]
            if "참가자" in line:
                j["verdict"] = "충족"
                j["question"] = "'대상'란이 참여 조건을 드러내는지 해석이 갈립니다."
                mem = [m for m in packet["memory"].get(cid, []) if m["same_clause"]]
                if mem:
                    j["same_case"] = {"case_id": mem[0]["id"], "why": "대상란에 '참가자'로만 기재"}
        elif cid == "3부 42조" and ov_doc:
            line = next(l for l in ov_doc["text"].splitlines() if l.startswith("사업내용"))
            j["evidence"] = [{"doc": ov_doc["id"], "quote": line}]
            if len(line) < 25:
                j["verdict"] = "미충족"
        elif cid in ("3부 18조", "3부 19조", "3부 20조"):
            hit = _find_line(docs, {"3부 18조": ["승인"], "3부 19조": ["선택한 방식"], "3부 20조": ["예금주"]}[cid])
            if hit:
                j["evidence"] = [{"doc": hit[0], "quote": hit[1]}]
        else:
            ok = [c for c in cks if c["result"] == "충족"]
            hit = _find_line(docs, [ok[0]["message"].split(" ")[0]] if ok else []) or (
                (ov_doc["id"], ov_doc["text"].splitlines()[0]) if ov_doc else None)
            if hit:
                j["evidence"] = [{"doc": hit[0], "quote": hit[1]}]
            elif not cks:
                j["evidence"] = []
        q = QUIRKS.get((title, cid, call_no))
        if q == "paraphrase_quote" and j["evidence"]:
            j["evidence"][0]["quote"] = j["evidence"][0]["quote"].replace("진행 및 배부", "진행 완료 후 전원 배부")
        if q == "flip_verdict":
            j["verdict"] = "미충족" if j["verdict"] == "충족" else "충족"
            if j["verdict"] == "미충족":
                mem = [m for m in packet["memory"].get(cid, []) if m["same_clause"] and m["disposition"]["type"] != "없음"]
                if mem:
                    j["same_case"] = {"case_id": mem[0]["id"], "why": "대상란에 참여 조건이 드러나지 않음"}
        out.append(j)
    return {"judgments": out}


def _packet_prompt(packet: dict) -> str:
    slim = {k: packet[k] for k in ("title", "clauses", "inquiries", "documents", "checks", "obligations")}
    slim["ledger_rows"] = [{k: r[k] for k in ("code", "date", "bank_desc", "content", "in", "out", "method", "class", "items", "note")}
                           for r in packet["ledger_rows"]]
    slim["memory"] = {k: [{x: m[x] for x in ("id", "period", "clause", "desc", "tags", "reason")} for m in v]
                      for k, v in packet["memory"].items()}
    return json.dumps(slim, ensure_ascii=False)


def _live(packet: dict) -> dict:
    key = os.environ["ANTHROPIC_API_KEY"]
    model = os.environ.get("AUDIT_MODEL", "claude-sonnet-5-5")
    body = {"model": model, "max_tokens": 4096, "temperature": 0, "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": "감사 패킷(JSON):\n" + _packet_prompt(packet) + "\n\nJSON만 출력하라."}]}
    r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=120,
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"])
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


def mode() -> str:
    return "live" if os.environ.get("AUDITON_LLM") == "live" and os.environ.get("ANTHROPIC_API_KEY") else "replay"


def call(packet: dict, call_no: int) -> dict:
    """JSON 형식이 깨지면 1회 재시도, 그래도 실패하면 모든 조항을 '확인 필요'로 돌려준다."""
    if mode() == "replay":
        return {**_mock(packet, call_no), "mode": "replay"}
    for _ in range(2):
        try:
            res = _live(packet)
            if isinstance(res.get("judgments"), list):
                return {**res, "mode": "live"}
        except Exception:  # noqa: BLE001
            continue
    return {"judgments": [{"clause": c["id"], "target": packet["title"], "verdict": "확인 필요", "evidence": [], "missing": [],
                           "same_case": None, "is_new_type": False, "question": "LLM 응답 형식 오류"} for c in packet["clauses"]],
            "mode": "live-error"}
