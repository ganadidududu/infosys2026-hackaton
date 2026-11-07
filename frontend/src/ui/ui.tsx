/* eslint-disable @typescript-eslint/no-explicit-any */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api'

// ---------- 판정 색 ----------
export const VERDICT: Record<string, { cls: string; mark: string; color: string }> = {
  충족: { cls: 't-g', mark: 'g', color: 'var(--green)' },
  미충족: { cls: 't-r', mark: 'r', color: 'var(--red)' },
  '확인 필요': { cls: 't-a', mark: 'a', color: 'var(--amber)' },
  '신규 유형': { cls: 't-v', mark: 'v', color: 'var(--violet)' },
}

export function Verdict({ v }: { v: string }) {
  return <span className={`tag ${VERDICT[v]?.cls ?? 't-n'}`}>{v}</span>
}

export function Disp({ d, verdict }: { d: any; verdict?: string }) {
  if (verdict === '확인 필요') return <span className="tag t-a">확인 필요</span>
  if (verdict === '충족' || !d) return <span className="tag t-n">처분 없음</span>
  if (d.type === '감점') return <span className="tag t-r">−{d.points}점</span>
  if (d.type === '경고') return <span className="tag t-a">경고</span>
  if (d.type === '신규 유형') return <span className="tag t-v">신규 유형 · 논의</span>
  return <span className="tag t-n">없음</span>
}

// ---------- 조항 칩 + 원문 서랍 (리드레이식 근거 보기) ----------
const ClauseCtx = createContext<(cid: string, hl?: string) => void>(() => {})
export const useClause = () => useContext(ClauseCtx)

export function ClauseProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState<{ cid: string; hl?: string } | null>(null)
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    if (!open) return
    setData(null)
    api(`/kijun/${encodeURIComponent(open.cid)}`).then(setData).catch(() => setData({ error: true }))
  }, [open])
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(null)
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])
  return (
    <ClauseCtx.Provider value={(cid, hl) => setOpen({ cid, hl })}>
      {children}
      {open && (
        <>
          <div className="scrim" onClick={() => setOpen(null)} />
          <aside className="drawer" role="dialog" aria-label="기준안 원문">
            <header>
              <div>
                <div className="xs muted">한양대학교 정보시스템학과 감사기준안 · 26.09.30. 개정</div>
                <h3 style={{ fontSize: 18, marginTop: 4 }}>{open.cid} {data?.title && <span className="muted" style={{ fontWeight: 500, fontSize: 14 }}>· {data.title}</span>}</h3>
              </div>
              <button className="btn ghost" onClick={() => setOpen(null)} aria-label="닫기">✕</button>
            </header>
            <div className="body">
              {!data ? <div className="muted">불러오는 중…</div> : data.error ? <div className="muted">원문을 찾지 못했습니다.</div> : (
                <>
                  <div className="orig"><Orig text={data.full} item={open.cid.match(/[①-⑩]$/)?.[0]} /></div>
                  <p className="xs muted" style={{ marginTop: 12, lineHeight: 1.6 }}>
                    PDF에서 자동 추출한 원문입니다. 줄바꿈 위치의 띄어쓰기가 원문과 다를 수 있으니 공식 인용은 원본 PDF와 대조하세요.
                  </p>
                </>
              )}
            </div>
          </aside>
        </>
      )}
    </ClauseCtx.Provider>
  )
}

function Orig({ text, item }: { text: string; item?: string }) {
  const parts = text.split(/(?=[①-⑩])/)
  return <>{parts.map((p, i) => <span key={i} className={i ? 'it' : ''}><span className={item && p.startsWith(item) ? 'hl' : ''}>{p}</span></span>)}</>
}

export function Cite({ c }: { c: string }) {
  const open = useClause()
  return <button className="cite" onClick={(e) => { e.stopPropagation(); open(c) }}>{c}</button>
}

// ---------- 토스트 ----------
const ToastCtx = createContext<(m: string, err?: boolean) => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ m: string; err?: boolean } | null>(null)
  useEffect(() => { if (t) { const h = setTimeout(() => setT(null), 2600); return () => clearTimeout(h) } }, [t])
  return <ToastCtx.Provider value={(m, err) => setT({ m, err })}>{children}{t && <div className={`toast ${t.err ? 'err' : ''}`}>{t.m}</div>}</ToastCtx.Provider>
}

// ---------- 링 (카피킬러 결과 숫자) ----------
export function Ring({ value, label, frac, color = 'var(--red)', size = 112 }: { value: ReactNode; label: string; frac: number; color?: string; size?: number }) {
  const inner = size - 24
  return (
    <div style={{ width: size, height: size, borderRadius: '50%', display: 'grid', placeItems: 'center', flexShrink: 0,
      background: `conic-gradient(${color} 0 ${Math.min(1, frac) * 100}%, var(--gray-soft) 0 100%)` }}>
      <div style={{ width: inner, height: inner, borderRadius: '50%', background: '#fff', display: 'grid', placeItems: 'center', textAlign: 'center' }}>
        <div><b style={{ fontSize: size * 0.3, letterSpacing: -1, lineHeight: 1 }}>{value}</b><br /><small className="xs muted">{label}</small></div>
      </div>
    </div>
  )
}

export function Loading() { return <div className="empty"><span className="spin" /> 불러오는 중…</div> }
export function ErrorBox({ msg }: { msg: string }) {
  return <div className="card pad" style={{ borderColor: 'var(--red)' }}><b>백엔드에 연결하지 못했습니다.</b><div className="small muted" style={{ marginTop: 6 }}>{msg} · backend 폴더에서 <code>uvicorn app.main:app --port 8000</code>을 실행했는지 확인하세요.</div></div>
}
