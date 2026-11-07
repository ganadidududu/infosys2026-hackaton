"""Auditon API (FastAPI). 실행: cd backend && uvicorn app.main:app --reload --port 8000

데이터: data/synthetic/<AUDITON_DATASET>/dataset.json (기본 tune). 사용자 결정은 backend/var/state.json에 저장.
"""
from __future__ import annotations

import copy
import io
import json
import os
import re
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
from ledger import csv_import, docx_export, export  # noqa: E402
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
    lc = st.get("ledger_csv")
    if lc and lc.get("mapping") and not csv_import.validate(lc["mapping"]):
        h, b = csv_import.read_rows(lc["text"])
        ds["transactions"], _ = csv_import.to_transactions(h, b, lc["mapping"])
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
def schedule_ds(st: dict) -> dict:
    ds = dict(DS)
    ds["schedule"] = DS["schedule"] + st.get("custom_events", [])
    return ds


@app.get("/api/checklist")
def checklist():
    st = load_state()
    res = checklist_engine.schedule(schedule_ds(st), st, st.get("today"))
    custom = {e["id"] for e in st.get("custom_events", [])}
    for e in res["events"]:
        e["custom"] = e["id"] in custom
    res["events"].sort(key=lambda e: e["date"])
    res["types"] = list(checklist_engine.TYPE_GROUPS) 
    res["flags"] = list(checklist_engine.FLAG_GROUPS)
    res["bar"] = schedule_bar(st)
    return res


def schedule_bar(st: dict) -> list[dict]:
    """학기 일정 바: 회계기간 → 감사 → 감사 후 절차(활성 감사 기록 기준)."""
    m = DS["meta"]
    p, a = m["period"], m["audit"]
    today = date.today().isoformat()
    rec = st.get("records", {}).get(st.get("active_record") or "", {})
    rep = rec.get("report", {})
    sent = rep.get("sent")
    objs = rec.get("objections", [])
    end = date.fromisoformat(p["end"])
    return [
        {"k": "회계기간 시작", "d": p["start"], "done": p["start"] <= today, "c": "3부 1조"},
        {"k": "감사 안내 공문", "d": (end - timedelta(days=30)).isoformat(), "done": (end - timedelta(days=30)).isoformat() <= today, "c": "4부 13조"},
        {"k": "회계기간 종료", "d": p["end"], "done": p["end"] <= today, "c": "3부 1조"},
        {"k": "감사자료 제출", "d": a["start"], "done": bool(rec.get("files")), "c": "3부 61조"},
        {"k": "감사 종료", "d": a["end"], "done": bool(rec.get("ran")), "c": ""},
        {"k": "보고서 송부", "d": sent or f"기한 {_plus(a['end'], 3)}", "done": bool(sent), "c": "4부 19조"},
        {"k": "이의 접수(3일)", "d": f"~ {_plus(sent, 3)}" if sent else "송부 후 3일", "done": bool(sent), "c": "4부 20조"},
        {"k": "답변·전문 공시(7일)", "d": f"~ {_plus(sent, 7)}" if sent else "송부 후 7일", "done": bool(sent) and all(o.get("answer") for o in objs), "c": "4부 21조"},
        {"k": "학생회 전자 공시", "d": rec.get("published") or "공시 후 1개월", "done": bool(rec.get("published")), "c": "3부 70조"},
    ]


@app.post("/api/schedule/events")
def schedule_add(body: dict = Body(...)):
    name = (body.get("name") or "").strip()
    try:
        date.fromisoformat(body.get("date", ""))
    except ValueError:
        raise HTTPException(400, "날짜 형식은 YYYY-MM-DD입니다")
    if not name:
        raise HTTPException(400, "행사명을 입력하세요")
    with LOCK:
        st = load_state()
        ev = st.setdefault("custom_events", [])
        ev.append({"id": f"U{len(ev)+1}-{datetime.now().strftime('%H%M%S%f')[:9]}", "name": name, "type": body.get("type") or "일반 행사",
                   "date": body["date"], "flags": body.get("flags") or []})
        save_state(st)
    return {"ok": True}


