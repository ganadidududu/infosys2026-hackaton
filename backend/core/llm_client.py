"""외부 LLM 호출 한 곳. 기본은 OpenRouter(키 하나로 Claude·GPT 등 여러 제공사), 없으면 Anthropic 직접.

- 보내는 것은 가명처리된 텍스트뿐이다(실명·계좌는 보내지 않는다). 예외: AUDITON_OCR=gemini를 켜면 영수증 사진을 보낸다.
- temperature 0, JSON 스키마 출력. 키·본문은 로그에 남기지 않는다.
"""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def provider() -> str | None:
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def _parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def chat_json(model: str, system: str, user: str, schema: dict | None = None, name: str = "result",
              max_tokens: int = 4096, timeout: float = 120, image: tuple[bytes, str] | None = None) -> dict:
    p = provider()
    if image and p != "openrouter":
        raise RuntimeError("이미지 입력은 OpenRouter에서만 지원합니다 (OPENROUTER_API_KEY)")
    if p == "openrouter":
        content: str | list = user
        if image:
            data, mime = image
            content = [{"type": "text", "text": user},
                       {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}]
        body: dict = {
            "model": model, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            # 모델이 고장 난 JSON을 내면 OpenRouter가 고쳐 준다
            "plugins": [{"id": "response-healing"}],
        }
        body["response_format"] = ({"type": "json_schema", "json_schema": {"name": name, "strict": False, "schema": schema}}
                                   if schema else {"type": "json_object"})
        r = httpx.post(OPENROUTER_URL, json=body, timeout=timeout, headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "X-OpenRouter-Title": "Auditon",
        })
        if r.status_code == 400 and schema:  # 스키마를 지원하지 않는 모델이면 JSON 모드로 한 번 더
            body["response_format"] = {"type": "json_object"}
            r = httpx.post(OPENROUTER_URL, json=body, timeout=timeout,
                           headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
        r.raise_for_status()
        return _parse(r.json()["choices"][0]["message"]["content"] or "")
    if p == "anthropic":
        m = model.split("/", 1)[-1]  # 'anthropic/claude-…' → 'claude-…'
        body = {"model": m, "max_tokens": max_tokens, "temperature": 0, "system": system,
                "messages": [{"role": "user", "content": user + "\n\nJSON만 출력하라."}]}
        r = httpx.post(ANTHROPIC_URL, json=body, timeout=timeout,
                       headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        return _parse("".join(b.get("text", "") for b in r.json()["content"]))
    raise RuntimeError("LLM 키가 없습니다 (OPENROUTER_API_KEY 또는 ANTHROPIC_API_KEY)")
