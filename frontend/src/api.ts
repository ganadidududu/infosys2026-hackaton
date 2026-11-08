/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from 'react'

// API 주소: 같은 서버면 비워 둔다. Cloudflare Pages에 화면만 올릴 때는 VITE_API_BASE=https://api.도메인
export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')
export const apiUrl = (p: string) => `${API_BASE}/api${p}`

// 로그인(Cloudflare Access)이 안 돼 있으면 API가 로그인 페이지로 돌려보낸다 → 화면 전체를 로그인으로 보냈다가 지금 화면으로 돌아온다.
// 10초 안에 또 돌려보내지면(쿠키 차단 등) 무한 반복 대신 오류를 보여 준다.
let leaving = false
function goLogin(): Promise<never> {
  if (leaving) return new Promise(() => {})  // 화면의 여러 요청이 동시에 걸려도 한 번만 이동
  const last = +(sessionStorage.getItem('auditon-login') ?? 0)
  if (Date.now() - last < 10_000) throw new Error('로그인이 필요합니다. 브라우저에서 쿠키를 허용한 뒤 새로고침하세요.')
  sessionStorage.setItem('auditon-login', String(Date.now()))
  leaving = true
  location.href = `${apiUrl('/login')}?next=${encodeURIComponent(location.pathname + location.search)}`
  return new Promise(() => {})
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any } = {}): Promise<T> {
  const r = await fetch(apiUrl(path), {
    method: opts.method ?? (opts.body ? 'POST' : 'GET'),
    headers: opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : undefined,
    body: opts.body ? (opts.body instanceof FormData ? opts.body : JSON.stringify(opts.body)) : undefined,
    redirect: 'manual',
  })
  if (r.type === 'opaqueredirect') return goLogin()
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}

export function useApi<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const reload = useCallback(async () => {
    if (!path) return
    setLoading(true)
    try { setData(await api<T>(path)); setError(null) } catch (e: any) { setError(e.message) }
    setLoading(false)
  }, [path])
  useEffect(() => { reload() }, [reload])
  return { data, error, loading, reload, setData }
}

export const won = (n: number | null | undefined) => (n == null ? '-' : n.toLocaleString('ko-KR'))
export const md = (iso?: string | null) => (iso ? `${+iso.slice(5, 7)}/${+iso.slice(8, 10)}` : '-')