@app.delete("/api/schedule/events/{eid}")
def schedule_del(eid: str):
    with LOCK:
        st = load_state()
        st["custom_events"] = [e for e in st.get("custom_events", []) if e["id"] != eid]
        save_state(st)
    return {"ok": True}


@app.post("/api/schedule/upload")
async def schedule_upload(file: UploadFile = File(...)):
    """학과 일정 CSV: 행사명, 날짜, 유형(선택), 특이사항(선택; '예약금', '세목 불가 업체'를 ; 또는 / 로 구분)."""
    import csv as _csv
    text = csv_import.decode(await file.read())
    rows = [r for r in _csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        raise HTTPException(400, "빈 파일입니다")
    head = [c.strip() for c in rows[0]]
    idx = lambda *ks: next((i for i, h in enumerate(head) if any(k in h for k in ks)), None)  # noqa: E731
    i_name, i_date, i_type, i_flag = idx("행사", "이름", "사업", "name"), idx("날짜", "일자", "date"), idx("유형", "종류", "type"), idx("특이", "메모", "flag")
    if i_name is None or i_date is None:
        raise HTTPException(400, "'행사명'과 '날짜' 열이 필요합니다")
    added, skipped = 0, []
    types = set(checklist_engine.TYPE_GROUPS)
    with LOCK:
        st = load_state()
        ev = st.setdefault("custom_events", [])
        for n, r in enumerate(rows[1:], start=2):
            d = csv_import.to_date(r[i_date] if i_date < len(r) else "")
            nm = r[i_name].strip() if i_name < len(r) else ""
            if not d or not nm:
                skipped.append(n)
                continue
            tp = r[i_type].strip() if i_type is not None and i_type < len(r) else ""
            fl = [f.strip() for f in re.split(r"[;/,]", r[i_flag])] if i_flag is not None and i_flag < len(r) else []
            ev.append({"id": f"U{len(ev)+1}-{n}{datetime.now().strftime('%M%S')}", "name": nm, "type": tp if tp in types else "일반 행사",
                       "date": d, "flags": [f for f in fl if f in checklist_engine.FLAG_GROUPS]})
            added += 1
        save_state(st)
    return {"ok": True, "added": added, "skipped": skipped}


@app.get("/api/schedule/sample.csv")
def schedule_sample():
    body = "행사명,날짜,유형,특이사항\n학과 체육대회,2026-05-28,참가비 사업,예약금\n졸업생 홈커밍,2026-06-20,일반 행사,\n학과 굿즈 판매,2026-04-15,물품 판매·공동구매,\n"
    return Response(("\ufeff" + body).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_q('학과일정_예시.csv')}"})


# ---------------- (수입·지출) 내역서: 기중 거래 장부 CSV → 수입/지출내역서 ----------------
@app.get("/api/statement")
def statement_view():
    """왼쪽: 엑셀(CSV) 원본 + 열 매핑, 오른쪽: 변환된 수입/지출내역서 페이지. 행 ↔ 페이지를 서로 잇는다."""
    st = load_state()
    lc = st.get("ledger_csv")
    ds, led = ledger_now()
    if lc:
        text, fname, mapping, source = lc["text"], lc["filename"], lc["mapping"], "upload"
    else:
        text, fname, source = csv_import.sample_csv(DS), "기중거래장부_예시.csv", "sample"
        h0, b0 = csv_import.read_rows(text)
        mapping = csv_import.auto_map(h0, b0)
    h, b = csv_import.read_rows(text)
    errs = csv_import.validate(mapping)
    ctx, sk = csv_import.to_transactions(h, b, mapping) if not errs else ([], [])
    # 원본 행 번호(본문 기준 0부터) 찾기: 날짜·통장내역·금액이 같은 행
    key_to_row = {}
    for t in ctx:
        key_to_row.setdefault((t["date"], t["desc"], t["in"], t["out"]), int(t["id"][1:]) - 1)
    tx_by = {t["id"]: t for t in ds["transactions"]}
    rows = [r for acc in ds["accounts"] for r in led["ledgers"][acc["id"]] if r["tx"] or r.get("transfer")]
    for r in rows:
        t = tx_by.get(r["tx"]) if r["tx"] else None
        r["src_row"] = key_to_row.get((t["date"], t["desc"], t["in"], t["out"])) if t else None
    imgs = {f.stem for f in RECEIPT_IMG.glob("*")} if RECEIPT_IMG.exists() else set()
    rcs = {r["id"]: {"items": r["items"], "ocr_text": r.get("ocr_text", ""), "kind": r["kind"], "vendor": r["vendor"], "image": r["id"] in imgs,
                     **st.get("receipt_edits", {}).get(r["id"], {})} for r in ds["receipts"]}
    return {
        "fields": csv_import.FIELDS,
        "csv": {"filename": fname, "source": source, "header": h, "body": b, "mapping": mapping, "errors": errs,
                "parsed": len(ctx), "skipped": sk[:50]},
        "statement": {"rows": rows, "receipts": rcs, "counts": led["reconcile"]["counts"]},
    }


@app.post("/api/statement/upload")
async def statement_upload(file: UploadFile = File(...)):
    raw = await file.read()
    name = (file.filename or "").lower()
    text = csv_import.xlsx_to_csv(raw) if name.endswith((".xlsx", ".xlsm")) else csv_import.decode(raw)
    h, b = csv_import.read_rows(text)
    if not h or not b:
        raise HTTPException(400, "파일에서 표를 찾지 못했습니다")
    m = csv_import.auto_map(h, b)
    with LOCK:
        st = load_state()
        st["ledger_csv"] = {"filename": file.filename, "text": text, "mapping": m, "auto": m}
        st.pop("pair_decisions", None)
        st.pop("income_overrides", None)
        save_state(st)
    return {"ok": True, "mapping": m, "errors": csv_import.validate(m)}


@app.post("/api/statement/mapping")
def statement_mapping(body: dict = Body(...)):
    """body: {field: col_index | null}"""
    with LOCK:
        st = load_state()
        lc = st.get("ledger_csv")
        if not lc:
            text = csv_import.sample_csv(DS)
            h0, b0 = csv_import.read_rows(text)
            lc = st["ledger_csv"] = {"filename": "기중거래장부_예시.csv", "text": text, "mapping": csv_import.auto_map(h0, b0)}
        h, _ = csv_import.read_rows(lc["text"])
        m = dict(lc["mapping"])
        for f, col in body.items():
            if f not in csv_import.FIELDS:
                continue
            m = {k: v for k, v in m.items() if not (col is not None and v["col"] == col)}
            if col is None:
                m.pop(f, None)
            else:
                m[f] = {"col": int(col), "header": h[int(col)], "confidence": 1.0, "manual": True}
        lc["mapping"] = m
        save_state(st)
    return {"ok": True, "errors": csv_import.validate(m)}


@app.delete("/api/statement")
def statement_clear():
    with LOCK:
        st = load_state()
        st.pop("ledger_csv", None)
        save_state(st)
    return {"ok": True}


@app.get("/api/statement/sample.csv")
def statement_sample():
    return Response(("\ufeff" + csv_import.sample_csv(DS)).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_q('기중거래장부_예시.csv')}"})


@app.get("/api/export/statement.docx")
def export_statement_docx():
    ds, led = ledger_now()
    st = load_state()
    rcs = {r["id"]: {**r, **st.get("receipt_edits", {}).get(r["id"], {})} for r in ds["receipts"]}
    return Response(docx_export.statement_docx(ds, led, rcs, RECEIPT_IMG),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_q('수입지출내역서.docx')}"})


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


RECEIPT_IMG = BACKEND / "var" / "files" / "receipts"


@app.get("/api/receipts/{rid}/image")
def receipt_image(rid: str):
    f = next(iter(sorted(RECEIPT_IMG.glob(f"{rid}.*"))), None) if RECEIPT_IMG.exists() else None
    if not f:
        raise HTTPException(404)
    return FileResponse(f)


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
    if file.content_type and file.content_type.startswith("image"):
        RECEIPT_IMG.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename or "x.jpg").suffix.lower() or ".jpg"
        (RECEIPT_IMG / f"{r['id']}{ext}").write_bytes(data)
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


