"""체크리스트 LLM: 학기 행사 하나를 받아 기준안에서 '행사 전·중·후 해야 할 일'을 뽑는다.

- 감사 LLM과 분리: 다른 모델(가능하면 다른 제공사)·다른 프롬프트, 과거 감사 기억(Case)에 접근하지 않는다.
- LLM은 할 일·근거 조항·원문 인용·선후 관계·권장 리드타임만 낸다. 기한 계산·정렬은 코드(engine.py)가 한다.
- 출력은 코드가 검증한다: 조항이 실제로 있는지, 인용이 그 조항 원문에 글자 그대로 있는지(없으면 '검수 필요').
- 같은 행사 유형·특이사항 조합은 한 번만 부르고 저장한다(비용·결과 일관성). 실패하면 감사인이 검수한 라이브러리로 돌아간다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.kijun import load_clauses  # noqa: E402
from core.llm_client import chat_json, provider  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("AUDITON_VAR", str(BACKEND / "var"))) / "checklist-llm.json"


def _vendor(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "anthropic"


def checklist_model() -> str:
    """감사 LLM과 다른 제공사를 고른다."""
    from audit.llm import AUDIT_MODEL
    m = os.environ.get("CHECKLIST_MODEL")
    if m:
        return m
    if provider() == "anthropic":
        return "claude-haiku-5-5"  # Anthropic 직접 연결만 있을 때(같은 제공사, 다른 모델·프롬프트)
    return "openai/gpt-5" if _vendor(AUDIT_MODEL) != "openai" else "anthropic/claude-sonnet-5"


def mode() -> str:
    return "live" if os.environ.get("AUDITON_LLM") == "live" and provider() else "replay"


SYSTEM = """너는 대학 학생회 집행부를 돕는 일정 비서다. 감사 판단을 하지 않는다.
주어진 학과 감사기준안 3부(회계기준) 원문만 보고, 이 행사를 위해 집행부가 '언제까지 무엇을' 준비해야 하는지 뽑아라.
규칙:
1. 근거는 원문 조항뿐이다. 조항 id는 원문 표기 그대로('3부 18조', '3부 32조의 2').
2. quote는 그 조항 원문에서 8~30자를 글자 그대로 복사한다. 바꾸어 쓰면 안 된다.
3. lead는 행사일 기준 권장 일수(행사 전은 음수, 후는 양수, -60~60). 기준안이 순서만 정했으면 kind를 "순서", 아니면 "권장".
4. deps는 먼저 끝나야 하는 할 일의 key 목록. key는 영문 소문자_밑줄.
5. 행사와 관계없는 일반 조항은 넣지 않는다. 할 일은 3~8개, 한 줄로 짧게.
출력 JSON: {"obligations":[{"key","task","clauses":[...],"quote","deps":[...],"lead","kind"}]}"""

SCHEMA = {
    "type": "object", "required": ["obligations"],
    "properties": {"obligations": {"type": "array", "items": {
        "type": "object", "required": ["key", "task", "clauses", "quote", "deps", "lead", "kind"],
        "properties": {
            "key": {"type": "string"}, "task": {"type": "string"},
            "clauses": {"type": "array", "items": {"type": "string"}},
            "quote": {"type": "string"}, "deps": {"type": "array", "items": {"type": "string"}},
            "lead": {"type": "integer"}, "kind": {"type": "string", "enum": ["권장", "순서"]},
        }}}},
}


def _part3_text() -> str:
    cs = [c for c in load_clauses().values() if c.part == 3]
    return "\n".join(f"[{c.id}] ({c.title}) {c.text}" for c in cs)


def _clean(obls: list[dict], prefix: str) -> list[dict]:
    """모양 검증: key 중복·자기 참조·없는 선행 제거, lead 범위 고정."""
    out, seen = [], set()
    for o in obls:
        k = re.sub(r"[^a-z0-9_]", "_", str(o.get("key", "")).lower()).strip("_")[:24] or f"t{len(out)}"
        if k in seen:
            continue
        seen.add(k)
        try:
            lead = max(-60, min(60, int(o.get("lead", 0))))
        except (TypeError, ValueError):
            lead = 0
        out.append({"key": k, "task": str(o.get("task", "")).strip()[:80], "clauses": [str(c).strip() for c in o.get("clauses", [])][:4],
                    "quote": str(o.get("quote", "")).strip(), "deps": [str(d) for d in o.get("deps", [])],
                    "lead": lead, "kind": "순서" if o.get("kind") == "순서" else "권장", "group": prefix})
    keys = {o["key"] for o in out}
    for o in out:
        o["deps"] = [d for d in o["deps"] if d in keys and d != o["key"]]
    return [o for o in out if o["task"]]


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(c: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, CACHE)


def extract_live(event: dict) -> list[dict] | None:
    """행사 유형·특이사항 조합마다 한 번 호출. 실패하면 None(호출한 쪽이 라이브러리로 대체)."""
    key = f"{event['type']}|{','.join(sorted(event.get('flags', [])))}|{checklist_model()}"
    cache = _load()
    if key in cache:
        return cache[key]
    user = (f"행사: 유형={event['type']}, 특이사항={', '.join(event.get('flags', [])) or '없음'}\n"
            "(행사 이름·날짜는 판단에 쓰지 않는다)\n\n감사기준안 3부 원문:\n" + _part3_text())
    try:
        res = chat_json(checklist_model(), SYSTEM, user, SCHEMA, name="checklist", max_tokens=3000, timeout=90)
        obls = _clean(res.get("obligations", []), f"LLM · {event['type']}")
    except Exception:  # noqa: BLE001  네트워크·형식 오류 → 라이브러리 사용
        return None
    if not obls:
        return None
    cache[key] = obls
    _save(cache)
    return obls
