import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { errorMessage } from '@/lib/api'
import { useFormProgress } from '@/lib/form'
import { useMe } from '@/lib/queries'

/** Every department's teaching for the term: the Directorate sees all, others their own. */
export function FormProgressPage() {
  const me = useMe()
  const [search] = useSearchParams()
  const term = search.get('term') || undefined
  const progress = useFormProgress(term)
  const suffix = term ? `?term=${encodeURIComponent(term)}` : ''

  if (progress.isPending) return <p className="text-sm text-muted">Loading…</p>
  if (progress.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(progress.error)}</p>
  const rows = progress.data.departments
  // A member of one department goes straight to it.
  if (!me.data?.timetabling_office && rows.length === 1) return <Navigate to={`/teaching/${encodeURIComponent(rows[0].code)}${suffix}`} replace />
  const published = rows.filter((d) => d.published).length

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Departments' teaching</h1>
        <p className="text-sm text-muted">{progress.data.term.name} · {published} of {rows.length} published to the Director</p>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Department</th><th className="px-3 py-2">Units</th>
              <th className="px-3 py-2">Groups with a lecturer</th><th className="px-3 py-2">Published</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.code} className="border-t border-line">
                <td className="px-3 py-2">
                  <Link to={`/teaching/${encodeURIComponent(d.code)}${suffix}`} className="font-medium text-brand-ink">{d.name}</Link>
                </td>
                <td className="px-3 py-2">{d.units}</td>
                <td className="px-3 py-2">{d.with_lecturer} of {d.groups}</td>
                <td className="px-3 py-2">
                  {d.published && d.publication ? (
                    <span className="text-success">{new Date(d.publication.published_at).toLocaleDateString()} by {d.publication.published_by}</span>
                  ) : d.publication?.reopened_at ? (
                    <span className="text-warning">Reopened</span>
                  ) : (
                    <span className="text-muted">Not yet</span>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">No departments.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
