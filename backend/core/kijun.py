"""감사기준안 원문(docs/감사기준안.md)을 부·조·항·호 단위 Clause로 나눈다.

조항 id 표기: '3부 35조', '3부 32조의 2', '4부 26조', '2부 6.4'. 호는 '3부 35조 ③'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIJUN_MD = ROOT / "docs" / "감사기준안.md"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


@dataclass
class Clause:
    id: str            # '3부 35조'
    part: int          # 3
    num: str           # '35' / '32의 2' / '6.4'
    title: str         # 장 제목 또는 괄호 제목
    text: str          # 원문 (줄바꿈 정리)
    items: dict[str, str] = field(default_factory=dict)  # '③' -> 내용
    auditable: bool = True

    def to_dict(self):
        return asdict(self)


def _clean(s: str) -> str:
    # PDF 추출본은 양쪽 정렬이라 줄바꿈이 대부분 단어 중간에서 일어난다 → 붙여 쓴다.
    s = re.sub(r"\s*\n\s*(?=[①-⑩])", " ", s.strip())
    s = re.sub(r"\s*\n\s*", "", s)
    return re.sub(r"\s{2,}", " ", s)


def _split_items(text: str) -> dict[str, str]:
    items = {}
    parts = re.split(f"([{CIRCLED}])", text)
    for i in range(1, len(parts) - 1, 2):
        items[parts[i]] = parts[i + 1].strip()
    return items


@lru_cache(maxsize=1)
def load_clauses() -> dict[str, Clause]:
    raw = KIJUN_MD.read_text(encoding="utf-8")
    clauses: dict[str, Clause] = {}

    # --- 2부: '6.4.' 형식 ---
    p2 = raw.split("2 부 : 회계보고를 위한 개념체계", 1)[1].split("3 부 : 회계기준", 1)[0]
    tokens = re.split(r"(?m)^(\d+\.\d+(?:\.\d+)?)\.\s*$", p2)
    # tokens: [pre, num, body, num, body...]
    titles = {m.group(1): m.group(2).strip() for m in re.finditer(r"(?m)^(\d+)\. (.+)$", p2)}
    for i in range(1, len(tokens) - 1, 2):
        num = tokens[i]
        body = re.split(r"(?m)^\d+\. .+$", tokens[i + 1])[0]
        sec_title = titles.get(num.split(".")[0], "")
        cid = f"2부 {num}"
        clauses[cid] = Clause(cid, 2, num, sec_title, _clean(body), auditable=False)

    # --- 3부, 4부: '제N조.' / '제N조의 2(제목)' ---
    for part, start, end in ((3, "3 부 : 회계기준", "4 부 : 감사품질제고를 위한 규정"),
                             (4, "4 부 : 감사품질제고를 위한 규정", "5 부 : 부")):
        body = raw.split(start, 1)[1].split(end, 1)[0]
        chapter = ""
        pat = re.compile(r"(?m)^(제\d+장\.\s*.+)$|^(제(\d+)조(?:의 (\d+))?(?:\(([^)]*)\)|\.))")
        marks = []
        for m in pat.finditer(body):
            if m.group(1):
                marks.append(("ch", m.start(), m.end(), m.group(1)))
            else:
                marks.append(("cl", m.start(), m.end(), m))
        for k, mk in enumerate(marks):
            if mk[0] == "ch":
                chapter = re.sub(r"^제\d+장\.\s*", "", mk[3]).strip()
                continue
            m = mk[3]
            nxt = marks[k + 1][1] if k + 1 < len(marks) else len(body)
            text = _clean(body[mk[2]:nxt])
            # 다른 조문 참조('제21조의')가 줄 앞에 오는 경우 방지: 조 번호가 증가하지 않으면 이전 조에 붙임
            num = m.group(3) + (f"조의 {m.group(4)}" if m.group(4) else "조")
            cid = f"{part}부 {num}"
            if cid in clauses:  # 본문 속 상호 참조(예: '제21조의 비정기감사')
                continue
            title = m.group(5) or chapter
            clauses[cid] = Clause(cid, part, num, title, text, _split_items(text))
    return clauses


def clause_text(cid: str) -> str:
    """'3부 35조 ③' 같은 id도 받아 해당 원문을 돌려준다."""
    m = re.match(r"^(\d부 [\d.]+(?:조(?:의 \d+)?)?)\s*([①-⑩])?$", cid.strip())
    if not m:
        return ""
    c = load_clauses().get(m.group(1))
    if not c:
        return ""
    if m.group(2):
        return c.items.get(m.group(2), "")
    return c.text


def exists(cid: str) -> bool:
    return bool(clause_text(cid))
