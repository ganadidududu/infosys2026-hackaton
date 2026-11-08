/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, useApi } from '../api'
import { ErrorBox, Loading, useToast } from '../ui/ui'

// 모의 채점 1단계: 지난 감사 기록 박스 + 새 감사 기록 만들기
export default function Grade() {
  const { data, error, reload } = useApi<any[]>('/records')
  const { data: meta } = useApi('/meta')
  const [open, setOpen] = useState(false)
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  return (
    <>
      <div className="ph">
        <div><div className="crumb">모의 채점</div><h1>감사 기록</h1>
          <p>감사자료를 올리면 기준안과 과거 선례로 모의 채점합니다. 점수는 100점에서 총 감점(사례 감점 + 경고 감점)을 뺀 값입니다.</p></div>
        <button className="btn b" onClick={() => setOpen(true)}>＋ 새 감사 기록 만들기</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))' }}>
        <button className="card" onClick={() => setOpen(true)} style={{ borderStyle: 'dashed', background: 'transparent', minHeight: 190, display: 'grid', placeItems: 'center', color: 'var(--mute)', cursor: 'pointer' }}>
          <div style={{ textAlign: 'center' }}><div style={{ fontSize: 34, lineHeight: 1 }}>＋</div><div className="small" style={{ marginTop: 8, fontWeight: 700 }}>새 감사 기록 만들기</div></div>
        </button>
        {data.map((r) => <RecordBox key={r.id} r={r} reload={reload} />)}
      </div>
      {open && <NewRecord meta={meta} close={() => setOpen(false)} />}
    </>
  )
}

function RecordBox({ r, reload }: any) {
  const toast = useToast()
  const done = r.score != null
  return (
    <Link to={`/admin/grade/${r.id}`} className="card pad" style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 190, position: 'relative' }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className={`tag ${r.readonly ? 't-n' : done ? 't-g' : 't-a'}`}>{r.status}</span>
        <span className="xs muted">{r.created?.replace('T', ' ')}</span>
      </div>
      <b style={{ fontSize: 15.5, lineHeight: 1.4 }}>{r.title}</b>
      <div className="xs muted">{r.dept} · {r.period.replace('-', '년 제')}차 회계기간</div>
      <div className="row" style={{ marginTop: 'auto', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        {done ? (
          <div className="row" style={{ alignItems: 'flex-end', gap: 6 }}>
            <span style={{ fontSize: 34, fontWeight: 800, letterSpacing: -1.5, lineHeight: 1 }}>{r.score}</span>
            <span className="small muted" style={{ paddingBottom: 3 }}>/ 100</span>
          </div>
        ) : (
          <div className="small ink2">서류 {r.submitted ?? 0}/{r.required ?? 7} 제출
            <div style={{ height: 6, width: 140, borderRadius: 999, background: 'var(--gray-soft)', marginTop: 6, overflow: 'hidden' }}>
              <i style={{ display: 'block', height: '100%', width: `${((r.submitted ?? 0) / (r.required || 7)) * 100}%`, background: 'var(--green)' }} /></div>
          </div>
        )}
        {done && <div className="xs muted" style={{ textAlign: 'right' }}>감점 {r.total} · 경고 {r.warnings}회{r.pending ? <><br /><span style={{ color: 'var(--amber-ink)' }}>미확정 {r.pending}건</span></> : null}{r.stale ? <><br /><span style={{ color: 'var(--amber-ink)' }}>다시 채점 필요</span></> : null}</div>}
      </div>
      {!r.readonly && (
        <button className="btn ghost sm" style={{ position: 'absolute', right: 8, bottom: 8, opacity: 0.4 }} title="삭제"
          onClick={async (e) => { e.preventDefault(); if (!confirm('이 감사 기록을 지울까요?')) return; await api(`/records/${r.id}`, { method: 'DELETE' }); toast('삭제했습니다'); reload() }}>🗑</button>
      )}
    </Link>
  )
}

function NewRecord({ meta, close }: any) {
  const nav = useNavigate()
  const toast = useToast()
  const [f, setF] = useState({ title: `${meta?.period?.label ?? ''} 정기감사 모의 채점`, dept: meta?.dept ?? '정보시스템학과', period: meta?.period?.id ?? '2026-1', kind: '정기감사', memo: '' })
  const [busy, setBusy] = useState(false)
  async function make() {
    setBusy(true)
    try { const r = await api('/records', { body: f }); nav(`/admin/grade/${r.id}`) } catch (e: any) { toast(e.message, true); setBusy(false) }
  }
  return (
    <>
      <div className="scrim" onClick={close} />
      <div role="dialog" className="card" style={{ position: 'fixed', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', zIndex: 41, width: 'min(480px,92vw)', padding: 24, boxShadow: '0 20px 60px rgba(14,21,37,.25)', animation: 'fade .15s' }}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 16 }}><h3 style={{ fontSize: 18 }}>새 감사 기록</h3><button className="btn ghost" onClick={close}>✕</button></div>
        <div className="grid" style={{ gap: 12 }}>
          <label className="field">제목<input className="input" autoFocus value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && make()} /></label>
          <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <label className="field">감사대상<input className="input" value={f.dept} onChange={(e) => setF({ ...f, dept: e.target.value })} /></label>
            <label className="field">회계기간<select className="input" value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })}>
              {['2026-1', '2026-2', '2025-2'].map((p) => <option key={p} value={p}>{p.replace('-', '년 제')}차</option>)}</select></label>
          </div>
          <label className="field">감사 종류<div className="seg">{['정기감사', '비정기감사'].map((k) => <button key={k} type="button" className={f.kind === k ? 'on' : ''} onClick={() => setF({ ...f, kind: k })}>{k}</button>)}</div></label>
          <label className="field">메모(선택)<textarea className="input" rows={3} placeholder="예: 제출 전 자체 점검용" value={f.memo} onChange={(e) => setF({ ...f, memo: e.target.value })} /></label>
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 4 }}>
            <button className="btn" onClick={close}>취소</button>
            <button className="btn b" disabled={busy || !f.title.trim()} onClick={make}>만들기</button>
          </div>
        </div>
      </div>
    </>
  )
}
