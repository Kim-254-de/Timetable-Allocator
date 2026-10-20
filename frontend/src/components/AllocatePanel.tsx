import { useState } from 'react'
import clsx from 'clsx'
import { X } from 'lucide-react'
import { errorBody, errorMessage } from '@/lib/api'
import { classRowText, employment, meetingText } from '@/lib/format'
import { useCandidates, useSaveAllocation } from '@/lib/queries'
import type { Candidate, Section } from '@/lib/types'

interface Props {
  section: Section
  departmentId: number
  term: string | undefined
  canAllocate: boolean
  onClose: () => void
}

const toNumber = (value: string): number | null => (value.trim() === '' ? null : Number(value))

function reasons(c: Candidate): string[] {
  const out = c.clashes.map((x) => `Teaches ${x.clashes_with} ${meetingText(x)}`)
  out.push(...c.unavailable.map((u) => `Unavailable ${meetingText(u)}${u.reason ? ` (${u.reason})` : ''}`))
  if (c.over_limit) out.push(`Would teach ${c.weekly_hours_after} h/week (limit ${c.lecturer.max_weekly_teaching_hours})`)
  return out
}

export function AllocatePanel({ section, departmentId, term, canAllocate, onClose }: Props) {
  const [scope, setScope] = useState<'department' | 'all'>('department')
  const candidates = useCandidates(section.key, term, scope)
  const save = useSaveAllocation(departmentId, term)
  const current = section.lecturer?.id ?? null
  const [chosen, setChosen] = useState<string | null>(current)
  const [hours, setHours] = useState({
    lecture: section.allocation?.lecture_hours?.toString() ?? '',
    practical: section.allocation?.practical_hours?.toString() ?? '',
    cf: section.allocation?.cf_hours?.toString() ?? '',
  })

  const submit = (lecturerId: string | null) =>
    save.mutate(
      {
        key: section.key,
        body: {
          lecturer_id: lecturerId,
          expected_lecturer_id: current,
          lecture_hours: toNumber(hours.lecture),
          practical_hours: toNumber(hours.practical),
          cf_hours: toNumber(hours.cf),
        },
      },
      { onSuccess: onClose },
    )

  const failure = save.isError ? errorBody(save.error) : undefined
  const clashDetails = (failure?.details as { clashes?: { clashes_with: string }[] } | undefined)?.clashes

  return (
    <aside
      aria-label={`Allocate ${section.code}`}
      className="fixed inset-y-0 right-0 z-20 flex w-full max-w-xl flex-col border-l border-line bg-card shadow-xl"
    >
      <header className="flex items-start justify-between border-b border-line p-4">
        <div>
          <h2 className="text-lg font-semibold">{section.code}</h2>
          <p className="text-sm text-muted">{section.unit.name}</p>
          <p className="mt-1 text-sm text-muted">
            {section.meetings.map((m) => `${meetingText(m)} · ${m.room.code}`).join('; ')}
          </p>
          <p className="text-xs text-muted">
            {section.class_rows.map(classRowText).join(', ')} · {section.registered_students} registered
          </p>
        </div>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-surface">
          <X size={18} />
        </button>
      </header>

      <div className="flex items-center gap-2 border-b border-line px-4 py-2 text-sm">
        <span className="text-muted">Show lecturers from</span>
        {(['department', 'all'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setScope(s)}
            className={clsx('rounded-full px-3 py-1', scope === s ? 'bg-brand text-white' : 'bg-surface')}
          >
            {s === 'department' ? 'This department' : 'All departments'}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {candidates.isPending && <p className="text-sm text-muted">Checking who is free…</p>}
        {candidates.isError && <p className="text-sm text-danger">{errorMessage(candidates.error)}</p>}
        <ul className="space-y-2">
          {candidates.data?.candidates.map((c) => {
            const why = reasons(c)
            const selectable = canAllocate && (c.free || c.current)
            return (
              <li key={c.lecturer.id}>
                <label
                  className={clsx(
                    'flex gap-3 rounded-lg border p-3 text-sm',
                    chosen === c.lecturer.id ? 'border-brand-ink bg-brand-soft' : 'border-line',
                    !selectable && 'opacity-60',
                  )}
                >
                  <input
                    type="radio"
                    name="lecturer"
                    disabled={!selectable}
                    checked={chosen === c.lecturer.id}
                    onChange={() => setChosen(c.lecturer.id)}
                    className="mt-1"
                  />
                  <span className="flex-1">
                    <span className="font-medium">
                      {c.lecturer.title ? `${c.lecturer.title} ` : ''}
                      {c.lecturer.full_name}
                    </span>{' '}
                    <span className="text-muted">
                      {employment(c.lecturer.employment_type)} · {c.weekly_hours}/{c.lecturer.max_weekly_teaching_hours} h
                    </span>
                    {c.current && <span className="ml-2 rounded bg-line px-1.5 text-xs">current</span>}
                    {c.free ? (
                      <span className="block text-success">Free at this time</span>
                    ) : (
                      why.map((r) => (
                        <span key={r} className="block text-warning">
                          {r}
                        </span>
                      ))
                    )}
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      </div>

      {canAllocate && (
        <footer className="space-y-3 border-t border-line p-4">
          <fieldset className="grid grid-cols-3 gap-2 text-sm">
            <legend className="mb-1 text-muted">Semester hours on the allocation form (optional)</legend>
            {(
              [
                ['lecture', 'L'],
                ['practical', 'P'],
                ['cf', 'CF'],
              ] as const
            ).map(([field, label]) => (
              <label key={field} className="block">
                <span className="text-xs font-medium text-muted">{label}</span>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={hours[field]}
                  onChange={(e) => setHours({ ...hours, [field]: e.target.value })}
                  className="w-full rounded-md border border-line px-2 py-1"
                />
              </label>
            ))}
          </fieldset>
          {failure && (
            <div role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
              {errorMessage(save.error)}
              {clashDetails?.map((d) => (
                <span key={d.clashes_with} className="block">
                  Clashes with {d.clashes_with}
                </span>
              ))}
            </div>
          )}
          <div className="flex justify-between gap-2">
            <button
              onClick={() => submit(null)}
              disabled={save.isPending || current === null}
              className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-50"
            >
              Clear lecturer
            </button>
            <button
              onClick={() => submit(chosen)}
              disabled={save.isPending || chosen === null}
              className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong disabled:opacity-50"
            >
              {save.isPending ? 'Saving…' : 'Save allocation'}
            </button>
          </div>
        </footer>
      )}
    </aside>
  )
}
