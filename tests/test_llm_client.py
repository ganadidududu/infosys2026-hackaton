"""OpenRouter 호출 형식과 실패 처리(실제 네트워크 없이 httpx.post를 바꿔 끼움)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx  # noqa: E402

from core import llm_client  # noqa: E402


class R:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)


def test_openrouter_body(monkeypatch):
    seen = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fake(url, json=None, headers=None, timeout=None):  # noqa: A002
        seen.append((url, json, headers))
        return R(200, {"choices": [{"message": {"content": '{"judgments": []}'}}]})

    monkeypatch.setattr(httpx, "post", fake)
    out = llm_client.chat_json("anthropic/claude-sonnet-5", "sys", "user", {"type": "object"})
    assert out == {"judgments": []}
    url, body, headers = seen[0]
    assert url.startswith("https://openrouter.ai/api/v1/")
    assert body["temperature"] == 0 and body["model"] == "anthropic/claude-sonnet-5"
    assert body["response_format"]["type"] == "json_schema"
    assert headers["Authorization"] == "Bearer k"


def test_schema_unsupported_falls_back_to_json_mode(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    def fake(url, json=None, headers=None, timeout=None):  # noqa: A002
        calls.append(json["response_format"]["type"])
        if len(calls) == 1:
            return R(400, {})
        return R(200, {"choices": [{"message": {"content": 'ok {"a": 1} done'}}]})

    monkeypatch.setattr(httpx, "post", fake)
    assert llm_client.chat_json("m", "s", "u", {"type": "object"}) == {"a": 1}
    assert calls == ["json_schema", "json_object"]


def test_audit_llm_failure_is_check_needed_not_score(monkeypatch):
    """LLM이 계속 실패하면 모든 조항이 '확인 필요'가 된다(점수를 지어내지 않음)."""
    monkeypatch.setenv("AUDITON_LLM", "live")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    from audit import llm

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    packet = {"title": "MT", "clauses": [{"id": "3부 13조"}, {"id": "3부 40조"}], "documents": [], "ledger_rows": [],
              "checks": [], "memory": {}}
    monkeypatch.setattr(llm, "_packet_prompt", lambda p: json.dumps({}))
    res = llm.call(packet, 1)
    assert res["mode"] == "live-error"
    assert {j["verdict"] for j in res["judgments"]} == {"확인 필요"}


def test_violation_without_precedent_goes_to_new_type(monkeypatch):
    """코드가 위반을 찾았는데 LLM이 선례를 안 짚으면 0점 처리하지 않고 신규 유형(전원 논의)으로 보류."""
    from audit import engine, llm

    def all_ok(packet, call_no):
        return {"mode": "live", "judgments": [
            {"clause": c["id"], "target": packet["title"], "verdict": "충족", "evidence": [], "missing": [],
             "same_case": None, "is_new_type": False, "question": None} for c in packet["clauses"]]}

    monkeypatch.setattr(llm, "call", all_ok)
    import json as _j
    root = Path(__file__).resolve().parents[1]
    ds = _j.loads((root / "data/synthetic/tune/dataset.json").read_text(encoding="utf-8"))
    from ledger.build import build
    res = engine.run(ds, build(ds, {}))
    bad = [f for f in res["findings"] if f["verdict"] == "미충족"]
    assert bad, "코드 검사로 잡히는 위반이 있어야 한다"
    assert all(f["disposition"] and f["disposition"]["type"] == "신규 유형" for f in bad)
