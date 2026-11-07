/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, useApi } from '../api'
import { Cite, Disp, ErrorBox, Loading, Ring, VERDICT, Verdict, useToast } from '../ui/ui'
import { DocViewer, Detail, ORDER, headline, vkey } from './AuditParts'

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
        <div className="row">
          <button className="btn" onClick={async () => { await api(`/records/${rid}/fill-sample`, { method: 'POST' }); toast('시연용 가상 서류로 채웠습니다'); reloadAll() }}>시연용 서류 채우기</button>
          <button className="btn b" disabled={!ready || running >= 0} title={ready ? '' : '필수 서류를 모두 올리세요'} onClick={run}>
            {running >= 0 ? <><span className="spin" /> 채점 중</> : audit.data.ran ? '다시 채점' : '채점 시작'}</button>
          {audit.data.ran && <Link className="btn p" to="/admin/report">감사보고서·공시 →</Link>}
        </div>
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
      ) : <Scored rid={rid} r={r} data={audit.data} titles={titles} reload={reloadAll} />}
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

// 모의 채점 2단계: 좌 제출 현황 · 중 서류 하이라이트 · 우 점수 + 지적 근거
function Scored({ rid, r, data, titles, reload }: any) {
  const t = data.totals, sc = data.score
  const packets = data.packets as any[]
  const all = data.findings as any[]
  const [pid, setPid] = useState<string>(() => all.find((f) => f.verdict !== '충족')?.packet ?? packets[0].id)
  const [onlyIssues, setOnlyIssues] = useState(true)
  const [sel, setSel] = useState<string | null>(null)
  const [advance, setAdvance] = useState(false)
  const checksBy = useMemo(() => Object.fromEntries(data.checks.map((c: any) => [c.id, c])), [data.checks])
  const packet = packets.find((p) => p.id === pid) ?? packets[0]
  const issueNo = useMemo(() => { const m: Record<string, number> = {}; let n = 0; all.filter((f) => f.verdict !== '충족').forEach((f) => { m[f.id] = ++n }); return m }, [all])
  const list = all.filter((f) => f.packet === pid && (!onlyIssues || f.verdict !== '충족')).sort((a, b) => (ORDER[a.verdict] ?? 2) - (ORDER[b.verdict] ?? 2))
  const listKey = list.map((f) => f.id).join('|')
  useEffect(() => { if (!sel || !list.find((f) => f.id === sel)) setSel(list[0]?.id ?? null) }, [pid, onlyIssues, listKey]) // eslint-disable-line
  useEffect(() => {
    if (!advance) return
    setAdvance(false)
    const next = list.find((f) => !f.confirmed && f.verdict !== '충족' && f.id !== sel) ?? all.find((f) => !f.confirmed && f.verdict !== '충족')
    if (next) { setPid(next.packet); setSel(next.id) }
  }, [data]) // eslint-disable-line
  const cur = all.find((f) => f.id === sel)
  const issuesPer = (id: string) => all.filter((f) => f.packet === id && f.verdict !== '충족').length
  const pending = t.pending_new + t.pending_check
  const color = sc.score >= 98 ? 'var(--green)' : sc.score >= 95 ? 'var(--brand)' : 'var(--red)'

  return (
    <div className="grid" style={{ gridTemplateColumns: '250px minmax(0,1fr) minmax(340px,410px)', alignItems: 'start' }}>
      {/* 좌: 제출 현황 */}
      <div className="card" style={{ position: 'sticky', top: 76 }}>
        <div className="pad" style={{ paddingBottom: 10 }}><div className="sec-t" style={{ margin: 0 }}>제출 서류 <small>{r.slots.filter((s: any) => s.file).length}/{r.slots.length}</small></div></div>
        {r.slots.map((s: any) => <SlotRow key={s.key} s={s} rid={rid} reload={reload} compact />)}
        <div className="pad xs muted" style={{ lineHeight: 1.6 }}>서류를 바꾸면 ‘다시 채점’을 누르세요.</div>
      </div>

      {/* 중: 서류 하이라이트 */}
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

      {/* 우: 점수 + 지적 */}
      <div className="grid" style={{ position: 'sticky', top: 76 }}>
        <div className="card pad">
          <div className="row" style={{ gap: 18 }}>
            <Ring value={sc.score} label="/ 100점" frac={sc.score / 100} color={color} size={118} />
            <div className="small" style={{ flex: 1 }}>
              <div className="muted xs">모의 점수 = 100 − 총 감점</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', rowGap: 4, marginTop: 8 }}>
                <span>사례 감점</span><b className="num" style={{ color: 'var(--red)' }}>−{t.case_points}</b>
                <span>경고 감점 <span className="xs muted">({t.warnings}회)</span></span><b className="num" style={{ color: 'var(--amber)' }}>−{t.warning_points}</b>
              </div>
              {pending > 0 && <div className="xs" style={{ marginTop: 8, color: 'var(--amber-ink)', lineHeight: 1.5 }}>미확정 {pending}건(확인 필요 {t.pending_check} · 신규 유형 {t.pending_new})은 아직 점수에 반영되지 않았어요</div>}
            </div>
          </div>
          <div style={{ display: 'flex', height: 8, borderRadius: 999, overflow: 'hidden', background: 'var(--gray-soft)', marginTop: 14 }}>
            {(['충족', '미충족', '확인 필요'] as const).map((k) => <i key={k} style={{ width: `${((t.by_verdict[k] ?? 0) / t.clauses) * 100}%`, background: VERDICT[k].color }} />)}
          </div>
          <div className="row xs muted" style={{ gap: 12, marginTop: 6 }}>
            {(['충족', '미충족', '확인 필요'] as const).map((k) => <span key={k}>{k} <b style={{ color: 'var(--ink)' }}>{t.by_verdict[k] ?? 0}</b></span>)}
            <span className="sp" /><span>{t.clauses}개 조항</span>
          </div>
        </div>

        <div className="card" style={{ padding: 6 }}>
          <div className="row" style={{ justifyContent: 'space-between', padding: '8px 10px 6px' }}>
            <b className="small">{packet.title} · 판정 {all.filter((f) => f.packet === pid).length}건</b>
            <div className="seg"><button className={onlyIssues ? 'on' : ''} onClick={() => setOnlyIssues(true)}>지적만</button><button className={!onlyIssues ? 'on' : ''} onClick={() => setOnlyIssues(false)}>전체</button></div>
          </div>
          <div style={{ maxHeight: 250, overflow: 'auto' }}>
            {list.length === 0 && <div className="empty small">지적 사항이 없습니다.</div>}
            {list.map((f) => {
              const vk = vkey(f)
              const msg = f.checks.map((c: string) => checksBy[c]?.message).find(Boolean)
              return (
                <button key={f.id} onClick={() => setSel(f.id)} style={{ all: 'unset', cursor: 'pointer', display: 'grid', gridTemplateColumns: '22px 1fr auto', gap: 10, padding: 12, borderRadius: 10, width: '100%', boxSizing: 'border-box', background: sel === f.id ? '#f6f8fc' : undefined, outline: sel === f.id ? '1px solid var(--line)' : undefined }}>
                  <span style={{ width: 22, height: 22, borderRadius: 6, background: VERDICT[vk]?.color, color: '#fff', fontSize: 11, fontWeight: 800, display: 'grid', placeItems: 'center' }}>{issueNo[f.id] ?? '✓'}</span>
                  <span>
                    <span style={{ display: 'block', fontSize: 13.5, fontWeight: 700, lineHeight: 1.4 }}>{headline(f, titles, msg)}</span>
                    <span className="xs muted">{f.clause} · {titles[f.clause] ?? ''}{f.confirmed && ' · 확정됨'}</span>
                  </span>
                  {f.verdict === '충족' ? <Verdict v="충족" /> : <Disp d={f.disposition} verdict={f.verdict} />}
                </button>
              )
            })}
          </div>
        </div>
        {cur && <Detail f={cur} data={data} titles={titles} checksBy={checksBy} base={`/records/${rid}`} reload={() => { setAdvance(true); reload() }} />}
      </div>
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
