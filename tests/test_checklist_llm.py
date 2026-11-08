"""체크리스트 LLM: 감사 LLM과 다른 제공사, 코드 검증(조항·인용), 실패 시 라이브러리, 같은 유형은 한 번만 호출."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def _setup(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDITON_LLM", "live")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.delenv("CHECKLIST_MODEL", raising=False)
    from checklist import llm as cl
    monkeypatch.setattr(cl, "CACHE", tmp_path / "c.json")
    return cl


def test_different_provider_from_audit(monkeypatch, tmp_path):
    cl = _setup(monkeypatch, tmp_path)
    from audit import llm as al
    assert cl.checklist_model().split("/")[0] != al.AUDIT_MODEL.split("/")[0]


def test_live_output_is_verified_and_cached(monkeypatch, tmp_path):
    cl = _setup(monkeypatch, tmp_path)
    from checklist import engine
    calls = []

    def fake(model, system, user, schema=None, **k):
        calls.append(model)
        return {"obligations": [
            {"key": "Open Account!", "task": "별도 통장 개설", "clauses": ["3부 18조"], "quote": "별도의 통장을 사용할 수 있으며", "deps": [], "lead": -14, "kind": "권장"},
            {"key": "copy", "task": "통장사본 승인", "clauses": ["3부 18조"], "quote": "지어낸 문장", "deps": ["open_account", "ghost"], "lead": -999, "kind": "순서"},
        ]}

    monkeypatch.setattr(cl, "chat_json", fake)
    ev = {"id": "E9", "name": "축제", "type": "축제 부스", "date": "2026-05-20", "flags": []}
    obls = engine.extract(ev)
    mine = {o["key"]: o for o in obls if o["group"].startswith("LLM")}
    assert set(mine) == {"open_account", "copy"}
    assert mine["copy"]["deps"] == ["open_account"] and mine["copy"]["lead"] == -60
    assert engine.verify(mine["open_account"])["status"] == "검증됨"
    assert engine.verify(mine["copy"])["status"] == "검수 필요"  # 인용이 원문에 없음
    assert any(o["group"] == "모든 사업" for o in obls)
    engine.extract(ev)
    assert len(calls) == 1  # 같은 유형은 저장된 결과 재사용


def test_failure_falls_back_to_library(monkeypatch, tmp_path):
    cl = _setup(monkeypatch, tmp_path)
    from checklist import engine

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(cl, "chat_json", boom)
    obls = engine.extract({"id": "E1", "name": "축제", "type": "축제 부스", "date": "2026-05-20", "flags": []})
    assert any(o["key"] == "fest_copy" for o in obls)
