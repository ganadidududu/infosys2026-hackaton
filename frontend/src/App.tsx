import { BrowserRouter, Link, Navigate, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { ClauseProvider, ToastProvider } from './ui/ui'
import { api, useApi } from './api'
import Statement from './admin/Statement'
import Checklist from './admin/Checklist'
import Grade from './admin/Grade'
import GradeRecord from './admin/GradeRecord'
import Report from './admin/Report'
import Kijun from './admin/Kijun'

// 상단 탭은 3개로 고정
const NAV = [
  ['/statement', '(수입·지출) 내역서'],
  ['/schedule', '학기 스케줄러'],
  ['/grade', '모의 채점'],
] as const

// 예전 주소(/admin/...)로 들어오면 같은 화면의 새 주소로
function OldAdminUrl() {
  const { pathname, search } = useLocation()
  return <Navigate to={(pathname.replace(/^\/admin/, '') || '/') + search} replace />
}

function AdminLayout() {
  const { data: meta } = useApi('/meta')
  async function resetMine() {
    if (!confirm('내 공간의 영수증·장부·채점 기록을 모두 지우고 가상 데이터 처음 상태로 되돌릴까요? 다른 사람 데이터에는 영향이 없습니다.')) return
    await api('/reset', { method: 'POST' })
    location.reload()
  }
  return (
    <>
      <header className="top">
        <Link to="/" className="logo"><i>A</i>Auditon</Link>
        <nav className="nav">
          {NAV.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        </nav>
        <div className="sp" />
        {meta?.user && <button className="chip hide-m" title="내 데이터를 처음 상태로 되돌립니다" onClick={resetMine}>{meta.user} · 처음 상태로</button>}
      </header>
      <main className="page"><Outlet /></main>
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <ClauseProvider>
          <Routes>
            <Route path="/admin/*" element={<OldAdminUrl />} />
            <Route path="/" element={<AdminLayout />}>
              <Route index element={<Navigate to="/statement" replace />} />
              <Route path="statement" element={<Statement />} />
              <Route path="schedule" element={<Checklist />} />
              <Route path="grade" element={<Grade />} />
              <Route path="grade/:rid" element={<GradeRecord />} />
              <Route path="report" element={<Report />} />
              <Route path="kijun" element={<Kijun />} />
              <Route path="*" element={<Navigate to="/statement" replace />} />
            </Route>
          </Routes>
        </ClauseProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
