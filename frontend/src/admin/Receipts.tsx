/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from 'react'
import { api, md, useApi, won } from '../api'
import { ErrorBox, Loading, useToast } from '../ui/ui'

const STATUS_TAG: Record<string, string> = { '자동 확정': 't-g', '확정(감사인)': 't-g', '확인 필요': 't-a', '통장에 없는 영수증': 't-r', 미매칭: 't-n' }

export default function Receipts({ embedded }: { embedded?: boolean }) {
  const { data, error, reload } = useApi('/receipts')
  const [sel, setSel] = useState<string | null>(null)
  const [month, setMonth] = useState('전체')
  const [up, setUp] = useState(false)
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  const rs = [...(data.receipts as any[])].sort((a, b) => a.date.localeCompare(b.date))
  const mkey = (d: string) => d.slice(0, 7)
  const months = Array.from(new Set(rs.map((r) => mkey(r.date))))
  const label = (m: string) => `${+m.slice(5, 7)}월`
  const cur = rs.find((r) => r.id === sel)
  const groups = (month === '전체' ? months : [month]).map((m) => ({ m, items: rs.filter((r) => mkey(r.date) === m) }))

  const card = (r: any) => {
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
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div className="seg">
          <button className={month === '전체' ? 'on' : ''} onClick={() => setMonth('전체')}>전체 <span className="muted">{rs.length}</span></button>
          {months.map((m) => <button key={m} className={month === m ? 'on' : ''} onClick={() => setMonth(m)}>{label(m)} <span className="muted">{rs.filter((r) => mkey(r.date) === m).length}</span></button>)}
        </div>
        <button className="btn b" onClick={() => setUp(true)}>＋ 영수증 올리기</button>
      </div>
      {groups.map(({ m, items }) => (
        <section key={m} style={{ marginBottom: 22 }}>
          <div className="row" style={{ justifyContent: 'space-between', margin: '0 2px 10px' }}>
            <b style={{ fontSize: 15 }}>{m.slice(0, 4)}년 {label(m)}</b>
            <span className="small muted num">{items.length}장 · {won(items.reduce((s, r) => s + r.amount, 0))}원</span>
          </div>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(230px,1fr))' }}>{items.map(card)}</div>
        </section>
      ))}
      {rs.length === 0 && <div className="empty">아직 올린 영수증이 없어요.</div>}
      {cur && <ReceiptDrawer r={cur} close={() => setSel(null)} reload={reload} />}
      {up && <Upload projects={data.projects} engine={data.engine} close={() => setUp(false)} reload={reload} />}
    </>
  )
}

