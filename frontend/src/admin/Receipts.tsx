/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from 'react'
import { api, md, useApi, won } from '../api'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'

const INVOICE = ['① 업체·책임자 이름·서명', '② 책임자 연락처', '③ 견적 산출 근거(세목)', '④ 집행부 담당자 이름·서명·연락처', '⑤ 일자·수단·총액', '⑥ 법적 책임 경고·담당자 서명']
const STATUS_TAG: Record<string, string> = { '자동 확정': 't-g', '확정(감사인)': 't-g', '확인 필요': 't-a', '통장에 없는 영수증': 't-r', 미매칭: 't-n' }

export default function Receipts({ embedded }: { embedded?: boolean }) {
  const { data, error, reload } = useApi('/receipts')
  const [sel, setSel] = useState<string | null>(null)
  const [filter, setFilter] = useState('전체')
  const [up, setUp] = useState(false)
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  const rs = data.receipts as any[]
  const projects = ['전체', ...Array.from(new Set(rs.map((r) => r.project)))]
  const shown = rs.filter((r) => filter === '전체' || r.project === filter)
  const cur = rs.find((r) => r.id === sel)
  const noItems = rs.filter((r) => !r.has_items).length
  const lowConf = rs.filter((r) => Object.values(r.confidence).some((v: any) => v < 0.8)).length

  return (
    <>
      <div className="ph">
        {embedded ? <p className="small ink2" style={{ margin: 0 }}>결제할 때마다 찍어 올립니다. 로컬 OCR이 일시·업체·금액·세목·증빙 종류를 읽고 자기 검산을 하며, 신뢰도가 낮은 칸만 노란색으로 표시합니다.</p> : <div><div className="crumb">학기 중</div><h1>영수증함</h1>
          <p>결제할 때마다 찍어 올립니다. 로컬 OCR이 읽고 자기 검산을 하며, 신뢰도가 낮은 칸만 노란색으로 표시합니다.</p></div>}
        <button className="btn b" onClick={() => setUp(true)}>＋ 영수증 올리기</button>
      </div>
      <div className="kpi" style={{ marginBottom: 16 }}>
        <div className="k"><span>모은 증빙</span><b>{rs.length}장</b></div>
        <div className="k amber"><span>세목 없음 → 계산서 필요</span><b>{noItems}</b></div>
        <div className="k amber"><span>확인할 칸(노란색)</span><b>{lowConf}</b></div>
        <div className="k red"><span>통장에 없는 영수증</span><b>{rs.filter((r) => r.match.status === '통장에 없는 영수증').length}</b></div>
      </div>
      <div className="row" style={{ marginBottom: 12, flexWrap: 'wrap', gap: 6 }}>
        {projects.map((p) => <button key={p} className={`chip`} style={filter === p ? { background: 'var(--ink)', color: '#fff' } : {}} onClick={() => setFilter(p)}>{p}</button>)}
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(230px,1fr))' }}>
        {shown.map((r) => {
          const low = Object.entries(r.confidence).filter(([, v]: any) => v < 0.8).map(([k]) => k)
          return (
            <button key={r.id} onClick={() => setSel(r.id)} className="card" style={{ textAlign: 'left', padding: 0, overflow: 'hidden', cursor: 'pointer' }}>
              <div style={{ background: 'repeating-linear-gradient(0deg,#fff,#fff 22px,#f6f7fa 22px,#f6f7fa 23px)', padding: '14px 16px', borderBottom: '1px dashed var(--line)', fontFamily: 'ui-monospace,Menlo,monospace', fontSize: 11.5, color: 'var(--ink2)', height: 96, overflow: 'hidden', lineHeight: '23px' }}>
                {r.ocr_text.split('\n').slice(0, 4).map((l: string, i: number) => <div key={i} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l}</div>)}
              </div>
              <div style={{ padding: '12px 16px' }}>
                <div className="row" style={{ justifyContent: 'space-between' }}><b style={{ fontSize: 14, background: low.includes('vendor') ? '#fffbea' : undefined }}>{r.vendor}</b><span className="num" style={{ fontWeight: 800 }}>{won(r.amount)}</span></div>
                <div className="xs muted" style={{ marginTop: 3 }}>{md(r.date)} · {r.project} · {r.kind} · {r.pay}</div>
                <div className="row" style={{ gap: 4, marginTop: 8, flexWrap: 'wrap' }}>
                  <span className={`tag ${STATUS_TAG[r.match.status] ?? 't-n'}`}>{r.match.status}</span>
                  {!r.has_items && <span className="tag t-a">세목 없음</span>}
                  {r.installment > 0 && <span className="tag t-r">할부 {r.installment}개월</span>}
                  {r.points > 0 && <span className="tag t-r">포인트 {won(r.points)}P</span>}
                  {low.length > 0 && <span className="tag t-a">확인 {low.length}칸</span>}
                </div>
              </div>
            </button>
          )
        })}
      </div>
      {cur && <ReceiptDrawer r={cur} projects={data.projects} close={() => setSel(null)} reload={reload} />}
      {up && <Upload projects={data.projects} engine={data.engine} close={() => setUp(false)} reload={reload} />}
    </>
  )
}

