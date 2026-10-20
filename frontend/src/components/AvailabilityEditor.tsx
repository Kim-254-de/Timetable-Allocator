import { useState } from 'react'
import { Plus, Trash2, X } from 'lucide-react'
import { errorMessage } from '@/lib/api'
import { DAYS, dayName } from '@/lib/format'
import { useSaveAvailability } from '@/lib/queries'
import type { DepartmentLecturer, Period } from '@/lib/types'

interface Props {
  lecturer: DepartmentLecturer
  departmentId: number
  term: string | undefined
  onClose: () => void
}

export function AvailabilityEditor({ lecturer, departmentId, term, onClose }: Props) {
  const [periods, setPeriods] = useState<Period[]>(lecturer.unavailable)
  const save = useSaveAvailability(departmentId, term)
  const [affected, setAffected] = useState<string[] | null>(null)

  const update = (i: number, patch: Partial<Period>) =>
    setPeriods(periods.map((p, j) => (i === j ? { ...p, ...patch } : p)))

  return (
    <div role="dialog" aria-modal="true" aria-label={`Availability of ${lecturer.full_name}`}
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-lg rounded-xl bg-card p-5 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">{lecturer.full_name}</h2>
            <p className="text-sm text-muted">Times this term when they cannot be given classes.</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-surface">
            <X size={18} />
          </button>
        </div>

        <ul className="mt-4 space-y-2">
          {periods.map((p, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <select aria-label="Day" value={p.day_of_week}
                onChange={(e) => update(i, { day_of_week: e.target.value as Period['day_of_week'] })}
                className="rounded-md border border-line px-2 py-1">
                {DAYS.map((d) => <option key={d} value={d}>{dayName(d)}</option>)}
              </select>
              <input aria-label="From" type="time" min="07:00" max="19:00" step={1800} value={p.start_time}
                onChange={(e) => update(i, { start_time: e.target.value })}
                className="rounded-md border border-line px-2 py-1" />
              <input aria-label="To" type="time" min="07:00" max="19:00" step={1800} value={p.end_time}
                onChange={(e) => update(i, { end_time: e.target.value })}
                className="rounded-md border border-line px-2 py-1" />
              <input aria-label="Reason" placeholder="Reason" value={p.reason} maxLength={255}
                onChange={(e) => update(i, { reason: e.target.value })}
                className="min-w-0 flex-1 rounded-md border border-line px-2 py-1" />
              <button aria-label="Remove" onClick={() => setPeriods(periods.filter((_, j) => j !== i))}
                className="rounded p-1 text-muted hover:bg-surface">
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
        <button
          onClick={() => setPeriods([...periods, { day_of_week: 'MON', start_time: '08:00', end_time: '10:00', reason: '' }])}
          className="mt-3 inline-flex items-center gap-1 text-sm text-brand-ink"
        >
          <Plus size={16} /> Add a period
        </button>

        {save.isError && <p role="alert" className="mt-3 text-sm text-danger">{errorMessage(save.error)}</p>}
        {affected && affected.length > 0 && (
          <p role="status" className="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">
            Saved. They are already allocated at these times: {affected.join(', ')}. Re-allocate those classes.
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Close</button>
          <button
            disabled={save.isPending}
            onClick={() =>
              save.mutate({ lecturerId: lecturer.id, unavailable: periods }, {
                onSuccess: (data) => (data.affected.length ? setAffected(data.affected) : onClose()),
              })
            }
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
