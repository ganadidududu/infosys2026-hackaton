import { BrowserRouter, Link, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import { useApi } from './api'
import { ClauseProvider, ToastProvider } from './ui/ui'
import Dashboard from './admin/Dashboard'
import Checklist from './admin/Checklist'
import Receipts from './admin/Receipts'
import Reconcile from './admin/Reconcile'
import AuditResult from './admin/AuditResult'
import Report from './admin/Report'
import Kijun from './admin/Kijun'
import PublicList from './public/PublicList'
import PublicDept from './public/PublicDept'

const NAV = [
  ['/admin/checklist', '체크리스트', 1],
  ['/admin/receipts', '영수증함', 2],
  ['/admin/reconcile', '대사·감사자료', 3],
  ['/admin/audit', '감사 결과지', 4],
  ['/admin/report', '보고서·공시', 5],
] as const

function AdminLayout() {
  const { data: meta } = useApi('/meta')
  return (
    <>
      <header className="top">
        <Link to="/admin" className="logo"><i>A</i>Auditon</Link>
        <nav className="nav">
          {NAV.map(([to, label, n]) => (
            <NavLink key={to} to={to}><span className="step">{n}</span>{label}</NavLink>
          ))}
          <NavLink to="/admin/kijun">기준안·선례</NavLink>
        </nav>
        <div className="sp" />
        {meta && <span className={`chip ${meta.llm_mode === 'live' ? 'live' : 'demo'} hide-m`}>{meta.llm_mode === 'live' ? 'LLM 라이브' : 'LLM 재생 모드'} · 가상 데이터</span>}
        {meta && <span className="chip hide-m">{meta.dept} · {meta.period.label}</span>}
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
              <Route index element={<Dashboard />} />
              <Route path="checklist" element={<Checklist />} />
              <Route path="receipts" element={<Receipts />} />
              <Route path="reconcile" element={<Reconcile />} />
              <Route path="audit" element={<AuditResult />} />
              <Route path="report" element={<Report />} />
              <Route path="kijun" element={<Kijun />} />
            </Route>
          </Routes>
        </ClauseProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
