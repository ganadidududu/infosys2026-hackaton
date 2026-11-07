/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, useApi } from '../api'
import { Cite, Disp, ErrorBox, Loading, Ring, useToast } from '../ui/ui'
import { Detail, headline } from './AuditParts'

const STEPS = ['감사 패킷 구성', '감사 LLM 1차 호출', '감사 LLM 2차 호출', '코드 검증', '선례 처분 · 경고 규칙']

export default function GradeRecord() {
  const { rid = '' } = useParams()
  const rec = useApi(`/records/${rid}`)
  const audit = useApi(`/records/${rid}/audit`)
  const { data: kijun } = useApi<any[]>('/kijun')
  const titles = useMemo(() => Object.fromEntries((kijun ?? []).map((c: any) => [c.id, c.title])), [kijun])
  const [running, setRunning] = useState(-1)
  const toast = useToast()
  if (rec.error) return <ErrorBox msg={rec.error} />
  if (!rec.data || !audit.data) return <Loading />
  const r = rec.data
  if (r.readonly) return <PastRecord r={r} />
  const reloadAll = () => { rec.reload(); audit.reload() }
  const req = r.slots.filter((s: any) => s.required)
  const submitted = req.filter((s: any) => s.file).length
  const ready = submitted === req.length

  async function run() {
    setRunning(0)
    const p = api(`/records/${rid}/run`, { method: 'POST' })
    for (let i = 1; i <= STEPS.length; i++) { await new Promise((res) => setTimeout(res, 380)); setRunning(i) }
    try { await p; reloadAll(); toast('모의 채점을 마쳤습니다') } catch (e: any) { toast(e.message, true) }
    setRunning(-1)
  }

  return (
    <>
      <div className="ph">
        <div>
          <div className="crumb"><Link to="/admin/grade" style={{ textDecoration: 'underline' }}>모의 채점</Link> › {r.kind} · {r.dept} · {r.period.replace('-', '년 제')}차</div>
          <h1>{r.title}</h1>
          {r.memo && <p>{r.memo}</p>}
        </div>
        {!audit.data.ran && <div className="row">
          <button className="btn" onClick={async () => { await api(`/records/${rid}/fill-sample`, { method: 'POST' }); toast('시연용 가상 서류로 채웠습니다'); reloadAll() }}>시연용 서류 채우기</button>
          <button className="btn b" disabled={!ready || running >= 0} title={ready ? '' : '필수 서류를 모두 올리세요'} onClick={run}>
            {running >= 0 ? <><span className="spin" /> 채점 중</> : audit.data.ran ? '다시 채점' : '채점 시작'}</button>
        </div>}
      </div>

      {running >= 0 && (
        <div className="card pad" style={{ marginBottom: 16 }}>
          <div className="steps">{STEPS.map((s, i) => <span key={s} className={`s ${i < running ? 'done' : i === running ? 'run' : ''}`}>{i < running ? '✓' : i === running ? <span className="spin" /> : i + 1} {s}</span>)}</div>
        </div>
      )}

      {!audit.data.ran ? (
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px', alignItems: 'start' }}>
          <div className="card">
            <div className="pad" style={{ borderBottom: '1px solid var(--line)' }}>
              <div className="sec-t" style={{ margin: 0 }}>① 감사자료 제출 <small>필수 {submitted}/{req.length} · 제출 순서와 범위는 <Cite c="3부 60조" /><Cite c="3부 65조" /></small></div>
              <div style={{ height: 6, borderRadius: 999, background: 'var(--gray-soft)', marginTop: 12, overflow: 'hidden' }}>
                <i style={{ display: 'block', height: '100%', width: `${(submitted / req.length) * 100}%`, background: 'var(--green)', transition: '.3s' }} /></div>
            </div>
            {r.slots.map((s: any) => <SlotRow key={s.key} s={s} rid={rid} reload={reloadAll} />)}
          </div>
          <div className="card pad">
            <div className="sec-t">채점 방식</div>
            <ol className="small ink2" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.85 }}>
              <li>엑셀 장부(CSV)를 읽어 거래로 바꾸고 영수증함 증빙과 헝가리안 대사</li>
              <li>사업별 감사 패킷 → 감사 LLM 2회 호출</li>
              <li>인용·조항·2회 일치·선례를 코드로 검증</li>
              <li>감점은 선례에서(<Cite c="4부 23조" />), 경고 w회 → max(0, w−2)</li>
              <li><b>점수 = 100 − 총 감점</b> (모의 점수. 기준안에는 점수제가 없고 감점만 있습니다)</li>
            </ol>
            <div className="xs muted" style={{ marginTop: 12, lineHeight: 1.6 }}>필수 서류를 모두 올리면 채점할 수 있어요. 시연할 때는 ‘시연용 서류 채우기’를 누르세요.</div>
          </div>
        </div>
      ) : <Scored rid={rid} r={r} data={audit.data} titles={titles} reload={reloadAll} onRun={run} running={running} />}
    </>
  )
}

