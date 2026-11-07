/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from 'react'
import { api, useApi, won } from '../api'
import { Cite, Disp, ErrorBox, Loading, Ring, VERDICT, Verdict, useToast } from '../ui/ui'

const STEPS = ['감사 패킷 구성', '감사 LLM 1차 호출', '감사 LLM 2차 호출', '코드 검증', '선례 처분 · 경고 규칙']
const ORDER: Record<string, number> = { 미충족: 0, '확인 필요': 1, 충족: 3 }

function vkey(f: any) {
  if (f.verdict === '미충족' && f.disposition?.type === '신규 유형') return '신규 유형'
  return f.verdict
}

export default function AuditResult() {
  const { data, error, loading, reload } = useApi('/audit')
  const { data: kijun } = useApi<any[]>('/kijun')
  const [running, setRunning] = useState(-1)
  const toast = useToast()
  const titles = useMemo(() => Object.fromEntries((kijun ?? []).map((c: any) => [c.id, c.title])), [kijun])

  async function run() {
    setRunning(0)
    const p = api('/audit/run', { method: 'POST' })
    for (let i = 1; i <= STEPS.length; i++) { await new Promise((r) => setTimeout(r, 420)); setRunning(i) }
    try { await p; await reload(); toast('감사 판단 초안을 만들었습니다') } catch (e: any) { toast(e.message, true) }
    setRunning(-1)
  }

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox msg={error} />

  return (
    <>
      <div className="ph">
        <div>
          <div className="crumb">4 · 감사 판단 {data?.ran && <>› {data.mode === 'live' ? 'LLM 라이브' : '재생 모드'} · 2회 호출 · 코드 검증 완료 · {data.ran_at?.replace('T', ' ')}</>}</div>
          <h1>감사 결과지</h1>
          <p>감사 LLM은 조항별 판정과 “어느 선례와 같은지”만 답합니다. 감점은 선례에서 코드가 가져오고(4부 23조), 확정은 감사인단이 합니다.</p>
        </div>
        <button className="btn b" onClick={run} disabled={running >= 0}>{running >= 0 ? <><span className="spin" /> 실행 중</> : data?.ran ? '다시 실행' : '감사 판단 실행'}</button>
      </div>

      {running >= 0 && (
        <div className="card pad" style={{ marginBottom: 16 }}>
          <div className="steps">
            {STEPS.map((s, i) => <span key={s} className={`s ${i < running ? 'done' : i === running ? 'run' : ''}`}>{i < running ? '✓' : i === running ? <span className="spin" /> : i + 1} {s}</span>)}
          </div>
        </div>
      )}

      {!data?.ran ? (
        <div className="card" style={{ padding: '56px 24px', textAlign: 'center' }}>
          <div style={{ fontSize: 40 }}>🔎</div>
          <h2 style={{ fontSize: 20, margin: '10px 0 8px' }}>아직 감사 판단을 실행하지 않았습니다</h2>
          <p className="ink2 small" style={{ maxWidth: 560, margin: '0 auto 20px', lineHeight: 1.7 }}>
            사업마다 감사 패킷(기준안 원문 · 질의·답변 · 감사자료 · 코드 검사 결과 · 같은 조항의 선례)을 만들어 감사 LLM에 두 번 보냅니다.
            인용이 서류에 없거나 두 번의 판정이 다르면 자동으로 ‘확인 필요’가 됩니다.
          </p>
          <button className="btn b" onClick={run} disabled={running >= 0}>감사 판단 실행</button>
        </div>
      ) : <Result data={data} titles={titles} reload={reload} />}
    </>
  )
}