# ---------------- 모의 채점: 감사 기록 ----------------
# 감사자료 슬롯 (3부 60·65·66조). required=True인 슬롯이 모두 초록이어야 '제출 완료'.
SLOTS = [
    {"key": "ledger", "label": "엑셀 장부(총거래장부)", "hint": ".xlsx · .csv — CSV면 거래를 읽어 채점에 사용", "required": True, "clause": "3부 56조"},
    {"key": "statement", "label": "수입/지출내역서", "hint": ".docx · .xlsx · .pdf", "required": True, "clause": "3부 49조"},
    {"key": "overview", "label": "사업개요서", "hint": "사업별 개요서 묶음", "required": True, "clause": "3부 39조"},
    {"key": "bankcopy", "label": "통장사본", "hint": "학생회비·축제 통장", "required": True, "clause": "3부 65조"},
    {"key": "history", "label": "과거거래내역서", "hint": "은행 발급본", "required": True, "clause": "3부 29조"},
    {"key": "evidence", "label": "증빙자료(영수증·계산서·이체내역서)", "hint": "영수증함과 연동", "required": True, "clause": "3부 31조"},
    {"key": "cover", "label": "표지·원본대조필", "hint": "자치기구명·회계기간·감사명칭", "required": True, "clause": "3부 63조"},
    {"key": "inquiry", "label": "질의·답변 기록", "hint": "선택", "required": False, "clause": "4부 15조"},
]
FILES = BACKEND / "var" / "files"


