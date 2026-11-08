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
import logging
import os
import re

log = logging.getLogger("auditon")
ENGINE = None
OCR_MODEL = os.environ.get("OCR_MODEL", "google/gemini-2.5-flash")


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


def active_engine() -> str | None:
    """AUDITON_OCR=gemini이고 OpenRouter 키가 있으면 Gemini(사진 외부 전송), 아니면 로컬 엔진."""
    from core.llm_client import provider
    if os.environ.get("AUDITON_OCR") == "gemini" and provider() == "openrouter":
        return "gemini"
    return engine_name()


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
    if active_engine() == "gemini":
        try:
            return read_image_gemini(data)
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini OCR 실패, 로컬 엔진으로 넘김: %s", type(e).__name__)
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


# ---------------- Gemini(선택): 사진 → 항목 JSON → 파서가 읽는 영수증 텍스트 ----------------
GEMINI_SYSTEM = ("너는 한국 영수증·카드전표·계산서를 읽는 OCR이다. 사진에 보이는 값만 글자 그대로 옮기고, "
                 "보이지 않는 값은 null로 둔다. 추측하거나 계산해서 채우지 않는다. 금액은 원 단위 정수. "
                 "할인·행사·쿠폰 줄이 어느 품목 바로 아래(또는 같은 품목 묶음)에 있으면 그 품목의 discount·discount_name에 넣고, "
                 "특정 품목에 붙지 않은 할인(영수증 전체 할인)만 discounts에 넣는다. 같은 할인을 두 곳에 넣지 않는다.")
GEMINI_SCHEMA = {
    "type": "object", "required": ["vendor", "date", "amount", "items"],
    "properties": {
        "vendor": {"type": ["string", "null"], "description": "상호(가맹점명)"},
        "biz_no": {"type": ["string", "null"], "description": "사업자번호 000-00-00000"},
        "date": {"type": ["string", "null"], "description": "거래일 YYYY-MM-DD"},
        "items": {"type": "array", "items": {"type": "object", "required": ["name", "qty", "price"], "properties": {
            "name": {"type": "string"}, "qty": {"type": "integer"}, "price": {"type": "integer", "description": "단가(할인 전)"},
            "discount": {"type": ["integer", "null"], "description": "이 품목에 붙은 할인액(양수), 없으면 null"},
            "discount_name": {"type": ["string", "null"], "description": "그 할인 줄의 이름, 예: [델리] 쓱데이 행사"}}}},
        "discounts": {"type": "array", "description": "특정 품목에 붙지 않은 영수증 전체 할인만",
                      "items": {"type": "object", "properties": {
                          "name": {"type": "string"}, "amount": {"type": "integer", "description": "할인액(양수)"}}}},
        "supply": {"type": ["integer", "null"], "description": "공급가액(과세물품)"},
        "vat": {"type": ["integer", "null"], "description": "부가세"},
        "amount": {"type": ["integer", "null"], "description": "최종 합계(결제대상금액)"},
        "card_last4": {"type": ["string", "null"], "description": "카드번호 끝 4자리"},
        "installment": {"type": ["integer", "null"], "description": "할부 개월 수, 일시불이면 0"},
        "points": {"type": ["integer", "null"], "description": "적립 포인트"},
    },
}


