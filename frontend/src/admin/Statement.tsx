/* eslint-disable @typescript-eslint/no-explicit-any */
import { useRef, useState } from 'react'
import { api, useApi, won } from '../api'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'
import Receipts from './Receipts'
import Reconcile from './Reconcile'

type Tab = 'receipts' | 'csv' | 'match' | 'preview'

export default function Statement() {
  const [tab, setTab] = useState<Tab>('receipts')
  const { data, error, reload } = useApi('/statement')
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  const csv = data.csv
  const steps: [Tab, string, string][] = [
    ['receipts', '영수증 OCR·저장', `${data.statement.counts['자동 확정'] + data.statement.counts['확인 필요']}건 대사`],
    ['csv', '기중 거래 장부(CSV) 올리기', csv ? (csv.errors.length ? '열 지정 필요' : `${csv.parsed}행 인식`) : '예시 데이터 사용 중'],
    ['match', '영수증 ↔ 거래 대사', `확인 필요 ${data.statement.counts['확인 필요'] + data.statement.counts['미분류 수입']}`],
    ['preview', '수입/지출내역서(Word)', `${data.statement.rows.length}행`],
  ]
  return (
    <>
      <div className="ph">
        <div><div className="crumb">(수입·지출) 내역서</div><h1>영수증과 거래 장부로 학기말 내역서 만들기</h1>
          <p>영수증을 모아 두고, 기중 거래 장부(CSV)를 올리면 열을 자동으로 맞춰 기준안 양식의 수입/지출내역서(Word)로 바꿉니다 <Cite c="3부 49조" />.</p></div>
        <a className="btn b" href="/api/export/statement.docx">수입/지출내역서 .docx 받기</a>
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 16 }}>
        {steps.map(([k, l, s], i) => (
          <button key={k} onClick={() => setTab(k)} className="card" style={{ textAlign: 'left', padding: '14px 16px', cursor: 'pointer', borderColor: tab === k ? 'var(--brand)' : 'var(--line)', boxShadow: tab === k ? '0 0 0 3px var(--brand-soft)' : undefined }}>
            <div className="row" style={{ gap: 8 }}><span style={{ width: 22, height: 22, borderRadius: 7, display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 800, background: tab === k ? 'var(--brand)' : 'var(--gray-soft)', color: tab === k ? '#fff' : 'var(--mute)' }}>{i + 1}</span><b style={{ fontSize: 14 }}>{l}</b></div>
            <div className="xs muted" style={{ marginTop: 6, paddingLeft: 30 }}>{s}</div>
          </button>
        ))}
      </div>
      {tab === 'receipts' && <Receipts embedded />}
      {tab === 'csv' && <CsvStep data={data} reload={reload} next={() => setTab('match')} />}
      {tab === 'match' && <Reconcile embedded />}
      {tab === 'preview' && <Preview data={data} />}
    </>
  )
}

