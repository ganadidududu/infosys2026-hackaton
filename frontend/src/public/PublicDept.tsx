/* eslint-disable @typescript-eslint/no-explicit-any */
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../api'
import { Cite, Loading } from '../ui/ui'
import './public.css'

export default function PublicDept() {
  const { dept = '' } = useParams()
  const { data, error } = useApi(`/public/${encodeURIComponent(dept)}`)
  if (error) return (
    <div className="pub"><header className="pub-top"><Link to="/" className="logo"><i>A</i>Auditon</Link></header>
      <div className="pub-sec"><b>{dept}</b><p className="small muted">{error}</p><Link to="/" className="btn sm">학과 목록</Link></div></div>
  )
  if (!data) return <Loading />
  const t = data.totals
  const hist = [...(data.history ?? []), { period: data.period.id, total: t.total }]
  const max = Math.max(4, ...hist.map((x: any) => x.total))
  const prev = data.history?.[data.history.length - 1]
  const warns = data.findings.filter((f: any) => f.disposition?.type === '경고')
  const pts = data.findings.filter((f: any) => f.disposition?.type === '감점')
  return (
    <div className="pub">
      <header className="pub-top"><Link to="/" className="logo"><i>A</i>Auditon</Link><Link to="/" className="chip">학과 목록</Link></header>
      <section className="pub-hero">
        <div className="xs muted">{data.period.label} · 학생회 전자 공시{data.versions > 1 && ` · 제${data.versions}판`}</div>
        <h1 style={{ fontSize: 24 }}>{data.dept} 학생회</h1>
        <div className="row" style={{ alignItems: 'flex-end', gap: 10, marginTop: 10 }}>
          <span className="pub-num" style={{ fontSize: 64 }}>{t.total}</span><span className="ink2" style={{ paddingBottom: 10 }}>점 총 감점</span>
        </div>
        <div className="pub-kpi">
          <div>사례 감점<b>{t.case_points}점</b></div>
          <div>경고<b>{t.warnings}회 · {t.warning_points}점</b></div>
          <div>직전 기간<b>{prev ? `${prev.total}점` : '-'}</b></div>
        </div>
      </section>

      {data.sample ? (
        <section className="pub-sec"><p className="small muted">예시 학과는 총점만 보여 줍니다. 감점 사유는 정보시스템학과 페이지에서 확인하세요.</p></section>
      ) : (
        <>
          <section className="pub-sec">
            <h5>왜 감점됐나요? <small>{pts.length + (warns.length ? 1 : 0)}건</small></h5>
            {pts.map((f: any, i: number) => (
              <div key={i} className="pub-ded"><div className="p r">−{f.disposition.points}</div>
                <div className="d">{f.text}<Cite c={f.clause} /><small>{f.source?.includes('논의') ? '새로운 유형 · 감사인단 전원 논의로 결정' : '지난 감사의 같은 사례와 동일하게 처리'}</small></div></div>
            ))}
            {warns.length > 0 && (
              <div className="pub-ded"><div className="p a">경고</div>
                <div className="d">{warns.map((f: any) => f.text.replace(/어요\.$/, '음')).join(', ')}
                  {warns.map((f: any) => <Cite key={f.clause + f.project} c={f.clause} />)}
                  <small>경고는 회계기간마다 새로 세며 3회째부터 1점씩 감점돼요(4부 26조) → {t.warning_points}점</small></div></div>
            )}
            {pts.length === 0 && warns.length === 0 && <p className="small muted">감점 사유가 없습니다.</p>}
          </section>
          <section className="pub-sec">
            <h5>감사의견 <small>4부 18조</small></h5>
            {data.opinions.map((o: any, i: number) => (
              <div key={o.key} className="pub-op"><span>{'①②③④'[i]} {o.key}</span><b style={{ color: o.grade === '양호' ? 'var(--green)' : 'var(--red)' }}>{o.grade}</b><small>{o.text}</small></div>
            ))}
          </section>
          <section className="pub-sec">
            <h5>이의와 답변 <small>4부 22조</small></h5>
            {data.objections.length === 0 ? <p className="small muted">학생회가 제기한 이의가 없습니다.</p> : data.objections.map((o: any, i: number) => (
              <div key={i} className="pub-thread"><div><b>학생회 이의</b>{o.text}</div><div><b>감사인단 답변</b>{o.answer}</div></div>
            ))}
          </section>
        </>
      )}
      <section className="pub-sec">
        <h5>회계기간별 총 감점</h5>
        <div className="row" style={{ alignItems: 'flex-end', gap: 14, height: 110 }}>
          {hist.map((x: any, i: number) => (
            <div key={x.period} style={{ flex: 1, textAlign: 'center' }} className={`xs ${i === hist.length - 1 ? '' : 'muted'}`}>
              <b style={{ display: 'block', marginBottom: 4 }}>{x.total}</b>
              <i style={{ display: 'block', margin: '0 auto 6px', width: 30, height: Math.max(6, (x.total / max) * 64), borderRadius: '7px 7px 3px 3px', background: i === hist.length - 1 ? 'var(--ink)' : '#cfd6e4' }} />
              {x.period.slice(2)}차
            </div>))}
        </div>
      </section>
      <footer className="pub-foot">
        공시: {data.publisher} · {data.published_at} · {data.keep_until}까지 보관(5년) · 수정 불가(3부 70·71조)<br />
        감사위원회는 징계 권한이 없으며, 감사결과 공고로 각 학생회 의결기구의 판단을 지원합니다(감사기준안 2부 9). 시연용 가상 데이터입니다.
      </footer>
    </div>
  )
}