function SlotRow({ s, rid, reload, compact }: any) {
  const ref = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const ok = !!s.file
  async function up(file: File) {
    setBusy(true)
    const fd = new FormData(); fd.append('file', file)
    try { const res = await api(`/records/${rid}/files/${s.key}`, { body: fd }); toast(`${s.label} 제출${res.file.rows ? ` · 거래 ${res.file.rows}건 인식` : ''}`); reload() } catch (e: any) { toast(e.message, true) }
    setBusy(false)
  }
  const dot = (
    <span style={{ width: compact ? 22 : 30, height: compact ? 22 : 30, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: compact ? 12 : 14,
      background: ok ? 'var(--green)' : 'var(--gray-soft)', color: ok ? '#fff' : 'var(--mute)', transition: '.25s' }}>{busy ? <span className="spin" /> : ok ? '✓' : ''}</span>
  )
  return (
    <div onClick={() => compact && ref.current?.click()} title={compact ? '눌러서 다시 올리기' : ''}
      style={{ display: 'flex', gap: compact ? 10 : 14, alignItems: 'center', padding: compact ? '9px 12px' : '14px 20px', borderBottom: '1px solid var(--line2)', cursor: compact ? 'pointer' : 'default',
        background: ok ? (compact ? 'transparent' : '#f6fcf9') : undefined, transition: '.25s' }}>
      <input ref={ref} type="file" hidden onChange={(e) => e.target.files?.[0] && up(e.target.files[0])} />
      {dot}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: compact ? 12.5 : 14, color: ok ? 'var(--ink)' : 'var(--ink2)' }}>{s.label}{!s.required && <span className="xs muted"> · 선택</span>}</div>
        <div className="xs muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {ok ? <>{s.file.name}{s.file.rows ? ` · 거래 ${s.file.rows}건` : ''}{!compact && ` · ${s.file.source} · ${s.file.uploaded.replace('T', ' ')}`}</> : s.hint}
        </div>
        {!compact && ok && s.file.mapping && <div className="xs" style={{ color: 'var(--green)', marginTop: 3 }}>열 자동 매핑: {Object.entries(s.file.mapping).map(([k, v]) => `${v}→${({ date: '일자', desc: '통장내역', in: '입금', out: '출금', amount: '금액', balance: '잔액', account: '통장', note: '비고', project: '사업', method: '결제수단' } as any)[k]}`).join(' · ')}</div>}
      </div>
      {!compact && <Cite c={s.clause} />}
      {!compact && (
        <div className="row" style={{ gap: 6 }}>
          {ok && <button className="btn sm ghost" onClick={async () => { await api(`/records/${rid}/files/${s.key}`, { method: 'DELETE' }); reload() }}>빼기</button>}
          <button className={`btn sm ${ok ? '' : 'p'}`} onClick={() => ref.current?.click()}>{ok ? '바꾸기' : '파일 올리기'}</button>
        </div>
      )}
    </div>
  )
}

// 모의 채점 2단계 (시안 v8): 좌 점수+제출 서류 · 중 감점 항목 · 우 서류(문제 줄에 말풍선)
const GROUPS = ['사업개요서', '장부 · 내역서 · 증빙', '통장 · 학과 전체']

function penalty(f: any): [string, string] {
  if (f.verdict === '확인 필요') return ['확인', 'q']
  const d = f.disposition
  if (!d) return ['', '']
  if (d.type === '신규 유형') return ['전원 논의', 'q']
  if (d.type === '감점') return [`−${d.points}`, 'm']
  if (d.type === '경고') return ['경고', 'w']
  return [d.type, '']
}