function CsvStep({ data, reload, next }: any) {
  const csv = data.csv
  const ref = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const [drag, setDrag] = useState(false)
  const fields = data.fields as Record<string, any>
  async function up(file: File) {
    const fd = new FormData(); fd.append('file', file)
    try { const r = await api('/statement/upload', { body: fd }); toast(r.errors.length ? '일부 열을 직접 지정해야 합니다' : '열을 자동으로 맞췄습니다'); reload() } catch (e: any) { toast(e.message, true) }
  }
  async function setCol(col: number, field: string) {
    const body: any = {}
    // 이 열에 있던 필드를 지우고 새 필드를 지정
    const prev = Object.entries(csv.mapping).find(([, v]: any) => v.col === col)?.[0]
    if (prev) body[prev] = null
    if (field) body[field] = col
    await api('/statement/mapping', { body }); reload()
  }
  const fieldOf = (j: number) => Object.entries(csv?.mapping ?? {}).find(([, v]: any) => v.col === j)
  return (
    <div className="grid">
      <div className="card pad" onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) up(f) }}
        style={{ borderStyle: 'dashed', background: drag ? 'var(--brand-soft)' : undefined, display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
        <input ref={ref} type="file" accept=".csv,.txt" hidden onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} />
        <div style={{ fontSize: 34 }}>📄</div>
        <div style={{ flex: 1, minWidth: 260 }}>
          <b>{csv ? csv.filename : '기중 거래 장부 CSV를 끌어다 놓거나 고르세요'}</b>
          <div className="small muted" style={{ marginTop: 4 }}>{csv ? `${csv.rows}행 · 인식 ${csv.parsed}행${csv.skipped.length ? ` · 건너뜀 ${csv.skipped.length}행` : ''}` : '은행 내보내기·학생회 장부 어느 양식이든 됩니다. UTF-8·CP949 모두 읽어요. 없으면 예시 데이터로 동작합니다.'}</div>
        </div>
        <a className="btn" href="/api/statement/sample.csv">예시 CSV 받기</a>
        {csv && <button className="btn" onClick={async () => { await api('/statement', { method: 'DELETE' }); reload() }}>지우기</button>}
        <button className="btn p" onClick={() => ref.current?.click()}>{csv ? '다른 파일' : 'CSV 올리기'}</button>
      </div>

      {csv && (
        <div className="card">
          <div className="pad row" style={{ justifyContent: 'space-between', borderBottom: '1px solid var(--line)' }}>
            <div className="sec-t" style={{ margin: 0 }}>열 자동 매핑 <small>열 이름과 값 모양(날짜·숫자·문자)으로 추정 · 틀리면 바꾸세요</small></div>
            {csv.errors.length ? <span className="tag t-r">{csv.errors.join(' · ')}</span> : <span className="tag t-g">매핑 완료 · {csv.parsed}행</span>}
          </div>
          <div className="scroll" style={{ maxHeight: 420 }}>
            <table className="t">
              <thead>
                <tr>{csv.header.map((h: string, j: number) => {
                  const fm = fieldOf(j) as any
                  return (
                    <th key={j} style={{ minWidth: 130, background: fm ? 'var(--green-soft)' : '#fafbfd' }}>
                      <select className="input" value={fm?.[0] ?? ''} onChange={(e) => setCol(j, e.target.value)} style={{ padding: '5px 6px', fontSize: 12, fontWeight: 700, borderColor: fm ? 'var(--green)' : undefined }}>
                        <option value="">사용 안 함</option>
                        {Object.entries(fields).map(([k, v]: any) => <option key={k} value={k}>{v.label}{v.required ? ' *' : ''}</option>)}
                      </select>
                      <div className="xs" style={{ marginTop: 4, fontWeight: 500, color: 'var(--ink2)' }}>원래 열: {h || `(${j + 1}열)`}
                        {fm && <span className="muted"> · {fm[1].manual ? '직접 지정' : `신뢰도 ${Math.round(fm[1].confidence * 100)}%`}</span>}</div>
                    </th>)
                })}</tr>
              </thead>
              <tbody>{csv.preview.map((r: string[], i: number) => <tr key={i}>{csv.header.map((_: any, j: number) => <td key={j} className="small">{r[j]}</td>)}</tr>)}</tbody>
            </table>
          </div>
          {csv.skipped.length > 0 && <div className="pad xs" style={{ color: 'var(--amber-ink)' }}>건너뛴 행: {csv.skipped.map((s: any) => `${s.row}행(${s.reason})`).join(', ')}</div>}
          <div className="pad row" style={{ justifyContent: 'flex-end' }}><button className="btn b" disabled={csv.errors.length > 0} onClick={next}>다음: 영수증과 대사 →</button></div>
        </div>
      )}
    </div>
  )
}

