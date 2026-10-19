import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import clsx from 'clsx'
import { AxiosError } from 'axios'
import { errorMessage } from '@/lib/api'
import { useLogout, useMe } from '@/lib/queries'
import { AllocationFormPage } from '@/pages/AllocationFormPage'
import { DepartmentPage } from '@/pages/DepartmentPage'
import { FormProgressPage } from '@/pages/FormProgressPage'
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
        <Route index element={<FormProgressPage />} />
        <Route path="form/:code" element={<AllocationFormPage />} />
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
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <span className="font-semibold text-emerald-800">Timetable Allocator</span>
          <nav className="flex flex-wrap gap-1 text-sm">
            <NavLink to="/" end
              className={({ isActive }) => clsx('rounded px-2 py-1', isActive ? 'bg-emerald-50 text-emerald-800' : 'text-slate-600')}>
              Course allocation
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
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