function Scored({ rid, r, data, titles, reload, onRun, running }: any) {
  const t = data.totals, sc = data.score
  const packets = data.packets as any[]
  const all = data.findings as any[]
  const { data: kijun } = useApi<any[]>('/kijun')
  const clauseText = useMemo(() => Object.fromEntries((kijun ?? []).map((c: any) => [c.id, c.text])), [kijun])
  const checksBy = useMemo(() => Object.fromEntries(data.checks.map((c: any) => [c.id, c])), [data.checks])
  const docKind = useMemo(() => { const m: Record<string, string> = {}; packets.forEach((p) => p.documents.forEach((d: any) => { m[d.id] = d.kind })); return m }, [packets])
  const issues = all.filter((f) => f.verdict !== '충족')
  const groupOf = (f: any) => {
    const kinds = (f.evidence ?? []).map((e: any) => docKind[e.doc])
    if (kinds.includes('사업개요서')) return 0
    if (f.packet === 'ALL' || kinds.includes('통장사본') || kinds.length === 0) return 2
    return 1
  }
  const pidNo = (pid: string) => (pid === 'ALL' ? 0 : +pid.slice(1))
  const loc = (f: any) => f.checks.map((c: string) => checksBy[c]?.target).find(Boolean) ?? (f.packet === 'ALL' ? '전체' : `사업 ${pidNo(f.packet)}`)
  const short = (f: any) => headline(f, titles, f.checks.map((c: string) => checksBy[c]?.message).find(Boolean))
  const ordered = GROUPS.map((_, g) => issues.filter((f) => groupOf(f) === g).sort((a, b) => pidNo(a.packet) - pidNo(b.packet)))
  const no: Record<string, number> = {}; let n = 0; ordered.flat().forEach((f) => { no[f.id] = ++n })

  const [sel, setSel] = useState<string | null>(() => ordered.flat()[0]?.id ?? null)
  const [pid, setPid] = useState<string>(() => ordered.flat()[0]?.packet ?? packets[0].id)
  const [open, setOpen] = useState<string | null>(null)
  const [advance, setAdvance] = useState(false)
  useEffect(() => {
    if (!advance) return
    setAdvance(false)
    const next = ordered.flat().find((f) => !f.confirmed && f.id !== sel)
    if (next) { setPid(next.packet); setSel(next.id); setOpen(null) }
  }, [data]) // eslint-disable-line
  const pick = (f: any) => { setPid(f.packet); setSel(f.id); setOpen(f.id === sel ? open : null) }
  const packet = packets.find((p) => p.id === pid) ?? packets[0]
  const pending = t.pending_new + t.pending_check
  const filed = r.slots.filter((s: any) => s.file).length
  // 화면 전체는 스크롤하지 않고, 각 칸 안에서만 스크롤
  const box = useRef<HTMLDivElement>(null)
  const [h, setH] = useState<number>()
  useLayoutEffect(() => {
    const fit = () => {
      const el = box.current; if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      const below = document.documentElement.scrollHeight - (top + el.offsetHeight) // 아래 여백
      setH(Math.max(420, window.innerHeight - top - Math.max(0, below)))
    }
    fit(); requestAnimationFrame(fit); window.addEventListener('resize', fit); return () => window.removeEventListener('resize', fit)
  }, [])

  return (
    <div className="grid sc-grid" ref={box} style={{ height: h }}>
      {/* 좌: 점수 + 제출 서류 */}
      <div className="sc-left">
        <div className="card sc-score">
          <div className="v num">{sc.score}<small>/ 100</small></div>
          <div className="cs">
            <span className="c">감점 −{t.case_points}</span>
            <span className="c">경고 {t.warnings}회 −{t.warning_points}</span>
            {pending > 0 && <span className="c a">미확정 {pending}</span>}
          </div>
          <div className="bb">
            <button className="btn sm" disabled={running >= 0} onClick={onRun}>{running >= 0 ? <><span className="spin" /> 채점 중</> : '다시 채점'}</button>
            <Link className="btn sm k" to="/admin/report">보고서</Link>
          </div>
        </div>
        <div className="card" style={{ paddingTop: 4 }}>
          <div className="sc-lh">제출 서류 {filed}/{r.slots.length}</div>
          {r.slots.map((s: any) => <SlotRow key={s.key} s={s} rid={rid} reload={reload} compact />)}
        </div>
      </div>

      {/* 중: 감점 항목 */}
      <div className="card sc-list">
        <div className="sc-h2">감점 항목</div>
        {issues.length === 0 && <div className="empty small">지적 사항이 없습니다.</div>}
        {ordered.map((fs, g) => fs.length > 0 && (
          <div key={g} className="sc-grp">
            <div className="sc-gl">{GROUPS[g]}</div>
            {fs.map((f) => {
              const [pl, pc] = penalty(f)
              return (
                <button key={f.id} className={`sc-row ${sel === f.id ? 'on' : ''} ${f.confirmed ? 'done' : ''}`} onClick={() => pick(f)}>
                  <span className="n">{no[f.id]}.</span>
                  <span className="tx"><b className="num">{loc(f)}</b>{short(f)}</span>
                  <span className={`sc-p ${pc}`}>{f.confirmed && <i>✓</i>}{pl}</span>
                </button>
              )
            })}
          </div>
        ))}
        <div className="sc-sum"><span>합계</span><span>−{t.total} · 경고 {t.warnings}</span></div>
      </div>

      {/* 우: 서류 + 말풍선 */}
      <div className="card sc-docs">
        <DocPane packet={packet} findings={issues.filter((f) => f.packet === packet.id)} sel={sel} open={open}
          onLine={(f: any) => { setSel(f.id); setOpen(open === f.id ? null : f.id) }}
          no={no} short={short} titles={titles} clauseText={clauseText}
          detail={(f: any) => <Detail f={f} data={data} titles={titles} checksBy={checksBy} base={`/records/${rid}`} reload={() => { setAdvance(true); reload() }} />} />
      </div>
    </div>
  )
}