def _shrink(data: bytes) -> tuple[bytes, str]:
    """긴 변 1600px JPEG로 줄여 전송량·지연을 줄인다(Pillow가 없으면 원본 그대로)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im.thumbnail((1600, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def _as_int(v) -> int | None:
    try:
        return int(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


def fields_to_text(j: dict) -> str:
    """Gemini 항목 → parse()가 그대로 읽는 영수증 텍스트. 저장·표시·검산은 로컬 OCR과 같은 길을 탄다."""
    lines = [(j.get("vendor") or "").strip() or "상호 미상"]
    if j.get("biz_no"):
        lines.append(f"사업자번호 {j['biz_no']}")
    if j.get("date"):
        lines.append(f"일시 {j['date']}")
    for it in j.get("items") or []:
        q, p = _as_int(it.get("qty")), _as_int(it.get("price"))
        if it.get("name") and q and p is not None:
            lines.append(f"{it['name']} {q} x {p:,} = {q * p:,}")
            if (a := _as_int(it.get("discount"))):  # 품목 바로 아래 줄 → parse()가 그 품목의 할인으로 묶는다
                lines.append(f"{it.get('discount_name') or '할인'} 할인 -{abs(a):,}")
    for key, label in (("supply", "공급가액"), ("vat", "부가세")):
        if (v := _as_int(j.get(key))) is not None:
            lines.append(f"{label} {v:,}")
    for d in j.get("discounts") or []:
        if (a := _as_int(d.get("amount"))):
            lines.append(f"{d.get('name') or '영수증'} 할인 -{abs(a):,}")
    if (v := _as_int(j.get("amount"))) is not None:
        lines.append(f"합계 {v:,}")
    last4 = re.sub(r"\D", "", str(j.get("card_last4") or ""))[-4:]
    if len(last4) == 4:
        inst = _as_int(j.get("installment")) or 0
        lines.append(f"카드 ****-{last4} " + (f"할부 {inst}개월" if inst > 1 else "일시불"))
    if (pt := _as_int(j.get("points"))):
        lines.append(f"포인트 적립 {pt:,}")
    return "\n".join(lines)


def read_image_gemini(data: bytes) -> str:
    from core.llm_client import chat_json
    j = chat_json(OCR_MODEL, GEMINI_SYSTEM, "이 영수증 사진의 항목을 JSON으로 옮겨라.", GEMINI_SCHEMA,
                  name="receipt", max_tokens=2048, timeout=60, image=_shrink(data))
    return fields_to_text(j)


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


BRANDS = {"emart": "이마트", "e-mart": "이마트", "homeplus": "홈플러스", "lottemart": "롯데마트", "daiso": "다이소",
          "gs25": "GS25", "cu ": "CU", "7-eleven": "세븐일레븐", "emart24": "이마트24", "coupang": "쿠팡", "olive young": "올리브영"}
TOTAL_KEYS = ("결제대상금액", "결제금액", "받을금액", "합계", "총액", "총금액", "합 계")
VENDOR_HINT = re.compile(r"(마트|점|편의점|상회|스토어|문구|식당|카페|약국|어패럴|㈜|\(주\))")


def parse(text: str) -> dict:
    raw = [l.strip() for l in text.splitlines() if l.strip()]
    lines = [fix_numbers(l) for l in raw]
    flat = [re.sub(r"\s+", "", l) for l in lines]  # '합 계' 같은 띄어쓰기 무시용
    f: dict = {"vendor": "", "items": [], "has_items": False, "discounts": []}

    # 업체: 위쪽 다섯 줄 중 상호처럼 보이는 줄, 없으면 첫 줄
    head = lines[:5]
    for logo, name in BRANDS.items():
        if any(logo in h.lower() for h in head):
            f["vendor"] = name
            break
    v = f["vendor"] or next((l for l in head if VENDOR_HINT.search(l) and not re.search(r"\d{3}-\d{2}-\d{5}", l)), head[0] if head else "")
    f["vendor"] = re.sub(r"\(?0\d{1,2}\)?[\s-]?\d{3,4}-\d{4}", "", v).strip(" ()")  # 전화번호 떼기

    for l, fl in zip(lines, flat):
        # 앞뒤가 숫자인 경우(사업자번호 206-86-50913)는 날짜가 아니다. 실제로 있는 날짜만 받는다.
        if "date" not in f and (m := re.search(r"(?<!\d)(20\d{1,2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)", l)):
            from datetime import date
            y = m.group(1)
            if len(y) == 3:  # OCR이 한 자리를 빠뜨림(206 → 2026): 올해·작년 중 끝자리가 맞는 해
                cur = date.today().year
                y = next((str(c) for c in (cur, cur - 1) if str(c)[0:2] + str(c)[3] == y), str(cur))
            try:
                f["date"] = date(int(y), int(m.group(2)), int(m.group(3))).isoformat()
            except ValueError:
                pass
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

    i, item_line = 0, -9  # item_line: 마지막 품목을 읽은 줄. 바로 다음 줄의 할인은 그 품목 할인이다
    while i < len(lines):
        l = lines[i]
        fl = flat[i]
        if m := re.match(rf"(.+?)\s+(\d+)\s*[xX×]\s*{NUM}\s*=\s*{NUM}", l):
            f["items"].append({"name": m.group(1).strip(), "qty": int(m.group(2)), "price": _int(m.group(3))})
            item_line = i
            i += 1
            continue
        # a) 마트 POS: '바코드(8~14자리) 단가 [수량] 금액' 줄 → 바로 윗줄이 상품명(앞 번호는 OCR이 깨도 무시)
        bm = re.match(r"^\s*\d{8,14}\s+(.*)$", l)
        if bm and i > 0:
            n = _nums(bm.group(1))
            name = re.sub(r"^\S{1,2}\s+", "", lines[i - 1]).strip() if re.match(r"^\S{1,2}\s", lines[i - 1]) else lines[i - 1].strip()
            item = None
            if len(n) >= 3 and fits(n[-3], n[-2], n[-1]):
                item = {"name": name, "qty": n[-2], "price": n[-3]}
            elif len(n) >= 2 and n[-2] > 0 and n[-1] % n[-2] == 0 and 0 < n[-1] // n[-2] < 1000:  # 수량을 못 읽음
                item = {"name": name, "qty": n[-1] // n[-2], "price": n[-2]}
            if item:
                f["items"].append(item)
                item_line = i
                i += 1
                continue
        n = _nums(l)
        if n and not re.search(r"\*{2,}-?\d{4}", l) and (n[-1] < 0 or re.search(r"(할인|행사|쿠폰|에누리)", fl)):  # 카드 '****-1234'는 할인 아님  # 할인 줄('-'가 지워져도 키워드로)
            d = {"name": re.sub(r"\s*할인$", "", re.split(NUM, l)[0].strip(" -:")), "amount": -abs(n[-1])}
            if i - item_line == 1:
                d["item"] = len(f["items"]) - 1
            f["discounts"].append(d)
        elif len(n) >= 3 and not re.match(r"(합계|부가세|과세|결제|받을|면세|카드)", fl) and not re.match(r"^\d{8,}", fl) \
                and fits(n[-3], n[-2], n[-1]):
            name = re.split(NUM, l)[0].strip(" -:")
            if name and not re.fullmatch(r"\d+", name):
                f["items"].append({"name": name, "qty": n[-2], "price": n[-3]})
                item_line = i
        if re.search(r"(일시불|할부|카드결제|승인금액)", fl) and (m := re.search(rf"/\s*{NUM}\s*$", l)):
            f["paid"] = _int(m.group(1))  # 카드로 실제 나간 금액
        i += 1

    if f.get("_totals"):
        f["amount"] = min(f["_totals"])[1]  # 결제대상금액 > 결제금액 > … > 합계 순
    f.pop("_totals", None)
    # 합계를 못 읽었으면: 카드 결제 금액 → (품목 합 + 할인)이 그와 같을 때 그 값
    if f.get("amount") is None and f.get("paid") is not None:
        f["amount"] = f["paid"]
    f["has_items"] = bool(f["items"])
    return f


def ledger_items(f: dict) -> list[dict]:
    """저장할 세목: 품목 뒤에 그 품목의 할인을 음수 줄로 붙이고, 영수증 전체 할인은 맨 끝에. 세목 합 = 합계."""
    out = []
    ds = f.get("discounts", [])
    for k, it in enumerate(f["items"]):
        out.append(it)
        out += [{"name": f"{it['name']} 할인" + (f"({d['name']})" if d["name"] else ""), "qty": 1, "price": d["amount"]}
                for d in ds if d.get("item") == k]
    out += [{"name": d["name"] or "할인", "qty": 1, "price": d["amount"]} for d in ds if d.get("item") is None]
    return out


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
