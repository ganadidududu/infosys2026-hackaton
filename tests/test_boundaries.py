"""경계 테스트 (PRD 10절). 실행: cd auditon && python -m pytest tests -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reconcile import hungarian, subset  # noqa: E402
from audit.engine import warning_penalty, totals, run  # noqa: E402
from ledger.build import build  # noqa: E402
from checklist.engine import topo  # noqa: E402
from core.kijun import load_clauses, clause_text  # noqa: E402


def rc(i, amt, d="2026-05-20", v="OO마트"):
    return {"id": i, "amount": amt, "date": d, "vendor": v}


def tx(i, amt, d="2026-05-20", desc="OO마트"):
    return {"id": i, "out": amt, "date": d, "desc": desc}


# ---------- 대사: s = 0.4 경계 ----------
def test_delta_is_point_three():
    assert hungarian.DELTA == pytest.approx(0.3)


@pytest.mark.parametrize("s,expect_pair", [(0.39, False), (0.41, True)])
def test_pair_only_above_s_min(monkeypatch, s, expect_pair):
    # 점수 행렬을 고정해 s=0.39/0.41 경계에서 짝 여부만 본다
    import numpy as np
    monkeypatch.setattr(hungarian, "score_matrix", lambda r, t: (np.array([[s]]), np.array([[False]]), {(0, 0): {"amt": 0, "date": 0, "name": 0}}))
    res = hungarian.match([rc("R1", 1000)], [tx("T1", 1000)])
    assert (len(res["pairs"]) == 1) is expect_pair


def test_same_day_same_amount_resolved_by_name():
    rs = [rc("R1", 87000, v="OO마트 왕십리점"), rc("R2", 87000, v="OO정육")]
    ts = [tx("T1", 87000, desc="OO정육"), tx("T2", 87000, desc="OO마트 왕십리점")]
    res = hungarian.match(rs, ts)
    got = {(p["rc"], p["tx"]) for p in res["pairs"]}
    assert got == {("R1", "T2"), ("R2", "T1")}


def test_tie_goes_to_confirmation():
    rs = [rc("R1", 50000, v="OO상점"), rc("R2", 50000, v="OO상점")]
    ts = [tx("T1", 50000, desc="OO상점"), tx("T2", 50000, desc="OO상점")]
    res = hungarian.match(rs, ts)
    assert all(p["status"] == "확인 필요" for p in res["pairs"])


def test_one_to_n_and_n_to_one_always_need_confirmation():
    g = subset.find([rc("R1", 240000)], [tx("T1", 120000), tx("T2", 120000)])
    assert g and g[0]["kind"] == "1:N" and g[0]["status"] == "확인 필요"
    g = subset.find([rc("R1", 30000), rc("R2", 20000)], [tx("T1", 50000)])
    assert g and g[0]["kind"] == "N:1" and g[0]["status"] == "확인 필요"


def test_half_amount_is_blocked_not_paired():
    res = hungarian.match([rc("R1", 240000)], [tx("T1", 120000)])
    assert res["pairs"] == []


def test_zero_receipts():
    res = hungarian.match([], [tx("T1", 1000)])
    assert res["unmatched_tx"] == ["T1"]


# ---------- 경고 규칙 (4부 26조) ----------
@pytest.mark.parametrize("w,p", [(0, 0), (2, 0), (3, 1), (4, 2), (7, 5)])
def test_warning_penalty(w, p):
    assert warning_penalty(w) == p


def _f(verdict, disp):
    return {"verdict": verdict, "disposition": disp}


def test_totals_new_type_not_counted():
    fs = [_f("미충족", {"type": "감점", "points": 1}), _f("미충족", {"type": "신규 유형"}),
          _f("미충족", {"type": "경고"}), _f("미충족", {"type": "경고"}), _f("미충족", {"type": "경고"}), _f("확인 필요", None)]
    t = totals(fs)
    assert (t["case_points"], t["warnings"], t["warning_points"], t["total"], t["pending_new"], t["pending_check"]) == (1, 3, 1, 2, 1, 1)


def test_only_new_type_total_is_zero():
    t = totals([_f("미충족", {"type": "신규 유형"})])
    assert t["total"] == 0 and t["pending_new"] == 1


# ---------- 기준안 파싱 ----------
def test_clause_ids_follow_kijun_notation():
    c = load_clauses()
    for cid in ["2부 6.4", "3부 32조의 2", "3부 35조", "4부 26조", "3부 71조"]:
        assert cid in c
    assert clause_text("3부 35조 ③").startswith("견적 산출 근거")


# ---------- 체크리스트 위상 정렬 ----------
def test_topo_detects_cycle():
    _, cyc = topo([{"key": "a", "deps": ["b"]}, {"key": "b", "deps": ["a"]}])
    assert cyc


# ---------- 조정용 세트 전체 파이프라인 = 정답 ----------
def test_tune_set_matches_truth():
    ds = json.loads((ROOT / "data/synthetic/tune/dataset.json").read_text())
    truth = json.loads((ROOT / "data/synthetic/tune/truth.json").read_text())
    led = build(ds, {})
    got = {(tuple(p["rc"]), tuple(p["tx"])) for p in led["reconcile"]["pairs"]}
    want = {(tuple(m["rc"]), tuple(m["tx"])) for m in truth["matches"]}
    assert got == want
    res = run(ds, led)
    bad = {(f["project"], f["clause"]) for f in res["findings"] if f["verdict"] == "미충족"}
    assert bad == {(t["project"], t["clause"]) for t in truth["findings"]}
    assert totals(res["findings"])["total"] == truth["total_penalty_before_new"]


def test_llm_quote_mismatch_and_disagreement_become_check_needed():
    ds = json.loads((ROOT / "data/synthetic/tune/dataset.json").read_text())
    res = run(ds, build(ds, {}))
    by = {(f["project"], f["clause"]): f for f in res["findings"]}
    assert by[("과잠 공동구매", "3부 42조")]["verdict"] == "확인 필요"
    assert any(r.startswith("인용") for r in by[("과잠 공동구매", "3부 42조")]["reasons"])
    assert by[("MT", "3부 40조")]["verdict"] == "확인 필요"


# ---------- 기중 거래 장부 CSV 자동 매핑 ----------
from ledger import csv_import  # noqa: E402


def test_csv_bank_style_headers():
    text = "거래일시,적요,입금액,출금액,거래후잔액\n2026.03.03 12:00,홍길동 학생회비,750000,,750000\n2026.03.04 09:10,다이소,,\"47,300\",702700\n"
    h, b = csv_import.read_rows(text)
    m = csv_import.auto_map(h, b)
    assert {k: v["header"] for k, v in m.items() if k in ("date", "desc", "in", "out")} == {"date": "거래일시", "desc": "적요", "in": "입금액", "out": "출금액"}
    tx, sk = csv_import.to_transactions(h, b, m)
    assert [(t["in"], t["out"]) for t in tx] == [(750000, 0), (0, 47300)] and not sk


def test_csv_signed_amount_and_cp949():
    raw = "일자,내용,금액,비고\n2026-03-03,학생회비,750000,\n2026-03-04,다이소,-47300,소모품\n".encode("cp949")
    h, b = csv_import.read_rows(csv_import.decode(raw))
    m = csv_import.auto_map(h, b)
    assert not csv_import.validate(m) and m["amount"]["header"] == "금액"
    tx, _ = csv_import.to_transactions(h, b, m)
    assert tx[1]["out"] == 47300


def test_csv_missing_amount_is_reported():
    h, b = csv_import.read_rows("일자,내용\n2026-03-03,학생회비\n")
    assert csv_import.validate(csv_import.auto_map(h, b))
