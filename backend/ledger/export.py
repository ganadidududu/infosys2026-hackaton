"""기준안 양식 엑셀 출력. 장부: 1시트 '사업목록', 2시트 '총거래장부'(3~5시트는 작성하지 않음, 3부 59조).
수입/지출내역서는 별도 파일(3부 49~55조). 축제 별도 통장은 별도 장부(3부 20조)."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEAD = PatternFill("solid", fgColor="E8EEFF")
THIN = Side(style="thin", color="C9D1E0")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _sheet(ws, headers, rows, widths):
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = HEAD
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BOX
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.border = BOX
            if isinstance(c.value, int):
                c.number_format = "#,##0"
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def ledger_xlsx(ds: dict, led: dict, account: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "사업목록"
    _sheet(ws, ["사업번호", "사업명", "수입 총액", "지출 총액(교비 제외)"],
           [[p["no"], p["name"], p["income"], p["expense"]] for p in led["projects"]], [10, 24, 16, 20])
    ws2 = wb.create_sheet("총거래장부")
    rows = []
    for r in led["ledgers"][account]:
        rows.append([r["seq"], r["date"], r["project_no"], r["bank_desc"], r["content"], r["in"] or None, (r["out"] or None),
                     r["method"], r["note"]])
    _sheet(ws2, ["일련번호", "일자", "사업번호", "통장내역", "거래내용", "수입액", "지출액", "결제수단", "비고"], rows,
           [9, 12, 9, 18, 34, 13, 13, 10, 40])
    ws2.protection.sheet = True   # 3부 66조: 수정 방지 조치
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def statement_xlsx(ds: dict, led: dict) -> bytes:
    wb = Workbook()
    first = True
    for acc in ds["accounts"]:
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = f"수입지출내역서-{acc['name'][:8]}"
        rows = []
        for r in led["ledgers"][acc["id"]]:
            if not r["tx"] and not r.get("transfer"):
                continue
            rows.append([r["code"], r["date"], r["bank_desc"], r["content"], "수입" if r["in"] else "지출", r["class"], r["items"],
                         r["in"] or r["out"], r["method"], ", ".join(r["evidence"]), r["note"]])
        _sheet(ws, ["사업 및 일련번호", "일자", "통장내역", "내용", "수입/지출", "구분", "세목", "금액", "지급방법", "증빙종류·증빙서류", "비고"],
               rows, [14, 12, 18, 30, 9, 11, 26, 12, 10, 30, 34])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
