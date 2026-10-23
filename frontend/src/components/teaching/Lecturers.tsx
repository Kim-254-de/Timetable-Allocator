import { useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import {
  employmentShort,
  splitTyped,
  useBulkLecturers,
  useDeleteLecturer,
  useSaveLecturer,
  type BoardLecturer,
  type FormBoard,
  type FormLecturer,
  type LecturerInput,
} from '@/lib/form'

export const LECTURER_COLUMNS: BulkColumn[] = [
  { key: 'name', label: 'Name', example: 'Dr. Jane Otieno (FT)', required: true },
  { key: 'staff_number', label: 'Staff number', example: 'TUN/STF/0123', required: true,
    hint: 'How the timetable knows the lecturer, here and on any other department\'s list.' },
  { key: 'phone', label: 'Phone', example: '07…' },
  { key: 'email', label: 'Email', example: 'jane@tharaka.ac.ke' },
  { key: 'max_hours', label: 'Max hours', example: '18', hint: 'Weekly teaching hours. Leave blank for no limit.' },
]

export const loadText = (x: BoardLecturer) =>
  `${x.weekly_hours}h/week${x.max_weekly_hours ? ` of ${x.max_weekly_hours}` : ''}`

/**
 * The lecturer for a group: type a name to find one on the department's list,
 * or add someone new with their full details (the form prints the phone).
 */
export function LecturerPicker({ lecturers, value, onChange, onAddNew }: {
  lecturers: BoardLecturer[]; value: string; onChange: (id: string) => void; onAddNew: (typed: string) => void
}) {
  const [query, setQuery] = useState('')
  const [changing, setChanging] = useState(false)
  const chosen = lecturers.find((x) => x.id === value)
  const typed = query.trim()
  const q = typed.toLowerCase()
  const matches = lecturers.filter((x) => !q || `${x.title} ${x.full_name} ${x.staff_number ?? ''} ${x.phone}`.toLowerCase().includes(q))
  const exact = lecturers.some((x) => x.full_name.toLowerCase() === splitTyped(typed).full_name.toLowerCase())

  return (
    <div className="text-sm">
      <p className="font-medium text-ink">Lecturer</p>
      {chosen && !changing ? (
        <div className="mt-1 flex items-start justify-between gap-3 rounded-md border border-line bg-brand-soft px-3 py-2">
          <div>
            <p className="font-medium">{chosen.display}</p>
            <p className="text-xs text-muted">{chosen.phone || 'No phone number yet'} · {loadText(chosen)}</p>
          </div>
          <div className="space-x-3 whitespace-nowrap">
            <button type="button" onClick={() => { setQuery(''); setChanging(true) }} className="text-brand-ink">Change</button>
            <button type="button" onClick={() => onChange('')} className="text-danger">Remove</button>
          </div>
        </div>
      ) : (
        <>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type the lecturer's name"
            aria-label="Lecturer" className={inputClass} />
          <ul className="mt-1 max-h-52 overflow-y-auto rounded-md border border-line">
            {matches.map((x) => (
              <li key={x.id}>
                <button type="button" onClick={() => { onChange(x.id); setChanging(false) }}
                  className="flex w-full justify-between gap-3 px-3 py-2 text-left hover:bg-brand-soft">
                  <span>{x.display}</span>
                  <span className="text-xs text-muted">{x.phone} · {loadText(x)}</span>
                </button>
              </li>
            ))}
            {typed && !exact && (
              <li>
                <button type="button" onClick={() => onAddNew(typed)} className="w-full px-3 py-2 text-left font-medium text-brand-ink hover:bg-brand-soft">
                  + Add “{typed}” as a new lecturer
                </button>
              </li>
            )}
            {!typed && matches.length === 0 && (
              <li className="px-3 py-2 text-muted">No lecturers on your list yet. Type a name to add one.</li>
            )}
          </ul>
          {chosen && <button type="button" onClick={() => setChanging(false)} className="mt-1 text-xs text-muted">Keep {chosen.display}</button>}
        </>
      )}
    </div>
  )
}

export function LecturersTab({ code, board }: { code: string; board: FormBoard }) {
  const [editing, setEditing] = useState<BoardLecturer | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const remove = useDeleteLecturer(code)
  const bulk = useBulkLecturers(code)
  const editable = board.role != null

  return (
    <section className="space-y-3">
      {editable && (
        <div className="flex justify-end gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>
          <button onClick={() => setEditing('new')} className="rounded-md bg-brand px-3 py-2 text-white">+ Add a lecturer</button>
        </div>
      )}
      {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Name</th><th className="px-3 py-2">Staff no.</th><th className="px-3 py-2">FT/PT</th>
              <th className="px-3 py-2">Phone</th><th className="px-3 py-2">Email</th><th className="px-3 py-2">Groups</th>
              <th className="px-3 py-2" title="Across every department they teach for">Hours / week</th><th />
            </tr>
          </thead>
          <tbody>
            {board.lecturers.map((x) => (
              <tr key={x.id} className={clsx('border-t border-line', !x.active && 'text-muted')}>
                <td className="px-3 py-2 font-medium">{x.title} {x.full_name}{!x.active && ' (inactive)'}</td>
                <td className="px-3 py-2">{x.staff_number || <span className="text-warning">Missing</span>}</td>
                <td className="px-3 py-2">{employmentShort(x.employment_type)}</td>
                <td className="px-3 py-2">{x.phone || <span className="text-warning">Missing</span>}</td>
                <td className="px-3 py-2">{x.email}</td>
                <td className="px-3 py-2">{x.groups}</td>
                <td className={clsx('px-3 py-2', x.max_weekly_hours && x.weekly_hours > x.max_weekly_hours && 'font-medium text-danger')}>
                  {x.weekly_hours}{x.max_weekly_hours ? ` / ${x.max_weekly_hours}` : ''}
                </td>
                <td className="space-x-3 px-3 py-2 text-right">
                  {editable && <button onClick={() => setEditing(x)} className="text-brand-ink">Edit</button>}
                  {editable && (
                    <button onClick={() => { if (window.confirm(`Remove ${x.full_name}?`)) remove.mutate(x.id) }} className="text-danger">Remove</button>
                  )}
                </td>
              </tr>
            ))}
            {board.lecturers.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-muted">No lecturers on the list yet. Add them here, then give them groups on the Units tab.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && <LecturerForm code={code} lecturer={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste lecturers" columns={LECTURER_COLUMNS} templateName="lecturers.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </section>
  )
}

export function LecturerForm({ code, lecturer, typed, onClose, onSaved }: {
  code: string; lecturer: BoardLecturer | null; typed?: string; onClose: () => void; onSaved: (saved: FormLecturer) => void
}) {
  const save = useSaveLecturer(code)
  const start = typed ? splitTyped(typed) : null
  const [form, setForm] = useState<LecturerInput>({
    title: lecturer?.title ?? start?.title ?? 'Dr.',
    full_name: lecturer?.full_name ?? start?.full_name ?? '',
    staff_number: lecturer?.staff_number ?? '',
    employment_type: lecturer?.employment_type ?? start?.employment_type ?? 'full_time',
    phone: lecturer?.phone ?? '',
    email: lecturer?.email ?? '',
    max_weekly_hours: lecturer?.max_weekly_hours ?? null,
    max_exam_duties: lecturer?.max_exam_duties ?? null,
    active: lecturer?.active ?? true,
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = {
      ...form,
      staff_number: form.staff_number?.trim() || null,
      // Editing: an empty limit is sent as 0, which clears it.
      max_weekly_hours: form.max_weekly_hours ?? (lecturer ? 0 : null),
      max_exam_duties: form.max_exam_duties ?? (lecturer ? 0 : null),
    }
    save.mutate({ id: lecturer?.id, body }, { onSuccess: onSaved })
  }
  return (
    <Dialog title={lecturer ? `Edit ${lecturer.full_name}` : 'Add a lecturer'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid grid-cols-4 gap-3">
          <Field label="Title"><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={inputClass} /></Field>
          <div className="col-span-3">
            <Field label="Full name"><input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className={inputClass} /></Field>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Staff number" hint="How the timetable, SMARTTT and attendance know them, and another department's list too.">
            <input required value={form.staff_number ?? ''} onChange={(e) => setForm({ ...form, staff_number: e.target.value })} placeholder="TUN/STF/0123" className={inputClass} />
          </Field>
          <Field label="Full or part time">
            <select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value as LecturerInput['employment_type'] })} className={inputClass}>
              <option value="full_time">Full time (FT)</option><option value="part_time">Part time (PT)</option>
            </select>
          </Field>
          <Field label="Phone" hint="Printed on your department's own downloads only.">
            <input required type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="07…" className={inputClass} />
          </Field>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputClass} /></Field>
          <Field label="Max teaching hours a week" hint="Counted across every department. Leave blank for no limit.">
            <input type="number" min={1} max={60} value={form.max_weekly_hours ?? ''}
              onChange={(e) => setForm({ ...form, max_weekly_hours: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Max invigilation duties" hint="In an exam period, across every department. Blank: no limit.">
            <input type="number" min={1} max={100} value={form.max_exam_duties ?? ''}
              onChange={(e) => setForm({ ...form, max_exam_duties: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
          </Field>
          <label className="mt-6 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Active
          </label>
        </div>
        {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}
