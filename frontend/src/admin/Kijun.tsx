/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo, useState } from 'react'
import { useApi } from '../api'
import { Cite, Disp, ErrorBox, Loading } from '../ui/ui'

export default function Kijun() {
  const k = useApi<any[]>('/kijun')
  const c = useApi('/cases')
  const [tab, setTab] = useState<'kijun' | 'cases' | 'criteria' | 'inq'>('kijun')
  const [q, setQ] = useState('')
  const [part, setPart] = useState(3)
  const list = useMemo(() => (k.data ?? []).filter((x) => x.part === part && (!q || (x.id + x.title + x.text).includes(q))), [k.data, q, part])
  if (k.error) return <ErrorBox msg={k.error} />
  if (!k.data || !c.data) return <Loading />
  const chapters = Array.from(new Set(list.map((x) => x.title)))
  return (
    <>
      <div className="ph"><div><div className="crumb">공통</div><h1>기준안 · 선례 · 질의</h1>
        <p>감사기준안 원문은 두 LLM의 유일한 판단 기준이고, 선례(기억)는 감점 기준의 출처입니다 <Cite c="4부 23조" />.</p></div></div>
      <div className="card">
        <div className="tabs">
          {([['kijun', `기준안 원문 ${k.data.length}`], ['cases', `선례 ${c.data.cases.length}`], ['criteria', '감점 기준 목록(4부 25조)'], ['inq', `질의·답변 ${c.data.inquiries.length}`]] as const).map(([key, l]) => (
            <button key={key} className={tab === key ? 'on' : ''} onClick={() => setTab(key)}>{l}</button>))}
        </div>
        {tab === 'kijun' && (
          <div style={{ padding: 18 }}>
            <div className="row" style={{ marginBottom: 14, gap: 10, flexWrap: 'wrap' }}>
              <div className="seg">{[2, 3, 4].map((p) => <button key={p} className={part === p ? 'on' : ''} onClick={() => setPart(p)}>{p}부 {['', '', '개념체계', '회계기준', '감사품질'][p]}</button>)}</div>
              <input className="input" style={{ maxWidth: 300 }} placeholder="조항·내용 검색 (예: 세목, 할부)" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {chapters.map((ch) => (
              <section key={ch} style={{ marginBottom: 18 }}>
                <div className="sec-t" style={{ color: 'var(--brand)' }}>{ch}</div>
                {list.filter((x) => x.title === ch).map((x) => (
                  <div key={x.id} style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--line2)' }}>
                    <div><Cite c={x.id} />{!x.auditable && <div className="xs muted" style={{ marginTop: 4 }}>강제력 없음</div>}</div>
                    <div className="small" style={{ lineHeight: 1.75 }}>{x.text.split(/(?=[①-⑩])/).map((s: string, i: number) => <div key={i} style={{ paddingLeft: i ? 8 : 0 }}>{s}</div>)}</div>
                  </div>))}
              </section>))}
          </div>
        )}
        {tab === 'cases' && (
          <table className="t"><thead><tr><th>선례</th><th>조항</th><th>사례</th><th>처분</th><th>판단 사유</th><th>이의</th></tr></thead>
            <tbody>{c.data.cases.map((x: any) => (
              <tr key={x.id}><td className="mono">{x.id}</td><td><Cite c={x.clause} /></td><td>{x.desc}<div className="row" style={{ gap: 4, marginTop: 4 }}>{x.tags.map((t: string) => <span key={t} className="tag t-n">{t}</span>)}</div></td>
                <td><Disp d={x.disposition} verdict="미충족" /></td><td className="small ink2">{x.reason}</td><td>{x.objection ? '있음' : '-'}</td></tr>))}</tbody></table>
        )}
        {tab === 'criteria' && (
          <div style={{ padding: 18 }}>
            <p className="small ink2" style={{ marginTop: 0 }}>감사위원회는 직전 회계기간까지 적용된 감점 기준을 감사대상에 제공해야 합니다 <Cite c="4부 25조" />. 이 목록은 선례에서 자동으로 만들어지며, 학기 체크리스트에서도 볼 수 있습니다.</p>
            <table className="t"><thead><tr><th>조항</th><th>사례 유형</th><th>처분</th><th>적용 회계기간</th></tr></thead>
              <tbody>{c.data.criteria.map((x: any) => <tr key={x.case}><td><Cite c={x.clause} /></td><td>{x.type}</td><td><Disp d={x.disposition} verdict="미충족" /></td><td>{x.period}</td></tr>)}</tbody></table>
            <p className="xs muted">경고는 회계기간마다 새로 세며, 3회째부터 1건마다 1점 감점합니다 <Cite c="4부 26조" />.</p>
          </div>
        )}
        {tab === 'inq' && (
          <div style={{ padding: 18, display: 'grid', gap: 10 }}>
            <p className="small ink2" style={{ margin: 0 }}>답변은 해당 회계기간 감사에서 기준안과 같은 지위를 갖습니다. 기준안과 충돌하면 기준안이 우선합니다 <Cite c="4부 15조" />.</p>
            {c.data.inquiries.map((x: any) => (
              <div key={x.id} className="card pad small" style={{ lineHeight: 1.7 }}>
                <div className="xs muted">{x.id} · {x.date} · {x.clauses.map((cl: string) => <Cite key={cl} c={cl} />)}</div>
                <div><b>Q.</b> {x.q}</div><div><b>A.</b> {x.a}</div>
              </div>))}
          </div>
        )}
      </div>
    </>
  )
}