function Result({ data, titles, reload }: { data: any; titles: Record<string, string>; reload: () => void }) {
  const t = data.totals
  const packets = data.packets as any[]
  const [pid, setPid] = useState<string>(() => {
    const first = data.findings.find((f: any) => f.verdict !== '충족')
    return first?.packet ?? packets[0].id
  })
  const [onlyIssues, setOnlyIssues] = useState(true)
  const [sel, setSel] = useState<string | null>(null)
  const checksBy = useMemo(() => Object.fromEntries(data.checks.map((c: any) => [c.id, c])), [data.checks])
  const packet = packets.find((p) => p.id === pid)!
  const all = data.findings as any[]
  const issueNo = useMemo(() => {
    const m: Record<string, number> = {}
    let n = 0
    all.filter((f) => f.verdict !== '충족').forEach((f) => { m[f.id] = ++n })
    return m
  }, [all])
  const list = all.filter((f) => f.packet === pid && (!onlyIssues || f.verdict !== '충족'))
    .sort((a, b) => (ORDER[a.verdict] ?? 2) - (ORDER[b.verdict] ?? 2))
  const listKey = list.map((f) => f.id).join('|')
  useEffect(() => { if (!sel || !list.find((f) => f.id === sel)) setSel(list[0]?.id ?? null) }, [pid, onlyIssues, listKey]) // eslint-disable-line
  const cur = all.find((f) => f.id === sel)
  const [advance, setAdvance] = useState(false)
  useEffect(() => {
    if (!advance) return
    setAdvance(false)
    const next = list.find((f) => !f.confirmed && f.verdict !== '충족' && f.id !== sel) ?? all.find((f) => !f.confirmed && f.verdict !== '충족')
    if (next) { setPid(next.packet); setSel(next.id) }
  }, [data]) // eslint-disable-line

  const bv = t.by_verdict
  const total = t.clauses || 1
  const newCnt = all.filter((f) => vkey(f) === '신규 유형').length
  const segs = [
    ['충족', bv['충족'] ?? 0], ['미충족', (bv['미충족'] ?? 0) - newCnt], ['확인 필요', bv['확인 필요'] ?? 0], ['신규 유형', newCnt],
  ] as const
  const issuesPer = (id: string) => all.filter((f) => f.packet === id && f.verdict !== '충족').length

  return (
    <>
      <div className="grid" style={{ gridTemplateColumns: 'minmax(250px,280px) 1fr minmax(280px,320px)', marginBottom: 16 }}>
        <div className="card pad row" style={{ gap: 18 }}>
          <Ring value={t.total} label={t.pending_new || t.pending_check ? '총 감점(초안)' : '총 감점'} frac={Math.min(1, t.total / 10)} />
          <div className="small">
            <div className="muted">사례 감점 + 경고 감점</div>
            <div style={{ marginTop: 6, lineHeight: 1.7 }}><b>{t.case_points}</b> + <b>{t.warning_points}</b> 점<br />
              {t.pending_new > 0 && <span style={{ color: 'var(--violet)', fontWeight: 700 }}>신규 유형 {t.pending_new}건 논의 대기<br /></span>}
              {t.pending_check > 0 && <span style={{ color: 'var(--amber-ink)', fontWeight: 700 }}>확인 필요 {t.pending_check}건</span>}
            </div>
          </div>
        </div>
        <div className="card pad">
          <div className="sec-t">조항별 판정 <small>{t.clauses}개 조항 · {packets.length}개 패킷</small></div>
          <div style={{ display: 'flex', height: 12, borderRadius: 999, overflow: 'hidden', background: 'var(--gray-soft)', marginBottom: 12 }}>
            {segs.map(([k, n]) => <i key={k} style={{ width: `${(n / total) * 100}%`, background: VERDICT[k].color }} />)}
          </div>
          <div className="row small ink2" style={{ gap: 18, flexWrap: 'wrap' }}>
            {segs.map(([k, n]) => <span key={k} className="row" style={{ gap: 6 }}><i style={{ width: 9, height: 9, borderRadius: 3, background: VERDICT[k].color }} />{k}<b style={{ color: 'var(--ink)' }}>{n}</b></span>)}
          </div>
          <div className="xs muted" style={{ marginTop: 10 }}>인용 불일치·2회 판정 불일치는 코드가 자동으로 ‘확인 필요’로 바꿉니다.</div>
        </div>
        <div className="card pad">
          <div className="sec-t"><span>경고 {t.warnings}회 · 이번 회계기간</span><span className="tag t-a">경고 감점 {t.warning_points}점</span></div>
          <div className="row" style={{ gap: 6, marginBottom: 10 }}>
            {Array.from({ length: Math.max(5, t.warnings + 1) }, (_, i) => (
              <i key={i} style={{ width: 30, height: 30, borderRadius: 8, display: 'grid', placeItems: 'center', fontStyle: 'normal', fontSize: 12,
                background: i < t.warnings ? 'var(--amber-soft)' : 'var(--gray-soft)', color: i < t.warnings ? 'var(--amber-ink)' : 'var(--mute)',
                fontWeight: i < t.warnings ? 800 : 400, outline: i < t.warnings && i >= 2 ? '2px solid var(--red)' : 'none', outlineOffset: -2 }}>{i + 1}</i>
            ))}
          </div>
          <div className="mono muted">max(0, w − 2) = max(0, {t.warnings} − 2) = {t.warning_points} · <Cite c="4부 26조" /></div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(360px,440px)', alignItems: 'start' }}>
        <div className="card">
          <div className="tabs">
            {packets.map((p) => (
              <button key={p.id} className={p.id === pid ? 'on' : ''} onClick={() => setPid(p.id)}>
                {p.id === 'ALL' ? '학과 전체' : `사업 ${p.id.slice(1)} · ${p.title}`}
                {issuesPer(p.id) > 0 && <span className="tag t-r" style={{ marginLeft: 6, padding: '1px 6px' }}>{issuesPer(p.id)}</span>}
              </button>
            ))}
          </div>
          <DocViewer packet={packet} findings={all.filter((f) => f.packet === pid)} sel={sel} setSel={setSel} issueNo={issueNo} />
        </div>

        <div className="grid" style={{ position: 'sticky', top: 76 }}>
          <div className="card" style={{ padding: 6 }}>
            <div className="row" style={{ justifyContent: 'space-between', padding: '8px 10px 6px' }}>
              <b className="small">{packet.title} · 판정 {all.filter((f) => f.packet === pid).length}건</b>
              <div className="seg"><button className={onlyIssues ? 'on' : ''} onClick={() => setOnlyIssues(true)}>지적만</button><button className={!onlyIssues ? 'on' : ''} onClick={() => setOnlyIssues(false)}>전체</button></div>
            </div>
            <div style={{ maxHeight: 300, overflow: 'auto' }}>
              {list.length === 0 && <div className="empty small">지적 사항이 없습니다. 모든 조항이 충족입니다.</div>}
              {list.map((f) => {
                const vk = vkey(f)
                const msg = f.checks.map((c: string) => checksBy[c]?.message).find(Boolean)
                return (
                  <button key={f.id} onClick={() => setSel(f.id)} style={{ all: 'unset', cursor: 'pointer', display: 'grid', gridTemplateColumns: '22px 1fr auto', gap: 10, padding: 12, borderRadius: 10, width: '100%', boxSizing: 'border-box', background: sel === f.id ? '#f6f8fc' : undefined, outline: sel === f.id ? '1px solid var(--line)' : undefined }}>
                    <span style={{ width: 22, height: 22, borderRadius: 6, background: VERDICT[vk]?.color, color: '#fff', fontSize: 11, fontWeight: 800, display: 'grid', placeItems: 'center' }}>{issueNo[f.id] ?? '✓'}</span>
                    <span>
                      <span style={{ display: 'block', fontSize: 13.5, fontWeight: 700, lineHeight: 1.4 }}>{headline(f, titles, msg)}</span>
                      <span className="xs muted">{f.clause} · {titles[f.clause.replace(/\s*[①-⑩]$/, '')] ?? ''}{f.confirmed && ' · 확정됨'}</span>
                    </span>
                    {f.verdict === '충족' ? <Verdict v="충족" /> : <Disp d={f.disposition} verdict={f.verdict} />}
                  </button>
                )
              })}
            </div>
          </div>
          {cur && <Detail f={cur} data={data} titles={titles} checksBy={checksBy} reload={() => { setAdvance(true); reload() }} />}
        </div>
      </div>
    </>
  )
}

