"""학기말 수입/지출내역서 Word(.docx) 출력. 기준안 3부 49~55조 칸 구성을 따른다."""
from __future__ import annotations

import io

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HEAD_FILL = "E8EEFF"


def _shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _font(doc):
    st = doc.styles["Normal"]
    st.font.name = "Malgun Gothic"
    st.font.size = Pt(9)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")


def _cell(c, text, bold=False, align=None, size=None):
    c.text = ""
    p = c.paragraphs[0]
    r = p.add_run(str(text))
    r.bold = bold
    if size:
        r.font.size = Pt(size)
    if align:
        p.alignment = align


def statement_docx(ds: dict, led: dict) -> bytes:
    doc = Document()
    _font(doc)
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(1.5))

    meta = ds["meta"]
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("수입/지출내역서")
    r.bold = True
    r.font.size = Pt(18)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"{meta['dept']} 학생회 · {meta['period']['label']} ({meta['period']['start']} ~ {meta['period']['end']})").font.size = Pt(10)
    note = doc.add_paragraph()
    nr = note.add_run("작성 기준: 한양대학교 정보시스템학과 감사기준안 3부 49~55조. '사업 및 일련번호'는 (사업번호)-(엑셀 장부 일련번호), "
                      "'통장내역'은 과거거래내역서 문구 그대로, 수입은 수수료를 뺀 순액, 지출 수수료는 별도 세목.")
    nr.font.size = Pt(8)
    nr.font.color.rgb = RGBColor(0x7A, 0x85, 0x99)

    # 사업목록 요약
    doc.add_heading("사업목록", level=2)
    tb = doc.add_table(rows=1, cols=4)
    tb.style = "Table Grid"
    for i, h in enumerate(["사업번호", "사업명", "수입 총액", "지출 총액(교비 제외)"]):
        _cell(tb.rows[0].cells[i], h, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(tb.rows[0].cells[i], HEAD_FILL)
    for pj in led["projects"]:
        if not pj["income"] and not pj["expense"]:
            continue
        row = tb.add_row().cells
        _cell(row[0], pj["no"], align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell(row[1], pj["name"])
        _cell(row[2], f"{pj['income']:,}", align=WD_ALIGN_PARAGRAPH.RIGHT)
        _cell(row[3], f"{pj['expense']:,}", align=WD_ALIGN_PARAGRAPH.RIGHT)

    heads = ["사업 및\n일련번호", "일자", "통장내역", "내용", "구분", "세목", "수입", "지출", "지급방법", "증빙종류·증빙서류", "비고"]
    widths = [1.6, 1.6, 3.0, 4.2, 1.6, 3.4, 1.9, 1.9, 1.6, 3.2, 3.0]
    for acc in ds["accounts"]:
        rows = [r for r in led["ledgers"].get(acc["id"], []) if r["tx"] or r.get("transfer")]
        if not rows:
            continue
        doc.add_heading(f"{acc['name']} ({acc.get('number', '')})", level=2)
        tb = doc.add_table(rows=1, cols=len(heads))
        tb.style = "Table Grid"
        tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(heads):
            _cell(tb.rows[0].cells[i], h, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=8)
            _shade(tb.rows[0].cells[i], HEAD_FILL)
        tin = tout = 0
        for r in rows:
            c = tb.add_row().cells
            vals = [r["code"], r["date"][5:], r["bank_desc"], r["content"], r["class"], r["items"],
                    f"{r['in']:,}" if r["in"] else "", f"{r['out']:,}" if r["out"] else "", r["method"],
                    ", ".join(r["evidence"]), r["note"]]
            for i, v in enumerate(vals):
                _cell(c[i], v, size=8, align=WD_ALIGN_PARAGRAPH.RIGHT if i in (6, 7) else None)
            if r["class"] != "내부 이체":
                tin += r["in"]
                tout += r["out"]
        c = tb.add_row().cells
        _cell(c[0], "합계", bold=True)
        _cell(c[6], f"{tin:,}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _cell(c[7], f"{tout:,}", bold=True, align=WD_ALIGN_PARAGRAPH.RIGHT)
        for row in tb.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    doc.add_paragraph("증빙서류는 과거거래내역서를 제외하고 각 행에 부착하며, 크기가 큰 경우 별도 문서로 첨부한다(3부 55조).").runs[0].font.size = Pt(8)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
