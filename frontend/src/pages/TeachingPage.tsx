import { Link, useParams, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download } from 'lucide-react'
import { CoursesTab } from '@/components/teaching/CoursesTab'
import { ExamsTab } from '@/components/teaching/ExamsTab'
import { LecturersTab } from '@/components/teaching/Lecturers'
import { UnitsTab } from '@/components/teaching/UnitsTab'
import { errorMessage } from '@/lib/api'
import { formExportUrl, meetingText, useFormBoard, useGeneratorTerms, usePublish, type FormBoard } from '@/lib/form'

const TABS = ['courses', 'units', 'lecturers', 'times', 'exams'] as const
type Tab = (typeof TABS)[number]

/**
 * One department's teaching for a term: its courses, units and groups (with
 * lecturers), and its lecturers. The COD publishes it to the Director, who
 * adds days, times and rooms; those then show on the Times tab and downloads.
 */
export function TeachingPage() {
  const { code = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const term = search.get('term') || undefined
  const tab: Tab = (TABS as readonly string[]).includes(search.get('tab') ?? '') ? (search.get('tab') as Tab) : 'units'
  const terms = useGeneratorTerms()
  const board = useFormBoard(code, term)
  const publish = usePublish(code, term)

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(search)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearch(Object.fromEntries(next))
  }

  if (board.isPending) return <p className="text-sm text-muted">Loading…</p>
  if (board.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(board.error)}</p>
  const data = board.data
  const counts: Record<Tab, number> = {
    courses: data.courses.length,
    units: data.units.length,
    lecturers: data.lecturers.length,
    times: data.summary.groups,
    exams: data.units.length,
  }
  const labels: Record<Tab, string> = { courses: 'Courses', units: 'Units & groups', lecturers: 'Lecturers', times: 'Times', exams: 'Exams' }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{data.department.name}</h1>
          <p className="text-sm text-muted">
            {data.term.name} · {data.summary.units} units, {data.summary.with_lecturer} of {data.summary.groups} groups with a lecturer
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select aria-label="Term" value={term ?? ''} onChange={(e) => setParam('term', e.target.value || null)}
            className="rounded-md border border-line px-2 py-2">
            <option value="">Latest term</option>
            {terms.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          {([['pdf', 'PDF'], ['docx', 'Word'], ['xlsx', 'Excel']] as const).map(([format, label]) => (
            <a key={format} href={formExportUrl(code, format, term)}
              className="inline-flex items-center gap-1 rounded-md border border-line bg-card px-3 py-2">
              <Download size={16} aria-hidden /> {label}
            </a>
          ))}
          {data.can_publish && (
            data.published ? (
              <button onClick={() => publish.mutate('reopen')} disabled={publish.isPending}
                className="rounded-md border border-line bg-card px-3 py-2">Reopen</button>
            ) : (
              <button onClick={() => publish.mutate('publish')} disabled={publish.isPending || data.problems.length > 0}
                title={data.problems.length > 0 ? 'Fix the items listed first' : undefined}
                className="rounded-md bg-brand px-4 py-2 font-medium text-white disabled:opacity-50">
                {publish.isPending ? 'Publishing…' : 'Publish to the Director'}
              </button>
            )
          )}
        </div>
      </div>

      <Status board={data} />
      {publish.isError && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(publish.error)}</p>}
      {!data.published && data.problems.length > 0 && (
        <details className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning" open={data.problems.length <= 5}>
          <summary className="cursor-pointer font-medium">
            {data.problems.length} {data.problems.length === 1 ? 'thing' : 'things'} to finish before publishing
          </summary>
          <ul className="mt-1 list-disc pl-5">
            {data.problems.map((p, i) => <li key={`${p.code}${i}`}>{p.message}</li>)}
          </ul>
        </details>
      )}
      {data.role == null && <p className="text-sm text-muted">You are viewing this department; only its COD and allocation staff can change it.</p>}

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button key={t} onClick={() => setParam('tab', t === 'units' ? null : t)}
            className={clsx('rounded-full px-3 py-1 text-sm', tab === t ? 'bg-brand text-white' : 'border border-line bg-card')}>
            {labels[t]}{t === 'exams' ? '' : ` (${counts[t]})`}
          </button>
        ))}
      </div>

      {tab === 'courses' && <CoursesTab code={code} term={term} board={data} />}
      {tab === 'units' && <UnitsTab code={code} term={term} board={data} />}
      {tab === 'lecturers' && <LecturersTab code={code} board={data} />}
      {tab === 'times' && <TimesTab board={data} />}
      {tab === 'exams' && <ExamsTab code={code} term={term} />}
      <p className="text-xs text-muted"><Link to="/" className="text-brand-ink">All departments</Link></p>
    </div>
  )
}

function Status({ board }: { board: FormBoard }) {
  const p = board.publication
  if (board.published && p) {
    return (
      <p role="status" className="rounded-md bg-success-soft px-3 py-2 text-sm text-success">
        Published to the Director by {p.published_by} on {new Date(p.published_at).toLocaleString()}.
        {board.can_publish ? ' Reopen it to make changes.' : ' The COD can reopen it.'}
      </p>
    )
  }
  if (p?.reopened_at) {
    return (
      <p role="status" className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
        Reopened by {p.reopened_by} on {new Date(p.reopened_at).toLocaleString()}. The Director still has the list published
        on {new Date(p.published_at).toLocaleDateString()}
        {board.summary.changed > 0 ? `; ${board.summary.changed} units changed since.` : '.'} Publish again when done.
      </p>
    )
  }
  return null
}

/** When and where each group meets, once the Director has published the timetable. */
function TimesTab({ board }: { board: FormBoard }) {
  if (board.times.error) return <p role="alert" className="text-sm text-danger">{board.times.error}</p>
  if (board.times.published_version == null) {
    return <p className="text-sm text-muted">The Director hasn't published the timetable yet. Each group's day, time and room will show here.</p>
  }
  const rows = board.units.flatMap((u) => u.groups.map((g) => ({ unit: u, group: g })))
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted">From version {board.times.published_version} of the timetable.</p>
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Class</th><th className="px-3 py-2">Lecturer</th><th className="px-3 py-2">Day, time & room</th></tr>
          </thead>
          <tbody>
            {rows.map(({ unit, group }) => (
              <tr key={group.id} className="border-t border-line align-top">
                <td className="px-3 py-2 font-medium whitespace-nowrap">{unit.code} {group.label}</td>
                <td className="px-3 py-2">{group.lecturer ?? '—'}</td>
                <td className="px-3 py-2">
                  {group.meetings.length ? group.meetings.map((m) => <div key={`${m.day_of_week}${m.start_time}`}>{meetingText(m)}</div>)
                    : <span className="text-warning">Not in the published timetable</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