function DocPane({ packet, findings, sel, open, onLine, no, short, titles, clauseText, detail }: any) {
  // 인용 위치: 원문에 있으면 그 줄, 없으면(인용 불일치) 같은 칸으로 시작하는 줄
  const hits: { doc: string; line: string; f: any }[] = []
  findings.forEach((f: any) => (f.evidence ?? []).forEach((e: any) => {
    const d = packet.documents.find((x: any) => x.id === e.doc)
    const q = (e.quote ?? '').trim()
    if (!d || !q) return
    const lines = d.text.split('\n')
    const line = lines.find((l: string) => l.includes(q)) ?? lines.find((l: string) => l.startsWith(q.split(':')[0]))
    if (line) hits.push({ doc: d.id, line, f })
  }))
  const placed = new Set(hits.map((h) => h.f.id))
  const loose = findings.filter((f: any) => !placed.has(f.id))
  const hasHit = (id: string) => hits.some((h) => h.doc === id)
  const docs = [...packet.documents].sort((a: any, b: any) => +hasHit(b.id) - +hasHit(a.id))
  useEffect(() => {
    const el = document.querySelector('.sc-ln.sel, .sc-loose.sel')
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [sel, packet.id])

  const call = (f: any) => {
    const [pl, pc] = penalty(f)
    return (
      <span className={`sc-call ${pc}`}>
        {pl && <span className={`tg ${pc}`}>{pl}</span>}<b>{no[f.id]}. {short(f)}</b><span className="cl">{f.clause}</span>
      </span>
    )
  }
  const expand = (f: any) => open === f.id && (
    <div className="sc-open" onClick={(e) => e.stopPropagation()}>
      <div className="sc-rule"><span className="cl">{f.clause} · {titles[f.clause] ?? ''}</span>{clauseText[f.clause] && <p>{clauseText[f.clause]}</p>}</div>
      {detail(f)}
    </div>
  )

  return (
    <div className="sc-pane">
      {loose.map((f: any) => (
        <div key={f.id} className={`sc-loose ${sel === f.id ? 'sel' : ''}`} onClick={() => onLine(f)}>
          <div className={`sc-ln hit ${penalty(f)[1]}`}><span className="muted">서류 밖 · 통장/장부 기준</span>{call(f)}</div>
          {expand(f)}
        </div>
      ))}
      {docs.length === 0 && loose.length === 0 && <div className="empty small">이 사업에 첨부된 서류가 없습니다.</div>}
      {docs.map((d: any) => (
        <div key={d.id} className="sc-paper">
          <div className="sc-ph"><b>{d.title}</b><em>{d.kind}</em></div>
          {d.text.split('\n').map((line: string, i: number) => {
            const hs = hits.filter((h) => h.doc === d.id && h.line === line)
            if (!hs.length) return <div key={i} className="sc-ln">{line}</div>
            const f = (hs.find((h) => h.f.id === sel) ?? hs[0]).f
            return (
              <div key={i} onClick={() => onLine(f)} style={{ cursor: 'pointer' }}>
                <div className={`sc-ln hit ${penalty(f)[1]} ${sel === f.id ? 'sel' : ''}`}><span>{line}</span>{call(f)}</div>
                {expand(f)}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function PastRecord({ r }: any) {
  const s = r.summary
  return (
    <>
      <div className="ph"><div><div className="crumb"><Link to="/admin/grade" style={{ textDecoration: 'underline' }}>모의 채점</Link> › 지난 기록</div><h1>{r.title}</h1>
        <p>{r.dept} · {r.period.replace('-', '년 제')}차 회계기간 · 확정된 감사 결과 요약(읽기 전용)</p></div></div>
      <div className="grid" style={{ gridTemplateColumns: '300px 1fr', alignItems: 'start' }}>
        <div className="card pad row" style={{ gap: 18 }}>
          <Ring value={s.score} label="/ 100점" frac={s.score / 100} color="var(--ink2)" />
          <div className="small"><div>총 감점 <b>{s.total}</b></div><div>경고 <b>{s.warnings}회</b></div></div>
        </div>
        <div className="card pad">
          <div className="sec-t">이 기간의 선례 <small>다음 감사의 감점 기준이 됩니다(4부 23조)</small></div>
          {s.cases.length === 0 ? <div className="small muted">기록된 선례가 없습니다.</div> : s.cases.map((c: any, i: number) => (
            <div key={i} className="row small" style={{ justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--line2)' }}>
              <span><Cite c={c.clause} /> {c.desc}</span><Disp d={c.disposition} verdict="미충족" /></div>))}
        </div>
      </div>
    </>
  )
}
