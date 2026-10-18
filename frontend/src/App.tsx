import { NavLink, Navigate, Outlet, Route, Routes, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { AxiosError } from 'axios'
import { errorMessage } from '@/lib/api'
import { termText } from '@/lib/format'
import { useDepartments, useLogout, useMe, useTerms } from '@/lib/queries'
import { DepartmentPage } from '@/pages/DepartmentPage'
import { LoginPage } from '@/pages/LoginPage'
import { ProgressPage } from '@/pages/ProgressPage'

export function App() {
  const me = useMe()
  if (me.isPending) return <p className="p-8 text-sm text-slate-500">Loading…</p>
  const unauthenticated = me.isError && me.error instanceof AxiosError && me.error.response?.status === 401
  if (unauthenticated || me.data === null) return <LoginPage />
  if (me.isError) return <p role="alert" className="p-8 text-sm text-red-700">{errorMessage(me.error)}</p>

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="departments/:departmentId" element={<DepartmentPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function Home() {
  const me = useMe()
  if (me.data?.timetabling_office) return <Navigate to="/progress" replace />
  const first = me.data?.departments[0]
  return first ? <Navigate to={`/departments/${first.id}`} replace /> : null
}

function Layout() {
  const me = useMe()
  const departments = useDepartments()
  const terms = useTerms()
  const logout = useLogout()
  const [search, setSearch] = useSearchParams()
  const term = search.get('term') ?? ''
  const suffix = term ? `?term=${term}` : ''

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <span className="font-semibold text-emerald-800">Timetable Allocator</span>
          <nav className="flex flex-wrap gap-1 text-sm">
            {me.data?.timetabling_office && (
              <NavLink to={`/progress${suffix}`}
                className={({ isActive }) => clsx('rounded px-2 py-1', isActive ? 'bg-emerald-50 text-emerald-800' : 'text-slate-600')}>
                All departments
              </NavLink>
            )}
            {(me.data?.timetabling_office ? [] : departments.data ?? []).map((d) => (
              <NavLink key={d.id} to={`/departments/${d.id}${suffix}`}
                className={({ isActive }) => clsx('rounded px-2 py-1', isActive ? 'bg-emerald-50 text-emerald-800' : 'text-slate-600')}>
                {d.name}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <select aria-label="Term" value={term}
              onChange={(e) => setSearch(e.target.value ? { term: e.target.value } : {})}
              className="rounded-md border border-slate-300 px-2 py-1">
              <option value="">Current term</option>
              {terms.data?.map((t) => <option key={t.id} value={t.id}>{termText(t)}</option>)}
            </select>
            <span className="text-slate-600">{me.data?.full_name}</span>
            <button onClick={() => logout.mutate()} className="text-emerald-700">Sign out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