function Preview({ data }: any) {
  const s = data.statement
  const [acc, setAcc] = useState(Object.keys(s.accounts)[0])
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 300px', alignItems: 'start' }}>
      {/* 문서 미리보기 (Word와 같은 칸) */}
      <div className="card" style={{ background: '#e9edf3', padding: 24 }}>
        <div style={{ background: '#fff', boxShadow: '0 2px 12px rgba(14,21,37,.12)', borderRadius: 4, padding: '36px 34px', minHeight: 600 }}>
          <div style={{ textAlign: 'center', fontSize: 22, fontWeight: 800, letterSpacing: 2 }}>수입/지출내역서</div>
          <div style={{ textAlign: 'center' }} className="small ink2">정보시스템학과 학생회 · 2026년 제1차 회계기간</div>
          <div className="row" style={{ justifyContent: 'center', margin: '14px 0 18px' }}>
            <div className="seg">{Object.entries(s.accounts).map(([k, v]: any) => <button key={k} className={acc === k ? 'on' : ''} onClick={() => setAcc(k)}>{v}</button>)}</div>
          </div>
          <table className="t" style={{ fontSize: 11.5 }}>
            <thead><tr><th>사업-일련</th><th>일자</th><th>통장내역</th><th>내용</th><th>구분</th><th>세목</th><th className="r">수입</th><th className="r">지출</th><th>지급방법</th><th>증빙</th><th>비고</th></tr></thead>
            <tbody>{s.rows.filter((r: any) => ledgerAcc(r) === acc).map((r: any, i: number) => (
              <tr key={i} style={r.class === '미분류' || r.note.includes('확인 필요') ? { background: 'var(--amber-soft)' } : undefined}>
                <td className="mono">{r.code}</td><td>{r.date.slice(5)}</td><td>{r.bank_desc}</td><td>{r.content}</td><td>{r.class}</td><td>{r.items}</td>
                <td className="r num">{r.in ? won(r.in) : ''}</td><td className="r num">{r.out ? won(r.out) : ''}</td><td>{r.method}</td><td>{r.evidence.join(', ')}</td><td className="muted">{r.note}</td></tr>))}</tbody>
          </table>
        </div>
      </div>
      <div className="grid" style={{ position: 'sticky', top: 76 }}>
        <div className="card pad">
          <div className="sec-t">내려받기</div>
          <a className="btn b" style={{ width: '100%', marginBottom: 8 }} href="/api/export/statement.docx">수입/지출내역서 .docx</a>
          <a className="btn" style={{ width: '100%', marginBottom: 8 }} href="/api/export/ledger/main.xlsx">총거래장부 .xlsx (학생회비 통장)</a>
          <a className="btn" style={{ width: '100%' }} href="/api/export/ledger/fest.xlsx">축제 장부 .xlsx (3부 20조)</a>
          <div className="xs muted" style={{ marginTop: 10, lineHeight: 1.6 }}>데이터: {data.using === 'csv' ? `올린 CSV(${data.csv.filename})` : '예시 거래 데이터'}</div>
        </div>
        <div className="card pad small ink2" style={{ lineHeight: 1.75 }}>
          <div className="sec-t">작성 규칙</div>
          · “(사업번호)-(일련번호)” <Cite c="3부 50조" /><br />· 통장내역은 과거거래내역서 문구 그대로 <Cite c="3부 51조" /><br />
          · 세목은 영수증 표기 그대로, 수입은 수수료 뺀 순액 <Cite c="3부 53조" /><br />· 지급방법·증빙종류 <Cite c="3부 54조" /><br />
          · 고정 사업번호 0·97·98·99·100 <Cite c="3부 38조" />
        </div>
        <div className="card pad small">
          <div className="sec-t">사업별 합계</div>
          {s.projects.filter((p: any) => p.income || p.expense).map((p: any) => (
            <div key={p.no} className="row" style={{ justifyContent: 'space-between', padding: '4px 0' }}><span><span className="tag t-b">{p.no}</span> {p.name}</span><span className="num xs">+{won(p.income)} / −{won(p.expense)}</span></div>))}
        </div>
      </div>
    </div>
  )
}

function ledgerAcc(r: any) { return r.account ?? 'main' }
