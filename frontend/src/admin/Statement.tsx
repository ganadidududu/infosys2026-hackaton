/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from 'react'
import { api, useApi, won } from '../api'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'
import Receipts from './Receipts'

type Tab = 'receipts' | 'convert'

export default function Statement() {
  const [tab, setTab] = useState<Tab>('convert')
  const { data, error, reload } = useApi('/statement')
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  const csv = data.csv
  const steps: [Tab, string, string][] = [
    ['receipts', '영수증 OCR·저장', `증빙 ${Object.keys(data.statement.receipts).length}장 · 대사 ${data.statement.counts['자동 확정'] + data.statement.counts['확인 필요']}건`],
    ['convert', '거래 장부 → 수입/지출내역서(Word)', `${csv.source === 'sample' ? '예시 장부' : csv.filename} · ${data.statement.rows.length}페이지`],
  ]
  return (
    <>
      <div className="ph">
        <div><div className="crumb">(수입·지출) 내역서</div><h1>영수증과 거래 장부로 학기말 내역서 만들기</h1>
          <p>기중 거래 장부(엑셀·CSV)를 올리면 열을 자동으로 맞춰, 거래 1건마다 한 페이지인 수입/지출내역서(Word)로 바꿉니다 <Cite c="3부 49조" />.</p></div>
        <a className="btn b" href="/api/export/statement.docx">수입/지출내역서 .docx 받기</a>
      </div>
      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
        {steps.map(([k, l, s], i) => (
          <button key={k} onClick={() => setTab(k)} className="card" style={{ textAlign: 'left', padding: '14px 16px', cursor: 'pointer', borderColor: tab === k ? 'var(--brand)' : 'var(--line)', boxShadow: tab === k ? '0 0 0 3px var(--brand-soft)' : undefined }}>
            <div className="row" style={{ gap: 8 }}><span style={{ width: 22, height: 22, borderRadius: 7, display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 800, background: tab === k ? 'var(--brand)' : 'var(--gray-soft)', color: tab === k ? '#fff' : 'var(--mute)' }}>{i + 1}</span><b style={{ fontSize: 14 }}>{l}</b></div>
            <div className="xs muted" style={{ marginTop: 6, paddingLeft: 30 }}>{s}</div>
          </button>
        ))}
      </div>
      {tab === 'receipts' && <Receipts embedded />}
      {tab === 'convert' && <Convert data={data} reload={reload} />}
    </>
  )
}

const COL = (j: number) => String.fromCharCode(65 + (j % 26))