def _past_records() -> list[dict]:
    """지난 회계기간 감사 기록(요약만, 읽기 전용)."""
    out = []
    for h in DS["history"]:
        y, n = h["period"].split("-")
        cs = [c for c in DS["cases"] if c["dept"] == DS["meta"]["dept"] and c["period"] == h["period"]]
        out.append({"id": f"past-{h['period']}", "title": f"{y}년 제{n}차 정기감사", "dept": DS["meta"]["dept"], "period": h["period"],
                    "created": f"{y}-{'07' if n == '1' else '01'}-1{n}", "status": "완료", "readonly": True,
                    "summary": {"total": h["total"], "warnings": h["warnings"], "score": 100 - h["total"],
                                "cases": [{"clause": c["clause"], "desc": c["desc"], "disposition": c["disposition"]} for c in cs]}})
    return out


def records_all(st: dict) -> list[dict]:
    return _past_records() + list(st.get("records", {}).values())


def get_record(st: dict, rid: str) -> dict:
    r = st.get("records", {}).get(rid) or next((x for x in _past_records() if x["id"] == rid), None)
    if not r:
        raise HTTPException(404, "감사 기록이 없습니다")
    return r


def record_dataset(rec: dict | None) -> dict:
    ds = dataset()
    f = (rec or {}).get("files", {}).get("ledger")
    if f and f.get("transactions"):
        ds["transactions"] = f["transactions"]
    return ds


RUN_CACHE: dict = {}


def active_id(st: dict) -> str | None:
    return st.get("active_record")


def audit_result(rid: str | None = None, force: bool = False) -> dict | None:
    st = load_state()
    rid = rid or active_id(st)
    rec = st.get("records", {}).get(rid) if rid else None
    if not rec or (not rec.get("ran") and not force):
        return None
    ds = record_dataset(rec)
    led = build(ds, st)
    key = json.dumps([rid, st.get("pair_decisions"), st.get("income_overrides"), st.get("receipt_edits"), st.get("transfer_notes"),
                      len(st.get("new_receipts", [])), st.get("ledger_csv", {}).get("mapping"), (rec.get("files", {}).get("ledger") or {}).get("name")],
                     sort_keys=True, default=str)
    c = RUN_CACHE.get(rid)
    if force or not c or c["key"] != key:
        cl = checklist_engine.schedule(schedule_ds(st), st, st.get("today"))
        status = {e["name"]: [{"task": i["task"], "done": bool(i["done"]), "clauses": i["clauses"]} for i in e["items"]] for e in cl["events"]}
        c = RUN_CACHE[rid] = {"key": key, "res": audit_engine.run(ds, led, status), "led": led, "ds": ds}
    findings = audit_engine.apply_decisions(c["res"]["findings"], rec.get("decisions", {}))
    return {"res": c["res"], "findings": findings, "totals": audit_engine.totals(findings), "ds": c["ds"], "led": c["led"], "rec": rec, "rid": rid}


