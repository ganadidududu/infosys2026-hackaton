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
  const [i, setI] = useState(0)
  const [q, setQ] = useState('')
  const rows = s.rows as any[]
  const idx = Math.min(i, rows.length - 1)
  const row = rows[idx]
  const go = (n: number) => setI(Math.max(0, Math.min(rows.length - 1, n)))
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 300px', alignItems: 'start' }}>
      <div className="card" style={{ background: '#e9edf3', padding: '16px 24px 28px' }}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 14 }}>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn sm" onClick={() => go(idx - 1)} disabled={idx === 0}>‹ 이전</button>
            <span className="small num" style={{ minWidth: 90, textAlign: 'center' }}><b>{idx + 1}</b> / {rows.length} 페이지</span>
            <button className="btn sm" onClick={() => go(idx + 1)} disabled={idx === rows.length - 1}>다음 ›</button>
          </div>
          <input className="input" style={{ maxWidth: 220 }} placeholder="번호·업체로 찾기 (예: 3-23)" value={q}
            onChange={(e) => { setQ(e.target.value); const k = rows.findIndex((r) => r.code === e.target.value || r.bank_desc.includes(e.target.value) || r.content.includes(e.target.value)); if (e.target.value && k >= 0) setI(k) }} />
        </div>
        {row && <FormPage row={row} rc={(row.rc ?? [])[0] ? s.receipts[row.rc[0]] : null} rid={(row.rc ?? [])[0]} />}
      </div>
      <div className="grid" style={{ position: 'sticky', top: 76 }}>
        <div className="card pad">
          <div className="sec-t">내려받기</div>
          <a className="btn b" style={{ width: '100%', marginBottom: 8 }} href="/api/export/statement.docx">수입/지출내역서 .docx ({rows.length}페이지)</a>
          <a className="btn" style={{ width: '100%', marginBottom: 8 }} href="/api/export/ledger/main.xlsx">총거래장부 .xlsx (학생회비 통장)</a>
          <a className="btn" style={{ width: '100%' }} href="/api/export/ledger/fest.xlsx">축제 장부 .xlsx (3부 20조)</a>
          <div className="xs muted" style={{ marginTop: 10, lineHeight: 1.6 }}>거래 1건이 1페이지입니다. 데이터: {data.using === 'csv' ? `올린 CSV(${data.csv.filename})` : '예시 거래 데이터'}</div>
        </div>
        <div className="card pad small ink2" style={{ lineHeight: 1.75 }}>
          <div className="sec-t">자동으로 채우는 칸</div>
          · 사업 및 일련번호 “(사업번호)-(일련번호)” <Cite c="3부 50조" /><br />· 통장내역은 과거거래내역서 문구 그대로 <Cite c="3부 51조" /><br />
          · 세목·수량·단가는 영수증 표기 그대로, 수입은 수수료 뺀 순액 <Cite c="3부 53조" /><br />· 지급방법·증빙종류 <Cite c="3부 54조" /><br />
          · 증빙서류 칸: 영수증 사진(없으면 인식한 영수증 내용) <Cite c="3부 55조" />
        </div>
        <div className="card pad" style={{ maxHeight: 300, overflow: 'auto' }}>
          <div className="sec-t">페이지 목록</div>
          {rows.map((r, k) => (
            <button key={k} onClick={() => setI(k)} className="row small" style={{ all: 'unset', cursor: 'pointer', display: 'flex', width: '100%', gap: 8, padding: '5px 6px', borderRadius: 6, background: k === idx ? 'var(--brand-soft)' : undefined }}>
              <span className="mono" style={{ minWidth: 44 }}>{r.code}</span><span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.bank_desc}</span>
              <span className="num xs" style={{ color: r.in ? 'var(--green)' : 'var(--ink2)' }}>{r.in ? '+' : '−'}{won(r.in || Math.abs(r.out))}</span>
            </button>))}
        </div>
      </div>
    </div>
  )
}