function ReceiptDrawer({ r, projects, close, reload }: any) {
  const toast = useToast()
  const [f, setF] = useState({ vendor: r.vendor, date: r.date, amount: r.amount, project: r.project })
  const [inv, setInv] = useState<Record<string, boolean>>(r.invoice ?? {})
  const low = (k: string) => (r.confidence[k] ?? 1) < 0.8
  async function save() {
    await api(`/receipts/${r.id}`, { method: 'PATCH', body: { ...f, amount: +f.amount, ...(r.invoice || !r.has_items ? { invoice: inv } : {}) } })
    toast('저장했습니다 · 대사와 감사자료에 바로 반영됩니다'); reload(); close()
  }
  return (
    <>
      <div className="scrim" onClick={close} />
      <aside className="drawer" style={{ width: 'min(720px,100vw)' }}>
        <header><div><div className="xs muted">{r.id} · {r.kind} · 로컬 OCR 결과</div><h3 style={{ fontSize: 18, marginTop: 4 }}>{r.vendor}</h3></div><button className="btn ghost" onClick={close}>✕</button></header>
        <div className="body" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
          <div>
            <div className="sec-t">인식한 원문</div>
            <pre style={{ margin: 0, background: '#fff', border: '1px solid var(--line)', borderRadius: 10, padding: 14, fontSize: 12, lineHeight: 1.8, whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace,Menlo,monospace' }}>{r.ocr_text}</pre>
            <div className="sec-t" style={{ marginTop: 16 }}>자기 검산</div>
            {r.self_check.map((c: any) => (
              <div key={c.check} className="row small" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--line2)' }}>
                <span>{c.ok ? '✓' : '✕'} {c.check}</span><span className={c.ok ? 'muted' : ''} style={{ color: c.ok ? undefined : 'var(--amber-ink)' }}>{c.detail}</span></div>
            ))}
          </div>
          <div style={{ display: 'grid', gap: 10, alignContent: 'start' }}>
            <div className="sec-t" style={{ margin: 0 }}>메타데이터 <small>노란 칸만 확인</small></div>
            <label className="field">업체<input className={`input ${low('vendor') ? 'warn' : ''}`} value={f.vendor} onChange={(e) => setF({ ...f, vendor: e.target.value })} /></label>
            <label className="field">일시<input className={`input ${low('date') ? 'warn' : ''}`} type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
            <label className="field">금액<input className={`input ${low('amount') ? 'warn' : ''}`} type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: +e.target.value })} /></label>
            <label className="field">사업 태그<select className="input" value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })}>{projects.map((p: string) => <option key={p}>{p}</option>)}</select></label>
            <div className="field">세목<div className={`input ${low('items') ? 'warn' : ''}`} style={{ minHeight: 38 }}>{r.items.length ? r.items.map((i: any) => `${i.name} ${i.qty}×${won(i.price)}`).join(' / ') : <span style={{ color: 'var(--amber-ink)' }}>세목 표기 없음</span>}</div></div>
            <div className="row small" style={{ gap: 6, flexWrap: 'wrap' }}>
              <span className="tag t-n">{r.pay}</span><span className="tag t-n">{r.kind}</span>{r.card_last4 && <span className="tag t-n">카드 끝 {r.card_last4}</span>}
              {r.attachments.map((a: string) => <span key={a} className="tag t-b">{a}</span>)}
            </div>
            {(r.invoice || !r.has_items) && (
              <div style={{ border: '1px solid var(--amber)', background: 'var(--amber-soft)', borderRadius: 10, padding: 12 }}>
                <b className="small">계산서 6항목 <Cite c="3부 35조" /></b>
                <div className="xs ink2" style={{ margin: '4px 0 8px' }}>세목 표기가 불가능한 업체는 총액 영수증과 아래 항목을 모두 갖춘 계산서가 필요합니다.</div>
                {INVOICE.map((t, i) => { const k = '①②③④⑤⑥'[i]; return (
                  <label key={k} className="row small" style={{ gap: 8, padding: '3px 0' }}><input type="checkbox" checked={!!inv[k]} onChange={(e) => setInv({ ...inv, [k]: e.target.checked })} />{t}{!inv[k] && <span className="tag t-r">누락</span>}</label>) })}
              </div>
            )}
            <div className="small muted">대사 상태: <b style={{ color: 'var(--ink)' }}>{r.match.status}</b>{r.match.tx && ` · ${r.match.tx.join(', ')}`}</div>
            <button className="btn p" onClick={save}>저장</button>
          </div>
        </div>
      </aside>
    </>
  )
}

