"""Gemini 영수증 인식 모드: 응답 → 파서 텍스트 왕복, 업로드 경로, 실패 시 대체."""
import base64
import io
import json as jsonlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("AUDITON_VAR", tempfile.mkdtemp(prefix="auditon-test-"))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402
from ocr import engine as ocr  # noqa: E402

FIELDS = {"vendor": "OO마트 왕십리점", "biz_no": "123-45-67890", "date": "2026-05-20",
          "items": [{"name": "생수 2L", "qty": 6, "price": 1200}, {"name": "종이컵", "qty": 2, "price": 3500}],
          "discounts": [{"name": "행사", "amount": 1000}], "supply": 12000, "vat": 1200, "amount": 13200,
          "card_last4": "4417", "installment": 3, "points": 140}


class R:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (3000, 4000), "white").save(buf, "PNG")
    return buf.getvalue()


def test_fields_round_trip_through_parser():
    f = ocr.parse(ocr.fields_to_text(FIELDS))
    assert f["vendor"] == "OO마트 왕십리점" and f["date"] == "2026-05-20" and f["amount"] == 13200
    assert sorted((i["qty"], i["price"]) for i in f["items"]) == [(2, 3500), (6, 1200)]
    assert f["discounts"][0]["amount"] == -1000
    assert (f["card_last4"], f["installment"], f["points"], f["biz_no"]) == ("4417", 3, 140, "123-45-67890")
    assert all(c["ok"] for c in ocr.self_check(f))


def test_item_discount_becomes_line_under_its_item():
    j = {"vendor": "이마트 왕십리점", "date": "2026-11-01", "amount": 9340, "supply": 8491, "vat": 849,
         "card_last4": "6746", "installment": 0, "points": 9,
         "items": [{"name": "마라탕 44.7g", "qty": 1, "price": 1680},
                   {"name": "(뉴)강성사새우(팩)", "qty": 1, "price": 9980, "discount": 3000, "discount_name": "[델리] 쓱데이 행사"},
                   {"name": "싱그림치킨무200g", "qty": 1, "price": 680}]}
    f = ocr.parse(ocr.fields_to_text(j))
    rows = ocr.ledger_items(f)
    assert [(r["name"], r["price"]) for r in rows] == [
        ("마라탕 44.7g", 1680), ("(뉴)강성사새우(팩)", 9980),
        ("(뉴)강성사새우(팩) 할인([델리] 쓱데이 행사)", -3000), ("싱그림치킨무200g", 680)]
    assert sum(r["qty"] * r["price"] for r in rows) == f["amount"] == 9340
    assert all(c["ok"] for c in ocr.self_check(f))


def test_biz_no_is_not_read_as_date():
    f = ocr.parse("이마트 왕십리점\n사업자번호 206-86-50913\n일시 2026-11-01\n합계 9,340")
    assert f["date"] == "2026-11-01" and f["biz_no"] == "206-86-50913"
    assert "date" not in ocr.parse("206-86-50913\n일시 2026-13-45")


def test_receipt_edit_rejects_bad_date():
    client = TestClient(app)
    assert client.patch("/api/receipts/R001", json={"date": "2026-86-50"}).status_code == 400
    assert client.get("/api/statement").status_code == 200


def test_local_pos_discount_attaches_to_item_above():
    text = "\n".join(["emart 왕십리점", "[구매]2026-11-01 20:11", "02 (뉴)강성사새우(팩)", "2140830099803 9,980 1 9,980",
                      "[델리] 쓱데이 행사 -3,000", "03 싱그림치킨무200g", "8809053273124 680 1 680", "합 계 7,660"])
    rows = ocr.ledger_items(ocr.parse(text))
    assert [(r["price"]) for r in rows] == [9980, -3000, 680]
    assert rows[1]["name"] == "(뉴)강성사새우(팩) 할인([델리] 쓱데이 행사)"


def test_upload_uses_gemini_with_shrunk_image(monkeypatch):
    monkeypatch.setenv("AUDITON_OCR", "gemini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    seen = []

    def fake(url, json=None, headers=None, timeout=None):  # noqa: A002
        seen.append(json)
        return R(200, {"choices": [{"message": {"content": jsonlib.dumps(FIELDS)}}]})

    monkeypatch.setattr(httpx, "post", fake)
    client = TestClient(app)
    assert client.get("/api/receipts").json()["engine"] == "gemini"
    r = client.post("/api/receipts/upload?project=MT", files={"file": ("r.png", png(), "image/png")}).json()
    assert r["ok"] and r["receipt"]["amount"] == 13200 and r["receipt"]["vendor"] == "OO마트 왕십리점"
    assert r["receipt"]["card_last4"] == "4417" and r["receipt"]["installment"] == 3
    body = seen[0]
    assert body["model"] == ocr.OCR_MODEL
    img = body["messages"][1]["content"][1]["image_url"]["url"]
    assert img.startswith("data:image/jpeg;base64,")
    sent = Image.open(io.BytesIO(base64.b64decode(img.split(",", 1)[1])))
    assert max(sent.size) == 1600


def test_gemini_failure_falls_back(monkeypatch):
    monkeypatch.setenv("AUDITON_OCR", "gemini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: R(500, {}))
    monkeypatch.setattr(ocr, "engine_name", lambda: None)
    r = TestClient(app).post("/api/receipts/upload", files={"file": ("r.png", png(), "image/png")}).json()
    assert r["ok"] is False and r["manual"] is True


def test_local_mode_without_flag(monkeypatch):
    monkeypatch.delenv("AUDITON_OCR", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(ocr, "engine_name", lambda: None)
    assert ocr.active_engine() is None
    assert TestClient(app).get("/api/receipts").json()["engine"] is None
