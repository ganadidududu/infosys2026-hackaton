/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApi } from '../api'
import { Cite, Disp, ErrorBox, Loading, useToast } from '../ui/ui'

export default function Report() {
  const { data, error, reload } = useApi('/report')
  const toast = useToast()
  const [ops, setOps] = useState<any[]>([])
  const [obj, setObj] = useState('')
  const [objF, setObjF] = useState('')
  useEffect(() => { if (data) setOps(data.opinions) }, [data])
  if (error) return <ErrorBox msg={error} />
  if (!data) return <Loading />
  if (!data.totals) return <div className="card empty">감사 판단을 먼저 실행하세요. <Link to="/admin/grade" className="btn sm b" style={{ marginLeft: 8 }}>모의 채점으로</Link></div>

  const h = data.fields.hours
  const minH = 20
  const hoursOk = h.total >= minH && h.senior * 2 >= minH && h.auditors.every((a: any) => a.h >= 2)
  async function saveOps(next: any[]) { setOps(next); await api('/report', { body: { opinions: next } }) }
  async function act(path: string, body: any, m: string) {
    try { await api(path, { body }); toast(m); reload() } catch (e: any) { toast(e.message, true) }
  }
  const t = data.totals
  const steps = [
    { k: '감사 종료', d: data.audit.end, done: true, c: '' },
    { k: '보고서 송부', d: data.sent ?? `기한 ${data.deadlines.send_by}`, done: !!data.sent, c: '4부 19조' },
    { k: '이의 접수(3일)', d: data.deadlines.objection_until ? `~ ${data.deadlines.objection_until}` : '송부 후 3일', done: !!data.sent, c: '4부 20조' },
    { k: '답변·전문 공시(7일)', d: data.deadlines.answer_by ? `~ ${data.deadlines.answer_by}` : '송부 후 7일', done: data.objections.every((o: any) => o.answer) && !!data.sent, c: '4부 21조' },
    { k: '학생회 전자 공시', d: data.published ?? (data.deadlines.publish_by ? `~ ${data.deadlines.publish_by}` : '공시 후 1개월'), done: !!data.published, c: '3부 70조' },
  ]

  return (
    <>
      <div className="ph">
        <div><div className="crumb"><Link to="/admin/grade" style={{ textDecoration: 'underline' }}>모의 채점</Link> › {data.record && <Link to={`/admin/grade/${data.record.id}`} style={{ textDecoration: 'underline' }}>{data.record.title}</Link>} › 감사 후</div><h1>감사보고서 · 이의 · 공시</h1>
          <p>감사보고서 항목은 <Cite c="4부 17조" />, 감사의견은 <Cite c="4부 18조" />의 4가지 평가로 씁니다. 등급은 없습니다.</p></div>
        <div className="row">
          {!data.sent && <button className="btn b" disabled={data.unconfirmed > 0} title={data.unconfirmed ? '확정하지 않은 항목이 있습니다' : ''} onClick={() => act('/report/send', {}, '감사보고서를 송부했습니다')}>감사보고서 송부</button>}
          {data.sent && <button className="btn p" disabled={!!data.published} onClick={() => act('/publish', {}, '학생회 전자 공시를 게시했습니다')}>{data.published ? '공시 완료' : '학생회 전자 공시 게시'}</button>}
          {data.published && <Link className="btn" to="/d/정보시스템학과">공개 페이지 보기 ↗</Link>}
        </div>
      </div>

      <div className="card pad" style={{ marginBottom: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${steps.length},1fr)`, gap: 8 }}>
          {steps.map((s, i) => (
            <div key={s.k} style={{ position: 'relative' }}>
              <div style={{ height: 6, borderRadius: 999, background: s.done ? 'var(--green)' : 'var(--gray-soft)', marginBottom: 10 }} />
              <div className="small" style={{ fontWeight: 700 }}>{i + 1}. {s.k}</div>
              <div className="xs muted num">{s.d}</div>
              {s.c && <Cite c={s.c} />}
            </div>
          ))}
        </div>
        {data.unconfirmed > 0 && <div className="small" style={{ marginTop: 12, color: 'var(--amber-ink)' }}>확정하지 않은 항목 {data.unconfirmed}건(확인 필요·신규 유형 포함)이 있습니다. <Link to={`/admin/grade/${data.record?.id}`} style={{ textDecoration: 'underline' }}>채점 페이지에서 확정</Link>해야 송부할 수 있습니다.</div>}
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr)', alignItems: 'start' }}>
        <div className="grid">
          <div className="card pad">
            <div className="sec-t">감사의견 <small>짧은 판정 + 한두 문장 · 감사인단이 고쳐 확정</small></div>
            {ops.map((o, i) => (
              <div key={o.key} style={{ padding: '12px 0', borderBottom: i < 3 ? '1px solid var(--line2)' : 0 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <b className="small">{'①②③④'[i]} {o.key}</b>
                  <div className="seg">{['양호', '미흡'].map((g) => <button key={g} className={o.grade === g ? 'on' : ''} style={o.grade === g ? { color: g === '양호' ? 'var(--green)' : 'var(--red)' } : {}}
                    onClick={() => saveOps(ops.map((x, k) => (k === i ? { ...x, grade: g } : x)))}>{g}</button>)}</div>
                </div>
                <textarea className="input" style={{ marginTop: 8, minHeight: 52 }} defaultValue={o.text}
                  onBlur={(e) => e.target.value !== o.text && saveOps(ops.map((x, k) => (k === i ? { ...x, text: e.target.value } : x)))} />
              </div>
            ))}
          </div>
          <div className="card pad">
            <div className="sec-t">감점 내역 <small>총 {t.total}점 = 사례 {t.case_points} + 경고 감점 {t.warning_points}(경고 {t.warnings}회)</small></div>
            <table className="t"><thead><tr><th>조항</th><th>사업</th><th>처분</th><th>출처</th></tr></thead>
              <tbody>{data.findings.map((f: any) => (
                <tr key={f.id}><td><Cite c={f.clause} /></td><td>{f.project}</td><td><Disp d={f.disposition} verdict={f.verdict} /></td><td className="xs muted">{f.disposition_source}</td></tr>))}</tbody></table>
          </div>
        </div>

        <div className="grid">
          <div className="card pad">
            <div className="sec-t">보고서 기본 항목 <small>4부 17조</small></div>
            <dl className="small" style={{ margin: 0, display: 'grid', gridTemplateColumns: '110px 1fr', rowGap: 10, lineHeight: 1.6 }}>
              <dt className="muted">① 감사대상</dt><dd style={{ margin: 0 }}>{data.fields.target}</dd>
              <dt className="muted">② 수행 범위</dt><dd style={{ margin: 0 }}>{data.fields.scope}</dd>
              <dt className="muted">③ 수행 기간</dt><dd style={{ margin: 0 }}>{data.fields.period}</dd>
              <dt className="muted">④ 감사시간</dt><dd style={{ margin: 0 }}>총 {h.total}시간 · 선임위원 {h.senior}시간 <span className={`tag ${hoursOk ? 't-g' : 't-r'}`}>{hoursOk ? '최소 시간 충족' : '최소 시간 미달'}</span>
                <div className="xs muted">{h.auditors.map((a: any) => `${a.name} ${a.h}h`).join(' · ')} · 정기 20시간, 1인 2시간, 선임 1/2 <Cite c="4부 9조" /><Cite c="4부 12조" /></div></dd>
              <dt className="muted">⑤ 질의·답변</dt><dd style={{ margin: 0 }}>{data.fields.inquiries.map((q: any) => <div key={q.id} className="xs" style={{ marginBottom: 4 }}><b>Q</b> {q.q}<br /><b>A</b> {q.a}</div>)}</dd>
              <dt className="muted">⑥ 감사의견</dt><dd style={{ margin: 0 }}>왼쪽 4가지 평가</dd>
              <dt className="muted">⑦ 서명</dt><dd style={{ margin: 0 }} className="muted">감사인단 서명란(출력 시)</dd>
            </dl>
          </div>
          <div className="card pad">
            <div className="sec-t">이의와 답변 <small>공시에 반드시 포함 · 4부 22조</small></div>
            {data.objections.length === 0 && <div className="small muted" style={{ marginBottom: 10 }}>접수된 이의가 없습니다.</div>}
            {data.objections.map((o: any, i: number) => <Objection key={i} i={i} o={o} act={act} />)}
            {data.sent && !data.published && (
              <div className="grid" style={{ gap: 8, marginTop: 10 }}>
                <select className="input" value={objF} onChange={(e) => setObjF(e.target.value)}><option value="">관련 지적(선택)</option>{data.findings.map((f: any) => <option key={f.id} value={f.id}>{f.clause} · {f.project}</option>)}</select>
                <textarea className="input" placeholder="학생회가 낸 이의 내용을 기록합니다(이의 접수 화면은 P1)" value={obj} onChange={(e) => setObj(e.target.value)} />
                <button className="btn sm" disabled={!obj.trim()} onClick={() => { act('/objections', { text: obj, finding: objF || null }, '이의를 기록했습니다'); setObj('') }}>이의 기록</button>
              </div>
            )}
            {!data.sent && <div className="xs muted">보고서를 송부하면 3일간 이의를 받을 수 있습니다.</div>}
          </div>
        </div>
      </div>
    </>
  )
}

function Objection({ i, o, act }: any) {
  const [a, setA] = useState('')
  return (
    <div style={{ background: 'var(--bg)', borderRadius: 12, padding: 12, marginBottom: 8 }} className="small">
      <div className="xs muted">학생회 이의 · {o.at}{o.finding && ` · ${o.finding.split(':')[1]}`}</div>
      <div style={{ margin: '2px 0 8px' }}>{o.text}</div>
      {o.answer ? <><div className="xs muted">감사인단 답변</div><div>{o.answer}</div></> : (
        <div className="row"><input className="input" placeholder="답변" value={a} onChange={(e) => setA(e.target.value)} />
          <button className="btn sm p" disabled={!a.trim()} onClick={() => act(`/objections/${i}/answer`, { answer: a }, '답변을 기록했습니다')}>답변</button></div>
      )}
    </div>
  )
}