function Upload({ projects, engine, close, reload }: any) {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState('')
  const [project, setProject] = useState(projects[5] ?? '')
  const [busy, setBusy] = useState(false)
  const sample = useMemo(() => `OO카페 왕십리점\n사업자번호 123-45-67890\n일시 2026-06-20 14:10\n아메리카노 10 x 3,000 = 30,000\n공급가액 27,273\n부가세 2,727\n합계 30,000\n카드 ****-4417 일시불`, [])
  async function go() {
    setBusy(true)
    const fd = new FormData()
    fd.append('file', file ?? new Blob([text], { type: 'text/plain' }), file?.name ?? 'receipt.txt')
    try {
      const r = await api(`/receipts/upload?project=${encodeURIComponent(project)}&text=${encodeURIComponent(file ? '' : text)}`, { body: fd })
      if (!r.ok) { toast(r.message, true) } else { toast(`${r.receipt.vendor} ${won(r.receipt.amount)}원 저장`); reload(); close() }
    } catch (e: any) { toast(e.message, true) }
    setBusy(false)
  }
  return (
    <>
      <div className="scrim" onClick={close} />
      <aside className="drawer">
        <header><h3 style={{ fontSize: 18 }}>영수증 올리기</h3><button className="btn ghost" onClick={close}>✕</button></header>
        <div className="body" style={{ display: 'grid', gap: 14, alignContent: 'start' }}>
          <label className="card" style={{ padding: 28, textAlign: 'center', borderStyle: 'dashed', cursor: 'pointer' }}>
            <input type="file" accept="image/*" capture="environment" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <div style={{ fontSize: 30 }}>📷</div><b className="small">{file ? file.name : '사진 찍기 · 이미지 선택'}</b>
            <div className="xs muted" style={{ marginTop: 6 }}>로컬 OCR: {engine ?? '설치되지 않음(아래에 인식 텍스트를 붙여 넣어 시연)'}</div>
          </label>
          {!file && (
            <label className="field">OCR 텍스트 붙여 넣기(엔진이 없을 때)
              <textarea className="input" rows={8} value={text} placeholder={sample} onChange={(e) => setText(e.target.value)} />
              <button className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={() => setText(sample)}>예시 넣기</button>
            </label>
          )}
          <label className="field">사업 태그<select className="input" value={project} onChange={(e) => setProject(e.target.value)}>{projects.map((p: string) => <option key={p}>{p}</option>)}</select></label>
          <div className="xs muted">원본 이미지는 서버 밖으로 보내지 않습니다. 카드번호는 끝 4자리만 남깁니다.</div>
          <button className="btn b" disabled={busy || (!file && !text.trim())} onClick={go}>{busy ? '인식 중…' : '인식하고 저장'}</button>
        </div>
      </aside>
    </>
  )
}