def _score(t: dict) -> dict:
    return {"score": 100 - t["total"], "max": 100, "formula": "100 − 총 감점(사례 감점 + 경고 감점)",
            "pending": t["pending_new"] + t["pending_check"]}


def _slots_view(rec: dict) -> list[dict]:
    files = rec.get("files", {})
    return [{**s, "file": {k: v for k, v in (files.get(s["key"]) or {}).items() if k != "transactions"} or None} for s in SLOTS]


@app.get("/api/records")
def records_list():
    st = load_state()
    out = []
    for r in records_all(st):
        item = {k: r[k] for k in ("id", "title", "dept", "period", "created", "status") if k in r} | {"readonly": r.get("readonly", False), "memo": r.get("memo", "")}
        if r.get("readonly"):
            item["score"], item["total"], item["warnings"] = r["summary"]["score"], r["summary"]["total"], r["summary"]["warnings"]
        else:
            res = audit_result(r["id"]) if r.get("ran") else None
            item["submitted"] = sum(1 for s in SLOTS if s["required"] and r.get("files", {}).get(s["key"]))
            item["required"] = sum(1 for s in SLOTS if s["required"])
            if res:
                item["score"], item["total"], item["warnings"] = _score(res["totals"])["score"], res["totals"]["total"], res["totals"]["warnings"]
                item["pending"] = res["totals"]["pending_new"] + res["totals"]["pending_check"]
        out.append(item)
    out.sort(key=lambda x: x["created"], reverse=True)
    return out


@app.post("/api/records")
def records_create(body: dict = Body(...)):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "제목을 입력하세요")
    with LOCK:
        st = load_state()
        n = len(st.get("records", {})) + 1
        rid = f"r{n}-{datetime.now().strftime('%H%M%S')}"
        st.setdefault("records", {})[rid] = {"id": rid, "title": title, "dept": body.get("dept") or DS["meta"]["dept"],
                                            "period": body.get("period") or DS["meta"]["period"]["id"], "kind": body.get("kind") or "정기감사",
                                            "memo": body.get("memo", ""), "created": datetime.now().isoformat(timespec="minutes"),
                                            "status": "서류 제출 중", "files": {}, "decisions": {}}
        st["active_record"] = rid
        save_state(st)
    return {"id": rid}


@app.get("/api/records/{rid}")
def record_view(rid: str):
    st = load_state()
    r = get_record(st, rid)
    if r.get("readonly"):
        return r
    return {k: v for k, v in r.items() if k not in ("files", "decisions")} | {"slots": _slots_view(r), "ran": r.get("ran")}


@app.delete("/api/records/{rid}")
def record_delete(rid: str):
    with LOCK:
        st = load_state()
        st.get("records", {}).pop(rid, None)
        if st.get("active_record") == rid:
            st["active_record"] = None
        save_state(st)
    return {"ok": True}


