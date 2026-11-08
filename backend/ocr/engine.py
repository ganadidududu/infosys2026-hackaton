"""영수증 인식: 로컬 OCR(EasyOCR 또는 PaddleOCR) → 줄 복원 → 영수증 파서 → 자기 검산.
원본 이미지는 외부로 보내지 않는다. 엔진이 없으면 '직접 입력' 모드로 돌려준다.

품질을 올리는 세 단계
1) 전처리: EXIF 회전 보정, 흑백, 작은 사진 확대, 대비 보정(CLAHE). 감열지 영수증의 흐린 글자를 살린다.
2) 줄 복원: OCR은 글자 덩어리를 따로따로 돌려준다. y 좌표가 겹치는 덩어리를 한 줄로 묶고 x 순서로 이어
   '상품명 / 단가 수량 금액'처럼 실제 영수증의 한 행을 되살린다.
3) 숫자 교정 + POS 영수증 파서: 숫자 자리의 O·o→0, l·I·|→1, 마침표 천 단위→쉼표.
   품목·할인·과세물품·부가세·합계·결제대상금액을 읽고, 품목 합 = 합계 같은 검산으로 오인식을 잡는다.
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


_READER = None


def _reader():
    """EasyOCR 모델은 한 번만 올린다(요청마다 만들면 수 초씩 걸린다)."""
    global _READER
    if _READER is None:
        import easyocr
        _READER = easyocr.Reader(["ko", "en"], gpu=False)
    return _READER


# ---------------- 1) 전처리 ----------------
def preprocess(data: bytes):
    """사진 → OCR 하기 좋은 흑백 배열."""
    import numpy as np
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    w, h = im.size
    # 글자 높이가 너무 작으면 인식률이 크게 떨어진다: 짧은 변을 최소 1400px로
    scale = max(1.0, 1400 / min(w, h))
    if scale > 1:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    arr = np.array(im)
    try:
        import cv2
        arr = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(arr)
        arr = cv2.fastNlMeansDenoising(arr, h=7)
    except Exception:  # noqa: BLE001  (opencv가 없으면 대비 자동 보정만)
        arr = np.array(ImageOps.autocontrast(Image.fromarray(arr), cutoff=1))
    return arr


# ---------------- 2) 줄 복원 ----------------
def group_rows(boxes: list[tuple[list, str, float]]) -> list[str]:
    """(꼭짓점 4개, 글자, 신뢰도) 목록 → 위에서 아래로 한 줄씩."""
    items = []
    for pts, text, _conf in boxes:
        ys = [p[1] for p in pts]
        xs = [p[0] for p in pts]
        items.append({"top": min(ys), "bot": max(ys), "cy": (min(ys) + max(ys)) / 2, "x": min(xs), "t": text.strip()})
    items.sort(key=lambda b: b["cy"])
    rows: list[list[dict]] = []
    for b in items:
        if not b["t"]:
            continue
        if rows:
            last = rows[-1]
            h = sum(x["bot"] - x["top"] for x in last) / len(last)
            cy = sum(x["cy"] for x in last) / len(last)
            if abs(b["cy"] - cy) < max(h, b["bot"] - b["top"]) * 0.55:
                last.append(b)
                continue
        rows.append([b])
    return [" ".join(x["t"] for x in sorted(r, key=lambda x: x["x"])) for r in rows]


def read_image(data: bytes) -> str | None:
    name = engine_name()
    if not name:
        return None
    img = preprocess(data)
    if name == "easyocr":
        res = _reader().readtext(img, paragraph=False, decoder="beamsearch", contrast_ths=0.05,
                                 adjust_contrast=0.7, text_threshold=0.6, low_text=0.3, mag_ratio=1.2)
        return "\n".join(group_rows(res))
    from paddleocr import PaddleOCR
    import numpy as np
    ocr = PaddleOCR(lang="korean")
    res = ocr.ocr(np.stack([img] * 3, axis=-1))
    return "\n".join(group_rows([(line[0], line[1][0], line[1][1]) for page in res for line in page]))


# ---------------- 3) 숫자 교정 + 파서 ----------------
# 전화번호·사업자번호처럼 하이픈으로 이어진 숫자는 금액으로 보지 않는다
NUM = r"((?<![\w-])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?![\d,-]))"
_DIGITISH = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"})


def fix_numbers(line: str) -> str:
    """숫자가 섞인 토큰만 교정(상품명은 건드리지 않음)."""
    out = []
    for tok in line.split(" "):
        digits = sum(c.isdigit() for c in tok)
        if digits >= 2 and digits >= len(tok) * 0.5:
            tok = tok.translate(_DIGITISH)
            tok = re.sub(r"(?<=\d)\.(?=\d{3}\b)", ",", tok)  # 1.680 → 1,680
        out.append(tok)
    return " ".join(out)


def _int(s: str) -> int:
    return int(s.replace(",", ""))


def _nums(line: str) -> list[int]:
    return [_int(m) for m in re.findall(NUM, line)]


TOTAL_KEYS = ("결제대상금액", "결제금액", "받을금액", "합계", "총액", "총금액", "합 계")
VENDOR_HINT = re.compile(r"(마트|점|편의점|상회|스토어|문구|식당|카페|약국|어패럴|㈜|\(주\))")


def parse(text: str) -> dict:
    raw = [l.strip() for l in text.splitlines() if l.strip()]
    lines = [fix_numbers(l) for l in raw]
    flat = [re.sub(r"\s+", "", l) for l in lines]  # '합 계' 같은 띄어쓰기 무시용
    f: dict = {"vendor": "", "items": [], "has_items": False, "discounts": []}

    # 업체: 위쪽 다섯 줄 중 상호처럼 보이는 줄, 없으면 첫 줄
    head = lines[:5]
    v = next((l for l in head if VENDOR_HINT.search(l) and not re.search(r"\d{3}-\d{2}-\d{5}", l)), head[0] if head else "")
    f["vendor"] = re.sub(r"\(?0\d{1,2}\)?[\s-]?\d{3,4}-\d{4}", "", v).strip(" ()")  # 전화번호 떼기

    for l, fl in zip(lines, flat):
        if m := re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", l):
            f.setdefault("date", f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
        if m := re.search(r"(\d{3}-\d{2}-\d{5})", l):
            f.setdefault("biz_no", m.group(1))
        if m := re.search(r"할부\s*(\d+)\s*개월", l):
            f["installment"] = int(m.group(1))
        if "일시불" in fl:
            f.setdefault("installment", 0)
        if m := re.search(r"\*{2,}-?(\d{4})", l):
            f["card_last4"] = m.group(1)
        if re.search(r"(포인트|적립)", fl) and (n := _nums(l)):
            f.setdefault("points", n[-1])
        if fl.startswith("부가세") and (n := _nums(l)):
            f["vat"] = n[-1]
        if re.match(r"(과세물품|공급가액|과세금액)", fl) and (n := _nums(l)):
            f["supply"] = n[-1]
        for k in TOTAL_KEYS:
            if fl.startswith(k.replace(" ", "")) and (n := _nums(l)):
                # 결제대상금액 > 합계 순으로 신뢰
                f.setdefault("_totals", []).append((TOTAL_KEYS.index(k), n[-1]))

    # 품목 세 가지 형식
    #  a) 'NN 상품명' 다음 줄 '바코드 단가 수량 금액' (마트 POS)
    #  b) 한 줄 '상품명 단가 수량 금액'
    #  c) '상품명 수량 x 단가 = 금액' (계산서·가상 데이터)
    def fits(price: int, qty: int, amt: int) -> bool:
        return 0 < qty < 1000 and price > 0 and abs(price * qty - amt) <= max(10, amt * 0.02)

    i = 0
    while i < len(lines):
        l = lines[i]
        fl = flat[i]
        if m := re.match(rf"(.+?)\s+(\d+)\s*[xX×]\s*{NUM}\s*=\s*{NUM}", l):
            f["items"].append({"name": m.group(1).strip(), "qty": int(m.group(2)), "price": _int(m.group(3))})
            i += 1
            continue
        m = re.match(r"^(\d{2})\s+(\D.*)$", l)
        nn = _nums(lines[i + 1]) if i + 1 < len(lines) else []
        if m and len(nn) >= 3 and fits(nn[-3], nn[-2], nn[-1]):
            f["items"].append({"name": m.group(2).strip(), "qty": nn[-2], "price": nn[-3]})
            i += 2
            continue
        n = _nums(l)
        if n and n[-1] < 0:  # 할인 줄
            f["discounts"].append({"name": re.split(NUM, l)[0].strip(" []"), "amount": n[-1]})
        elif len(n) >= 3 and not re.match(r"(합계|부가세|과세|결제|받을|면세|카드)", fl) and fits(n[-3], n[-2], n[-1]):
            name = re.split(NUM, l)[0].strip(" -:")
            if name and not re.fullmatch(r"\d+", name):
                f["items"].append({"name": name, "qty": n[-2], "price": n[-3]})
        i += 1

    if f.get("_totals"):
        f["amount"] = min(f["_totals"])[1]  # 결제대상금액 > 결제금액 > … > 합계 순
    f.pop("_totals", None)
    f["has_items"] = bool(f["items"])
    return f


def self_check(f: dict) -> list[dict]:
    """품목 합 + 할인 = 합계, 과세물품 + 부가세 = 합계, 날짜·사업자번호 형식."""
    out = []
    amt = f.get("amount")
    if f.get("items") and amt is not None:
        s = sum(i["qty"] * i["price"] for i in f["items"]) + sum(d["amount"] for d in f.get("discounts", []))
        out.append({"check": "품목 합 = 합계", "ok": s == amt, "detail": f"{s:,} / {amt:,}"})
    if f.get("supply") is not None and f.get("vat") is not None and amt is not None:
        out.append({"check": "공급가액 + 부가세 = 합계", "ok": f["supply"] + f["vat"] == amt, "detail": f"{f['supply']+f['vat']:,} / {amt:,}"})
    out.append({"check": "날짜 형식", "ok": bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.get("date", "")))})
    if f.get("biz_no"):
        out.append({"check": "사업자번호 형식", "ok": bool(re.fullmatch(r"\d{3}-\d{2}-\d{5}", f["biz_no"]))})
    if not f.get("has_items"):
        out.append({"check": "세목 표기", "ok": False, "detail": "세목 없음 → 계산서 6항목 필요(3부 35조)"})
    return out
