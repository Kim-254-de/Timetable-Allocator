import { useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download } from 'lucide-react'
import { AllocatePanel } from '@/components/AllocatePanel'
import { AvailabilityEditor } from '@/components/AvailabilityEditor'
import { errorBody, errorMessage } from '@/lib/api'
import { classRowText, dateTime, employment, meetingText, termText } from '@/lib/format'
import { exportUrl, useBoard, useDepartmentLecturers, useSubmit } from '@/lib/queries'
import type { DepartmentLecturer, Section, SectionState } from '@/lib/types'

const STATE_LABEL: Record<SectionState, string> = {
  allocated: 'Allocated',
  outstanding: 'To allocate',
  unmatched: 'Name only',
  conflict: 'Conflict',
}
const STATE_STYLE: Record<SectionState, string> = {
  allocated: 'bg-emerald-100 text-emerald-800',
  outstanding: 'bg-amber-100 text-amber-900',
  unmatched: 'bg-sky-100 text-sky-900',
  conflict: 'bg-red-100 text-red-800',
}

type Filter = 'all' | 'todo' | 'attention' | 'servicing'

const ATTENTION_LABEL: Record<Section['attention'][number], string> = {
  time_or_room_changed: 'Time or room changed since allocation',
  lecturer_cleared: 'Lecturer no longer on this class',
  lecturer_changed: 'Lecturer changed outside the Allocator',
}

export function DepartmentPage() {
  const departmentId = Number(useParams().departmentId)
  const [search] = useSearchParams()
  const term = search.get('term') ?? undefined
  const [tab, setTab] = useState<'classes' | 'lecturers'>('classes')

  return (
    <div className="space-y-4">
      <div className="flex gap-2 border-b border-slate-200">
        {(['classes', 'lecturers'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={clsx('-mb-px border-b-2 px-3 py-2 text-sm font-medium',
              tab === t ? 'border-emerald-700 text-emerald-800' : 'border-transparent text-slate-600')}>
            {t === 'classes' ? 'Classes' : 'Lecturers'}
          </button>
        ))}
      </div>
      {tab === 'classes'
        ? <ClassesTab departmentId={departmentId} term={term} />
        : <LecturersTab departmentId={departmentId} term={term} />}
    </div>
  )
}