@app.post("/api/records/{rid}/files/{slot}")
async def record_upload(rid: str, slot: str, file: UploadFile = File(...)):
    if slot not in {s["key"] for s in SLOTS}:
        raise HTTPException(404, "없는 서류 칸")
    data = await file.read()
    info = {"name": file.filename, "size": len(data), "uploaded": datetime.now().isoformat(timespec="minutes"), "source": "업로드"}
    if slot == "ledger" and (file.filename or "").lower().endswith((".csv", ".txt")):
        h, b = csv_import.read_rows(csv_import.decode(data))
        m = csv_import.auto_map(h, b)
        errs = csv_import.validate(m)
        if errs:
            raise HTTPException(400, "장부 CSV 열을 알아보지 못했습니다: " + ", ".join(errs))
        tx, sk = csv_import.to_transactions(h, b, m)
        info |= {"transactions": tx, "rows": len(tx), "skipped": len(sk), "mapping": {k: v["header"] for k, v in m.items()}}
    d = FILES / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slot}__{Path(file.filename or 'file').name}").write_bytes(data)
    with LOCK:
        st = load_state()
        rec = get_record(st, rid)
        rec.setdefault("files", {})[slot] = info
        save_state(st)
    return {"ok": True, "file": {k: v for k, v in info.items() if k != "transactions"}}


@app.delete("/api/records/{rid}/files/{slot}")
def record_file_delete(rid: str, slot: str):
    with LOCK:
        st = load_state()
        get_record(st, rid).get("files", {}).pop(slot, None)
        save_state(st)
    return {"ok": True}


@app.post("/api/records/{rid}/fill-sample")
def record_fill_sample(rid: str):
    """시연용: 가상 데이터로 모든 서류 칸을 채운다(장부는 가상 거래 CSV)."""
    ds = dataset()
    sample = csv_import.sample_csv(ds)
    h, b = csv_import.read_rows(sample)
    m = csv_import.auto_map(h, b)
    tx, _ = csv_import.to_transactions(h, b, m)
    now = datetime.now().isoformat(timespec="minutes")
    names = {"ledger": "기중거래장부_2026-1.csv", "statement": "수입지출내역서_2026-1.docx", "overview": "사업개요서_6건.pdf",
             "bankcopy": "통장사본_학생회비·축제.pdf", "history": "과거거래내역서_2026-1.pdf", "evidence": f"영수증함 연동 · {len(ds['receipts'])}장",
             "cover": "표지·원본대조필.pdf", "inquiry": f"질의·답변 {len(ds['inquiries'])}건"}
    with LOCK:
        st = load_state()
        rec = get_record(st, rid)
        for s in SLOTS:
            info = {"name": names[s["key"]], "size": None, "uploaded": now, "source": "시연용 가상 서류"}
            if s["key"] == "ledger":
                info |= {"transactions": tx, "rows": len(tx), "skipped": 0, "mapping": {k: v["header"] for k, v in m.items()}}
            rec.setdefault("files", {})[s["key"]] = info
        save_state(st)
    return {"ok": True}


@app.post("/api/records/{rid}/run")
def record_run(rid: str):
    with LOCK:
        st = load_state()
        rec = get_record(st, rid)
        if rec.get("readonly"):
            raise HTTPException(400, "지난 기록은 다시 채점할 수 없습니다")
        missing = [s["label"] for s in SLOTS if s["required"] and not rec.get("files", {}).get(s["key"])]
        if missing:
            raise HTTPException(400, "제출하지 않은 서류: " + ", ".join(missing))
        rec["ran"] = datetime.now().isoformat(timespec="seconds")
        rec["status"] = "채점 완료"
        st["active_record"] = rid
        save_state(st)
    r = audit_result(rid, force=True)
    return {"ok": True, "totals": r["totals"], "score": _score(r["totals"]), "mode": r["res"]["mode"]}


@app.get("/api/records/{rid}/audit")
def record_audit(rid: str):
    st = load_state()
    rec = get_record(st, rid)
    r = audit_result(rid) if rec.get("ran") else None
    if not r:
        return {"ran": False}
    cases_by = {c["id"]: c for c in r["ds"]["cases"]}
    packets = [{k: p[k] for k in ("id", "title", "projects", "clauses", "inquiries", "documents", "checks", "obligations", "memory", "ledger_rows")}
               for p in r["res"]["packets"]]
    return {"ran": True, "ran_at": rec.get("ran"), "mode": r["res"]["mode"], "findings": r["findings"], "totals": r["totals"],
            "score": _score(r["totals"]), "packets": packets, "cases": cases_by, "checks": r["led"]["checks"]}


