import { NavLink, Navigate, Outlet, Route, Routes, useLocation, useParams } from 'react-router-dom'
import clsx from 'clsx'
import { AxiosError } from 'axios'
import { errorMessage } from '@/lib/api'
import { useLogout, useMe } from '@/lib/queries'
import { TeachingPage } from '@/pages/TeachingPage'
import { DepartmentPage } from '@/pages/DepartmentPage'
import { FormProgressPage } from '@/pages/FormProgressPage'
import { LoginPage } from '@/pages/LoginPage'
import { ProgressPage } from '@/pages/ProgressPage'
import { ThemeToggle } from '@/components/ThemeToggle'

export function App() {
  const me = useMe()
  if (me.isPending) return <p className="p-8 text-sm text-muted">Loading…</p>
  const unauthenticated = me.isError && me.error instanceof AxiosError && me.error.response?.status === 401
  if (unauthenticated || me.data === null) return <LoginPage />
  if (me.isError) return <p role="alert" className="p-8 text-sm text-danger">{errorMessage(me.error)}</p>

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<FormProgressPage />} />
        <Route path="teaching/:code" element={<TeachingPage />} />
        <Route path="form/:code" element={<FormRedirect />} />
        {/* The earlier board over SMARTTT's sections, kept for when SMARTTT's allocation endpoints are live. */}
        <Route path="departments/:departmentId" element={<DepartmentPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function Layout() {
  const me = useMe()
  const logout = useLogout()

  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b-2 border-gold-500 bg-topbar text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <span className="font-semibold">Timetable Allocator</span>
          <nav className="flex flex-wrap gap-1 text-sm">
            <NavLink to="/" end
              className={({ isActive }) => clsx('rounded px-2 py-1', isActive ? 'bg-white/15 text-white' : 'text-brand-100 hover:text-white')}>
              Departments
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <ThemeToggle />
            <span className="text-brand-100">{me.data?.full_name}</span>
            <button onClick={() => logout.mutate()} className="font-medium text-gold-500 hover:underline">Sign out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

/** Old links to a department's allocation form open its page. */
function FormRedirect() {
  const { code = '' } = useParams()
  const { search } = useLocation()
  return <Navigate to={`/teaching/${encodeURIComponent(code)}${search}`} replace />
}
