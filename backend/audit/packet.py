"""감사 패킷 구성(코드). 사업마다 하나 + 학과 전체 하나."""
from __future__ import annotations

import re

from core.kijun import clause_text, load_clauses
from audit import memory

BASE_EVENT_CLAUSES = ["3부 40조", "3부 42조"]
FESTIVAL_CLAUSES = ["3부 18조", "3부 19조", "3부 20조"]
ALL_CLAUSES = ["3부 5조", "3부 6조", "3부 11조"]


def _base(cid: str) -> str:
    return re.sub(r"\s*[①-⑩]$", "", cid.strip())


def build_packets(ds: dict, led: dict, checklist_status: dict | None = None) -> list[dict]:
    period = ds["meta"]["period"]["id"]
    packets = []
    events = [p for p in led["projects"] if not p["fixed"] and p["overview"]]
    checks = led["checks"]
    all_docs = ds["documents"]

    def make(pid, title, project_names, clauses, docs):
        cl = []
        for c in dict.fromkeys(clauses):
            if clause_text(c):
                cl.append({"id": c, "title": load_clauses()[_base(c)].title, "text": clause_text(c)})
        cks = [c for c in checks if (c["project"] in project_names) or (None in project_names and c["project"] is None)]
        rows = [r for acc in led["ledgers"].values() for r in acc if r["project"] in project_names and r["tx"]]
        inq = [q for q in ds["inquiries"] if q["period"] == period and (set(q["clauses"]) & set(clauses) or not q["clauses"])]
        mem = {c["id"]: memory.search(ds["cases"], c["id"], " ".join(x["message"] for x in cks if x["clause"] == c["id"]), before=period)
               for c in cl}
        return {"id": pid, "title": title, "projects": [p for p in project_names if p], "clauses": cl,
                "inquiries": inq, "documents": docs, "ledger_rows": rows, "checks": cks,
                "obligations": (checklist_status or {}).get(title, []), "memory": mem}

    for p in events:
        cls = list(BASE_EVENT_CLAUSES)
        cls += [c["clause"] for c in checks if c["project"] == p["name"] and c["clause"].startswith("3부")]
        if p["name"] == "축제 부스":
            cls += FESTIVAL_CLAUSES
        docs = [d for d in all_docs if d["project"] == p["name"]]
        packets.append(make(f"P{p['no']}", p["name"], [p["name"]], cls, docs))
    fixed = [p["name"] for p in led["projects"] if p["fixed"]]
    cls = list(ALL_CLAUSES) + [c["clause"] for c in checks if (c["project"] in fixed or c["project"] is None) and c["clause"].startswith("3부")]
    docs = [d for d in all_docs if d["project"] in fixed]
    packets.append(make("ALL", "학과 전체", fixed + [None], cls, docs))
    return packets
