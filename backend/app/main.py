"""Auditon API (FastAPI). 실행: cd backend && uvicorn app.main:app --reload --port 8000

데이터: data/synthetic/<AUDITON_DATASET>/dataset.json (기본 tune). 사용자 결정은 backend/var/state.json에 저장.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from fastapi import Body, FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from audit import engine as audit_engine, memory  # noqa: E402
from audit.llm import mode as llm_mode  # noqa: E402
from checklist import engine as checklist_engine  # noqa: E402
from core.kijun import clause_text, load_clauses  # noqa: E402
from ledger import export  # noqa: E402
from ledger.build import build  # noqa: E402
from ocr import engine as ocr  # noqa: E402

ROOT = BACKEND.parent
DATASET = os.environ.get("AUDITON_DATASET", "tune")
if DATASET == "eval" and os.environ.get("AUDITON_ALLOW_EVAL") != "1":
    raise SystemExit("평가용 세트는 개발 중 열지 않습니다. 최종 측정 때만 AUDITON_ALLOW_EVAL=1로 실행하세요.")
DS_PATH = ROOT / "data" / "synthetic" / DATASET / "dataset.json"
STATE_PATH = BACKEND / "var" / f"state-{DATASET}.json"
LOCK = threading.Lock()

app = FastAPI(title="Auditon API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def load_ds() -> dict:
    return json.loads(DS_PATH.read_text(encoding="utf-8"))


DS = load_ds()


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def dataset() -> dict:
    """업로드한 영수증·내역 등 런타임 추가분을 반영한 데이터셋."""
    st = load_state()
    ds = copy.deepcopy(DS)
    ds["receipts"] += st.get("new_receipts", [])
    for r in st.get("new_receipts", []):
        ds["documents"].append({"id": f"증빙-{r['id']}", "kind": "증빙", "project": r["project"],
                                "title": f"{r['kind']} · {r['vendor']}", "text": r.get("ocr_text", "")})
    for tr in ds["transfers"]:
        k = f"{tr['date']}|{tr['from']}|{tr['to']}"
        if k in st.get("transfer_notes", {}):
            tr["note"] = st["transfer_notes"][k]
    return ds


def ledger_now():
    ds = dataset()
    return ds, build(ds, load_state())


# ---------------- 메타·기준안 ----------------
@app.get("/api/meta")
def meta():
    st = load_state()
    return {**DS["meta"], "accounts": DS["accounts"], "dataset": DATASET, "llm_mode": llm_mode(),
            "ocr_engine": ocr.engine_name(), "published": bool(st.get("published")), "today": st.get("today")}


@app.get("/api/kijun")
def kijun():
    return [c.to_dict() for c in load_clauses().values()]


@app.get("/api/kijun/{cid:path}")
def kijun_one(cid: str):
    t = clause_text(cid)
    if not t:
        raise HTTPException(404, "없는 조항")
    base = cid.split(" ")[0] + " " + cid.split(" ")[1]
    c = load_clauses().get(base)
    return {"id": cid, "text": t, "title": c.title if c else "", "full": c.text if c else t}


@app.get("/api/cases")
def cases():
    return {"cases": DS["cases"], "inquiries": DS["inquiries"],
            "criteria": memory.deduction_criteria(DS["cases"], DS["meta"]["period"]["id"])}


# ---------------- 체크리스트 (기능 3) ----------------
@app.get("/api/checklist")
def checklist():
    st = load_state()
    return checklist_engine.schedule(DS, st, st.get("today"))


@app.post("/api/checklist/{oid:path}/done")
def checklist_done(oid: str, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("obligation_done", {})[oid] = date.today().isoformat() if body.get("done") else None
        save_state(st)
    return {"ok": True}


@app.post("/api/checklist/{oid:path}/lead")
def checklist_lead(oid: str, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("lead_days", {})[oid] = int(body["days"])
        save_state(st)
    return {"ok": True}


# ---------------- 영수증 (기능 1) ----------------
@app.get("/api/receipts")
def receipts():
    ds, led = ledger_now()
    st = load_state()
    rec = led["reconcile"]
    state_of = {}
    for p in rec["pairs"]:
        for r in p["rc"]:
            state_of[r] = {"status": p["status"], "tx": p["tx"]}
    out = []
    for r in ds["receipts"]:
        r = {**r, **st.get("receipt_edits", {}).get(r["id"], {})}
        parsed = ocr.parse(r.get("ocr_text", ""))
        out.append({**r, "parsed": parsed, "self_check": ocr.self_check({**parsed, "amount": r["amount"], "has_items": r["has_items"]}),
                    "match": state_of.get(r["id"], {"status": "통장에 없는 영수증" if r["id"] in rec["not_in_bank"] else "미매칭"})})
    return {"receipts": out, "projects": [p["name"] for p in ds["projects"]], "engine": ocr.engine_name()}


@app.patch("/api/receipts/{rid}")
def receipt_edit(rid: str, body: dict = Body(...)):
    allowed = {"vendor", "date", "amount", "project", "kind", "pay", "has_items", "installment", "points", "invoice"}
    with LOCK:
        st = load_state()
        st.setdefault("receipt_edits", {}).setdefault(rid, {}).update({k: v for k, v in body.items() if k in allowed})
        save_state(st)
    return {"ok": True}


@app.post("/api/receipts/upload")
async def receipt_upload(file: UploadFile = File(...), project: str = "", text: str = ""):
    data = await file.read()
    ocr_text = text or None
    if not ocr_text and file.content_type and file.content_type.startswith("text"):
        ocr_text = data.decode("utf-8", "ignore")
    if not ocr_text:
        ocr_text = ocr.read_image(data)
    if not ocr_text:
        return {"ok": False, "manual": True, "message": "로컬 OCR 엔진(EasyOCR/PaddleOCR)이 설치되지 않아 직접 입력이 필요합니다."}
    f = ocr.parse(ocr_text)
    with LOCK:
        st = load_state()
        n = len(DS["receipts"]) + len(st.get("new_receipts", [])) + 1
        r = {"id": f"R{n:03d}", "project": project or "미지정", "date": f.get("date", date.today().isoformat()),
             "vendor": f.get("vendor", ""), "amount": f.get("amount", 0), "items": f["items"], "has_items": f["has_items"],
             "kind": "카드전표" if f.get("card_last4") else "현금영수증", "pay": "카드" if f.get("card_last4") else "계좌이체",
             "card_last4": f.get("card_last4"), "installment": f.get("installment", 0), "points": f.get("points", 0),
             "invoice": None, "attachments": [], "ocr_text": ocr_text,
             "confidence": {"date": 0.9, "vendor": 0.7, "amount": 0.95, "items": 0.8}}
        st.setdefault("new_receipts", []).append(r)
        save_state(st)
    return {"ok": True, "receipt": r, "self_check": ocr.self_check(f)}


# ---------------- 대사·감사자료 ----------------
@app.get("/api/reconcile")
def reconcile_view():
    ds, led = ledger_now()
    tx_by = {t["id"]: t for t in ds["transactions"]}
    rc_by = {r["id"]: r for r in ds["receipts"]}
    return {"reconcile": led["reconcile"], "transactions": tx_by, "receipts": rc_by, "numbering": led["numbering"]}


@app.post("/api/reconcile/decide")
def reconcile_decide(body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("pair_decisions", {})[body["key"]] = body["decision"]
        save_state(st)
    return {"ok": True}


@app.post("/api/income/{tx}")
def income_set(tx: str, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("income_overrides", {})[tx] = {"project": body.get("project"), "class": body["class"]}
        save_state(st)
    return {"ok": True}


@app.post("/api/transfer-note")
def transfer_note(body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("transfer_notes", {})[body["key"]] = body["note"]
        save_state(st)
    return {"ok": True}


@app.get("/api/ledger")
def ledger_view():
    ds, led = ledger_now()
    return {"ledgers": led["ledgers"], "projects": led["projects"], "checks": led["checks"], "accounts": ds["accounts"],
            "transfers": ds["transfers"]}


@app.get("/api/export/ledger/{account}.xlsx")
def export_ledger(account: str):
    ds, led = ledger_now()
    if account not in led["ledgers"]:
        raise HTTPException(404)
    name = "총거래장부_학생회비통장.xlsx" if account == "main" else "총거래장부_축제통장.xlsx"
    return Response(export.ledger_xlsx(ds, led, account), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_q(name)}"})


@app.get("/api/export/statement.xlsx")
def export_statement():
    ds, led = ledger_now()
    return Response(export.statement_xlsx(ds, led), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_q('수입지출내역서.xlsx')}"})


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


# ---------------- 감사 판단 (기능 2) ----------------
RUN_CACHE: dict = {}


def audit_result(force: bool = False) -> dict | None:
    st = load_state()
    if not st.get("audit_ran") and not force:
        return None
    ds, led = ledger_now()
    key = json.dumps([st.get("pair_decisions"), st.get("income_overrides"), st.get("receipt_edits"), st.get("transfer_notes"),
                      len(st.get("new_receipts", []))], sort_keys=True, default=str)
    if force or RUN_CACHE.get("key") != key:
        cl = checklist_engine.schedule(DS, st, st.get("today"))
        status = {e["name"]: [{"task": i["task"], "done": bool(i["done"]), "clauses": i["clauses"]} for i in e["items"]] for e in cl["events"]}
        RUN_CACHE.update(key=key, res=audit_engine.run(ds, led, status), led=led, ds=ds)
    res = RUN_CACHE["res"]
    findings = audit_engine.apply_decisions(res["findings"], st.get("finding_decisions", {}))
    return {"res": res, "findings": findings, "totals": audit_engine.totals(findings), "ds": RUN_CACHE["ds"], "led": RUN_CACHE["led"]}


@app.post("/api/audit/run")
def audit_run():
    with LOCK:
        st = load_state()
        st["audit_ran"] = datetime.now().isoformat(timespec="seconds")
        save_state(st)
    r = audit_result(force=True)
    return {"ok": True, "totals": r["totals"], "mode": r["res"]["mode"],
            "steps": [{"packet": p["id"], "title": p["title"], "clauses": len(p["clauses"])} for p in r["res"]["packets"]]}


@app.get("/api/audit")
def audit_view():
    r = audit_result()
    if not r:
        return {"ran": False}
    st = load_state()
    cases_by = {c["id"]: c for c in r["ds"]["cases"]}
    packets = [{k: p[k] for k in ("id", "title", "projects", "clauses", "inquiries", "documents", "checks", "obligations", "memory")}
               | {"ledger_rows": p["ledger_rows"]} for p in r["res"]["packets"]]
    return {"ran": True, "ran_at": st.get("audit_ran"), "mode": r["res"]["mode"], "findings": r["findings"], "totals": r["totals"],
            "packets": packets, "cases": cases_by, "checks": r["led"]["checks"]}


@app.post("/api/audit/finding/{fid:path}")
def finding_decide(fid: str, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        d = st.setdefault("finding_decisions", {}).setdefault(fid, {})
        d.update({k: v for k, v in body.items() if k in {"verdict", "disposition", "source", "confirmed", "note", "public_text"}})
        save_state(st)
    return {"ok": True}


# ---------------- 감사보고서·이의·공시 ----------------
def _plus(d: str, n: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


@app.get("/api/report")
def report():
    r = audit_result()
    st = load_state()
    rep = st.get("report", {})
    meta_ = DS["meta"]
    audit_end = meta_["audit"]["end"]
    sent = rep.get("sent")
    findings = r["findings"] if r else []
    deadlines = {
        "send_by": _plus(audit_end, 3),
        "objection_until": _plus(sent, 3) if sent else None,
        "answer_by": _plus(sent, 7) if sent else None,
        "publish_by": _plus(rep.get("opinion_published") or _plus(sent, 7), 30) if sent else None,
    }
    return {
        "dept": meta_["dept"], "period": meta_["period"], "audit": meta_["audit"],
        "fields": {"target": f"{meta_['dept']} 학생회 집행부 · 책임자: 학생회장(전반적 책임), 회계 담당(제한적 책임)",
                   "scope": f"{meta_['period']['label']} 학생회비 통장·축제 부스 통장의 모든 수입 및 지출(3부 2조)",
                   "period": f"{meta_['audit']['start']} ~ {meta_['audit']['end']}",
                   "hours": rep.get("hours", {"total": 22, "senior": 12, "auditors": [{"name": "감사인 A(선임)", "h": 7}, {"name": "감사인 B(선임)", "h": 5}, {"name": "감사인 C", "h": 6}, {"name": "감사인 D", "h": 4}]}),
                   "inquiries": DS["inquiries"]},
        "opinions": rep.get("opinions") or audit_engine.draft_opinions(findings),
        "totals": r["totals"] if r else None,
        "findings": [f for f in findings if f["verdict"] == "미충족"],
        "unconfirmed": sum(1 for f in findings if not f.get("confirmed") and f["verdict"] != "충족"),
        "sent": sent, "objections": st.get("objections", []), "deadlines": deadlines,
        "published": st.get("published"),
    }


@app.post("/api/report")
def report_update(body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("report", {}).update({k: v for k, v in body.items() if k in {"opinions", "hours"}})
        save_state(st)
    return {"ok": True}


@app.post("/api/report/send")
def report_send():
    with LOCK:
        st = load_state()
        st.setdefault("report", {})["sent"] = _plus(DS["meta"]["audit"]["end"], 2)  # 감사 종료 후 3일 이내(4부 19조)
        save_state(st)
    return {"ok": True}


@app.post("/api/objections")
def objection_add(body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st.setdefault("objections", []).append({"finding": body.get("finding"), "text": body["text"], "answer": None,
                                                 "at": date.today().isoformat()})
        save_state(st)
    return {"ok": True}


@app.post("/api/objections/{i}/answer")
def objection_answer(i: int, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        st["objections"][i]["answer"] = body["answer"]
        save_state(st)
    return {"ok": True}


@app.post("/api/publish")
def publish():
    """학생회 집행부의 전자 공시(3부 70·71조). 한 번 게시하면 수정할 수 없고, 새 판만 추가할 수 있다."""
    rep = report()
    r = audit_result()
    if not r:
        raise HTTPException(400, "감사 판단을 먼저 실행하세요.")
    pend = [f for f in r["findings"] if f["verdict"] == "확인 필요" or (f.get("disposition") or {}).get("type") == "신규 유형"]
    if pend:
        raise HTTPException(400, f"확정되지 않은 항목 {len(pend)}건(확인 필요·신규 유형)이 있습니다.")
    if any(o["answer"] is None for o in rep["objections"]):
        raise HTTPException(400, "답변하지 않은 이의가 있습니다(4부 22조).")
    snap = {
        "version": len(load_state().get("published_versions", [])) + 1,
        "dept": DS["meta"]["dept"], "period": DS["meta"]["period"], "published_at": date.today().isoformat(),
        "keep_until": _plus(date.today().isoformat(), 365 * 5), "publisher": "정보시스템학과 학생회 집행부",
        "totals": r["totals"], "opinions": rep["opinions"], "objections": rep["objections"],
        "findings": [{"clause": f["clause"], "project": f["project"], "disposition": f["disposition"],
                      "source": f["disposition_source"], "text": f.get("public_text") or _public_text(f)}
                     for f in r["findings"] if f["verdict"] == "미충족"],
        "history": DS["history"],
    }
    with LOCK:
        st = load_state()
        st.setdefault("published_versions", []).append(snap)
        st["published"] = snap["published_at"]
        save_state(st)
    return {"ok": True, "version": snap["version"]}


PUBLIC_TEXT = {
    "3부 35조": "{project} 지출 계산서에 견적 산출 근거(세목)가 빠졌어요.",
    "3부 13조": "{project} 참가비가 실제 지출보다 많이 걷혔어요.",
    "3부 8조": "{project} 비용을 할부로 결제했어요.",
    "3부 9조": "{project} 결제에서 포인트를 적립했어요.",
    "3부 27조": "{project} 물품 전용 처리에 산출 근거가 없었어요.",
    "3부 31조": "카드 결제 증빙(세목)이 부족했어요.",
    "3부 40조": "{project} 사업개요서에 참여 조건이 드러나지 않았어요.",
    "3부 42조": "{project} 사업개요서의 사업내용이 부실했어요.",
    "3부 12조": "출처를 확인하지 못한 입금이 있었어요.",
}


def _public_text(f: dict) -> str:
    return PUBLIC_TEXT.get(f["clause"], "{project} 관련 지적 사항").format(project=f["project"])


# ---------------- 학생 공개 페이지 ----------------
@app.get("/api/public")
def public_list():
    st = load_state()
    vers = st.get("published_versions", [])
    items = []
    me = vers[-1] if vers else None
    items.append({"dept": DS["meta"]["dept"], "period": DS["meta"]["period"]["id"], "published": bool(me),
                  "total": me["totals"]["total"] if me else None, "warnings": me["totals"]["warnings"] if me else None,
                  "prev": DS["history"][-1]["total"], "history": DS["history"] + ([{"period": DS["meta"]["period"]["id"], "total": me["totals"]["total"], "warnings": me["totals"]["warnings"]}] if me else [])})
    for o in DS["other_depts"]:
        cur = o["history"][-1]
        items.append({"dept": o["dept"], "period": cur["period"], "published": True, "total": cur["total"], "warnings": cur["warnings"],
                      "prev": o["history"][-2]["total"], "history": o["history"], "sample": True})
    items.sort(key=lambda x: x["dept"])
    return {"period": DS["meta"]["period"], "items": items}


@app.get("/api/public/{dept}")
def public_dept(dept: str):
    st = load_state()
    if dept == DS["meta"]["dept"]:
        vers = st.get("published_versions", [])
        if not vers:
            raise HTTPException(404, "아직 공시되지 않았습니다.")
        return {**vers[-1], "versions": len(vers)}
    o = next((x for x in DS["other_depts"] if x["dept"] == dept), None)
    if not o:
        raise HTTPException(404)
    cur = o["history"][-1]
    return {"dept": dept, "period": DS["meta"]["period"], "sample": True, "totals": {"total": cur["total"], "warnings": cur["warnings"],
            "warning_points": max(0, cur["warnings"] - 2), "case_points": cur["total"] - max(0, cur["warnings"] - 2)},
            "history": o["history"][:-1], "findings": [], "opinions": [], "objections": [], "publisher": f"{dept} 학생회 집행부",
            "published_at": "2026-08-14", "keep_until": "2031-08-14"}


@app.post("/api/reset")
def reset():
    with LOCK:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
    RUN_CACHE.clear()
    return {"ok": True}


# ---------------- 프론트엔드 정적 파일 ----------------
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
