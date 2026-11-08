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


def test_receipt_parser_pos_and_invoice():
    """마트 POS 영수증(두 줄 품목·할인·띄어 쓴 합계)과 계산서 형식을 모두 읽고 검산이 맞는다."""
    from ocr.engine import parse, self_check
    pos = parse("가상마트 테스트점 (02)000-0000\n123-45-67890\n[구매]2026-11-01 20:11\n01 컵라면 44.7g\n"
                "8801000000001 1.68O 1 1,680\n02 새우튀김(팩)\n2100000000002 9,980 1 9,980\n[델리] 행사 -3,000\n"
                "과 세 물 품 7,873\n부 가 세 787\n합 계 8,660\n결 제 대 상 금 액 8,660")
    assert [i["price"] for i in pos["items"]] == [1680, 9980] and pos["amount"] == 8660
    assert all(c["ok"] for c in self_check(pos)), self_check(pos)
    inv = parse("OO어패럴\n사업자번호 369-46-10536\n일시 2026-03-25 12:26\n학과 과잠 제작 115 x 44,000 = 5,060,000\n"
                "공급가액 4,600,000\n부가세 460,000\n합계 5,060,000")
    assert inv["items"][0]["qty"] == 115 and all(c["ok"] for c in self_check(inv))


def test_receipt_parser_survives_ocr_noise():
    """실제 OCR에서 나온 깨짐(품목 번호 '@'·'0', 할인 '-' 누락, 연도 '206', 수량 누락, 합계 줄 깨짐)을 견딘다."""
    from ocr.engine import parse, self_check
    noisy = ("emart %8-요8 앞실리점 (0216438-1234\n[구 대]206-11-01 20,11 POS:7506-7219\n상품 명 단 가 수량 금 액\n"
             "01  오무기 컴누들 마라탕 44,7g\n8801045512518 1,680 1 1,680\n@ (뉴)강성사새우(팩)\n2149830099803 9,980 1 9,980\n"
             "[덜리] 속데이 행사 3,000\n0  싱그락치권무-Dg\n8309053273124 680 680\n8,491\n곁 세 대 {## 액 930 849\n"
             "카드결걸제(IC) 일시불 / 9,340")
    f = parse(noisy)
    assert f["vendor"] == "이마트" and f["date"].endswith("-11-01")
    assert [i["price"] for i in f["items"]] == [1680, 9980, 680]
    assert f["discounts"][0]["amount"] == -3000 and f["amount"] == 9340
    assert self_check(f)[0]["ok"]


def test_audit_call_reports_real_failure_reason(monkeypatch):
    from audit import llm as al
    monkeypatch.setenv("AUDITON_LLM", "live")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    class Resp:
        status_code = 402

    def broke(packet):
        raise httpx.HTTPStatusError("x", request=None, response=Resp())

    monkeypatch.setattr(al, "_live", broke)
    out = al.call({"title": "MT", "clauses": [{"id": "3부 13조"}]}, 1)
    assert out["mode"] == "live-error"
    assert out["judgments"][0]["question"] == "LLM 호출 실패: 크레딧 부족(402)"