// 감사위원회 양식 그대로: 거래 1건 = 1페이지
function FormPage({ row, rc, rid }: any) {
  const L: React.CSSProperties = { background: '#d9d9d9', textAlign: 'center', fontWeight: 600, whiteSpace: 'nowrap' }
  const C: React.CSSProperties = { textAlign: 'center' }
  const items = rc?.items?.length ? rc.items.map((i: any) => [i.name, i.qty, won(i.price)]) : [[row.items && !row.items.startsWith('(') ? row.items : row.content, 1, won(row.in || Math.abs(row.out))]]
  const N = 19
  const kinds = row.evidence.filter((e: string) => e !== '과거거래내역서')
  return (
    <div style={{ background: '#fff', boxShadow: '0 2px 14px rgba(14,21,37,.14)', borderRadius: 3, padding: '34px 30px 40px', maxWidth: 760, margin: '0 auto', aspectRatio: '210 / 297' }}>
      <div style={{ textAlign: 'center', fontSize: 24, fontWeight: 800, letterSpacing: 3, marginBottom: 16 }}>수입 / 지출 내역서</div>
      <table className="form-t">
        <colgroup><col style={{ width: '23%' }} /><col style={{ width: '9%' }} /><col style={{ width: '13%' }} /><col style={{ width: '14%' }} /><col style={{ width: '13%' }} /><col style={{ width: '11%' }} /><col style={{ width: '17%' }} /></colgroup>
        <tbody>
          <tr><td style={L}>사업 및 일련번호</td><td colSpan={6} style={C}>{row.code}</td></tr>
          <tr><td style={L}>사업명</td><td colSpan={6} style={C}>{row.project ?? ''}</td></tr>
          <tr><td style={L}>날짜</td><td colSpan={2} style={C}>{row.date.slice(5, 7)}.{row.date.slice(8, 10)}.</td><td style={L}>수입/지출</td><td style={C}>{row.in ? '수입' : '지출'}</td><td style={L}>구분</td><td style={C}>{row.class}</td></tr>
          <tr><td style={L}>통장내역</td><td colSpan={6} style={C}>{row.bank_desc}</td></tr>
          <tr><td style={L}>내용</td><td colSpan={6} style={C}>{row.content}</td></tr>
          <tr><td style={L}>세목</td><td style={L}>수량</td><td style={L}>단가</td><td style={L}>지급방법</td><td colSpan={3} style={C}>{row.method}</td></tr>
          {Array.from({ length: N + 1 }, (_, k) => {
            const it = items[k]
            const cells = <><td style={C}>{it?.[0]}</td><td style={C}>{it?.[1]}</td><td style={C}>{it?.[2]}</td></>
            if (k === 0) return <tr key={k}>{cells}<td style={L}>증빙종류</td><td colSpan={3} style={C}>{kinds[0] ?? row.evidence[0] ?? ''}</td></tr>
            if (k === 1) return <tr key={k}>{cells}<td colSpan={4} style={L}>증빙서류</td></tr>
            if (k === 2) return (
              <tr key={k}>{cells}
                <td colSpan={4} rowSpan={N - 1} style={{ verticalAlign: 'middle', textAlign: 'center', padding: 10 }}>
                  {rc?.image ? <img src={`/api/receipts/${rid}/image`} alt="영수증" style={{ maxWidth: '70%', maxHeight: 380 }} />
                    : rc ? <pre style={{ display: 'inline-block', textAlign: 'left', margin: 0, fontSize: 10.5, lineHeight: 1.55, fontFamily: 'ui-monospace,Menlo,monospace', background: '#fff', border: '1px dashed #c9cfdb', padding: '10px 14px' }}>{rc.ocr_text}</pre>
                    : <span className="small muted">{kinds.join(', ') || '과거거래내역서로 갈음'}</span>}
                </td></tr>)
            return <tr key={k}>{cells}</tr>
          })}
          <tr><td style={L}>총액</td><td colSpan={2} style={C}>{won(row.in || Math.abs(row.out))}</td></tr>
          <tr style={{ height: 44 }}><td style={L}>비고</td><td colSpan={6} style={{ ...C, fontSize: 12 }}>{row.note}</td></tr>
        </tbody>
      </table>
    </div>
  )
}