function ClassesTab({ departmentId, term }: { departmentId: number; term: string | undefined }) {
  const board = useBoard(departmentId, term)
  const submit = useSubmit(departmentId, term)
  const [selected, setSelected] = useState<Section | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')

  const sections = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (board.data?.sections ?? []).filter((s) => {
      if (filter === 'todo' && s.state === 'allocated') return false
      if (filter === 'servicing' && !s.servicing) return false
      if (filter === 'attention' && s.attention.length === 0) return false
      return !q || s.code.toLowerCase().includes(q) || s.unit.name.toLowerCase().includes(q)
        || (s.lecturer?.full_name.toLowerCase().includes(q) ?? false)
    })
  }, [board.data, filter, query])

  if (board.isPending) return <p className="text-sm text-slate-500">Loading the published timetable…</p>
  if (board.isError) return <p role="alert" className="text-sm text-red-700">{errorMessage(board.error)}</p>
  const { summary, submission } = board.data
  const pending = (errorBody(submit.error)?.details as { sections?: string[] } | undefined)?.sections

  return (
    <>
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <div>
          <p className="text-sm text-slate-600">{termText(board.data.term)}</p>
          <p className="text-lg font-semibold">
            {summary.allocated} of {summary.sections} classes allocated
            {summary.conflicts > 0 && <span className="ml-2 text-sm text-red-700">{summary.conflicts} conflicts</span>}
            {(summary.needs_attention ?? 0) > 0 && (
              <span className="ml-2 text-sm text-amber-800">{summary.needs_attention} changed by the new timetable</span>
            )}
          </p>
          <p className="text-sm text-slate-600">
            {submission?.is_current
              ? `Submitted by ${submission.submitted_by} on ${dateTime(submission.submitted_at)}`
              : submission ? 'Changed since it was submitted — submit again' : 'Not submitted yet'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a href={exportUrl(departmentId, term)}
            className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-3 py-2 text-sm">
            <Download size={16} /> Allocation form (PDF)
          </a>
          {board.data.can_submit && (
            <button onClick={() => submit.mutate()} disabled={submit.isPending}
              className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {submit.isPending ? 'Submitting…' : 'Submit allocation'}
            </button>
          )}
        </div>
        {submit.isError && (
          <p role="alert" className="w-full text-sm text-red-700">
            {errorMessage(submit.error)} {pending && pending.slice(0, 10).join(', ')}
            {pending && pending.length > 10 && '…'}
          </p>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-2">
        {(['all', 'todo', 'attention', 'servicing'] as const).map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={clsx('rounded-full px-3 py-1 text-sm', filter === f ? 'bg-emerald-700 text-white' : 'bg-white border border-slate-200')}>
            {f === 'all' ? 'All' : f === 'todo' ? 'Still to allocate' : f === 'attention' ? 'Changed' : 'Servicing'}
          </button>
        ))}
        <input type="search" placeholder="Search code, title or lecturer" value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="ml-auto w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Class</th>
              <th className="px-3 py-2">Students</th>
              <th className="px-3 py-2">When and where</th>
              <th className="px-3 py-2">Lecturer</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {sections.map((s) => (
              <tr key={s.key} onClick={() => setSelected(s)}
                className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2">
                  <span className="font-medium">{s.code}</span>
                  {s.servicing && <span className="ml-2 rounded bg-violet-100 px-1.5 text-xs text-violet-800">servicing</span>}
                  <span className="block text-slate-600">{s.unit.name}</span>
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {s.class_rows.map(classRowText).join(', ')}
                  <span className="block text-xs">{s.registered_students} registered</span>
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {s.meetings.map((m) => <span key={`${m.day_of_week}${m.start_time}`} className="block">{meetingText(m)} · {m.room.code}</span>)}
                </td>
                <td className="px-3 py-2">
                  {s.lecturer
                    ? <>{s.lecturer.full_name} <span className="text-slate-500">{employment(s.lecturer.employment_type)}</span></>
                    : s.lecturer_name_text
                      ? <span className="text-sky-900">{s.lecturer_name_text}</span>
                      : <span className="text-slate-400">—</span>}
                </td>
                <td className="px-3 py-2">
                  <span className={clsx('rounded px-2 py-0.5 text-xs font-medium', STATE_STYLE[s.state])}>{STATE_LABEL[s.state]}</span>
                  {s.attention.map((a) => (
                    <span key={a} className="mt-1 block text-xs text-amber-800">{ATTENTION_LABEL[a]}</span>
                  ))}
                </td>
              </tr>
            ))}
            {sections.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-500">No classes match.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <AllocatePanel section={selected} departmentId={departmentId} term={term}
          canAllocate={board.data.can_allocate} onClose={() => setSelected(null)} />
      )}
    </>
  )
}

function LecturersTab({ departmentId, term }: { departmentId: number; term: string | undefined }) {
  const lecturers = useDepartmentLecturers(departmentId, term)
  const [editing, setEditing] = useState<DepartmentLecturer | null>(null)

  if (lecturers.isPending) return <p className="text-sm text-slate-500">Loading lecturers…</p>
  if (lecturers.isError) return <p role="alert" className="text-sm text-red-700">{errorMessage(lecturers.error)}</p>

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Lecturer</th>
              <th className="px-3 py-2">Load</th>
              <th className="px-3 py-2">Classes</th>
              <th className="px-3 py-2">Unavailable</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {lecturers.data.lecturers.map((l) => (
              <tr key={l.id} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  <span className="font-medium">{l.title ? `${l.title} ` : ''}{l.full_name}</span>
                  <span className="block text-xs text-slate-500">{l.staff_number} · {employment(l.employment_type)}</span>
                </td>
                <td className={clsx('px-3 py-2', (l.weekly_hours ?? 0) >= l.max_weekly_teaching_hours && 'text-amber-800')}>
                  {l.weekly_hours ?? 0} / {l.max_weekly_teaching_hours} h
                </td>
                <td className="px-3 py-2 text-slate-600">{l.classes.join(', ') || '—'}</td>
                <td className="px-3 py-2 text-slate-600">
                  {l.unavailable.map((p) => <span key={`${p.day_of_week}${p.start_time}`} className="block">{meetingText(p)}</span>)}
                  {l.unavailable.length === 0 && '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  <button onClick={() => setEditing(l)} className="text-sm text-emerald-700">Availability</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <AvailabilityEditor lecturer={editing} departmentId={departmentId} term={term} onClose={() => setEditing(null)} />
      )}
    </>
  )
}
