/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react'
import { api, md, useApi } from '../api'
import { Cite, ErrorBox, Loading, useToast } from '../ui/ui'

export default function Checklist() {
  const { data, error, reload } = useApi('/checklist')
  const [view, setView] = useState<'event' | 'time'>('event')
  const toast = useToast()
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />

  async function toggle(id: string, done: boolean) {
    await api(`/checklist/${encodeURIComponent(id)}/done`, { body: { done } }); reload()
  }
  async function setLead(id: string, days: number) {
    await api(`/checklist/${encodeURIComponent(id)}/lead`, { body: { days } }); toast('권장 기한을 바꿨습니다'); reload()
  }
  const items = data.events.flatMap((e: any) => e.items)
  const byWeek: Record<string, any[]> = {}
  for (const it of [...items, ...data.fixed].sort((a, b) => a.due.localeCompare(b.due))) {
    const d = new Date(it.due)
    const monday = new Date(d); monday.setDate(d.getDate() - ((d.getDay() + 6) % 7))
    const k = monday.toISOString().slice(0, 10)
    ;(byWeek[k] ??= []).push(it)
  }
  const s = data.stats

  return (
    <>
      <div className="ph">
        <div>
          <div className="crumb">1 · 학기 전</div>
          <h1>학기 체크리스트</h1>
          <p>체크리스트 LLM이 기준안에서 행사별 의무를 뽑고, 코드가 조항 실존·인용을 검증한 뒤 선후 관계로 기한을 거꾸로 계산합니다.</p>
        </div>
        <div className="seg"><button className={view === 'event' ? 'on' : ''} onClick={() => setView('event')}>행사별</button><button className={view === 'time' ? 'on' : ''} onClick={() => setView('time')}>주 단위 타임라인</button></div>
      </div>
      <div className="kpi" style={{ marginBottom: 16 }}>
        <div className="k green"><span>이행 완료</span><b>{s.done}/{s.total}</b></div>
        <div className="k red"><span>이미 늦음</span><b>{s.late}</b></div>
        <div className="k amber"><span>몰리는 주(4건 이상)</span><b>{Object.keys(data.crowded_weeks).length}</b></div>
        <div className="k"><span>조항 검증</span><b>{s.total - s.unverified}/{s.total}</b></div>
      </div>
      <div className="card pad small ink2" style={{ marginBottom: 16, lineHeight: 1.7 }}>
        기한 표기: <span className="tag t-b">기준안 기한</span> 기준안이 날짜를 정한 것 · <span className="tag t-v">순서(사용 전)</span> 기준안이 순서만 정한 것 · <span className="tag t-n">권장 기한</span> 학생회가 정한 날짜(숫자를 눌러 바꿀 수 있음)
      </div>

      {view === 'event' ? (
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(420px,1fr))' }}>
          {data.events.map((e: any) => (
            <div key={e.id} className="card">
              <div className="pad" style={{ borderBottom: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div><b style={{ fontSize: 15 }}>{e.name}</b> <span className="small muted">· {e.type} · {e.date}</span>
                  <div className="row" style={{ gap: 4, marginTop: 6 }}>{e.flags.map((f: string) => <span key={f} className="tag t-a">{f}</span>)}</div></div>
                <span className="small muted">{e.items.filter((i: any) => i.done).length}/{e.items.length}</span>
              </div>
              <div>
                {e.items.map((it: any) => <Item key={it.id} it={it} toggle={toggle} setLead={setLead} />)}
              </div>
            </div>
          ))}
          <div className="card">
            <div className="pad" style={{ borderBottom: '1px solid var(--line)' }}><b style={{ fontSize: 15 }}>기준안이 날짜를 정한 일</b></div>
            {data.fixed.map((it: any) => <Item key={it.id} it={it} toggle={toggle} />)}
          </div>
        </div>
      ) : (
        <div className="card">
          {Object.entries(byWeek).map(([wk, its]) => (
            <div key={wk} style={{ display: 'grid', gridTemplateColumns: '120px 1fr', borderBottom: '1px solid var(--line)' }}>
              <div className="pad small" style={{ background: its.length >= 4 ? 'var(--amber-soft)' : '#fafbfd' }}>
                <b>{md(wk)} 주</b>{its.length >= 4 && <div className="xs" style={{ color: 'var(--amber-ink)', marginTop: 4 }}>몰림 {its.length}건</div>}
              </div>
              <div>{its.map((it) => <Item key={it.id} it={it} toggle={toggle} setLead={setLead} showEvent />)}</div>
            </div>
          ))}
        </div>
      )}
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
