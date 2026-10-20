import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { errorMessage } from '@/lib/api'
import { useFormProgress } from '@/lib/form'
import { useMe } from '@/lib/queries'

/** Every department's allocation form for the term: the Directorate sees all, others their own. */
export function FormProgressPage() {
  const me = useMe()
  const [search] = useSearchParams()
  const term = search.get('term') || undefined
  const progress = useFormProgress(term)
  const suffix = term ? `?term=${encodeURIComponent(term)}` : ''

  if (progress.isPending) return <p className="text-sm text-muted">Loading…</p>
  if (progress.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(progress.error)}</p>
  const rows = progress.data.departments
  // A member of one department goes straight to its form.
  if (!me.data?.timetabling_office && rows.length === 1) return <Navigate to={`/form/${encodeURIComponent(rows[0].code)}${suffix}`} replace />

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Course allocation</h1>
        <p className="text-sm text-muted">{progress.data.term.name}</p>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Department</th><th className="px-3 py-2">Allocated</th><th className="px-3 py-2">Submitted</th></tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.code} className="border-t border-line">
                <td className="px-3 py-2">
                  <Link to={`/form/${encodeURIComponent(d.code)}${suffix}`} className="font-medium text-brand-ink">{d.name}</Link>
                </td>
                <td className="px-3 py-2">{d.allocated} of {d.classes}</td>
                <td className="px-3 py-2 text-muted">
                  {d.submitted_at ? `${new Date(d.submitted_at).toLocaleDateString()} by ${d.submitted_by}` : 'Not yet'}
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={3} className="px-3 py-6 text-center text-muted">No departments.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