function ReceiptDrawer({ r, close, reload }: any) {
  const toast = useToast()
  const [f, setF] = useState({ vendor: r.vendor, date: r.date, amount: r.amount })
  const [items, setItems] = useState<any[]>(r.items?.length ? r.items.map((i: any) => ({ ...i })) : [{ name: '', qty: 1, price: 0 }])
  const low = (k: string) => (r.confidence[k] ?? 1) < 0.8
  const setItem = (k: number, key: string, v: any) => setItems(items.map((it, i) => (i === k ? { ...it, [key]: v } : it)))
  async function save() {
    await api(`/receipts/${r.id}`, { method: 'PATCH', body: { ...f, amount: +f.amount, items: items.map((i) => ({ ...i, qty: +i.qty, price: +i.price })) } })
    toast('저장했습니다'); reload(); close()
  }
  return (
    <>
      <div className="scrim" onClick={close} />
      <aside className="drawer" style={{ width: 'min(820px,100vw)' }}>
        <header><div><div className="xs muted">{r.id} · {r.kind}</div><h3 style={{ fontSize: 18, marginTop: 4 }}>{r.vendor}</h3></div><button className="btn ghost" onClick={close}>✕</button></header>
        <div className="body" style={{ display: 'grid', gap: 20, alignContent: 'start' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div className="sec-t">영수증 사진</div>
              <div style={{ background: '#eef0f4', border: '1px solid var(--line)', borderRadius: 10, height: 420, display: 'grid', placeItems: 'center', overflow: 'hidden' }}>
                {r.image ? <img src={`/api/receipts/${r.id}/image`} alt="영수증 원본" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                  : <span className="small muted">원본 사진이 없습니다</span>}
              </div>
            </div>
            <div>
              <div className="sec-t">인식한 원문</div>
              <pre style={{ margin: 0, height: 420, overflow: 'auto', background: '#fff', border: '1px solid var(--line)', borderRadius: 10, padding: 14, fontSize: 12.5, lineHeight: 1.85, whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace,Menlo,monospace' }}>{r.ocr_text}</pre>
            </div>
          </div>
          <div>
            <div className="sec-t">메타데이터 <small>노란 칸만 확인</small></div>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 10 }}>
              <label className="field">업체<input className={`input ${low('vendor') ? 'warn' : ''}`} value={f.vendor} onChange={(e) => setF({ ...f, vendor: e.target.value })} /></label>
              <label className="field">일시<input className={`input ${low('date') ? 'warn' : ''}`} type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
              <label className="field">금액<input className={`input num ${low('amount') ? 'warn' : ''}`} type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: +e.target.value })} /></label>
            </div>
            <div className="field" style={{ marginTop: 10 }}>세목
              <div style={{ border: `1px solid ${low('items') ? '#f3d37a' : 'var(--line)'}`, background: low('items') ? '#fffbea' : '#fff', borderRadius: 9, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 120px 32px', gap: 0, fontSize: 12, color: 'var(--mute)', padding: '6px 10px', borderBottom: '1px solid var(--line)' }}><span>세목</span><span>수량</span><span>단가</span><span /></div>
                {items.map((it, k) => (
                  <div key={k} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 120px 32px', gap: 6, padding: '6px 10px', alignItems: 'center' }}>
                    <input className="input" value={it.name} placeholder="품목" onChange={(e) => setItem(k, 'name', e.target.value)} />
                    <input className="input num" type="number" value={it.qty} onChange={(e) => setItem(k, 'qty', e.target.value)} />
                    <input className="input num" type="number" value={it.price} onChange={(e) => setItem(k, 'price', e.target.value)} />
                    <button className="btn sm ghost" title="줄 삭제" onClick={() => setItems(items.filter((_, i) => i !== k))}>✕</button>
                  </div>
                ))}
                <button className="btn sm ghost" style={{ margin: '0 6px 6px' }} onClick={() => setItems([...items, { name: '', qty: 1, price: 0 }])}>＋ 세목 추가</button>
              </div>
            </div>
          </div>
          <button className="btn p" onClick={save}>저장</button>
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
      const r = await api(`/receipts/upload?project=${encodeURIComponent(project)}&text=${encodeURIComponent(text)}`, { body: fd })
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
          {(!file || !engine) && (
            <label className="field">{file ? '영수증 내용 입력(OCR 엔진이 없어 사진은 증빙서류 칸에만 붙습니다)' : 'OCR 텍스트 붙여 넣기(엔진이 없을 때)'}
              <textarea className="input" rows={8} value={text} placeholder={sample} onChange={(e) => setText(e.target.value)} />
              <button className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={() => setText(sample)}>예시 넣기</button>
            </label>
          )}
          <label className="field">사업 태그<select className="input" value={project} onChange={(e) => setProject(e.target.value)}>{projects.map((p: string) => <option key={p}>{p}</option>)}</select></label>
          <div className="xs muted">원본 이미지는 서버 밖으로 보내지 않습니다. 카드번호는 끝 4자리만 남깁니다.</div>
          <button className="btn b" disabled={busy || (!text.trim() && (!file || !engine))} onClick={go}>{busy ? '인식 중…' : '인식하고 저장'}</button>
        </div>
      </aside>
    </>
  )
}
