/* eslint-disable @typescript-eslint/no-explicit-any */
import { useRef, useState } from 'react'
import { api, useApi, apiUrl } from '../api'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'

const WD = ['일', '월', '화', '수', '목', '금', '토']
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export default function Checklist() {
  const { data, error, reload } = useApi('/checklist')
  const [adding, setAdding] = useState<string | null>(null)   // 추가할 날짜('' = 날짜 미정)
  const [month, setMonth] = useState<string | null>(null)     // 'YYYY-MM'
  const [focus, setFocus] = useState<string | null>(null)     // 강조할 날짜
  const fileRef = useRef<HTMLInputElement>(null)
  const toast = useToast()
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />

  async function toggle(id: string, done: boolean) {
    await api(`/checklist/${encodeURIComponent(id)}/done`, { body: { done } }); reload()
  }
  async function setLead(id: string, days: number) {
    await api(`/checklist/${encodeURIComponent(id)}/lead`, { body: { days } }); toast('권장 기한을 바꿨습니다'); reload()
  }
  const items: any[] = [...data.events.flatMap((e: any) => e.items), ...data.fixed]
  const allMonths = Array.from(new Set([...items.map((i) => i.due.slice(0, 7)), ...data.events.map((e: any) => e.date.slice(0, 7))])).sort()
  const thisMonth = ymd(new Date()).slice(0, 7)
  const firstEv = [...data.events].sort((a: any, b: any) => a.date.localeCompare(b.date))[0]?.date.slice(0, 7)
  const m = month ?? (allMonths.includes(thisMonth) ? thisMonth : firstEv ?? allMonths[0] ?? thisMonth)
  const [y, mo] = m.split('-').map(Number)
  const first = new Date(y, mo - 1, 1)
  const start = new Date(first); start.setDate(1 - first.getDay())
  const cells = Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d })
  const weeks = cells[35].getMonth() === mo - 1 ? 6 : 5
  const evByDay: Record<string, any[]> = {}
  data.events.forEach((e: any) => (evByDay[e.date] ??= []).push(e))
  const dueByDay: Record<string, any[]> = {}
  items.forEach((i) => (dueByDay[i.due] ??= []).push(i))
  const monthItems = items.filter((i) => i.due.startsWith(m)).sort((a, b) => a.due.localeCompare(b.due))
  const monthEvents = data.events.filter((e: any) => e.date.startsWith(m))
  const done = monthItems.filter((i) => i.done).length
  const shift = (n: number) => { const d = new Date(y, mo - 1 + n, 1); setMonth(ymd(d).slice(0, 7)); setFocus(null) }
  const today = ymd(new Date())
  const groups: [string, any[]][] = []
  monthItems.forEach((i) => { const g = groups.find((x) => x[0] === i.due); if (g) g[1].push(i); else groups.push([i.due, [i]]) })

  return (
    <>
      <div className="ph">
        <div>
          <div className="crumb">학기 스케줄러</div>
          <h1>학기 일정과 기준안 체크리스트</h1>
        </div>
        <div className="row">
          <input ref={fileRef} type="file" accept=".csv,.txt" hidden onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return
            const fd = new FormData(); fd.append('file', f)
            try { const r = await api('/schedule/upload', { body: fd }); toast(`일정 ${r.added}건 추가${r.skipped.length ? ` · ${r.skipped.length}행 건너뜀` : ''}`); reload() } catch (err: any) { toast(err.message, true) }
            e.target.value = '' }} />
          <a className="btn sm ghost" href={apiUrl('/schedule/sample.csv')}>일정 CSV 양식</a>
          <button className="btn" onClick={() => fileRef.current?.click()}>일정 CSV 올리기</button>
        </div>
      </div>
      <StageBar bar={data.bar} />

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1.55fr) minmax(320px,1fr)', alignItems: 'start' }}>
        {/* 왼쪽: 달력 */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="row" style={{ justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn sm" onClick={() => shift(-1)} aria-label="이전 달">‹</button>
              <select className="input" value={m} onChange={(e) => { setMonth(e.target.value); setFocus(null) }} style={{ width: 'auto', fontWeight: 800, fontSize: 15, border: 0, padding: '4px 6px' }}>
                {Array.from(new Set([...allMonths, m])).sort().map((x) => <option key={x} value={x}>{x.slice(0, 4)}년 {+x.slice(5)}월</option>)}
              </select>
              <button className="btn sm" onClick={() => shift(1)} aria-label="다음 달">›</button>
            </div>
            <div className="row xs muted" style={{ gap: 12 }}>
              <span className="row" style={{ gap: 5 }}><i className="cal-dot ev" />행사</span>
              <span className="row" style={{ gap: 5 }}><i className="cal-dot" />할 일 기한</span>
              <span className="row" style={{ gap: 5 }}><i className="cal-dot kj" />기준안 기한</span>
              <button className="btn sm b" onClick={() => setAdding(focus ?? '')}>＋ 일정 추가</button>
            </div>
          </div>
          <div className="cal">
            {WD.map((w, i) => <div key={w} className={`cal-wd ${i === 0 ? 'sun' : i === 6 ? 'sat' : ''}`}>{w}</div>)}
            {cells.slice(0, weeks * 7).map((d) => {
              const k = ymd(d)
              const inMonth = d.getMonth() === mo - 1
              const evs = evByDay[k] ?? []
              const dues = dueByDay[k] ?? []
              const shown = [...evs.map((e: any) => ({ t: 'ev', e })), ...dues.map((i: any) => ({ t: 'due', i }))]
              return (
                <div key={k} className={`cal-day ${inMonth ? '' : 'out'} ${k === today ? 'today' : ''} ${focus === k ? 'focus' : ''}`}
                  onClick={() => { if (!inMonth) { setMonth(k.slice(0, 7)); return } setFocus(k); document.getElementById(`due-${k}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }}
                  onDoubleClick={() => setAdding(k)} title="두 번 눌러 이 날 일정 추가">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <span className={`cal-n ${d.getDay() === 0 ? 'sun' : d.getDay() === 6 ? 'sat' : ''}`}>{d.getDate()}</span>
                    {inMonth && <button className="cal-add" onClick={(e) => { e.stopPropagation(); setAdding(k) }} title="이 날 일정 추가">＋</button>}
                  </div>
                  {shown.slice(0, 3).map((x: any, n: number) => x.t === 'ev'
                    ? <div key={n} className="cal-ev" title={`${x.e.name} · ${x.e.type}`}>{x.e.name}</div>
                    : <div key={n} className={`cal-due ${x.i.done ? 'done' : ''} ${x.i.due_kind === '기준안 기한' ? 'kj' : ''} ${x.i.late ? 'late' : ''}`} title={x.i.task}>{x.i.task}</div>)}
                  {shown.length > 3 && <div className="xs muted" style={{ paddingLeft: 4 }}>+{shown.length - 3}개</div>}
                </div>
              )
            })}
          </div>
        </div>

        {/* 오른쪽: 이번 달 체크리스트 */}
        <div className="card" style={{ position: 'sticky', top: 76 }}>
          <div className="pad" style={{ borderBottom: '1px solid var(--line)' }}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <b style={{ fontSize: 15 }}>{mo}월에 해야 할 일</b>
              <span className="small muted num">{done}/{monthItems.length} 완료</span>
            </div>
            <div style={{ height: 6, borderRadius: 999, background: 'var(--gray-soft)', marginTop: 10, overflow: 'hidden' }}>
              <i style={{ display: 'block', height: '100%', width: `${monthItems.length ? (done / monthItems.length) * 100 : 0}%`, background: 'var(--green)', transition: '.3s' }} />
            </div>
            {monthEvents.length > 0 && <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
              {monthEvents.map((e: any) => (
                <span key={e.id} className="tag t-b" style={{ gap: 6 }}>{+e.date.slice(8)}일 {e.name}
                  {e.custom && <button onClick={async () => { if (!confirm(`${e.name} 일정을 지울까요?`)) return; await api(`/schedule/events/${e.id}`, { method: 'DELETE' }); reload() }} style={{ all: 'unset', cursor: 'pointer', opacity: 0.6 }} title="일정 삭제">✕</button>}</span>))}
            </div>}
          </div>
          <div style={{ maxHeight: 'calc(100vh - 260px)', overflow: 'auto' }}>
            {groups.length === 0 && <div className="empty small">이 달에는 할 일이 없어요.</div>}
            {groups.map(([day, its]) => (
              <div key={day} id={`due-${day}`} style={{ background: focus === day ? 'var(--brand-soft)' : undefined, transition: '.2s' }}>
                <div className="xs" style={{ padding: '10px 18px 2px', fontWeight: 700, color: day < today && its.some((i) => !i.done) ? 'var(--red)' : 'var(--ink2)' }}>
                  {+day.slice(5, 7)}월 {+day.slice(8)}일 ({WD[new Date(day).getDay()]})
                </div>
                {its.map((it) => <Item key={it.id} it={it} toggle={toggle} setLead={setLead} showEvent />)}
              </div>
            ))}
          </div>
        </div>
      </div>
      {adding !== null && <AddEvent types={data.types} flags={data.flags} date={adding} close={() => setAdding(null)} reload={reload} />}
    </>
  )
}

export function StageBar({ bar }: { bar: any[] }) {
  return (
    <div className="card pad" style={{ marginBottom: 16, overflowX: 'auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${bar.length},minmax(110px,1fr))`, gap: 8 }}>
        {bar.map((s, i) => (
          <div key={s.k}>
            <div style={{ height: 6, borderRadius: 999, background: s.done ? 'var(--green)' : 'var(--gray-soft)', marginBottom: 10 }} />
            <div className="small" style={{ fontWeight: 700 }}>{i + 1}. {s.k}</div>
            <div className="xs muted num">{s.d}</div>
            {s.c && <Cite c={s.c} />}
          </div>
        ))}
      </div>
    </div>
  )
}

function AddEvent({ types, flags, date, close, reload }: any) {
  const toast = useToast()
  const [f, setF] = useState<any>({ name: '', date: date || '', type: types[0], flags: [] })
  async function save() {
    try { await api('/schedule/events', { body: f }); toast(`${f.name} 일정을 추가했습니다`); reload(); close() } catch (e: any) { toast(e.message, true) }
  }
  return (
    <>
      <div className="scrim" onClick={close} />
      <div role="dialog" className="card" style={{ position: 'fixed', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', zIndex: 41, width: 'min(460px,92vw)', padding: 24, boxShadow: '0 20px 60px rgba(14,21,37,.25)' }}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 16 }}><h3 style={{ fontSize: 18 }}>학과 일정 추가</h3><button className="btn ghost" onClick={close}>✕</button></div>
        <div className="grid" style={{ gap: 12 }}>
          <label className="field">행사명<input className="input" autoFocus placeholder="예: 학과 체육대회" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label className="field">날짜<input className="input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
          <label className="field">행사 유형<select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{types.map((t: string) => <option key={t}>{t}</option>)}</select></label>
          <div className="field">특이사항
            <div className="row" style={{ gap: 14 }}>{flags.map((fl: string) => (
              <label key={fl} className="row small" style={{ gap: 6 }}><input type="checkbox" checked={f.flags.includes(fl)} onChange={(e) => setF({ ...f, flags: e.target.checked ? [...f.flags, fl] : f.flags.filter((x: string) => x !== fl) })} />{fl}</label>))}</div>
          </div>
          <div className="xs muted">유형과 특이사항에 따라 기준안 의무(예: 참가비 ≤ 지출, 예약금 이체내역서, 계산서 6항목)가 자동으로 붙습니다.</div>
          <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={close}>취소</button><button className="btn b" disabled={!f.name.trim() || !f.date} onClick={save}>추가</button></div>
        </div>
      </div>
    </>
  )
}

function Item({ it, toggle, setLead, showEvent }: any) {
  const [ed, setEd] = useState(false)
  const kindTag = it.due_kind === '기준안 기한' ? 't-b' : it.due_kind.startsWith('순서') ? 't-v' : 't-n'
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '28px 1fr auto', gap: 10, padding: '12px 18px', borderBottom: '1px solid var(--line2)', alignItems: 'start', opacity: it.done ? 0.6 : 1 }}>
      <input type="checkbox" checked={!!it.done} onChange={(e) => toggle(it.id, e.target.checked)} style={{ width: 18, height: 18, marginTop: 2, accentColor: 'var(--green)' }} />
      <div>
        <div style={{ fontSize: 13.5, fontWeight: 600, textDecoration: it.done ? 'line-through' : 'none' }}>{showEvent && <span className="muted">[{it.event}] </span>}{it.task}</div>
        <div className="row" style={{ gap: 2, marginTop: 4, flexWrap: 'wrap' }}>
          {it.clauses.map((c: string) => <Cite key={c} c={c} />)}
          {it.verify?.status !== '검증됨' && <span className="tag t-a">검수 필요</span>}
          {it.late && <span className="tag t-r">이미 늦음</span>}
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div className="num" style={{ fontWeight: 700, fontSize: 13.5 }}>
          {ed && setLead ? (
            <input className="input" type="number" defaultValue={it.lead} style={{ width: 70 }} autoFocus
              onBlur={(e) => { setEd(false); if (+e.target.value !== it.lead) setLead(it.id, +e.target.value) }}
              onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
          ) : <span style={{ cursor: setLead && it.due_kind === '권장 기한' ? 'pointer' : 'default' }} title={setLead ? '행사일 기준 일수 바꾸기' : ''} onClick={() => setLead && it.due_kind === '권장 기한' && setEd(true)}>{it.due}</span>}
        </div>
        <span className={`tag ${kindTag}`} style={{ marginTop: 4 }}>{it.due_kind}</span>
      </div>
    </div>
  )
}
