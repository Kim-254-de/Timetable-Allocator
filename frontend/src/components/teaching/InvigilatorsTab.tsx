import { useState } from 'react'
import clsx from 'clsx'
import { errorMessage } from '@/lib/api'
import {
  useInvigilationBoard,
  usePublishInvigilators,
  useSetInvigilator,
  type InvigilationBoard,
  type InvigilationRow,
} from '@/lib/form'

const when = (p: InvigilationRow) =>
  p.date ? `${new Date(`${p.date}T00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })} ${p.start_time}–${p.end_time}` : 'Not placed'

/**
 * Invigilators on the exam draft the Director shared: one per paper, who
 * administers it and takes the scripts away. Anyone on any department's list
 * can be named; one person is never in two places in a session.
 */
export function InvigilatorsTab({ code, term }: { code: string; term: string | undefined }) {
  const board = useInvigilationBoard(code, term)
  const publish = usePublishInvigilators(code, term)

  if (board.isPending) return <p className="text-sm text-muted">Loading invigilators…</p>
  if (board.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(board.error)}</p>
  const data = board.data
  if (!data.draft) {
    return <p className="text-sm text-muted">The Director hasn't shared an exam draft yet. Your papers' dates, sessions and rooms will show here, to name invigilators.</p>
  }
  const named = data.papers.filter((p) => p.invigilator_id).length

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">
          {data.draft.name} · {named} of {data.papers.length} papers have an invigilator
          {data.published && data.publication && ` · published on ${new Date(data.publication.published_at).toLocaleDateString()}`}
        </p>
        {data.can_publish && (
          data.published ? (
            <button onClick={() => publish.mutate('reopen')} disabled={publish.isPending} className="rounded-md border border-line bg-card px-3 py-2 text-sm">Reopen invigilators</button>
          ) : (
            <button onClick={() => publish.mutate('publish')} disabled={publish.isPending || data.problems.length > 0}
              title={data.problems.length ? 'Name an invigilator for every paper first' : undefined}
              className="rounded-md bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50">Publish invigilators</button>
          )
        )}
      </div>
      {publish.isError && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(publish.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Paper</th><th className="px-3 py-2">When</th><th className="px-3 py-2">Rooms</th><th className="px-3 py-2">Invigilator</th></tr>
          </thead>
          <tbody>
            {data.papers.map((p) => <Row key={p.paper_id} code={code} term={term} board={data} paper={p} />)}
            {data.papers.length === 0 && <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">No papers.</td></tr>}
          </tbody>
        </table>
      </div>
      <Duties board={data} />
    </section>
  )
}

function Row({ code, term, board, paper }: { code: string; term: string | undefined; board: InvigilationBoard; paper: InvigilationRow }) {
  const save = useSetInvigilator(code, term)
  const [others, setOthers] = useState(Boolean(paper.invigilator_department && paper.invigilator_department !== board.department.code))
  const choices = board.lecturers.filter((x) => others || x.own || x.id === paper.invigilator_id)
  return (
    <tr className={clsx('border-t border-line align-top', !paper.invigilator_id && 'bg-warning-soft')}>
      <td className="px-3 py-2"><span className="font-medium">{paper.codes}</span><span className="block text-xs text-muted">{paper.title}</span></td>
      <td className="px-3 py-2 whitespace-nowrap">{when(paper)}</td>
      <td className="px-3 py-2 text-xs">{paper.rooms.join(', ')}</td>
      <td className="px-3 py-2">
        {board.can_edit ? (
          <div className="space-y-1">
            <select aria-label={`Invigilator for ${paper.codes}`} value={paper.invigilator_id ?? ''} disabled={save.isPending || !paper.date}
              onChange={(e) => save.mutate({ paperId: paper.paper_id, lecturerId: e.target.value || null })}
              className="w-full rounded-md border border-line px-2 py-1">
              <option value="">Not named</option>
              {choices.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.display}{x.own ? '' : ` · ${x.department_code}`} ({x.duties}{x.max_exam_duties ? ` of ${x.max_exam_duties}` : ''} duties)
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs text-muted">
              <input type="checkbox" checked={others} onChange={(e) => setOthers(e.target.checked)} /> Show other departments' lecturers
            </label>
            {save.isError && <p role="alert" className="text-xs text-danger">{errorMessage(save.error)}</p>}
          </div>
        ) : (
          paper.invigilator ?? <span className="text-warning">Not named</span>
        )}
      </td>
    </tr>
  )
}

/** Duties per lecturer on the department's list, across every department, so they are shared fairly. */
function Duties({ board }: { board: InvigilationBoard }) {
  const own = board.lecturers.filter((x) => x.own).sort((a, b) => b.duties - a.duties)
  if (own.length === 0) return null
  return (
    <details className="rounded-lg border border-line bg-card px-3 py-2 text-sm">
      <summary className="cursor-pointer font-medium">Duties per lecturer</summary>
      <ul className="mt-2 grid gap-1 sm:grid-cols-2">
        {own.map((x) => (
          <li key={x.id} className="flex justify-between">
            <span>{x.display}</span>
            <span className={clsx(x.max_exam_duties && x.duties >= x.max_exam_duties ? 'text-warning' : 'text-muted')}>
              {x.duties}{x.max_exam_duties ? ` of ${x.max_exam_duties}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}
