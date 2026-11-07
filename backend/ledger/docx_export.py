"""학기말 수입/지출내역서 Word(.docx) 출력 — 거래 1건 = 1페이지.

양식(감사위원회 제시 양식, 3부 49~55조):
  사업 및 일련번호 / 사업명 / 날짜 · 수입/지출 · 구분 / 통장내역 / 내용
  왼쪽: 세목 · 수량 · 단가 표,  오른쪽: 지급방법 · 증빙종류 · 증빙서류(영수증 부착 칸)
  총액 / 비고
증빙서류 칸에는 업로드한 영수증 사진이 있으면 그 사진을, 없으면 OCR로 읽은 영수증 내용을 넣는다.
과거거래내역서는 증빙서류 칸에 붙이지 않는다(3부 55조).
"""
from __future__ import annotations

import io
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

LABEL_FILL = "D9D9D9"
COLS = [4.0, 1.5, 2.3, 2.5, 2.2, 2.0, 2.9]   # 세목 | 수량 | 단가 | 라벨 | 값 | 라벨 | 값  (합 17.4cm)
ITEM_ROWS = 19                              # 세목 칸 줄 수(양식처럼 빈 줄 포함)
ROW_H = 0.78


def _shade(cell, fill=LABEL_FILL):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _put(cell, text, bold=False, size=10.5, align=WD_ALIGN_PARAGRAPH.CENTER, label=False):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run("" if text is None else str(text))
    r.bold = bold
    r.font.size = Pt(size)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    if label:
        _shade(cell)


def _font(doc):
    st = doc.styles["Normal"]
    st.font.name = "Malgun Gothic"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")


def _md(iso: str) -> str:
    return f"{iso[5:7]}.{iso[8:10]}."


METHOD = {"카드": "카드", "계좌이체": "계좌이체", "현금": "현금", "-": "-"}


def _items_for(row: dict, rc: dict | None) -> list[tuple[str, str, str]]:
    """세목은 영수증에 표기된 그대로(3부 53조). 영수증이 없으면 거래 내용으로 한 줄."""
    if rc and rc.get("items"):
        return [(i["name"], str(i["qty"]), f"{i['price']:,}") for i in rc["items"]]
    amt = row["in"] or abs(row["out"])
    name = row["items"] if row["items"] and not row["items"].startswith("(") else row["content"]
    return [(name, "1", f"{amt:,}")]


def _page(doc, row: dict, rc: dict | None, img: Path | None, new_page: bool):
    t = doc.add_paragraph()
    t.paragraph_format.page_break_before = new_page
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_after = Pt(10)
    r = t.add_run("수입 / 지출 내역서")
    r.bold = True
    r.font.size = Pt(20)

    n_rows = 5 + 1 + ITEM_ROWS + 1 + 1   # 머리 5줄 + 세목 머리 + 세목 줄 + 총액 + 비고
    tb = doc.add_table(rows=n_rows, cols=7)
    tb.style = "Table Grid"
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    tb.autofit = False
    for i, w in enumerate(COLS):
        tb.columns[i].width = Cm(w)
    for row_ in tb.rows:
        row_.height = Cm(ROW_H)
        row_.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        for i, w in enumerate(COLS):
            row_.cells[i].width = Cm(w)
    R = tb.rows

    def full(ri, label, value):
        _put(R[ri].cells[0], label, label=True)
        v = R[ri].cells[1].merge(R[ri].cells[6])
        _put(v, value)

    is_in = row["in"] > 0
    full(0, "사업 및 일련번호", row["code"])
    full(1, "사업명", row.get("project") or "")
    # 날짜 · 수입/지출 · 구분
    _put(R[2].cells[0], "날짜", label=True)
    _put(R[2].cells[1].merge(R[2].cells[2]), _md(row["date"]))
    _put(R[2].cells[3], "수입/지출", label=True)
    _put(R[2].cells[4], "수입" if is_in else "지출")
    _put(R[2].cells[5], "구분", label=True)
    _put(R[2].cells[6], row["class"])
    full(3, "통장내역", row["bank_desc"])
    full(4, "내용", row["content"])
    # 세목 머리 + 지급방법
    hr = 5
    for i, h in enumerate(["세목", "수량", "단가"]):
        _put(R[hr].cells[i], h, label=True)
    _put(R[hr].cells[3], "지급방법", label=True)
    _put(R[hr].cells[4].merge(R[hr].cells[6]), METHOD.get(row["method"], row["method"]))
    # 증빙종류
    _put(R[hr + 1].cells[3], "증빙종류", label=True)
    kinds = [e for e in row["evidence"] if e != "과거거래내역서"] or row["evidence"]
    _put(R[hr + 1].cells[4].merge(R[hr + 1].cells[6]), kinds[0] if kinds else "")
    # 증빙서류 머리
    _put(R[hr + 2].cells[3].merge(R[hr + 2].cells[6]), "증빙서류", label=True)
    # 세목 줄
    items = _items_for(row, rc)
    for k in range(ITEM_ROWS):
        ri = hr + 1 + k
        if k < len(items):
            nm, q, p = items[k]
            _put(R[ri].cells[0], nm, size=10)
            _put(R[ri].cells[1], q, size=10)
            _put(R[ri].cells[2], p, size=10)
    # 증빙서류 부착 칸: 세목 셋째 줄부터 총액 줄까지 오른쪽 4칸을 하나로
    total_r = hr + 1 + ITEM_ROWS
    box = R[hr + 3].cells[3].merge(R[total_r].cells[6])
    box.text = ""
    box.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    bp = box.paragraphs[0]
    bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if img and img.exists():
        bp.add_run().add_picture(str(img), width=Cm(6.2))
    elif rc and rc.get("ocr_text"):
        for k, line in enumerate(rc["ocr_text"].splitlines()):
            p = bp if k == 0 else box.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.left_indent = Cm(1.0)
            p.paragraph_format.space_after = Pt(0)
            rr = p.add_run(line)
            rr.font.size = Pt(8.5)
            rr.font.name = "Consolas"
        note = box.add_paragraph()
        note.paragraph_format.left_indent = Cm(1.0)
        nr = note.add_run("(영수증 원본은 인쇄본에 부착)")
        nr.font.size = Pt(7.5)
    else:
        extra = [e for e in row["evidence"] if e != "과거거래내역서"]
        bp.add_run("\n".join(extra) if extra else "과거거래내역서로 갈음(3부 29조)").font.size = Pt(9)
    # 총액
    _put(R[total_r].cells[0], "총액", label=True)
    _put(R[total_r].cells[1].merge(R[total_r].cells[2]), f"{(row['in'] or abs(row['out'])):,}")
    # 비고
    full(total_r + 1, "비고", row["note"])
    R[total_r + 1].height = Cm(1.3)


def statement_docx(ds: dict, led: dict, receipts: dict | None = None, image_dir: Path | None = None) -> bytes:
    doc = Document()
    _font(doc)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(1.8)
    sec.top_margin = sec.bottom_margin = Cm(1.6)
    rc_by = receipts or {r["id"]: r for r in ds["receipts"]}
    rows = [r for acc in ds["accounts"] for r in led["ledgers"].get(acc["id"], []) if r["tx"] or r.get("transfer")]
    for k, row in enumerate(rows):
        rid = (row.get("rc") or [None])[0]
        rc = rc_by.get(rid) if rid else None
        img = None
        if image_dir and rid:
            img = next(iter(sorted(image_dir.glob(f"{rid}.*"))), None)
        _page(doc, row, rc, img, new_page=k > 0)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