@app.post("/api/records/{rid}/finding/{fid:path}")
def record_finding(rid: str, fid: str, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        rec = get_record(st, rid)
        d = rec.setdefault("decisions", {}).setdefault(fid, {})
        d.update({k: v for k, v in body.items() if k in {"verdict", "disposition", "source", "confirmed", "note", "public_text"}})
        st["active_record"] = rid
        save_state(st)
    return {"ok": True}


# 이전 단일 감사 API (활성 기록 기준) — 보고서·공시 화면이 사용
@app.get("/api/audit")
def audit_view():
    st = load_state()
    rid = active_id(st)
    return record_audit(rid) if rid else {"ran": False}


# ---------------- 감사보고서·이의·공시 (활성 감사 기록 기준) ----------------
def _plus(d: str, n: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def _rec_state(st: dict) -> dict:
    rid = active_id(st)
    if not rid or rid not in st.get("records", {}):
        raise HTTPException(400, "모의 채점에서 감사 기록을 먼저 채점하세요.")
    return st["records"][rid]


@app.get("/api/report")
def report():
    r = audit_result()
    st = load_state()
    rec = st.get("records", {}).get(active_id(st) or "", {})
    rep = rec.get("report", {})
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
        "record": {"id": rec.get("id"), "title": rec.get("title")} if rec else None,
        "dept": meta_["dept"], "period": meta_["period"], "audit": meta_["audit"],
        "fields": {"target": f"{meta_['dept']} 학생회 집행부 · 책임자: 학생회장(전반적 책임), 회계 담당(제한적 책임)",
                   "scope": f"{meta_['period']['label']} 학생회비 통장·축제 부스 통장의 모든 수입 및 지출(3부 2조)",
                   "period": f"{meta_['audit']['start']} ~ {meta_['audit']['end']}",
                   "hours": rep.get("hours", {"total": 22, "senior": 12, "auditors": [{"name": "감사인 A(선임)", "h": 7}, {"name": "감사인 B(선임)", "h": 5}, {"name": "감사인 C", "h": 6}, {"name": "감사인 D", "h": 4}]}),
                   "inquiries": DS["inquiries"]},
        "opinions": rep.get("opinions") or audit_engine.draft_opinions(findings),
        "totals": r["totals"] if r else None,
        "score": _score(r["totals"]) if r else None,
        "findings": [f for f in findings if f["verdict"] == "미충족"],
        "unconfirmed": sum(1 for f in findings if not f.get("confirmed") and f["verdict"] != "충족"),
        "sent": sent, "objections": rec.get("objections", []), "deadlines": deadlines,
        "published": rec.get("published"),
    }


@app.post("/api/report")
def report_update(body: dict = Body(...)):
    with LOCK:
        st = load_state()
        _rec_state(st).setdefault("report", {}).update({k: v for k, v in body.items() if k in {"opinions", "hours"}})
        save_state(st)
    return {"ok": True}


@app.post("/api/report/send")
def report_send():
    with LOCK:
        st = load_state()
        _rec_state(st).setdefault("report", {})["sent"] = _plus(DS["meta"]["audit"]["end"], 2)  # 감사 종료 후 3일 이내(4부 19조)
        save_state(st)
    return {"ok": True}


@app.post("/api/objections")
def objection_add(body: dict = Body(...)):
    with LOCK:
        st = load_state()
        _rec_state(st).setdefault("objections", []).append({"finding": body.get("finding"), "text": body["text"], "answer": None,
                                                            "at": date.today().isoformat()})
        save_state(st)
    return {"ok": True}


@app.post("/api/objections/{i}/answer")
def objection_answer(i: int, body: dict = Body(...)):
    with LOCK:
        st = load_state()
        _rec_state(st)["objections"][i]["answer"] = body["answer"]
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
        _rec_state(st)["published"] = snap["published_at"]
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
        import shutil
        shutil.rmtree(FILES, ignore_errors=True)
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
