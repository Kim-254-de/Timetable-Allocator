import { useState, type FormEvent } from 'react'
import { errorMessage } from '@/lib/api'
import { useLogin } from '@/lib/queries'

export function LoginPage() {
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate({ identifier, password })
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Timetable Allocator</h1>
          <p className="mt-1 text-sm text-slate-600">Sign in with your SMARTTT staff account.</p>
        </div>
        <label className="block text-sm">
          <span className="font-medium text-slate-700">Staff ID or email</span>
          <input
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 focus:border-emerald-600 focus:outline-none"
            autoComplete="username"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium text-slate-700">Password</span>
          <input
            type="password"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 focus:border-emerald-600 focus:outline-none"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {login.isError && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {errorMessage(login.error)}
          </p>
        )}
        <button
          type="submit"
          disabled={login.isPending}
          className="w-full rounded-md bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
