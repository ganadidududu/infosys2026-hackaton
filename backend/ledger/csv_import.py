"""기중 거래 장부(CSV) → 표준 거래. 열 이름과 값 모양으로 행·열을 자동 매핑한다.

은행·학생회마다 열 이름이 달라서(거래일시/일자/날짜, 적요/통장내역/내용, 입금액/수입, 출금액/지출 …)
키워드 점수 + 값 검사(날짜 모양, 숫자 비율)로 표준 필드에 대응시킨다. 사용자가 화면에서 고칠 수 있다.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

FIELDS = {
    "date": {"label": "일자", "required": True, "kw": ["거래일시", "거래일자", "일자", "날짜", "일시", "date"]},
    "desc": {"label": "통장내역(적요)", "required": True, "kw": ["통장내역", "적요", "거래내용", "기재내용", "받는분", "보낸분", "내용", "description"]},
    "in": {"label": "입금(수입)", "required": False, "kw": ["입금액", "입금", "맡기신", "수입액", "수입", "credit", "deposit"]},
    "out": {"label": "출금(지출)", "required": False, "kw": ["출금액", "출금", "찾으신", "지출액", "지출", "debit", "withdraw"]},
    "amount": {"label": "금액(±)", "required": False, "kw": ["거래금액", "금액", "amount"]},
    "balance": {"label": "잔액", "required": False, "kw": ["거래후잔액", "잔액", "balance"]},
    "account": {"label": "통장 구분", "required": False, "kw": ["통장", "계좌", "account"]},
    "project": {"label": "사업", "required": False, "kw": ["사업명", "사업번호", "사업", "행사"]},
    "method": {"label": "결제수단", "required": False, "kw": ["결제수단", "지급방법", "거래구분", "구분", "수단"]},
    "note": {"label": "비고", "required": False, "kw": ["비고", "메모", "memo", "note"]},
}


def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def read_rows(text: str) -> tuple[list[str], list[list[str]]]:
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    # 머리글 행 찾기: 키워드가 가장 많이 들어간 앞쪽 10행 중 하나
    best, best_i = -1, 0
    for i, r in enumerate(rows[:10]):
        s = sum(1 for c in r for f in FIELDS.values() if any(k in c for k in f["kw"]))
        if s > best:
            best, best_i = s, i
    header = [c.strip() for c in rows[best_i]]
    body = [r + [""] * (len(header) - len(r)) for r in rows[best_i + 1:]]
    return header, body


DATE_RE = re.compile(r"(\d{4})[./-]\s?(\d{1,2})[./-]\s?(\d{1,2})")


def to_date(s: str) -> str | None:
    m = DATE_RE.search(s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def to_int(s: str) -> int | None:
    t = re.sub(r"[,\s원₩]", "", s or "")
    if t in ("", "-"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = int(float(t))
    except ValueError:
        return None
    return -v if neg else v


def auto_map(header: list[str], body: list[list[str]]) -> dict:
    """열마다 각 필드 점수를 매기고, 높은 점수부터 겹치지 않게 배정한다."""
    sample = body[:30]
    scores = []
    for j, h in enumerate(header):
        col = [r[j] for r in sample if j < len(r)]
        date_ratio = sum(1 for v in col if to_date(v)) / max(1, len(col))
        num_ratio = sum(1 for v in col if to_int(v) is not None) / max(1, len(col))
        text_ratio = sum(1 for v in col if v.strip() and to_int(v) is None and not to_date(v)) / max(1, len(col))
        for f, spec in FIELDS.items():
            kw = max((len(k) / max(len(h), 1) for k in spec["kw"] if k.lower() in h.lower()), default=0)
            sc = 0.0
            if kw:
                sc += 0.6 + 0.3 * min(1, kw)
            if f == "date":
                sc += 0.4 * date_ratio
            elif f in ("in", "out", "amount", "balance"):
                sc += 0.3 * num_ratio - (0.6 if date_ratio > 0.5 else 0)
            elif f in ("desc", "note", "project", "method", "account"):
                sc += 0.2 * text_ratio - (0.5 if num_ratio > 0.8 else 0)
            scores.append((sc, j, f))
    scores.sort(reverse=True)
    mapping: dict[str, dict] = {}
    used = set()
    for sc, j, f in scores:
        if sc < 0.5 or f in mapping or j in used:
            continue
        mapping[f] = {"col": j, "header": header[j], "confidence": round(min(1.0, sc), 2)}
        used.add(j)
    if "in" in mapping and "out" in mapping:
        mapping.pop("amount", None)
    return mapping


def validate(mapping: dict) -> list[str]:
    errs = [f"'{FIELDS[f]['label']}' 열을 지정하세요" for f in ("date", "desc") if f not in mapping]
    if not (("in" in mapping and "out" in mapping) or "amount" in mapping):
        errs.append("입금·출금 두 열 또는 금액(±) 한 열이 필요합니다")
    return errs


ACCOUNT_HINT = [("축제", "fest")]


def to_transactions(header: list[str], body: list[list[str]], mapping: dict) -> tuple[list[dict], list[dict]]:
    """반환: (거래 목록, 건너뛴 행). 계좌 열 값에 '축제'가 있으면 축제 통장(fest)으로 본다."""
    g = lambda r, f: r[mapping[f]["col"]].strip() if f in mapping and mapping[f]["col"] < len(r) else ""  # noqa: E731
    out, skipped = [], []
    for i, r in enumerate(body, start=1):
        d = to_date(g(r, "date"))
        if not d:
            skipped.append({"row": i, "reason": "날짜를 읽지 못함", "raw": r})
            continue
        if "amount" in mapping and not ("in" in mapping and "out" in mapping):
            a = to_int(g(r, "amount")) or 0
            inflow, outflow = (a, 0) if a > 0 else (0, -a)
        else:
            inflow, outflow = abs(to_int(g(r, "in")) or 0), abs(to_int(g(r, "out")) or 0)
        if not inflow and not outflow:
            skipped.append({"row": i, "reason": "금액 없음", "raw": r})
            continue
        acc_raw = g(r, "account")
        acc = next((a for k, a in ACCOUNT_HINT if k in acc_raw), "main")
        desc = g(r, "desc")
        t = {"id": f"C{i:03d}", "account": acc, "date": d, "desc": desc, "in": inflow, "out": outflow,
             "balance": to_int(g(r, "balance")), "note_src": g(r, "note"), "project_src": g(r, "project"), "method_src": g(r, "method")}
        if re.search(r"(축제통장|학생회비통장)", desc.replace(" ", "")):
            t["internal"] = True
        out.append(t)
    out.sort(key=lambda x: (x["date"], x["id"]))
    return out, skipped


def sample_csv(ds: dict) -> str:
    """시연용: 가상 데이터셋을 은행 내보내기처럼 다른 열 이름으로 만든 CSV."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["정보시스템학과 학생회 기중 거래 장부", "", "", "", "", ""])
    w.writerow(["거래일시", "적요", "입금액", "출금액", "거래후잔액", "계좌", "메모"])
    for t in sorted(ds["transactions"], key=lambda x: (x["date"], x["id"])):
        acc = "축제 부스 통장" if t["account"] == "fest" else "학생회비 통장"
        w.writerow([t["date"].replace("-", ".") + " 12:00", t["desc"], f"{t['in']:,}" if t["in"] else "", f"{t['out']:,}" if t["out"] else "",
                    f"{t['balance']:,}", acc, ""])
    return buf.getvalue()
