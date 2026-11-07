/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react'
import { api, md, useApi, won } from '../api'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'

const CLASSES = ['학생회비', '참가비', '사업수익금', '예금결산이자', '기타', '취소']

export default function Reconcile({ embedded }: { embedded?: boolean }) {
  const rec = useApi('/reconcile')
  const led = useApi('/ledger')
  const [tab, setTab] = useState<'match' | 'ledger' | 'projects'>('match')
  const [acc, setAcc] = useState('main')
  const toast = useToast()
  if (rec.error) return <ErrorBox msg={rec.error} />
  if (!rec.data || !led.data) return <Loading />
  const R = rec.data.reconcile, T = rec.data.transactions, RC = rec.data.receipts
  const reload = () => { rec.reload(); led.reload() }
  async function decide(key: string, decision: string) {
    await api('/reconcile/decide', { body: { key, decision } }); toast(decision === '확정' ? '대사를 확정했습니다' : '짝을 풀었습니다'); reload()
  }
  const pending = R.pairs.filter((p: any) => p.status === '확인 필요')
  const auto = R.pairs.filter((p: any) => p.status !== '확인 필요')
  const C = R.counts
  const buckets = [
    ['자동 확정', C['자동 확정'] + C['확정(감사인)'], 'green'], ['확인 필요', C['확인 필요'], 'amber'], ['증빙 없음', C['증빙 없음'], 'red'],
    ['미분류 수입', C['미분류 수입'], 'amber'], ['통장에 없는 영수증', C['통장에 없는 영수증'], 'violet'],
  ] as const

  return (
    <>
      <div className="ph">
        {embedded ? <p className="small ink2" style={{ margin: 0 }}>지출은 역진법(모든 출금 → 증빙), 수입은 전진법(모든 입금 → 장부·수입 구분)으로 맞춥니다 <Cite c="2부 6.4" />.</p> : <div><div className="crumb">감사 기간</div><h1>통장 대사 · 감사자료</h1>
          <p>지출은 역진법(모든 출금 → 증빙), 수입은 전진법(모든 입금 → 장부·수입 구분)으로 맞춥니다 <Cite c="2부 6.4" />.</p></div>}
        <div className="row">
          <a className="btn" href="/api/export/statement.docx">수입/지출내역서 .docx</a>
          <a className="btn" href="/api/export/ledger/main.xlsx">총거래장부 .xlsx</a>
          <a className="btn" href="/api/export/ledger/fest.xlsx">축제 장부 .xlsx</a>
        </div>
      </div>
      <div className="kpi" style={{ marginBottom: 16 }}>
        {buckets.map(([k, n, c]) => <div key={k} className={`k ${n ? c : ''}`}><span>{k}</span><b>{n}</b></div>)}
      </div>
      <div className="card">
        <div className="tabs">
          <button className={tab === 'match' ? 'on' : ''} onClick={() => setTab('match')}>대사 결과</button>
          <button className={tab === 'ledger' ? 'on' : ''} onClick={() => setTab('ledger')}>총거래장부 · 내역서</button>
          <button className={tab === 'projects' ? 'on' : ''} onClick={() => setTab('projects')}>사업목록 · 사업개요서</button>
        </div>

        {tab === 'match' && (
          <div style={{ padding: 18, display: 'grid', gap: 18 }}>
            {pending.length > 0 && (
              <section>
                <div className="sec-t">확인 필요 <small>자동 확정 조건(s ≥ 0.85, 2위와 차 ≥ 0.1, 대안 대비 비용 차 ≥ Δ)을 못 넘었거나 나눠·묶음 결제</small></div>
                {pending.map((p: any) => (
                  <div key={p.key} className="card" style={{ padding: 14, marginBottom: 10, borderColor: 'var(--amber)', display: 'grid', gridTemplateColumns: '1fr 40px 1fr auto', gap: 12, alignItems: 'center' }}>
                    <div>{p.rc.map((id: string) => <div key={id} className="small"><span className="tag t-b">증빙</span> <b>{RC[id].vendor}</b> {won(RC[id].amount)} · {md(RC[id].date)}</div>)}</div>
                    <div style={{ textAlign: 'center' }} className="muted">{p.kind}</div>
                    <div>{p.tx.map((id: string) => <div key={id} className="small"><span className="tag t-n">출금</span> {T[id].desc} {won(T[id].out)} · {md(T[id].date)}</div>)}</div>
                    <div className="row"><button className="btn sm" onClick={() => decide(p.key, '거절')}>짝 풀기</button><button className="btn sm p" onClick={() => decide(p.key, '확정')}>확정</button></div>
                    <div className="xs" style={{ gridColumn: '1/-1', color: 'var(--amber-ink)' }}>
                      {p.reason ?? p.reasons?.join(' · ')}{p.s != null && ` · s=${p.s} (금액 ${p.parts.amt}, 날짜 ${p.parts.date}, 이름 ${p.parts.name})`}
                    </div>
                  </div>
                ))}
              </section>
            )}
            {R.unclassified.length > 0 && (
              <section>
                <div className="sec-t">미분류 수입 <small>전진법: 모든 입금은 장부에 기록하고 수입 구분 <Cite c="3부 12조" /></small></div>
                {R.unclassified.map((id: string) => <IncomeFix key={id} t={T[id]} projects={led.data.projects} reload={reload} />)}
              </section>
            )}
            {R.no_evidence.length > 0 && (
              <section><div className="sec-t">증빙 없음 <small>역진법: 출금에 증빙이 없음</small></div>
                {R.no_evidence.map((id: string) => <div key={id} className="small" style={{ padding: 8 }}>{T[id].date} {T[id].desc} {won(T[id].out)}원</div>)}</section>
            )}
            {R.not_in_bank.length > 0 && (
              <section><div className="sec-t">통장에 없는 영수증 <small>학생회비 통장 결제가 아님(개인 결제 등)</small></div>
                {R.not_in_bank.map((id: string) => <div key={id} className="small" style={{ padding: 8 }}><span className="tag t-v">{id}</span> {RC[id].vendor} {won(RC[id].amount)}원 · {RC[id].date} · 카드 끝 {RC[id].card_last4}</div>)}</section>
            )}
            <section>
              <div className="sec-t">확정된 짝 <small>{auto.length}건 · 헝가리안 전체 최적(총비용 {R.total_cost})</small></div>
              <div className="scroll" style={{ maxHeight: 420, border: '1px solid var(--line)', borderRadius: 12 }}>
                <table className="t"><thead><tr><th>증빙</th><th>출금</th><th className="r">금액</th><th className="r">점수 s</th><th>금액·날짜·이름</th><th>상태</th></tr></thead>
                  <tbody>{auto.map((p: any) => (
                    <tr key={p.key}><td>{p.rc.map((i: string) => RC[i].vendor).join(', ')}</td><td>{p.tx.map((i: string) => `${md(T[i].date)} ${T[i].desc}`).join(' + ')}</td>
                      <td className="r num">{won(p.tx.reduce((s: number, i: string) => s + T[i].out, 0))}</td><td className="r num">{p.s?.toFixed(2) ?? '–'}</td>
                      <td className="mono muted">{p.parts ? `${p.parts.amt} · ${p.parts.date} · ${p.parts.name}` : p.kind}</td>
                      <td><span className="tag t-g">{p.status}</span></td></tr>))}</tbody></table>
              </div>
            </section>
          </div>
        )}

        {tab === 'ledger' && (
          <div>
            <div className="row" style={{ padding: '12px 18px', justifyContent: 'space-between' }}>
              <div className="seg">{led.data.accounts.map((a: any) => <button key={a.id} className={acc === a.id ? 'on' : ''} onClick={() => setAcc(a.id)}>{a.name}</button>)}</div>
              <span className="xs muted">“(사업번호)-(일련번호)” <Cite c="3부 50조" /> · 첫 행 전기 이월 <Cite c="3부 58조" /></span>
            </div>
            <div className="scroll">
              <table className="t">
                <thead><tr><th>사업-일련</th><th>일자</th><th>통장내역</th><th>거래내용</th><th>구분</th><th>세목</th><th className="r">수입</th><th className="r">지출</th><th>결제</th><th>증빙</th><th>비고</th></tr></thead>
                <tbody>{led.data.ledgers[acc].map((r: any) => (
                  <tr key={r.seq} style={r.class === '미분류' || r.note.includes('확인 필요') ? { background: 'var(--amber-soft)' } : undefined}>
                    <td className="mono">{r.code}</td><td className="num">{r.date.slice(5)}</td><td>{r.bank_desc}</td><td>{r.content}</td>
                    <td><span className="tag t-n">{r.class}</span></td><td className="xs">{r.items}</td>
                    <td className="r num">{r.in ? won(r.in) : ''}</td><td className="r num">{r.out ? won(r.out) : ''}</td><td>{r.method}</td>
                    <td className="xs">{r.evidence.join(', ')}</td><td className="xs muted">{r.note}</td></tr>))}</tbody>
              </table>
            </div>
            {acc === 'main' && <TransferNotes transfers={led.data.transfers} reload={reload} />}
          </div>
        )}

        {tab === 'projects' && (
          <div style={{ padding: 18 }} className="grid">
            <p className="small ink2" style={{ margin: 0 }}>사업번호는 발생 순서대로 1부터, 학생회비 0·관리운영비 97·소모품비 98·사업무관거래 99·감사비용 100은 고정입니다 <Cite c="3부 37조" /><Cite c="3부 38조" />. 수입·지출 총액(교비 제외)은 자동, 나머지 칸은 집행부가 씁니다 <Cite c="3부 46조" />.</p>
            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))' }}>
              {led.data.projects.map((p: any) => (
                <div key={p.no} className="card pad">
                  <div className="row" style={{ justifyContent: 'space-between' }}><b><span className="tag t-b" style={{ marginRight: 6 }}>{p.no}</span>{p.name}</b>{p.fixed && <span className="tag t-n">고정</span>}</div>
                  <div className="row small" style={{ gap: 18, margin: '10px 0' }}><span>수입 <b className="num">{won(p.income)}</b></span><span>지출 <b className="num">{won(p.expense)}</b></span></div>
                  {p.overview && <div className="xs ink2" style={{ lineHeight: 1.7 }}>대상: {p.overview['대상']} · 참가 {p.overview['참가인원']['집행부']}/{p.overview['참가인원']['전체']}명<br />{p.overview['사업내용']}</div>}
                </div>))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function IncomeFix({ t, projects, reload }: any) {
  const [project, setProject] = useState('')
  const [cls, setCls] = useState('기타')
  const toast = useToast()
  return (
    <div className="card" style={{ padding: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', borderColor: 'var(--amber)' }}>
      <span className="small"><b>{t.date}</b> “{t.desc}” 입금 <b className="num">{won(t.in)}</b>원</span><span className="sp" />
      <select className="input" style={{ width: 'auto' }} value={project} onChange={(e) => setProject(e.target.value)}>
        <option value="">사업 선택</option>{projects.map((p: any) => <option key={p.no} value={p.name}>{p.no} · {p.name}</option>)}</select>
      <select className="input" style={{ width: 'auto' }} value={cls} onChange={(e) => setCls(e.target.value)}>{CLASSES.map((c) => <option key={c}>{c}</option>)}</select>
      <button className="btn sm p" disabled={!project} onClick={async () => { await api(`/income/${t.id}`, { body: { project, class: cls } }); toast('수입 구분을 지정했습니다'); reload() }}>지정</button>
    </div>
  )
}

function TransferNotes({ transfers, reload }: any) {
  const toast = useToast()
  return (
    <div style={{ padding: 18, borderTop: '1px solid var(--line)' }}>
      <div className="sec-t">전용 처리 <small>산출 근거를 비고에 적어야 합니다 <Cite c="3부 27조" /></small></div>
      {transfers.map((tr: any) => {
        const key = `${tr.date}|${tr.from}|${tr.to}`
        return (
          <div key={key} className="row small" style={{ gap: 10, flexWrap: 'wrap' }}>
            <span>{tr.date} · {tr.from} → {tr.to} · {won(tr.amount)}원 · {tr.content}</span>
            <input className="input" style={{ maxWidth: 320 }} placeholder="예: 음료 8박스 중 2박스(25%) 사용" defaultValue={tr.note}
              onBlur={async (e) => { if (e.target.value !== tr.note) { await api('/transfer-note', { body: { key, note: e.target.value } }); toast('산출 근거를 저장했습니다'); reload() } }} />
          </div>)
      })}
    </div>
  )
}
