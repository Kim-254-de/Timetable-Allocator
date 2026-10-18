import { Link, useSearchParams } from 'react-router-dom'
import { errorMessage } from '@/lib/api'
import { dateTime, termText } from '@/lib/format'
import { useMe, useProgress } from '@/lib/queries'

/** The Directorate's view: which departments have allocated and submitted. */
export function ProgressPage() {
  const me = useMe()
  const [search] = useSearchParams()
  const term = search.get('term') ?? undefined
  const progress = useProgress(term, Boolean(me.data?.timetabling_office))

  if (!me.data?.timetabling_office) {
    return <p className="text-sm text-slate-600">Only the Directorate of Examinations and Timetabling sees this page.</p>
  }
  if (progress.isPending) return <p className="text-sm text-slate-500">Loading every department…</p>
  if (progress.isError) return <p role="alert" className="text-sm text-red-700">{errorMessage(progress.error)}</p>

  const rows = progress.data.departments
  const outstanding = rows.filter((r) => !r.submission?.is_current)

  return (
    <div className="space-y-4">
      <div>
        {progress.data.term && <p className="text-sm text-slate-600">{termText(progress.data.term)}</p>}
        <h1 className="text-lg font-semibold">
          {rows.length - outstanding.length} of {rows.length} departments have submitted
        </h1>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Department</th>
              <th className="px-3 py-2">Allocated</th>
              <th className="px-3 py-2">Outstanding</th>
              <th className="px-3 py-2">Conflicts</th>
              <th className="px-3 py-2">Submitted</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.department.id} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  <Link to={`/departments/${r.department.id}${term ? `?term=${term}` : ''}`} className="font-medium text-emerald-800">
                    {r.department.name}
                  </Link>
                  <span className="block text-xs text-slate-500">{r.department.cod?.full_name ?? 'No COD recorded'}</span>
                </td>
                <td className="px-3 py-2">{r.allocated} / {r.sections}</td>
                <td className="px-3 py-2">{r.outstanding}</td>
                <td className="px-3 py-2">{r.conflicts}</td>
                <td className="px-3 py-2">
                  {r.submission?.is_current ? dateTime(r.submission.submitted_at)
                    : r.submission ? 'Changed since submitting' : 'Not yet'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
