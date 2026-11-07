"""영수증 인식: 로컬 OCR(EasyOCR 또는 PaddleOCR, 설치된 것) + 텍스트 파서 + 자기 검산.
원본 이미지는 외부로 보내지 않는다. 엔진이 없으면 '직접 입력' 모드로 돌려준다.
"""
from __future__ import annotations

import io
import re

ENGINE = None


def engine_name() -> str | None:
    global ENGINE
    if ENGINE is not None:
        return ENGINE or None
    try:
        import easyocr  # noqa: F401
        ENGINE = "easyocr"
    except Exception:  # noqa: BLE001
        try:
            import paddleocr  # noqa: F401
            ENGINE = "paddleocr"
        except Exception:  # noqa: BLE001
            ENGINE = ""
    return ENGINE or None


def read_image(data: bytes) -> str | None:
    name = engine_name()
    if name == "easyocr":
        import easyocr
        import numpy as np
        from PIL import Image
        reader = easyocr.Reader(["ko", "en"], gpu=False)
        img = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
        return "\n".join(t for _, t, _ in reader.readtext(img))
    if name == "paddleocr":
        from paddleocr import PaddleOCR
        import numpy as np
        from PIL import Image
        ocr = PaddleOCR(lang="korean")
        img = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
        res = ocr.ocr(img)
        return "\n".join(line[1][0] for page in res for line in page)
    return None


NUM = r"([\d,]+)"


def _int(s: str) -> int:
    return int(s.replace(",", ""))


def parse(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    f: dict = {"vendor": lines[0] if lines else "", "items": [], "has_items": False}
    for l in lines:
        if m := re.search(r"(\d{4}-\d{2}-\d{2})", l):
            f.setdefault("date", m.group(1))
        if m := re.search(r"사업자번호\s*([\d-]+)", l):
            f["biz_no"] = m.group(1)
        if m := re.match(rf"(.+?)\s+(\d+)\s*x\s*{NUM}\s*=\s*{NUM}", l):
            f["items"].append({"name": m.group(1), "qty": int(m.group(2)), "price": _int(m.group(3))})
        if m := re.search(rf"합계\s*{NUM}", l):
            f["amount"] = _int(m.group(1))
        if m := re.search(rf"공급가액\s*{NUM}", l):
            f["supply"] = _int(m.group(1))
        if m := re.search(rf"부가세\s*{NUM}", l):
            f["vat"] = _int(m.group(1))
        if m := re.search(r"할부\s*(\d+)개월", l):
            f["installment"] = int(m.group(1))
        if m := re.search(rf"포인트 적립\s*{NUM}", l):
            f["points"] = _int(m.group(1))
        if m := re.search(r"\*{4}-(\d{4})", l):
            f["card_last4"] = m.group(1)
    f["has_items"] = bool(f["items"])
    return f


def self_check(f: dict) -> list[dict]:
    """품목 합 = 합계, 공급가액 + 부가세 = 합계, 날짜·사업자번호 형식."""
    out = []
    amt = f.get("amount")
    if f.get("items") and amt is not None:
        s = sum(i["qty"] * i["price"] for i in f["items"])
        out.append({"check": "품목 합 = 합계", "ok": s == amt, "detail": f"{s:,} / {amt:,}"})
    if f.get("supply") is not None and f.get("vat") is not None and amt is not None:
        out.append({"check": "공급가액 + 부가세 = 합계", "ok": f["supply"] + f["vat"] == amt, "detail": f"{f['supply']+f['vat']:,} / {amt:,}"})
    out.append({"check": "날짜 형식", "ok": bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.get("date", "")))})
    if f.get("biz_no"):
        out.append({"check": "사업자번호 형식", "ok": bool(re.fullmatch(r"\d{3}-\d{2}-\d{5}", f["biz_no"]))})
    if not f.get("has_items"):
        out.append({"check": "세목 표기", "ok": False, "detail": "세목 없음 → 계산서 6항목 필요(3부 35조)"})
    return out
