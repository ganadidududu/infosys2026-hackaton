import { BrowserRouter, Link, Navigate, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { useApi } from './api'
import { ClauseProvider, ToastProvider } from './ui/ui'
import Statement from './admin/Statement'
import Checklist from './admin/Checklist'
import Grade from './admin/Grade'
import GradeRecord from './admin/GradeRecord'
import Report from './admin/Report'
import Kijun from './admin/Kijun'
import PublicList from './public/PublicList'
import PublicDept from './public/PublicDept'

// 상단 탭은 3개로 고정
const NAV = [
  ['/admin/statement', '(수입·지출) 내역서'],
  ['/admin/schedule', '학기 스케줄러'],
  ['/admin/grade', '모의 채점'],
] as const

function AdminLayout() {
  const { data: meta } = useApi('/meta')
  return (
    <>
      <header className="top">
        <Link to="/admin" className="logo"><i>A</i>Auditon</Link>
        <nav className="nav">
          {NAV.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        </nav>
        <div className="sp" />
        {meta && <span className={`chip ${meta.llm_mode === 'live' ? 'live' : 'demo'} hide-m`}>{meta.llm_mode === 'live' ? 'LLM 라이브' : 'LLM 재생 모드'} · 가상 데이터</span>}
        {meta && <span className="chip hide-m">{meta.dept} · {meta.period.label}</span>}
        <Link to="/admin/kijun" className="chip hide-m">기준안·선례</Link>
        <Link to="/" className="chip" style={{ background: 'var(--ink)', color: '#fff' }}>학생 공개 페이지 ↗</Link>
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
            <Route path="/" element={<PublicList />} />
            <Route path="/d/:dept" element={<PublicDept />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<Navigate to="/admin/statement" replace />} />
              <Route path="statement" element={<Statement />} />
              <Route path="schedule" element={<Checklist />} />
              <Route path="grade" element={<Grade />} />
              <Route path="grade/:rid" element={<GradeRecord />} />
              <Route path="report" element={<Report />} />
              <Route path="kijun" element={<Kijun />} />
              <Route path="*" element={<Navigate to="/admin/statement" replace />} />
            </Route>
          </Routes>
        </ClauseProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
