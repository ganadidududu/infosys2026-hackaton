"""가상 영수증 이미지 만들기(시연용). dataset.json의 OCR 텍스트를 감열지 영수증처럼 그린다.

  python data/synthetic/render_receipts.py      # tune/receipts/*.png, eval/receipts/*.png

실제 영수증 사진이 아니라 가상 데이터를 그린 그림이다. 필요: Pillow, 한글 글꼴(Noto Sans CJK 등).
"""
from __future__ import annotations

import glob
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONT_CANDIDATES = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                   "/Library/Fonts/NanumGothicCoding.ttf"]


def font(size: int):
    for f in FONT_CANDIDATES + glob.glob("/usr/share/fonts/**/*CJK*.tt*", recursive=True):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    raise SystemExit("한글 글꼴을 찾지 못했습니다")


def render(rc: dict, seed: int) -> Image.Image:
    r = random.Random(seed)
    W, pad = 400, 26
    f, fb, fs = font(17), font(22), font(14)
    lines = rc["ocr_text"].splitlines()
    H = 150 + len(lines) * 30 + 110
    im = Image.new("RGB", (W, H), (252, 251, 247))
    d = ImageDraw.Draw(im)
    y = 26
    d.text((W // 2, y), lines[0], font=fb, fill=(25, 25, 25), anchor="mt")
    y += 42
    d.text((W // 2, y), "가상 영수증 · 시연용", font=fs, fill=(120, 120, 120), anchor="mt")
    y += 30
    def dash(yy):
        for x in range(pad, W - pad, 8):
            d.line([(x, yy), (x + 4, yy)], fill=(110, 110, 110), width=1)
    dash(y + 8)
    y += 22
    for ln in lines[1:]:
        if ln.startswith("합계"):
            dash(y + 6)
            y += 18
            k, v = ln.split(" ", 1)
            d.text((pad, y), k, font=fb, fill=(15, 15, 15))
            d.text((W - pad, y), v, font=fb, fill=(15, 15, 15), anchor="ra")
            y += 38
            continue
        d.text((pad, y), ln, font=f, fill=(35, 35, 35))
        y += 30
    y += 6
    dash(y + 6)
    y += 22
    x = pad
    while x < W - pad:   # 바코드
        w = r.choice([1, 1, 2, 3])
        d.rectangle([x, y, x + w, y + 46], fill=(20, 20, 20))
        x += w + r.choice([1, 2, 2, 3])
    im = im.rotate(r.uniform(-1.2, 1.2), expand=True, fillcolor=(232, 234, 238))
    if rc.get("confidence", {}).get("vendor", 1) < 0.6:
        im = im.filter(ImageFilter.GaussianBlur(1.6))
    return im


def main():
    for name in ("tune", "eval"):
        p = HERE / name / "dataset.json"
        if not p.exists():
            continue
        ds = json.loads(p.read_text(encoding="utf-8"))
        out = HERE / name / "receipts"
        out.mkdir(exist_ok=True)
        for i, rc in enumerate(ds["receipts"]):
            render(rc, i).save(out / f"{rc['id']}.png", optimize=True)
        print(f"{name}: {len(ds['receipts'])}장 → {out}")


if __name__ == "__main__":
    main()
