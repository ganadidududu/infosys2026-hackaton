/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api'
import { ErrorBox, Loading } from '../ui/ui'
import './public.css'

export default function PublicList() {
  const { data, error } = useApi('/public')
  const [q, setQ] = useState('')
  if (error) return <div className="pub"><ErrorBox msg={error} /></div>
  if (!data) return <Loading />
  const items = data.items.filter((x: any) => x.dept.includes(q))
  return (
    <div className="pub">
      <header className="pub-top">
        <Link to="/" className="logo"><i>A</i>Auditon</Link>
        <Link to="/admin" className="chip">관리자</Link>
      </header>
      <section className="pub-hero">
        <div className="xs muted">{data.period.label} · 학생회 전자 공시</div>
        <h1>우리 과 학생회비,<br />잘 쓰였을까?</h1>
        <p>감사위원회가 확정한 감사 결과를 각 학생회가 공시합니다. 순위가 아니라 <b>감점 사유</b>를 보세요.</p>
        <input className="input" placeholder="학과 검색" value={q} onChange={(e) => setQ(e.target.value)} />
      </section>
      <section className="pub-list">
        {items.map((x: any) => {
          const diff = x.total != null && x.prev != null ? x.total - x.prev : null
          const inner = (
            <>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b style={{ fontSize: 16 }}>{x.dept}</b>
                {x.sample && <span className="tag t-n">예시 학과</span>}
              </div>
              {x.published ? (
                <div className="row" style={{ alignItems: 'flex-end', gap: 10, marginTop: 12 }}>
                  <span className="pub-num">{x.total}</span><span className="small ink2" style={{ paddingBottom: 6 }}>점 총 감점</span>
                  <span className="sp" />
                  <div style={{ textAlign: 'right' }} className="small">
                    <div className="muted">경고 {x.warnings}회</div>
                    {diff != null && <div style={{ color: diff > 0 ? 'var(--red)' : diff < 0 ? 'var(--green)' : 'var(--mute)', fontWeight: 700 }}>직전 대비 {diff > 0 ? `+${diff}` : diff === 0 ? '변화 없음' : diff}</div>}
                  </div>
                </div>
              ) : <div className="small muted" style={{ marginTop: 14 }}>아직 공시되지 않았습니다 · 감사 진행 중</div>}
              <Spark h={x.history} />
            </>
          )
          return x.published ? <Link key={x.dept} to={`/d/${x.dept}`} className="pub-card">{inner}</Link> : <div key={x.dept} className="pub-card" style={{ opacity: 0.7 }}>{inner}</div>
        })}
      </section>
      <footer className="pub-foot">
        감사위원회는 징계 권한이 없으며, 감사결과 공고로 각 학생회 의결기구의 판단을 지원합니다(감사기준안 2부 9). 학과 이름순으로 정렬합니다. 시연용 가상 데이터입니다.
      </footer>
    </div>
  )
}

export function Spark({ h }: { h: any[] }) {
  const max = Math.max(4, ...h.map((x) => x.total))
  return (
    <div className="row" style={{ gap: 8, alignItems: 'flex-end', height: 44, marginTop: 14 }}>
      {h.map((x, i) => (
        <div key={x.period} style={{ flex: 1, textAlign: 'center' }}>
          <i style={{ display: 'block', height: Math.max(4, (x.total / max) * 30), borderRadius: 4, background: i === h.length - 1 ? 'var(--ink)' : '#cfd6e4' }} />
          <span className="xs muted">{x.period.slice(2).replace('-', '-')}차</span>
        </div>
      ))}
    </div>
  )
}
