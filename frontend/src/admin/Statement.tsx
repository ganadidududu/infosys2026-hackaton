/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef, useState } from 'react'
import { api, useApi, won, apiUrl } from '../api'
import type React from 'react'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'
import Receipts from './Receipts'

type Tab = 'receipts' | 'convert'

export default function Statement() {
  const [tab, setTab] = useState<Tab>('convert')
  const { data, error, reload } = useApi('/statement')
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  return (
    <>
      <div className="subtabs">
        <button className={tab === 'receipts' ? 'on' : ''} onClick={() => setTab('receipts')}><i>1</i>영수증 OCR·저장</button>
        <button className={tab === 'convert' ? 'on' : ''} onClick={() => setTab('convert')}><i>2</i>거래 장부 → 수입/지출내역서(Word)</button>
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
  const [busy, setBusy] = useState(false)
  const [page, setPage] = useState(0)
  const idx = Math.min(page, Math.max(0, rows.length - 1))
  const cur = rows[idx]
  const pageOfRow = (r: number) => rows.findIndex((x) => x.src_row === r)

  async function up(file: File | Blob, name?: string) {
    setBusy(true)
    const fd = new FormData(); fd.append('file', file, name ?? (file as File).name)
    try { const r = await api('/statement/upload', { body: fd }); toast(r.errors.length ? '일부 열을 직접 지정해야 합니다' : '열을 자동으로 맞췄습니다'); setPage(0); reload() } catch (e: any) { toast(e.message, true) }
    setBusy(false)
  }
  async function trySample() {
    const b = await (await fetch(apiUrl('/statement/sample.csv'))).blob()
    up(b, '기중거래장부_예시.csv')
  }
  async function setCol(col: number, field: string) {
    const body: any = {}
    const prev = Object.entries(csv.mapping).find(([, v]: any) => v.col === col)?.[0]
    if (prev) body[prev] = null
    if (field) body[field] = col
    await api('/statement/mapping', { body }); reload()
  }
  const fieldOf = (j: number) => Object.entries(csv?.mapping ?? {}).find(([, v]: any) => v.col === j) as any
  useEffect(() => { document.querySelector('tr.src-sel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [idx])
  const dropProps = {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setDrag(true) },
    onDragLeave: () => setDrag(false),
    onDrop: (e: React.DragEvent) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) up(f) },
  }

  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', alignItems: 'start', gap: 12 }}>
      <input ref={ref} type="file" accept=".xlsx,.xlsm,.csv,.txt" hidden onChange={(e) => { if (e.target.files?.[0]) up(e.target.files[0]); e.target.value = '' }} />
      {/* 왼쪽: 원본 장부 */}
      <div className="card" style={{ overflow: 'hidden' }} {...(csv ? dropProps : {})}>
        <div className="row" style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)', justifyContent: 'space-between', minHeight: 46 }}>
          <div className="row" style={{ gap: 8, minWidth: 0 }}>
            <b className="small">원본 장부</b>
            {csv && <span className="xs muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{csv.filename} · {csv.body.length}행</span>}
            {csv && (csv.errors.length ? <span className="tag t-r">{csv.errors[0]}</span> : <span className="tag t-g">열 매핑 완료</span>)}
          </div>
          {csv && <button className="xbtn" title="장부 지우고 다시 올리기" onClick={async () => { await api('/statement', { method: 'DELETE' }); setPage(0); reload() }}>✕</button>}
        </div>
        {!csv ? (
          <div {...dropProps} onClick={() => ref.current?.click()} className={`dropzone ${drag ? 'over' : ''}`}>
            {busy ? <span className="spin" /> : <>
              <div style={{ fontSize: 38, lineHeight: 1 }}>⤓</div>
              <b style={{ marginTop: 12 }}>기중 거래 장부를 여기로 끌어다 놓으세요</b>
              <span className="small muted" style={{ marginTop: 6 }}>또는 눌러서 파일 선택 · 엑셀(.xlsx)·CSV</span>
              <button className="btn sm ghost" style={{ marginTop: 18, textDecoration: 'underline' }} onClick={(e) => { e.stopPropagation(); trySample() }}>예시 장부로 해 보기</button>
            </>}
          </div>
        ) : (
          <div className="xl-wrap" style={drag ? { outline: '2px dashed var(--brand)', outlineOffset: -4 } : undefined}>
            <table className="xl">
              <thead>
                <tr><th className="rn" />{csv.header.map((_: string, j: number) => <th key={j} className="cl">{COL(j)}</th>)}</tr>
                <tr className="map"><th className="rn">↳</th>{csv.header.map((_: string, j: number) => {
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
        )}
      </div>

      {/* 오른쪽: 변환된 Word 페이지 */}
      <div className="card" style={{ background: '#e9edf3', overflow: 'hidden' }}>
        <div className="row" style={{ padding: '8px 12px', justifyContent: 'space-between', background: '#fff', borderBottom: '1px solid var(--line)', minHeight: 46 }}>
          {rows.length ? (
            <div className="row" style={{ gap: 6 }}>
              <button className="btn sm" onClick={() => setPage(idx - 1)} disabled={idx === 0}>‹</button>
              <span className="small num" style={{ minWidth: 76, textAlign: 'center' }}><b>{idx + 1}</b> / {rows.length}쪽</span>
              <button className="btn sm" onClick={() => setPage(idx + 1)} disabled={idx >= rows.length - 1}>›</button>
              {cur && <span className="xs muted">· {cur.code}{cur.src_row != null ? ` · 원본 ${cur.src_row + 2}행` : ' · 전용 처리'}</span>}
            </div>
          ) : <b className="small">수입/지출내역서</b>}
          {rows.length > 0 && <a className="btn sm b" href={apiUrl('/export/statement.docx')}>.docx 받기</a>}
        </div>
        <div style={{ padding: 14, maxHeight: 'calc(100vh - 190px)', overflow: 'auto' }}>
          {cur ? <FormPage row={cur} rc={(cur.rc ?? [])[0] ? data.statement.receipts[cur.rc[0]] : null} rid={(cur.rc ?? [])[0]} />
            : <div className="dropzone" style={{ cursor: 'default', borderColor: 'transparent', background: 'transparent' }}>
                <span className="small muted">{csv ? '열 매핑을 마치면 변환된 페이지가 여기에 보여요.' : '장부를 올리면 거래마다 한 페이지씩 변환된 내역서가 여기에 보여요.'}</span></div>}
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
                  {rc?.image ? <img src={apiUrl(`/receipts/${rid}/image`)} alt="영수증" style={{ maxWidth: '70%', maxHeight: 380 }} />
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

