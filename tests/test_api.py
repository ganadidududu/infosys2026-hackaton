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
from app.main import app  # noqa: E402

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
