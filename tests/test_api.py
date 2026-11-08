"""API 경계 테스트: 정적 파일 경로 탈출, 송부·확정 전 공시 차단, 이의 입력 검사."""
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["AUDITON_VAR"] = tempfile.mkdtemp(prefix="auditon-test-")
os.environ.pop("AUDITON_LLM", None)

from fastapi.testclient import TestClient  # noqa: E402
from app import main  # noqa: E402
from app.main import app  # noqa: E402
from audit import llm  # noqa: E402

client = TestClient(app)


def test_static_path_traversal_blocked():
    for p in ("/..%2f..%2fbackend%2fapp%2fmain.py", "/..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc%2fpasswd"):
        r = client.get(p)
        assert "Auditon API" not in r.text
        assert "root:" not in r.text


def test_objection_input_validation():
    client.post("/api/reset")
    rid = client.post("/api/records", json={"title": "t"}).json()["id"]
    assert client.post(f"/api/records/{rid}/fill-sample").status_code == 200
    assert client.post(f"/api/records/{rid}/run").status_code == 200
    assert client.post("/api/objections", json={"finding": "x"}).status_code == 400
    assert client.post("/api/objections", json={"text": "  "}).status_code == 400
    assert client.post("/api/objections/0/answer", json={"answer": "a"}).status_code == 404
    assert client.post("/api/objections", json={"text": "이의"}).status_code == 200
    assert client.post("/api/objections/0/answer", json={}).status_code == 400
    assert client.post("/api/objections/0/answer", json={"answer": "답"}).status_code == 200


def test_saved_run_reused_without_llm_calls(monkeypatch):
    client.post("/api/reset")
    rid = client.post("/api/records", json={"title": "t"}).json()["id"]
    client.post(f"/api/records/{rid}/fill-sample")
    calls = []
    real = llm.call
    monkeypatch.setattr(llm, "call", lambda p, n: calls.append(n) or real(p, n))
    assert client.post(f"/api/records/{rid}/run").status_code == 200
    ran = len(calls)
    assert ran > 0
    first = client.get(f"/api/records/{rid}/audit").json()

    main.RUN_CACHE.clear()
    item = next(r for r in client.get("/api/records").json() if r["id"] == rid)
    again = client.get(f"/api/records/{rid}/audit").json()
    assert len(calls) == ran
    assert item["score"] == first["score"]["score"] and item["stale"] is False
    assert again["findings"] == first["findings"] and again["stale"] is False

    assert client.post("/api/transfer-note", json={"key": "qa", "note": "통장 간 이체"}).status_code == 200
    assert client.get(f"/api/records/{rid}/audit").json()["stale"] is True
    assert len(calls) == ran


def test_login_returns_to_same_site_path_only():
    go = lambda n: client.get("/api/login", params={"next": n}, follow_redirects=False).headers["location"]
    assert go("/grade?x=1") == "/grade?x=1"
    assert go("https://evil.example") == "/" and go("//evil.example") == "/" and go("/\\evil.example") == "/"


def test_receipt_delete():
    client.post("/api/reset")
    ids = lambda: [r["id"] for r in client.get("/api/receipts").json()["receipts"]]
    up = lambda: client.post("/api/receipts/upload", files={"file": ("r.txt", "OO카페\n일시 2026-06-20\n합계 3,000", "text/plain")}).json()["receipt"]["id"]
    a, b = up(), up()
    assert client.delete(f"/api/receipts/{a}").status_code == 200
    assert a not in ids() and b in ids()
    c = up()
    assert c not in (a, b)
    assert client.delete("/api/receipts/R001").status_code == 200 and "R001" not in ids()
    assert client.delete("/api/receipts/R999").status_code == 404
    assert client.get("/api/statement").status_code == 200


def test_each_login_email_has_its_own_space():
    a = {"cf-access-authenticated-user-email": "a@example.com"}
    b = {"cf-access-authenticated-user-email": "B@Example.com "}
    up = lambda h: client.post("/api/receipts/upload", headers=h,
                               files={"file": ("r.txt", "OO카페\n일시 2026-06-20\n합계 3,000", "text/plain")}).json()["receipt"]["id"]
    ids = lambda h: {r["id"] for r in client.get("/api/receipts", headers=h).json()["receipts"]}
    client.post("/api/reset", headers=a), client.post("/api/reset", headers=b), client.post("/api/reset")
    ra = up(a)
    assert ra in ids(a) and ra not in ids(b) and ra not in ids({})
    rid = client.post("/api/records", headers=b, json={"title": "B 기록"}).json()["id"]
    assert rid in {r["id"] for r in client.get("/api/records", headers=b).json()}
    assert rid not in {r["id"] for r in client.get("/api/records", headers=a).json()}
    assert client.get("/api/meta", headers=a).json()["user"] == "a@example.com"
    client.post("/api/reset", headers=a)
    assert ra not in ids(a) and rid in {r["id"] for r in client.get("/api/records", headers=b).json()}


def test_publish_requires_confirm_and_send():
    client.post("/api/reset")
    rid = client.post("/api/records", json={"title": "t"}).json()["id"]
    client.post(f"/api/records/{rid}/fill-sample")
    client.post(f"/api/records/{rid}/run")
    findings = client.get(f"/api/records/{rid}/audit").json()["findings"]
    pending = [f for f in findings if f["verdict"] != "충족"]
    assert pending

    assert client.post("/api/report/send").status_code == 400
    for f in pending:
        body = {"confirmed": True}
        if f["verdict"] == "확인 필요":
            body["verdict"] = "충족"
        elif (f.get("disposition") or {}).get("type") == "신규 유형":
            body |= {"disposition": {"type": "감점", "points": 1}, "source": "감사인단 전원 논의"}
        client.post(f"/api/records/{rid}/finding/{quote(f['id'], safe='')}", json=body)
    assert client.get("/api/report").json()["unconfirmed"] == 0

    assert client.post("/api/publish").status_code == 400
    assert client.post("/api/report/send").status_code == 200
    r = client.post("/api/publish")
    assert r.status_code == 200, r.text
