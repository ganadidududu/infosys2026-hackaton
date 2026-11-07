"""Auditon 가상 데이터 생성기.

기준안 양식을 본뜬 한 회계기간(1차: 1/1~6/30)의 통장·영수증·감사자료·과거 감사 사례·질의·답변·학기 일정과
정답(truth)을 만든다. 실제 학생회 데이터는 쓰지 않는다.

  python data/synthetic/generate.py            # tune(seed 7) + eval(seed 2026) 생성
  python data/synthetic/generate.py --set tune

조정용(tune)과 평가용(eval)은 시드가 달라 금액·날짜·업체명·이름이 바뀐다. 평가용은 개발 중 열지 않는다.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDS = {"tune": 7, "eval": 2026}

SURNAMES = list("김이박최정강조윤장임한오서신권황안송류홍")
GIVEN = ["민준", "서연", "지호", "하은", "도윤", "수아", "예준", "지유", "시우", "채원", "주원", "다은", "건우", "소윤", "현우", "유나"]


def won(x: float) -> int:
    return int(round(x / 100.0)) * 100


class Gen:
    def __init__(self, seed: int, year: int = 2026):
        self.r = random.Random(seed)
        self.year = year
        self.tx: list[dict] = []
        self.rc: list[dict] = []
        self.docs: list[dict] = []
        self.truth_match: list[dict] = []
        self.truth_income: dict[str, dict] = {}
        self.transfers: list[dict] = []
        self.n_tx = 0
        self.n_rc = 0

    # ---------- helpers ----------
    def d(self, m: int, day: int, jitter: int = 0) -> date:
        dd = date(self.year, m, day)
        if jitter:
            dd += timedelta(days=self.r.randint(-jitter, jitter))
        return dd

    def name(self) -> str:
        return self.r.choice(SURNAMES) + self.r.choice(GIVEN)

    def amt(self, base: int, pct: float = 0.08) -> int:
        return won(base * (1 + self.r.uniform(-pct, pct)))

    def add_tx(self, acc: str, dt: date, desc: str, inflow: int = 0, outflow: int = 0, **kw) -> str:
        self.n_tx += 1
        tid = f"T{self.n_tx:03d}"
        self.tx.append({"id": tid, "account": acc, "date": dt.isoformat(), "desc": desc,
                        "in": inflow, "out": outflow, **kw})
        return tid

    def add_rc(self, project: str, dt: date, vendor: str, items: list[tuple[str, int, int]] | None, total: int,
               kind: str, pay: str, **kw) -> str:
        self.n_rc += 1
        rid = f"R{self.n_rc:03d}"
        has_items = bool(items)
        lines = [f"{vendor}", f"사업자번호 {self.r.randint(100,999)}-{self.r.randint(10,99)}-{self.r.randint(10000,99999)}",
                 f"일시 {dt.isoformat()} {self.r.randint(10,21)}:{self.r.randint(0,59):02d}"]
        if items:
            for nm, q, p in items:
                lines.append(f"{nm} {q} x {p:,} = {q*p:,}")
        else:
            lines.append("품목: (세목 표기 없음)")
        supply = round(total / 1.1)
        lines += [f"공급가액 {supply:,}", f"부가세 {total-supply:,}", f"합계 {total:,}"]
        if pay == "카드":
            lines.append(f"카드 ****-{kw.get('card_last4','4417')} " + ("일시불" if not kw.get("installment") else f"할부 {kw['installment']}개월"))
        if kw.get("points"):
            lines.append(f"포인트 적립 {kw['points']:,}P")
        conf = {"date": round(self.r.uniform(0.9, 0.99), 2), "vendor": round(self.r.uniform(0.75, 0.98), 2),
                "amount": round(self.r.uniform(0.93, 0.995), 3), "items": round(self.r.uniform(0.8, 0.97), 2)}
        if kw.pop("blurry", False):
            conf["vendor"] = 0.52
            conf["items"] = 0.61
        self.rc.append({"id": rid, "project": project, "date": dt.isoformat(), "vendor": vendor,
                        "amount": total, "items": [{"name": n, "qty": q, "price": p} for n, q, p in (items or [])],
                        "has_items": has_items, "kind": kind, "pay": pay,
                        "card_last4": kw.get("card_last4", "4417" if pay == "카드" else None),
                        "installment": kw.get("installment", 0), "points": kw.get("points", 0),
                        "invoice": kw.get("invoice"), "attachments": kw.get("attachments", []),
                        "ocr_text": "\n".join(lines), "confidence": conf})
        return rid

    def doc(self, did: str, kind: str, project: str | None, title: str, text: str):
        self.docs.append({"id": did, "kind": kind, "project": project, "title": title, "text": text})

    # ---------- scenario ----------
    def build(self) -> dict:
        r = self.r
        y = self.year
        carry = self.amt(2_350_000, 0.1)

        # ---- 학생회비 (사업 0) ----
        for i, grade in enumerate(["1학년", "2학년", "3학년", "4학년"]):
            cnt = r.randint(28, 40)
            a = cnt * 25_000
            t = self.add_tx("main", self.d(3, 3 + i, 1), f"{self.name()} 학생회비{grade}", inflow=a)
            self.truth_income[t] = {"project": "학생회비", "class": "학생회비"}

        # ---- 관리운영비 97: 정수기 렌탈 자동이체 (같은 금액 반복) ----
        rent = self.amt(33_000, 0.0)
        for m in range(1, 7):
            dt = self.d(m, 25)
            t = self.add_tx("main", dt, "OO렌탈 자동이체", outflow=rent)
            rid = self.add_rc("관리운영비", dt, "OO렌탈", [("정수기 렌탈료", 1, rent)], rent, "현금영수증", "계좌이체")
            self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})

        # ---- 감사비용 100 ----
        a = self.amt(27_500)
        dt = self.d(1, 20, 2)
        t = self.add_tx("main", dt, "OO인쇄소", outflow=a)
        rid = self.add_rc("감사비용", dt, "OO인쇄소", [("감사자료 인쇄·제본", 1, a)], a, "카드전표", "카드")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})

        # ---- 소모품비 98 ----
        for (m, dd, v, it, base) in [(3, 4, "다이소 OO점", "청소용품·건전지", 48_500), (4, 20, "OO문구", "필기구·포스트잇", 23_000)]:
            a = self.amt(base)
            dt = self.d(m, dd, 1)
            t = self.add_tx("main", dt, v, outflow=a)
            rid = self.add_rc("소모품비", dt, v, [(it, 1, a)], a, "카드전표", "카드")
            self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})

        # ---- 개강총회: 장소 예약금 → 장소 변경으로 환불, 음식 카드 ----
        dep = 100_000
        dt = self.d(3, 5)
        t1 = self.add_tx("main", dt, "OO홀 예약금", outflow=dep)
        rid = self.add_rc("개강총회", dt, "OO홀", None, dep, "이체내역서", "계좌이체", attachments=["과거거래내역서", "이체내역서"])
        self.truth_match.append({"tx": [t1], "rc": [rid], "kind": "1:1"})
        t2 = self.add_tx("main", self.d(3, 9), "OO홀 환불", inflow=dep)
        self.truth_income[t2] = {"project": "개강총회", "class": "취소"}
        a = self.amt(312_000)
        dt = self.d(3, 6)
        t = self.add_tx("main", dt, "OO치킨 신촌점", outflow=a)
        n = a // 19_000
        rid = self.add_rc("개강총회", dt, "OO치킨 신촌점", [("후라이드", n, 19_000), ("음료", 1, a - n * 19_000)], a, "카드전표", "카드")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})

        # ---- 과잠 공동구매: 수금(사업수익금, 질의·답변), 제작비 카드 할부 3개월 ----
        price = 45_000
        total_people = 0
        for k in range(5):
            cnt = r.randint(18, 30)
            total_people += cnt
            t = self.add_tx("main", self.d(3, 11 + k), f"{self.name()} 과잠{cnt}명", inflow=cnt * price)
            self.truth_income[t] = {"project": "과잠 공동구매", "class": "사업수익금"}
        cost = won(total_people * 44_000)
        dt = self.d(3, 25)
        t = self.add_tx("main", dt, "OO어패럴", outflow=cost)
        rid = self.add_rc("과잠 공동구매", dt, "OO어패럴", [("학과 과잠 제작", total_people, 44_000)], cost, "카드전표", "카드", installment=3)
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})

        # ---- MT: 참가비 > 지출 (신규 유형), 예약금, 포인트 적립, 버스 ----
        fee = 60_000
        mt_people = r.randint(29, 33)
        fee_total = 0
        groups = [mt_people // 3, mt_people // 3, mt_people - 2 * (mt_people // 3)]
        for k, g in enumerate(groups):
            t = self.add_tx("main", self.d(4, 1 + k), f"{self.name()} MT{g}명", inflow=g * fee)
            fee_total += g * fee
            self.truth_income[t] = {"project": "MT", "class": "참가비"}
        dep = 300_000
        dt = self.d(4, 3)
        t = self.add_tx("main", dt, "OO펜션 예약금", outflow=dep)
        rid = self.add_rc("MT", dt, "OO펜션", None, dep, "이체내역서", "계좌이체", attachments=["과거거래내역서", "이체내역서"])
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        bal = won(fee_total * 0.39)
        mart = won(fee_total * 0.21)
        bus = won(fee_total * 0.15)
        dt = self.d(4, 24)
        t = self.add_tx("main", dt, "OO펜션", outflow=bal)
        rid = self.add_rc("MT", dt, "OO펜션", [("객실 잔금", 1, bal)], bal, "카드전표", "카드")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        t = self.add_tx("main", dt, "OO마트 가평점", outflow=mart)
        rid = self.add_rc("MT", dt, "OO마트 가평점", [("식재료", 1, mart - 42_000), ("음료", 1, 42_000)], mart, "카드전표", "카드", points=won(mart * 0.0033) // 10 * 10 or 1240)
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        t = self.add_tx("main", dt, "OO관광", outflow=bus)
        rid = self.add_rc("MT", dt, "OO관광", [("버스 대절(왕복)", 1, bus)], bus, "현금영수증", "계좌이체")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        # 통장에 없는 영수증 (개인 카드로 결제)
        self.add_rc("MT", dt, "OO편의점", [("얼음", 2, 7_800)], 15_600, "카드전표", "카드", card_last4="9021", blurry=True)
        mt_spend = dep + bal + mart + bus

        # ---- 공대 연합 체육대회: 단체간거래 수입 ----
        a = 400_000
        t = self.add_tx("main", self.d(5, 2), "공과대학학생회", inflow=a)
        self.truth_income[t] = {"project": "공대 연합 체육대회", "class": "기타"}
        a2 = self.amt(186_000)
        dt = self.d(5, 9)
        t = self.add_tx("main", dt, "OO베이커리", outflow=a2)
        rid = self.add_rc("공대 연합 체육대회", dt, "OO베이커리", [("간식 세트", a2 // 6_000, 6_000)], (a2 // 6_000) * 6_000, "카드전표", "카드")
        # 금액 차이(묶음 할인)로 대사 점수가 조금 낮아진다
        self.rc[-1]["amount"] = (a2 // 6_000) * 6_000
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})

        # ---- 축제 부스: 별도 통장(승인), 카드 매출 수수료, 세목 없는 업체 계산서(③ 누락), 같은 날 같은 금액 2건 ----
        seed_money = 1_000_000
        t = self.add_tx("main", self.d(5, 18), "축제통장 이체", outflow=seed_money, internal=True)
        t2 = self.add_tx("fest", self.d(5, 18), "학생회비통장 이체", inflow=seed_money, internal=True)
        self.truth_income[t2] = {"project": "축제 부스", "class": "내부 이체"}
        rent_eq = 450_000
        dt = self.d(5, 20)
        t = self.add_tx("fest", dt, "OO음향", outflow=rent_eq)
        rid = self.add_rc("축제 부스", dt, "OO음향", None, rent_eq, "계산서", "계좌이체",
                          invoice={"①": True, "②": True, "③": False, "④": True, "⑤": True, "⑥": True},
                          attachments=["총액 영수증", "계산서", "이체내역서"])
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        same = self.amt(87_000, 0.0)
        for v in ["OO마트 왕십리점", "OO정육"]:
            t = self.add_tx("fest", dt, v, outflow=same)
            rid = self.add_rc("축제 부스", dt, v, [("식재료", 1, same)], same, "카드전표", "카드", card_last4="7730")
            self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        a = self.amt(54_000)
        t = self.add_tx("fest", dt, "OO유통", outflow=a)
        rid = self.add_rc("축제 부스", dt, "OO유통", [("일회용 용기", 1, a)], a, "카드전표", "카드", card_last4="7730")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        drinks = 120_000
        dt = self.d(5, 21)
        t = self.add_tx("fest", dt, "OO음료도매", outflow=drinks)
        rid = self.add_rc("축제 부스", dt, "OO음료도매", [("탄산음료 박스", 8, 15_000)], drinks, "카드전표", "카드", card_last4="7730")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        gross = self.amt(820_000)
        fee_ = won(gross * 0.022)
        t = self.add_tx("fest", self.d(5, 22), "카드매출정산", inflow=gross - fee_, gross=gross, fee=fee_)
        self.truth_income[t] = {"project": "축제 부스", "class": "사업수익금"}
        cash = self.amt(412_000)
        t = self.add_tx("fest", self.d(5, 22), "현금매출 입금", inflow=cash)
        self.truth_income[t] = {"project": "축제 부스", "class": "사업수익금"}
        fest_bal = seed_money - rent_eq - 2 * same - a - drinks + (gross - fee_) + cash
        t = self.add_tx("fest", self.d(5, 31), "학생회비통장 이체", outflow=fest_bal, internal=True)
        t2 = self.add_tx("main", self.d(5, 31), "축제통장 잔액", inflow=fest_bal, internal=True)
        self.truth_income[t2] = {"project": "축제 부스", "class": "내부 이체"}

        # ---- 미분류 입금 ----
        t = self.add_tx("main", self.d(5, 28), self.name(), inflow=15_000)
        self.truth_income[t] = {"project": None, "class": "미분류"}

        # ---- 종강총회: 나눠 결제(1:N), 전용(비고 없음) ----
        half = 120_000
        dt = self.d(6, 5)
        ta = self.add_tx("main", dt, "OO애드", outflow=half)
        tb = self.add_tx("main", dt, "OO애드", outflow=half)
        rid = self.add_rc("종강총회", dt, "OO애드", [("현수막", 2, half)], 2 * half, "카드전표", "카드")
        self.truth_match.append({"tx": [ta, tb], "rc": [rid], "kind": "1:N"})
        a = self.amt(245_000)
        dt = self.d(6, 12)
        t = self.add_tx("main", dt, "OO족발", outflow=a)
        rid = self.add_rc("종강총회", dt, "OO족발", [("족발 세트", 1, a)], a, "카드전표", "카드")
        self.truth_match.append({"tx": [t], "rc": [rid], "kind": "1:1"})
        self.transfers.append({"date": self.d(6, 12).isoformat(), "from": "축제 부스", "to": "종강총회",
                               "amount": 32_000, "content": "축제 잔여 음료 사용", "note": ""})

        # ---- 이자 ----
        t = self.add_tx("main", self.d(6, 27), "예금결산이자", inflow=self.r.randint(900, 1600))
        self.truth_income[t] = {"project": "사업무관거래", "class": "예금결산이자"}

        # 정렬 + 잔액
        self.tx.sort(key=lambda x: (x["date"], x["id"]))
        remap = {x["id"]: f"T{i+1:03d}" for i, x in enumerate(self.tx)}
        for x in self.tx:
            x["id"] = remap[x["id"]]
        for m in self.truth_match:
            m["tx"] = [remap[i] for i in m["tx"]]
        self.truth_income = {remap[k]: v for k, v in self.truth_income.items()}
        bal = {"main": carry, "fest": 0}
        for x in self.tx:
            bal[x["account"]] += x["in"] - x["out"]
            x["balance"] = bal[x["account"]]

        return self.assemble(carry, fee_total, mt_spend, total_people, mt_people)

    def assemble(self, carry, fee_total, mt_spend, gwajam_people, mt_people) -> dict:
        y = self.year
        projects = [
            {"name": "학생회비", "fixed": 0}, {"name": "관리운영비", "fixed": 97}, {"name": "소모품비", "fixed": 98},
            {"name": "사업무관거래", "fixed": 99}, {"name": "감사비용", "fixed": 100},
            {"name": "개강총회", "overview": {"대상": "정보시스템학과 재학생", "참가인원": {"집행부": 9, "전체": 64},
                "사업내용": "새 학기 개강총회를 열어 학생회 사업 계획을 안내하고 학년별 교류 시간을 가졌다.",
                "수입적요": "장소 변경으로 대관 예약금이 환불됨", "지출적요": "대관 예약금, 개강총회 음식", "비고": ""}},
            {"name": "과잠 공동구매", "overview": {"대상": "정보시스템학과 재학생", "참가인원": {"집행부": 9, "전체": gwajam_people},
                "사업내용": "과잠 공동구매 진행 및 배부. 수요조사 후 업체 견적을 받아 제작했다.",
                "수입적요": "과잠 구매 신청자의 대금 수취", "지출적요": "과잠 제작비", "비고": "수입 구분은 2026-03-02 질의·답변에 따름"}},
            {"name": "MT", "overview": {"대상": "MT 참가자", "참가인원": {"집행부": 8, "전체": mt_people},
                "사업내용": "1박 2일 학과 MT를 가평에서 진행했다.",
                "수입적요": "MT 참가비", "지출적요": "숙소 예약금·잔금, 장보기, 버스 대절", "비고": ""}},
            {"name": "공대 연합 체육대회", "overview": {"대상": "공과대학 재학생", "참가인원": {"집행부": 6, "전체": 48},
                "사업내용": "공과대학 학생회와 공동으로 체육대회를 열고 학과 참가자 간식을 지원했다.",
                "수입적요": "공과대학 학생회 분담금(단체간거래)", "지출적요": "참가자 간식", "비고": "단체간거래확인서 첨부"}},
            {"name": "축제 부스", "overview": {"대상": "정보시스템학과 학생회비 납부자(운영 인력)", "참가인원": {"집행부": 9, "전체": 22},
                "사업내용": "대동제 기간 학과 부스를 운영해 음식을 판매했다. 축제 별도 통장(수입·지출 모두)을 사용했다.",
                "수입적요": "부스 음식 판매(카드·현금)", "지출적요": "무대·음향 장비 대여, 식재료, 일회용품, 음료", "비고": "축제 통장 사본 2026-05-12 승인"}},
            {"name": "종강총회", "overview": {"대상": "정보시스템학과 재학생", "참가인원": {"집행부": 9, "전체": 51},
                "사업내용": "학기를 마무리하는 종강총회를 열었다.",
                "수입적요": "", "지출적요": "현수막, 음식", "비고": ""}},
        ]
        # 감사자료 문서 (인용 대상)
        for p in projects:
            ov = p.get("overview")
            if not ov:
                continue
            txt = (f"사업명: {p['name']}\n대상: {ov['대상']}\n참가인원: 집행부 {ov['참가인원']['집행부']}명 / 전체 {ov['참가인원']['전체']}명\n"
                   f"사업내용: {ov['사업내용']}\n수입 적요: {ov['수입적요']}\n지출 적요: {ov['지출적요']}\n비고: {ov['비고']}")
            self.doc(f"사업개요서-{p['name']}", "사업개요서", p["name"], f"사업개요서 · {p['name']}", txt)
        for rc in self.rc:
            self.doc(f"증빙-{rc['id']}", "증빙", rc["project"], f"{rc['kind']} · {rc['vendor']}", rc["ocr_text"])
            if rc.get("invoice"):
                inv = rc["invoice"]
                lines = [
                    "① 거래 업체: OO음향 · 대표 홍OO (서명)" if inv["①"] else "① (누락)",
                    "② 업체 연락처: 010-0000-1234" if inv["②"] else "② (누락)",
                    f"③ 산출 근거: 장비 대여 일체 {rc['amount']:,}원",
                    "④ 집행부 담당: 김OO · 010-0000-5678 · (서명)" if inv["④"] else "④ (누락)",
                    f"⑤ 거래 일자·수단·총액: {rc['date']} · 계좌이체 · {rc['amount']:,}원",
                    "⑥ 본 문서를 조작할 경우 법적 책임을 질 수 있음 · 담당자 (서명)" if inv["⑥"] else "⑥ (누락)",
                ]
                self.doc(f"계산서-{rc['id']}", "계산서", rc["project"], f"계산서 · {rc['vendor']}", "\n".join(lines))
        self.doc("이행기록-축제통장", "이행기록", "축제 부스", "체크리스트 이행 기록 · 축제 통장",
                 "2026-05-12 축제 부스 별도 통장 사본을 감사위원회에 전달함\n2026-05-12 감사위원회 승인(승인번호 26-F-03)\n선택한 방식: 수입·지출 모두 별도 통장")
        self.doc("통장사본-축제", "통장사본", "축제 부스", "통장사본 · 축제 부스 통장", "예금주: 정보시스템학과 학생회 · 가상은행 ***-***-7730 · 개설일 2026-05-11")

        cases = [
            {"id": "2025-2-산업공학과-C04", "dept": "산업공학과", "period": "2025-2", "clause": "3부 35조", "tags": ["계산서", "산출 근거", "세목 없음"],
             "desc": "세목 표기가 불가능한 업체 계산서에 견적 산출 근거(세목)가 빠짐", "disposition": {"type": "감점", "points": 1},
             "reason": "총액만 적힌 계산서는 35조 ③을 충족하지 않으며 지출 내역을 확인할 수 없음", "objection": False},
            {"id": "2025-1-정보시스템학과-C06", "dept": "정보시스템학과", "period": "2025-1", "clause": "3부 31조", "tags": ["카드 전표", "세목 없음"],
             "desc": "카드 전표에 세목이 표기되지 않음", "disposition": {"type": "감점", "points": 1},
             "reason": "세목 없는 전표로는 지출 성격을 확인할 수 없음", "objection": False},
            {"id": "2025-2-기계공학과-C11", "dept": "기계공학과", "period": "2025-2", "clause": "3부 8조", "tags": ["할부"],
             "desc": "학생회비 카드로 할부 결제함", "disposition": {"type": "경고"},
             "reason": "결제는 즉시 이루어져야 하며 할부는 허용되지 않음. 금액 손실이 없어 경고", "objection": True},
            {"id": "2025-1-정보시스템학과-C02", "dept": "정보시스템학과", "period": "2025-1", "clause": "3부 9조", "tags": ["포인트 적립"],
             "desc": "학생회비 결제로 마트 포인트를 적립함", "disposition": {"type": "경고"},
             "reason": "포인트 적립 금지 위반. 소액이고 사적 사용 정황이 없어 경고", "objection": False},
            {"id": "2025-2-산업공학과-C07", "dept": "산업공학과", "period": "2025-2", "clause": "3부 27조", "tags": ["전용", "비고 누락"],
             "desc": "물품 전용 처리에 산출 근거 비고가 없음", "disposition": {"type": "경고"},
             "reason": "전용 금액의 산출 근거를 확인할 수 없음", "objection": False},
            {"id": "2025-1-기계공학과-C03", "dept": "기계공학과", "period": "2025-1", "clause": "3부 40조", "tags": ["사업개요서", "대상란"],
             "desc": "사업개요서 '대상'란에 참여 조건 대신 '참가자'로만 적음", "disposition": {"type": "없음"},
             "reason": "다른 칸에서 참여 조건을 알 수 있어 감점하지 않음(주의)", "objection": False},
            {"id": "2025-2-산업공학과-C09", "dept": "산업공학과", "period": "2025-2", "clause": "3부 40조", "tags": ["사업개요서", "대상란"],
             "desc": "사업개요서 '대상'란에 참여 조건이 드러나지 않음", "disposition": {"type": "경고"},
             "reason": "참여 조건을 사업개요서 어디에서도 확인할 수 없음", "objection": True},
            {"id": "2025-2-기계공학과-C02", "dept": "기계공학과", "period": "2025-2", "clause": "3부 18조", "tags": ["축제 통장", "미승인"],
             "desc": "축제 별도 통장을 감사위원회 승인 없이 사용함", "disposition": {"type": "감점", "points": 2},
             "reason": "사전 승인 절차를 지키지 않아 통장의 신뢰성을 확인할 수 없음", "objection": False},
            {"id": "2025-1-산업공학과-C05", "dept": "산업공학과", "period": "2025-1", "clause": "3부 42조", "tags": ["사업개요서", "사업내용"],
             "desc": "사업내용란이 한 줄로 부실함", "disposition": {"type": "경고"},
             "reason": "사업 내용을 충실히 서술하지 않음", "objection": False},
            {"id": "2025-2-정보시스템학과-C01", "dept": "정보시스템학과", "period": "2025-2", "clause": "3부 11조", "tags": ["수입", "미분류"],
             "desc": "출처가 확인되지 않는 입금을 장부에 기록하지 않음", "disposition": {"type": "경고"},
             "reason": "모든 수입은 장부에 기록하고 구분해야 함", "objection": False},
        ]
        inquiries = [
            {"id": "Q-2026-1-01", "period": "2026-1", "date": "2026-03-02", "clauses": ["3부 12조"],
             "q": "과잠 공동구매 대금은 참가비와 사업수익금 중 무엇으로 구분하나요?",
             "a": "학생에게 물품을 판매하는 대가이므로 사업수익금(3부 12조 ③)으로 구분합니다."},
            {"id": "Q-2026-1-02", "period": "2026-1", "date": "2026-05-10", "clauses": ["3부 19조", "3부 20조"],
             "q": "축제 부스 수입·지출을 모두 별도 통장으로 처리하려 합니다. 축제 후 남은 금액은 어떻게 하나요?",
             "a": "축제 종료 후 학생회비 통장으로 이체하고, 두 장부 비고에 통장 간 이체임을 적어 주세요."},
        ]
        schedule = [
            {"id": "E1", "name": "개강총회", "type": "일반 행사", "date": f"{y}-03-06", "flags": ["예약금"]},
            {"id": "E2", "name": "과잠 공동구매", "type": "물품 판매·공동구매", "date": f"{y}-03-25", "flags": []},
            {"id": "E3", "name": "MT", "type": "참가비 사업", "date": f"{y}-04-24", "flags": ["예약금"]},
            {"id": "E4", "name": "공대 연합 체육대회", "type": "공동 사업", "date": f"{y}-05-09", "flags": []},
            {"id": "E5", "name": "축제 부스", "type": "축제 부스", "date": f"{y}-05-20", "flags": ["별도 통장", "세목 불가 업체"]},
            {"id": "E6", "name": "종강총회", "type": "일반 행사", "date": f"{y}-06-12", "flags": []},
        ]
        truth = {
            "matches": self.truth_match,
            "income": self.truth_income,
            "rule_violations": [
                {"clause": "3부 8조", "project": "과잠 공동구매"}, {"clause": "3부 9조", "project": "MT"},
                {"clause": "3부 13조", "project": "MT", "detail": {"참가비": fee_total, "지출": mt_spend}},
                {"clause": "3부 27조", "project": "종강총회"}, {"clause": "3부 35조", "project": "축제 부스", "item": "③"},
            ],
            "findings": [
                {"clause": "3부 35조", "project": "축제 부스", "same_case": "2025-2-산업공학과-C04", "disposition": {"type": "감점", "points": 1}},
                {"clause": "3부 8조", "project": "과잠 공동구매", "same_case": "2025-2-기계공학과-C11", "disposition": {"type": "경고"}},
                {"clause": "3부 9조", "project": "MT", "same_case": "2025-1-정보시스템학과-C02", "disposition": {"type": "경고"}},
                {"clause": "3부 27조", "project": "종강총회", "same_case": "2025-2-산업공학과-C07", "disposition": {"type": "경고"}},
                {"clause": "3부 13조", "project": "MT", "same_case": None, "new_type": True},
            ],
            "total_penalty_before_new": 2,
        }
        other = [
            {"dept": "산업공학과", "history": [{"period": "2025-1", "total": 1, "warnings": 2}, {"period": "2025-2", "total": 5, "warnings": 4}, {"period": "2026-1", "total": 2, "warnings": 1}]},
            {"dept": "기계공학과", "history": [{"period": "2025-1", "total": 0, "warnings": 1}, {"period": "2025-2", "total": 3, "warnings": 3}, {"period": "2026-1", "total": 1, "warnings": 2}]},
        ]
        return {
            "meta": {"dept": "정보시스템학과", "period": {"id": f"{y}-1", "label": f"{y}년 제1차 회계기간", "start": f"{y}-01-01", "end": f"{y}-06-30"},
                     "carry_over": carry, "synthetic": True, "audit": {"start": f"{y}-07-06", "end": f"{y}-07-10"}},
            "accounts": [{"id": "main", "name": "학생회비 통장", "number": "가상은행 ***-***-1234"},
                         {"id": "fest", "name": "축제 부스 통장", "number": "가상은행 ***-***-7730", "festival": True, "approved": f"{y}-05-12"}],
            "projects": projects, "transactions": self.tx, "receipts": self.rc, "documents": self.docs,
            "transfers": self.transfers, "cases": cases, "inquiries": inquiries, "schedule": schedule,
            "audited_evidence": [],
            "history": [{"period": "2025-1", "total": 2, "warnings": 2}, {"period": "2025-2", "total": 4, "warnings": 4}],
            "other_depts": other, "truth": truth,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["tune", "eval", "all"], default="all")
    a = ap.parse_args()
    for name, seed in SEEDS.items():
        if a.set not in (name, "all"):
            continue
        data = Gen(seed).build()
        out = HERE / name
        out.mkdir(parents=True, exist_ok=True)
        truth = data.pop("truth")
        (out / "dataset.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: 거래 {len(data['transactions'])}건, 증빙 {len(data['receipts'])}장 → {out}")


if __name__ == "__main__":
    main()