function Convert({ data, reload }: any) {
  const csv = data.csv
  const rows = data.statement.rows as any[]
  const fields = data.fields as Record<string, any>
  const ref = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const [drag, setDrag] = useState(false)
  const [page, setPage] = useState(0)
  const idx = Math.min(page, Math.max(0, rows.length - 1))
  const cur = rows[idx]
  const pageOfRow = (r: number) => rows.findIndex((x) => x.src_row === r)

  async function up(file: File) {
    const fd = new FormData(); fd.append('file', file)
    try { const r = await api('/statement/upload', { body: fd }); toast(r.errors.length ? '일부 열을 직접 지정해야 합니다' : '열을 자동으로 맞췄습니다'); setPage(0); reload() } catch (e: any) { toast(e.message, true) }
  }
  async function setCol(col: number, field: string) {
    const body: any = {}
    const prev = Object.entries(csv.mapping).find(([, v]: any) => v.col === col)?.[0]
    if (prev) body[prev] = null
    if (field) body[field] = col
    await api('/statement/mapping', { body }); reload()
  }
  const fieldOf = (j: number) => Object.entries(csv.mapping ?? {}).find(([, v]: any) => v.col === j) as any
  useEffect(() => { document.querySelector('tr.src-sel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [idx])

  return (
    <div className="grid" style={{ gap: 12 }}>
      {/* 파일 줄 */}
      <div className="card" onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) up(f) }}
        style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', borderStyle: 'dashed', background: drag ? 'var(--brand-soft)' : undefined }}>
        <input ref={ref} type="file" accept=".xlsx,.xlsm,.csv,.txt" hidden onChange={(e) => { if (e.target.files?.[0]) up(e.target.files[0]); e.target.value = '' }} />
        <span style={{ fontSize: 22 }}>📊</span>
        <div style={{ flex: 1, minWidth: 240 }}>
          <b className="small">{csv.filename}</b> {csv.source === 'sample' && <span className="tag t-a">예시</span>}
          <div className="xs muted">{csv.body.length}행 · 변환 {csv.parsed}건{csv.skipped.length ? ` · 건너뜀 ${csv.skipped.length}` : ''} · 엑셀(.xlsx)·CSV를 끌어다 놓아도 됩니다</div>
        </div>
        {csv.errors.length ? <span className="tag t-r">{csv.errors.join(' · ')}</span> : <span className="tag t-g">열 매핑 완료</span>}
        <a className="btn sm" href="/api/statement/sample.csv">예시 장부</a>
        {csv.source === 'upload' && <button className="btn sm" onClick={async () => { await api('/statement', { method: 'DELETE' }); setPage(0); reload() }}>예시로 되돌리기</button>}
        <button className="btn sm p" onClick={() => ref.current?.click()}>장부 올리기</button>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', alignItems: 'start', gap: 12 }}>
        {/* 왼쪽: 엑셀 원본 */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="row" style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)', justifyContent: 'space-between' }}>
            <b className="small">원본 장부</b><span className="xs muted">맨 위 칸에서 열 매핑을 바꿀 수 있어요 · 행을 누르면 오른쪽 페이지로</span>
          </div>
          <div className="xl-wrap">
            <table className="xl">
              <thead>
                <tr><th className="rn" />{csv.header.map((_: string, j: number) => <th key={j} className="cl">{COL(j)}</th>)}</tr>
                <tr className="map"><th className="rn">↳</th>{csv.header.map((h: string, j: number) => {
                  const fm = fieldOf(j)
                  return (
                    <th key={j} className={fm ? 'on' : ''}>
                      <select value={fm?.[0] ?? ''} onChange={(e) => setCol(j, e.target.value)}>
                        <option value="">— 사용 안 함</option>
                        {Object.entries(fields).map(([k, v]: any) => <option key={k} value={k}>{v.label}{v.required ? ' *' : ''}</option>)}
                      </select>
                    </th>)
                })}</tr>
                <tr className="hdr"><th className="rn">1</th>{csv.header.map((h: string, j: number) => <th key={j}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {csv.body.map((r: string[], i: number) => {
                  const p = pageOfRow(i)
                  return (
                    <tr key={i} className={`${cur?.src_row === i ? 'src-sel' : ''} ${p < 0 ? 'nolink' : ''}`} onClick={() => p >= 0 && setPage(p)} title={p >= 0 ? `${rows[p].code} 페이지로` : '변환되지 않은 행'}>
                      <th className="rn">{i + 2}</th>{csv.header.map((_: string, j: number) => <td key={j}>{r[j]}</td>)}
                    </tr>)
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* 오른쪽: 변환된 Word 페이지 */}
        <div className="card" style={{ background: '#e9edf3', overflow: 'hidden' }}>
          <div className="row" style={{ padding: '8px 12px', justifyContent: 'space-between', background: '#fff', borderBottom: '1px solid var(--line)' }}>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn sm" onClick={() => setPage(idx - 1)} disabled={idx === 0}>‹</button>
              <span className="small num" style={{ minWidth: 76, textAlign: 'center' }}><b>{idx + 1}</b> / {rows.length}쪽</span>
              <button className="btn sm" onClick={() => setPage(idx + 1)} disabled={idx >= rows.length - 1}>›</button>
              {cur && <span className="xs muted">· {cur.code}{cur.src_row != null ? ` · 원본 ${cur.src_row + 2}행` : ' · 전용 처리(원본 행 없음)'}</span>}
            </div>
            <a className="btn sm b" href="/api/export/statement.docx">.docx 받기</a>
          </div>
          <div style={{ padding: 14, maxHeight: 'calc(100vh - 250px)', overflow: 'auto' }}>
            {cur ? <FormPage row={cur} rc={(cur.rc ?? [])[0] ? data.statement.receipts[cur.rc[0]] : null} rid={(cur.rc ?? [])[0]} />
              : <div className="empty">열 매핑을 마치면 변환된 페이지가 여기에 보여요.</div>}
          </div>
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
    <div style={{ background: '#fff', boxShadow: '0 2px 14px rgba(14,21,37,.14)', borderRadius: 3, padding: '34px 30px 40px', maxWidth: 720, margin: '0 auto', aspectRatio: '210 / 297', fontSize: 12 }}>
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

