/* eslint-disable @typescript-eslint/no-explicit-any */
import { Link } from 'react-router-dom'
import { api, useApi } from '../api'
import { ErrorBox, Loading, useToast } from '../ui/ui'

export default function Dashboard() {
  const meta = useApi('/meta')
  const cl = useApi('/checklist')
  const rec = useApi('/reconcile')
  const au = useApi('/audit')
  const rep = useApi('/report')
  const toast = useToast()
  if (meta.error) return <ErrorBox msg={meta.error} />
  if (!meta.data || !cl.data || !rec.data || !au.data || !rep.data) return <Loading />
  const m = meta.data, c = cl.data.stats, r = rec.data.reconcile.counts, a = au.data, p = rep.data

  const cards = [
    { n: 1, to: '/admin/checklist', t: '학기 전 · 체크리스트', when: '학기 시작 전', big: `${c.done}/${c.total}`, sub: `이행 완료 · 늦음 ${c.late}건`, state: c.done === c.total ? 'done' : 'todo',
      desc: '학기 일정을 넣으면 기준안에서 행사별 의무를 뽑고 권장 기한을 계산합니다.' },
    { n: 2, to: '/admin/receipts', t: '학기 중 · 영수증함', when: '결제할 때마다', big: `${rec.data ? Object.keys(rec.data.receipts).length : 0}장`, sub: `세목·증빙 종류 자동 인식`, state: 'done',
      desc: '사진 한 장이면 일시·업체·금액·세목·증빙 종류가 저장됩니다. 원본은 외부로 나가지 않습니다.' },
    { n: 3, to: '/admin/reconcile', t: '감사 기간 · 대사·감사자료', when: '회계기간 종료 후', big: `${r['자동 확정']}건`, sub: `자동 확정 · 확인 필요 ${r['확인 필요']} · 증빙 없음 ${r['증빙 없음']} · 미분류 ${r['미분류 수입']}`,
      state: r['확인 필요'] + r['미분류 수입'] === 0 ? 'done' : 'todo', desc: '헝가리안 대사 → 사업번호 → 수입/지출내역서 · 총거래장부(엑셀).' },
    { n: 4, to: '/admin/audit', t: '감사 · 감사 결과지', when: '감사 기간', big: a.ran ? `${a.totals.total}점` : '–', sub: a.ran ? `사례 ${a.totals.case_points} + 경고 ${a.totals.warning_points} · 확인 필요 ${a.totals.pending_check} · 신규 ${a.totals.pending_new}` : '아직 실행 전',
      state: a.ran && !a.totals.pending_check && !a.totals.pending_new ? 'done' : 'todo', desc: '감사 LLM 2회 → 코드 검증 → 선례 감점 + 경고 규칙 → 감사인단 확정.' },
    { n: 5, to: '/admin/report', t: '감사 후 · 보고서·공시', when: '감사 종료 후 3·7일, 1개월', big: p.published ? '공시됨' : p.sent ? '송부됨' : '–', sub: p.published ? `공시일 ${p.published}` : `송부 기한 ${p.deadlines.send_by}`,
      state: p.published ? 'done' : 'todo', desc: '감사의견 4가지 평가 → 송부 → 이의·답변 → 학생회 전자 공시.' },
  ]
  return (
    <>
      <div className="ph">
        <div>
          <div className="crumb">{m.dept} 학생회 · {m.period.label} ({m.period.start} ~ {m.period.end})</div>
          <h1>소 잃기 전에, 외양간부터.</h1>
          <p>학기 전에 알려 주고, 학기 중에 모아 두고, 감사는 기준안과 선례로 초안을 쓰고, 결과는 학생에게 공개합니다.</p>
        </div>
        <div className="row">
          <button className="btn" onClick={async () => { if (!confirm('시연 상태(확정·이의·공시 등)를 모두 지울까요?')) return; await api('/reset', { method: 'POST' }); toast('시연 상태를 초기화했습니다'); setTimeout(() => location.reload(), 400) }}>시연 초기화</button>
          <Link to="/admin/audit" className="btn b">감사 결과지 열기</Link>
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))' }}>
        {cards.map((x) => (
          <Link key={x.n} to={x.to} className="card pad" style={{ display: 'flex', flexDirection: 'column', gap: 10, transition: '.15s', borderColor: x.state === 'done' ? 'var(--line)' : 'var(--line)' }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span style={{ width: 26, height: 26, borderRadius: 8, background: x.state === 'done' ? 'var(--green)' : 'var(--brand)', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 13 }}>{x.state === 'done' ? '✓' : x.n}</span>
              <span className="xs muted">{x.when}</span>
            </div>
            <b style={{ fontSize: 15 }}>{x.t}</b>
            <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: -1 }}>{x.big}</div>
            <div className="small ink2">{x.sub}</div>
            <div className="xs muted" style={{ lineHeight: 1.6, marginTop: 'auto' }}>{x.desc}</div>
          </Link>
        ))}
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', marginTop: 16 }}>
        <div className="card pad">
          <div className="sec-t">설계 원칙</div>
          <ul className="small ink2" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
            <li><b>숫자는 코드가 정합니다.</b> 대사·증빙 유무·참가비 ≤ 지출·기한·감점 합산.</li>
            <li><b>감점은 선례에서 가져옵니다</b>(4부 23조). 선례가 없으면 감사인단 전원 논의(24조).</li>
            <li><b>경고</b> w회 → max(0, w − 2)(4부 26조), 회계기간마다 새로 셉니다.</li>
            <li><b>등급은 없습니다.</b> 감사의견은 4부 18조의 4가지 평가로 씁니다.</li>
            <li><b>두 LLM은 분리</b>합니다. 체크리스트 LLM과 감사 LLM은 모델·프롬프트가 다릅니다.</li>
          </ul>
        </div>
        <div className="card pad">
          <div className="sec-t">이 시연 환경</div>
          <div className="small ink2" style={{ lineHeight: 1.9 }}>
            데이터: <b>{m.dataset === 'tune' ? '조정용(tune) 가상 세트' : m.dataset}</b> · 실제 학생회 데이터 없음<br />
            감사 LLM: <b>{m.llm_mode === 'live' ? '라이브 API' : '재생 모드(모의 응답)'}</b> — <code className="mono">AUDITON_LLM=live</code>와 API 키로 전환<br />
            OCR: <b>{m.ocr_engine ?? '엔진 미설치 → 직접 입력'}</b> · 원본 이미지는 외부로 보내지 않음
          </div>
        </div>
      </div>
    </>
  )
}