function headline(f: any, titles: Record<string, string>, msg?: string) {
  if (f.reasons.some((r: string) => r.startsWith('2회 판정'))) return `2회 판정 불일치 · ${titles[f.clause] ?? f.clause}`
  if (f.reasons.some((r: string) => r.startsWith('인용'))) return `인용 검증 실패 · ${titles[f.clause] ?? f.clause}`
  if (msg) return msg
  if (f.question) return f.question
  return `${titles[f.clause] ?? f.clause} 충족`
}

// ---------- 왼쪽: 서류 뷰어 (카피킬러식 하이라이트) ----------
function DocViewer({ packet, findings, sel, setSel, issueNo }: any) {
  const [view, setView] = useState<'docs' | 'ledger' | 'checks' | 'packet'>('docs')
  // 인용 위치 찾기: 원문에 있으면 그 문장, 없으면(인용 불일치) 같은 칸으로 시작하는 줄을 '불일치'로 표시
  const quotes: { doc: string; quote: string; f: any; bad?: boolean }[] = []
  findings.forEach((f: any) => (f.evidence ?? []).forEach((e: any) => {
    const d = packet.documents.find((x: any) => x.id === e.doc)
    const q = (e.quote ?? '').trim()
    if (!d || !q) return
    if (d.text.includes(q)) quotes.push({ doc: e.doc, quote: q, f })
    else {
      const head = q.split(':')[0]
      const line = d.text.split('\n').find((l: string) => l.startsWith(head))
      if (line) quotes.push({ doc: e.doc, quote: line.trim(), f, bad: true })
    }
  }))
  const rank = (id: string) => Math.min(9, ...quotes.filter((q) => q.doc === id).map((q) => ORDER[q.f.verdict] ?? 2))
  const docs = [...packet.documents].sort((a: any, b: any) => rank(a.id) - rank(b.id) || a.kind.localeCompare(b.kind))
  useEffect(() => {
    const el = document.querySelector('mark.sel')
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [sel, view])
  return (
    <div>
      <div className="row" style={{ padding: '12px 18px 0', justifyContent: 'space-between' }}>
        <div className="seg">
          {([['docs', `감사자료 ${packet.documents.length}`], ['ledger', `장부 행 ${packet.ledger_rows.length}`], ['checks', `코드 검사 ${packet.checks.length}`], ['packet', 'LLM에 보낸 패킷']] as const).map(([k, l]) => (
            <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{l}</button>
          ))}
        </div>
        <span className="xs muted hide-m">가명처리된 텍스트 · 이름·연락처는 코드로 바뀌어 전송</span>
      </div>
      {view === 'docs' && (
        <div style={{ padding: 18, display: 'grid', gap: 14 }}>
          {docs.length === 0 && <div className="empty small">이 패킷에 첨부된 서류가 없습니다.</div>}
          {docs.map((d: any) => (
            <div key={d.id} style={{ border: '1px solid var(--line)', borderRadius: 10, padding: '18px 22px', background: '#fff' }}>
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
                <h4 style={{ fontSize: 14.5 }}>{d.title}</h4><span className="tag t-n">{d.kind}</span>
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.95 }}>
                {d.text.split('\n').map((line: string, i: number) => {
                  const q = quotes.find((x) => x.doc === d.id && x.f.id === sel && line.includes(x.quote)) ?? quotes.find((x) => x.doc === d.id && line.includes(x.quote))
                  if (!q) return <div key={i}>{line}</div>
                  const vk = vkey(q.f)
                  const cls = VERDICT[vk]?.mark ?? 'g'
                  const k = line.indexOf(q.quote)
                  return (
                    <div key={i}>{line.slice(0, k)}
                      <mark className={`${cls} ${sel === q.f.id ? 'sel' : ''}`} style={{ color: sel === q.f.id ? VERDICT[vk]?.color : undefined }} onClick={() => setSel(q.f.id)}>
                        <span style={{ color: 'var(--ink)' }}>{q.quote}</span></mark>
                      {issueNo[q.f.id] && <sup className={`n ${cls === 'r' ? '' : cls}`}>{issueNo[q.f.id]}</sup>}
                      {q.bad && <span className="tag t-a" style={{ marginLeft: 6 }}>LLM 인용과 다름</span>}
                      {line.slice(k + q.quote.length)}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
      {view === 'ledger' && (
        <div className="scroll" style={{ padding: '12px 0 0' }}>
          <table className="t">
            <thead><tr><th>번호</th><th>일자</th><th>통장내역</th><th>내용</th><th>구분</th><th className="r">수입</th><th className="r">지출</th><th>지급</th><th>증빙</th></tr></thead>
            <tbody>{packet.ledger_rows.map((r: any) => (
              <tr key={r.code + r.date}><td className="mono">{r.code}</td><td className="num">{r.date.slice(5)}</td><td>{r.bank_desc}</td><td>{r.content}</td><td>{r.class}</td>
                <td className="r num">{r.in ? won(r.in) : ''}</td><td className="r num">{r.out ? won(r.out) : ''}</td><td>{r.method}</td><td className="xs">{r.evidence.join(', ')}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {view === 'checks' && (
        <div style={{ padding: 18 }}>
          <p className="small ink2" style={{ marginTop: 0 }}>숫자로 판단되는 규칙은 LLM이 아니라 코드가 확인합니다. 이 결과는 LLM 판정보다 우선합니다.</p>
          <table className="t"><thead><tr><th>조항</th><th>결과</th><th>내용</th></tr></thead>
            <tbody>{packet.checks.map((c: any) => (
              <tr key={c.id}><td><Cite c={c.clause} /></td><td><span className={`tag ${c.result === '위반' ? 't-r' : c.result === '충족' ? 't-g' : 't-a'}`}>{c.result}</span></td><td>{c.message}</td></tr>
            ))}</tbody></table>
        </div>
      )}
      {view === 'packet' && (
        <div style={{ padding: 18, display: 'grid', gap: 12 }}>
          <div className="small ink2">감사 LLM에는 아래 항목만 들어갑니다. 감점 값은 들어가지 않고, 체크리스트는 이행 사실로만 전달됩니다.</div>
          <div className="card pad"><div className="sec-t">기준안 조항 원문 <small>{packet.clauses.length}개</small></div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 4 }}>{packet.clauses.map((c: any) => <Cite key={c.id} c={c.id} />)}</div></div>
          <div className="card pad"><div className="sec-t">해당 회계기간 질의·답변 <small>4부 15조 · 기준안과 같은 지위</small></div>
            {packet.inquiries.length === 0 ? <div className="small muted">관련 질의 없음</div> : packet.inquiries.map((q: any) => (
              <div key={q.id} className="small" style={{ marginBottom: 8, lineHeight: 1.6 }}><b>Q.</b> {q.q}<br /><b>A.</b> {q.a}</div>))}
          </div>
          <div className="card pad"><div className="sec-t">체크리스트 이행 기록 <small>사실로만 전달</small></div>
            {packet.obligations.length === 0 ? <div className="small muted">-</div> : packet.obligations.map((o: any, i: number) => (
              <div key={i} className="small" style={{ marginBottom: 4 }}>{o.done ? '☑' : '☐'} {o.task}</div>))}
          </div>
          <div className="card pad"><div className="sec-t">기억 · 같은 조항 선례</div>
            {Object.entries(packet.memory).flatMap(([cid, ms]: any) => ms.map((m: any) => (
              <div key={cid + m.id} className="small row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--line2)' }}>
                <span><span className="mono muted">{m.id}</span> · {m.desc}</span><Disp d={m.disposition} verdict="미충족" /></div>)))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- 오른쪽: 근거 리포트 (리드레이식) ----------
function Detail({ f, data, titles, checksBy, reload }: any) {
  const toast = useToast()
  const [edit, setEdit] = useState(false)
  const [pts, setPts] = useState(1)
  const [type, setType] = useState<string>('감점')
  const [note, setNote] = useState('')
  const vk = vkey(f)
  const c = f.same_case ? data.cases[f.same_case] : null
  const [j1, j2] = f.llm
  const [v1, v2] = f.verify
  const msgs = f.checks.map((id: string) => checksBy[id]).filter(Boolean)
  const disagree = j2 && j1.verdict !== j2.verdict
  const ok = (b: boolean | null | undefined) => (b === false ? 'bad' : 'ok')

  async function decide(body: any, m: string) {
    try { await api(`/audit/finding/${encodeURIComponent(f.id)}`, { body }); toast(m); setEdit(false); reload() } catch (e: any) { toast(e.message, true) }
  }

  return (
    <div className="card pad">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <Cite c={f.missing?.[0] ? `${f.clause} ${f.missing[0]}` : f.clause} />
        <span className="row" style={{ gap: 6 }}>{f.confirmed && <span className="tag t-b">확정됨</span>}<Verdict v={vk} /></span>
      </div>
      <h3 style={{ fontSize: 16, margin: '10px 0 6px', lineHeight: 1.45 }}>{headline(f, titles, msgs[0]?.message)}</h3>
      <p className="small ink2" style={{ margin: '0 0 12px', lineHeight: 1.7 }}>
        {f.verdict === '미충족' && f.missing?.length > 0 && <>계산서에 {f.missing.join('·')} 항목이 없습니다. </>}
        {f.reasons.length > 0 ? f.reasons.join(' · ') : f.question ?? (f.verdict === '충족' ? '서류 인용과 코드 검사가 모두 조항을 충족합니다.' : '')}
      </p>

      {(f.evidence ?? []).map((e: any, i: number) => (
        <div key={i} className={`quote ${v1.quote ? '' : 'bad'}`}><small>서류 인용 · {e.doc} {v1.quote ? '(원문 일치 ✓)' : '(원문에 없음 ✕)'}</small>“{e.quote}”</div>
      ))}
      {msgs.map((m: any) => <div key={m.id} className="quote" style={{ borderColor: 'var(--ink2)', background: 'var(--gray-soft)' }}><small>코드 검사 · {m.result}</small>{m.message}</div>)}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 6, margin: '12px 0' }}>
        {[['인용', v1.quote && (!v2 || v2.quote), '서류에 있음'], ['조항', v1.clause, '감사 대상'], ['2회', !disagree, disagree ? '판정 다름' : '판정 일치'], ['선례', f.verdict !== '미충족' ? null : !!f.same_case || f.new_type, f.new_type ? '선례 없음' : '같은 조항']].map(([k, b, s]: any) => (
          <div key={k} style={{ fontSize: 11.5, textAlign: 'center', padding: '8px 4px', borderRadius: 8, lineHeight: 1.35,
            background: b === null ? 'var(--gray-soft)' : b ? 'var(--green-soft)' : 'var(--amber-soft)', color: 'var(--ink2)' }}>
            <b style={{ display: 'block', fontSize: 12, color: b === null ? 'var(--mute)' : b ? 'var(--green)' : 'var(--amber-ink)' }}>{k} {b === null ? '–' : b ? '✓' : '!'}</b>{b === null ? '해당 없음' : s}
          </div>
        ))}
      </div>
      <span hidden>{ok(null)}</span>

      {disagree && (
        <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
          {[j1, j2].map((j: any, i: number) => (
            <div key={i} style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 10 }}>
              <div className="xs muted">{i + 1}차 호출</div><Verdict v={j.verdict} />
              {j.same_case && <div className="xs muted" style={{ marginTop: 6 }}>선례 {j.same_case.case_id}</div>}
            </div>
          ))}
        </div>
      )}

      {c && (
        <div style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 12, display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
          <div><div className="xs muted">동일 선례 · {c.period.replace('-', '년 제')}차 · {c.dept} · {c.id.split('-').pop()}</div>
            <div className="small" style={{ fontWeight: 600, marginTop: 2 }}>{c.desc}</div>
            <div className="xs muted" style={{ marginTop: 4 }}>판단 사유: {c.reason}</div></div>
          <div style={{ fontSize: 20, fontWeight: 800, color: c.disposition.type === '감점' ? 'var(--red)' : 'var(--amber)', whiteSpace: 'nowrap' }}>
            {c.disposition.type === '감점' ? `−${c.disposition.points}` : c.disposition.type}</div>
        </div>
      )}
      {f.same_case_alt?.length > 0 && <div className="xs" style={{ marginTop: 8, color: 'var(--amber-ink)' }}>처분이 다른 선례가 있어 가장 최근 것을 제안: {f.same_case_alt.map((a: any) => a.case).join(', ')}</div>}
      {f.new_type && f.disposition?.type === '신규 유형' && (
        <div style={{ border: '1px dashed var(--violet)', background: 'var(--violet-soft)', borderRadius: 10, padding: 12 }}>
          <b className="small" style={{ color: 'var(--violet)' }}>신규 유형 · 감사인단 전원 논의</b>
          <div className="xs ink2" style={{ marginTop: 4, lineHeight: 1.6 }}>같은 사례로 볼 선례가 없어 시스템은 감점을 정하지 않습니다(<Cite c="4부 24조" />). 전원 논의 결과를 입력하면 다음 감사부터 이 결정이 선례가 됩니다.</div>
        </div>
      )}
      {f.disposition_source && f.verdict === '미충족' && <div className="xs muted" style={{ marginTop: 8 }}>처분 출처: {f.disposition_source}</div>}

      {edit && (
        <div style={{ marginTop: 12, display: 'grid', gap: 8, background: '#fafbfd', padding: 12, borderRadius: 10, border: '1px solid var(--line)' }}>
          <div className="row" style={{ gap: 8 }}>
            <select className="input" value={type} onChange={(e) => setType(e.target.value)} style={{ width: 'auto' }}>
              <option>감점</option><option>경고</option><option>없음</option>
            </select>
            {type === '감점' && <input className="input" type="number" min={1} value={pts} onChange={(e) => setPts(+e.target.value)} style={{ width: 80 }} />}
            {type === '감점' && <span className="small muted">점</span>}
          </div>
          <input className="input" placeholder="판단 사유(감사보고서·기억에 남음)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row"><button className="btn sm" onClick={() => setEdit(false)}>취소</button>
            <button className="btn sm p" onClick={() => decide({ verdict: type === '없음' ? '충족' : '미충족', disposition: type === '없음' ? null : type === '감점' ? { type, points: pts } : { type }, source: f.new_type ? '감사인단 전원 논의' : '감사인 수정', note, confirmed: true }, '처분을 확정했습니다')}>저장·확정</button></div>
        </div>
      )}

      {!edit && (
        <div className="row" style={{ marginTop: 14, gap: 8 }}>
          {f.verdict === '확인 필요' ? (
            <>
              <button className="btn" style={{ flex: 1 }} onClick={() => decide({ verdict: '충족', disposition: null, confirmed: true, source: '감사인 확인' }, '충족으로 확정')}>충족으로 확정</button>
              <button className="btn p" style={{ flex: 1 }} onClick={() => setEdit(true)}>미충족 · 처분 입력</button>
            </>
          ) : f.new_type && f.disposition?.type === '신규 유형' ? (
            <button className="btn p" style={{ flex: 1, background: 'var(--violet)', borderColor: 'var(--violet)' }} onClick={() => { setType('감점'); setEdit(true) }}>전원 논의 결과 입력</button>
          ) : (
            <>
              <button className="btn" style={{ flex: 1 }} onClick={() => setEdit(true)}>처분 수정</button>
              <button className="btn" style={{ flex: 1 }} onClick={() => decide({ verdict: '확인 필요', confirmed: false }, '확인 필요로 돌렸습니다')}>확인 필요로</button>
              <button className="btn p" style={{ flex: 1 }} disabled={f.confirmed} onClick={() => decide({ confirmed: true }, '이 항목을 확정했습니다')}>{f.confirmed ? '확정됨' : '이 항목 확정'}</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
