import { useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Download } from 'lucide-react'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import {
  employmentShort,
  formExportUrl,
  splitTyped,
  useBulkEntries,
  useBulkLecturers,
  useDeleteEntry,
  useDeleteLecturer,
  useFormBoard,
  useGeneratorTerms,
  useSaveEntry,
  useSaveLecturer,
  usePublishAgain,
  useSubmitForm,
  type BoardLecturer,
  type FormBoard,
  type FormLecturer,
  type FormRow,
  type LecturerInput,
  type SmartttState,
} from '@/lib/form'

const ENTRY_COLUMNS: BulkColumn[] = [
  { key: 'course_code', label: 'Course code', example: 'COSC 103', required: true,
    hint: 'A group can be in the same cell ("COSC 103 Group A") or in the Group column.' },
  { key: 'group', label: 'Group', example: 'A' },
  { key: 'course_title', label: 'Course title', example: 'Introduction to Programming',
    hint: 'Only needed for a unit that is not in the timetable yet.' },
  { key: 'l', label: 'L', example: '3' },
  { key: 'p', label: 'P', example: '' },
  { key: 'cf', label: 'CF', example: '3' },
  { key: 'lecturer', label: 'Lecturer', example: 'Dr. Jane Otieno (FT)',
    hint: 'As written on the Word form. A lecturer not on your list yet is added to it.' },
]

const LECTURER_COLUMNS: BulkColumn[] = [
  { key: 'name', label: 'Name', example: 'Dr. Jane Otieno (FT)', required: true },
  { key: 'staff_number', label: 'Staff number', example: 'TUN/STF/0123',
    hint: 'Used to recognise the same lecturer on another department\'s list and in SMARTTT.' },
  { key: 'phone', label: 'Phone', example: '07…' },
  { key: 'email', label: 'Email', example: 'jane@tharaka.ac.ke' },
  { key: 'max_hours', label: 'Max hours', example: '18', hint: 'Weekly teaching hours. Leave blank for no limit.' },
]

const hours = (v: number | null | undefined) => (v == null ? '' : String(v))
const toNumber = (v: string) => (v.trim() === '' ? null : Number(v))

const loadText = (x: BoardLecturer) =>
  `${x.weekly_hours}h/week${x.max_weekly_hours ? ` of ${x.max_weekly_hours}` : ''}`

/** One department's allocation form: units (from the Timetable Generator) and the department's own lecturers. */
export function AllocationFormPage() {
  const { code = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const term = search.get('term') || undefined
  const tab = search.get('tab') === 'lecturers' ? 'lecturers' : 'units'
  const terms = useGeneratorTerms()
  const board = useFormBoard(code, term)
  const submit = useSubmitForm(code, term)
  const publishAgain = usePublishAgain(code, term)

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(search)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearch(Object.fromEntries(next))
  }

  if (board.isPending) return <p className="text-sm text-slate-500">Loading the allocation form…</p>
  if (board.isError) return <p role="alert" className="text-sm text-red-700">{errorMessage(board.error)}</p>
  const data = board.data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{data.department.name}</h1>
          <p className="text-sm text-slate-600">
            {data.term.name} course allocation · {data.summary.allocated} of {data.summary.classes} classes allocated
            {data.published_version == null && ' · timetable not published yet (no clash checks until it is)'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select aria-label="Term" value={term ?? ''} onChange={(e) => setParam('term', e.target.value || null)}
            className="rounded-md border border-slate-300 px-2 py-2">
            <option value="">Latest term</option>
            {terms.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          {([['pdf', 'PDF'], ['docx', 'Word'], ['xlsx', 'Excel']] as const).map(([format, label]) => (
            <a key={format} href={formExportUrl(code, format, term)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-2">
              <Download size={16} /> {label}
            </a>
          ))}
          {data.can_submit && data.submission && data.summary.not_in_smarttt > 0 && (
            <button onClick={() => publishAgain.mutate()} disabled={publishAgain.isPending}
              className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 disabled:opacity-50">
              {publishAgain.isPending ? 'Publishing…' : `Publish again (${data.summary.not_in_smarttt})`}
            </button>
          )}
          {data.can_submit && (
            data.submission ? (
              <button onClick={() => submit.mutate('reopen')} disabled={submit.isPending}
                className="rounded-md border border-slate-300 bg-white px-3 py-2">Reopen</button>
            ) : (
              <button onClick={() => submit.mutate('submit')} disabled={submit.isPending}
                className="rounded-md bg-emerald-700 px-4 py-2 font-medium text-white disabled:opacity-50">
                {submit.isPending ? 'Publishing…' : 'Submit & publish'}
              </button>
            )
          )}
        </div>
      </div>

      {data.submission && (
        <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Submitted and published to SMARTTT by {data.submission.submitted_by} on {new Date(data.submission.submitted_at).toLocaleString()}.
          {data.can_submit ? ' Reopen it to make changes.' : ' The COD can reopen it.'}
        </p>
      )}
      {submit.isError && <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{errorMessage(submit.error)}</p>}
      {publishAgain.isError && <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{errorMessage(publishAgain.error)}</p>}
      {data.role == null && <p className="text-sm text-slate-500">You are viewing this department's form; only its COD and allocation staff can change it.</p>}

      <div className="flex gap-2">
        {(['units', 'lecturers'] as const).map((t) => (
          <button key={t} onClick={() => setParam('tab', t === 'units' ? null : t)}
            className={clsx('rounded-full px-3 py-1 text-sm', tab === t ? 'bg-emerald-700 text-white' : 'border border-slate-200 bg-white')}>
            {t === 'units' ? `Units (${data.rows.length})` : `Lecturers (${data.lecturers.length})`}
          </button>
        ))}
      </div>

      {tab === 'units' ? <UnitsTab code={code} term={term} board={data} /> : <LecturersTab code={code} board={data} />}
      <p className="text-xs text-slate-500">
        Units and groups come from the Timetable Generator. <Link to="/" className="text-emerald-700">All departments</Link>
      </p>
    </div>
  )
}

function UnitsTab({ code, term, board }: { code: string; term: string | undefined; board: FormBoard }) {
  const [editing, setEditing] = useState<FormRow | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const remove = useDeleteEntry(code, term)
  const bulk = useBulkEntries(code, term)
  const editable = board.can_edit

  return (
    <section className="space-y-3">
      {editable && (
        <div className="flex flex-wrap justify-end gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-slate-300 bg-white px-3 py-2">Paste from Excel / Word</button>
          <button onClick={() => setEditing('new')} className="rounded-md border border-slate-300 bg-white px-3 py-2">+ A unit not in the timetable</button>
        </div>
      )}
      {editable && board.lecturers.length === 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Add your department's lecturers first, with their phone numbers, in the{' '}
          <Link to={`?${new URLSearchParams(term ? { term, tab: 'lecturers' } : { tab: 'lecturers' })}`} className="font-medium underline">Lecturers</Link> table. Then press Allocate on each unit and pick one.
        </p>
      )}
      {remove.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Course code</th><th className="px-3 py-2">Course title</th>
              <th className="px-3 py-2">Class</th><th className="px-3 py-2">When</th>
              <th className="px-3 py-2">L</th><th className="px-3 py-2">P</th><th className="px-3 py-2">CF</th>
              <th className="px-3 py-2">Lecturer</th><th />
            </tr>
          </thead>
          <tbody>
            {board.rows.map((r) => (
              <tr key={r.key} className={clsx('border-t border-slate-100 align-top', r.problems.length > 0 && 'bg-red-50')}>
                <td className="px-3 py-2 font-medium whitespace-nowrap">{r.unit_code} {r.group}</td>
                <td className="px-3 py-2">
                  {r.unit_title}
                  {!r.in_timetable && <span className="ml-1 rounded bg-amber-100 px-1 text-xs text-amber-900">not in timetable</span>}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600">
                  {r.class_rows.map((c) => c.label).join(', ')}
                  {r.servicing && <span className="ml-1 rounded bg-sky-100 px-1 text-sky-900">servicing</span>}
                </td>
                <td className="px-3 py-2 text-xs text-slate-600 whitespace-nowrap">
                  {r.meetings.map((m) => <div key={`${m.day_of_week}${m.start_time}`}>{m.day_of_week} {m.start_time}–{m.end_time} {m.room}</div>)}
                </td>
                <td className="px-3 py-2">{hours(r.entry?.lecture_hours)}</td>
                <td className="px-3 py-2">{hours(r.entry?.practical_hours)}</td>
                <td className="px-3 py-2">{hours(r.entry?.cf_hours)}</td>
                <td className="px-3 py-2">
                  {r.entry?.lecturer ?? <span className="text-slate-400">Not allocated</span>}
                  <SmartttBadge smarttt={r.smarttt} />
                  {r.problems.map((p) => <p key={p.message} className="text-xs text-red-700">{p.message}</p>)}
                </td>
                <td className="space-x-3 px-3 py-2 text-right whitespace-nowrap">
                  {editable && <button onClick={() => setEditing(r)} className="text-emerald-700">{r.entry ? 'Edit' : 'Allocate'}</button>}
                  {editable && r.entry && (
                    <button onClick={() => { if (window.confirm(`Clear ${r.unit_code} ${r.group}?`)) remove.mutate(r.entry!.id) }}
                      className="text-red-700">Clear</button>
                  )}
                </td>
              </tr>
            ))}
            {board.rows.length === 0 && (
              <tr><td colSpan={9} className="px-3 py-6 text-center text-slate-500">
                The Timetable Generator has no units for this department in this term yet.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && <EntryForm code={code} term={term} board={board} row={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste the allocation form" columns={ENTRY_COLUMNS} templateName="allocation.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </section>
  )
}

/** Whether SMARTTT (lecturers' timetables, Smart Attendance) has this class's lecturer. */
function SmartttBadge({ smarttt }: { smarttt: SmartttState }) {
  if (smarttt.state == null) return null
  if (smarttt.state === 'sent') return <span className="block text-xs text-emerald-700">Published to SMARTTT</span>
  if (smarttt.state === 'pending') return <span className="block text-xs text-slate-500">Not published yet</span>
  return (
    <span className={clsx('block text-xs', smarttt.state === 'waiting' ? 'text-slate-500' : 'text-amber-800')}>
      {smarttt.state === 'waiting' ? 'Not in SMARTTT yet' : 'Not in SMARTTT'}{smarttt.message ? `: ${smarttt.message}` : ''}
    </span>
  )
}

function EntryForm({ code, term, board, row, onClose }: {
  code: string; term: string | undefined; board: FormBoard; row: FormRow | null; onClose: () => void
}) {
  const save = useSaveEntry(code, term)
  const [unit, setUnit] = useState(row?.unit_code ?? '')
  const [group, setGroup] = useState(row?.group ?? '')
  const [title, setTitle] = useState(row?.unit_title ?? '')
  const [lecturer, setLecturer] = useState(row?.entry?.lecturer_id ?? '')
  const [l, setL] = useState(hours(row?.entry?.lecture_hours))
  const [p, setP] = useState(hours(row?.entry?.practical_hours))
  const [cf, setCf] = useState(hours(row?.entry?.cf_hours))
  const [adding, setAdding] = useState<string | null>(null)
  const active = board.lecturers.filter((x) => x.active || x.id === lecturer)

  // A unit typed in that the timetable has: offer its groups.
  const matching = board.rows.filter((r) => r.in_timetable && r.unit_code.replace(/\s/g, '').toUpperCase() === unit.replace(/\s/g, '').toUpperCase())
  const groups = matching.map((r) => r.group)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({
      unit_code: unit,
      group_label: group,
      unit_title: title,
      lecturer_id: lecturer || null,
      lecture_hours: toNumber(l),
      practical_hours: toNumber(p),
      cf_hours: toNumber(cf),
    }, { onSuccess: onClose })
  }

  return (
    <>
    <Dialog title={row ? `${row.unit_code} ${row.group}`.trim() : 'A unit not in the timetable'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        {row ? (
          <p className="text-sm text-slate-600">
            {row.unit_title} · {row.class_rows.map((c) => c.label).join(', ')}
            {row.meetings.length > 0 && ` · ${row.meetings.map((m) => `${m.day_of_week} ${m.start_time}–${m.end_time}`).join(', ')}`}
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Course code">
                <input required list="form-units" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="COSC 499" className={inputClass} />
                <datalist id="form-units">
                  {[...new Set(board.rows.map((r) => r.unit_code))].map((u) => <option key={u} value={u} />)}
                </datalist>
              </Field>
              <Field label="Group">
                {groups.some(Boolean) ? (
                  <select value={group} onChange={(e) => setGroup(e.target.value)} className={inputClass}>
                    <option value="">Choose…</option>
                    {groups.map((g) => <option key={g} value={g}>{g || 'Whole class'}</option>)}
                  </select>
                ) : (
                  <input value={group} onChange={(e) => setGroup(e.target.value)} placeholder="GR A (if split)" className={inputClass} />
                )}
              </Field>
            </div>
            {matching.length === 0 && (
              <Field label="Course title" hint="This unit isn't in the timetable yet, so the Director's office will see it flagged.">
                <input required value={title} onChange={(e) => setTitle(e.target.value)} className={inputClass} />
              </Field>
            )}
          </>
        )}
        <LecturerPicker lecturers={active} value={lecturer} onChange={setLecturer} onAddNew={setAdding} />
        <div className="grid grid-cols-3 gap-3">
          <Field label="L"><input type="number" min={0} step={0.5} value={l} onChange={(e) => setL(e.target.value)} className={inputClass} /></Field>
          <Field label="P"><input type="number" min={0} step={0.5} value={p} onChange={(e) => setP(e.target.value)} className={inputClass} /></Field>
          <Field label="CF"><input type="number" min={0} step={0.5} value={cf} onChange={(e) => setCf(e.target.value)} className={inputClass} /></Field>
        </div>
        {save.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50">
            {save.isPending ? 'Checking…' : 'Save'}
          </button>
        </div>
      </form>
    </Dialog>
    {adding != null && (
      <LecturerForm code={code} lecturer={null} typed={adding} onClose={() => setAdding(null)}
        onSaved={(created) => { setLecturer(created.id); setAdding(null) }} />
    )}
    </>
  )
}

/**
 * The lecturer for a unit: type a name to find one on the department's list,
 * or add someone new with their full details (the form prints the phone).
 */
function LecturerPicker({ lecturers, value, onChange, onAddNew }: {
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
      <p className="font-medium text-slate-700">Lecturer</p>
      {chosen && !changing ? (
        <div className="mt-1 flex items-start justify-between gap-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2">
          <div>
            <p className="font-medium">{chosen.display}</p>
            <p className="text-xs text-slate-600">{chosen.phone || 'No phone number yet'} · {loadText(chosen)}</p>
          </div>
          <div className="space-x-3 whitespace-nowrap">
            <button type="button" onClick={() => { setQuery(''); setChanging(true) }} className="text-emerald-700">Change</button>
            <button type="button" onClick={() => onChange('')} className="text-red-700">Remove</button>
          </div>
        </div>
      ) : (
        <>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type the lecturer's name"
            aria-label="Lecturer" className={inputClass} />
          <ul className="mt-1 max-h-52 overflow-y-auto rounded-md border border-slate-200">
            {matches.map((x) => (
              <li key={x.id}>
                <button type="button" onClick={() => { onChange(x.id); setChanging(false) }}
                  className="flex w-full justify-between gap-3 px-3 py-2 text-left hover:bg-emerald-50">
                  <span>{x.display}</span>
                  <span className="text-xs text-slate-500">{x.phone} · {loadText(x)}</span>
                </button>
              </li>
            ))}
            {typed && !exact && (
              <li>
                <button type="button" onClick={() => onAddNew(typed)} className="w-full px-3 py-2 text-left font-medium text-emerald-700 hover:bg-emerald-50">
                  + Add “{typed}” as a new lecturer
                </button>
              </li>
            )}
            {!typed && matches.length === 0 && (
              <li className="px-3 py-2 text-slate-500">No lecturers on your list yet. Type a name to add one.</li>
            )}
          </ul>
          {chosen && <button type="button" onClick={() => setChanging(false)} className="mt-1 text-xs text-slate-600">Keep {chosen.display}</button>}
        </>
      )}
    </div>
  )
}

function LecturersTab({ code, board }: { code: string; board: FormBoard }) {
  const [editing, setEditing] = useState<BoardLecturer | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const remove = useDeleteLecturer(code)
  const bulk = useBulkLecturers(code)
  const editable = board.role != null

  return (
    <section className="space-y-3">
      {editable && (
        <div className="flex justify-end gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-slate-300 bg-white px-3 py-2">Paste from Excel</button>
          <button onClick={() => setEditing('new')} className="rounded-md bg-emerald-700 px-3 py-2 text-white">+ Add a lecturer</button>
        </div>
      )}
      {remove.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Name</th><th className="px-3 py-2">Staff no.</th><th className="px-3 py-2">FT/PT</th>
              <th className="px-3 py-2">Phone</th><th className="px-3 py-2">Email</th><th className="px-3 py-2">Classes</th>
              <th className="px-3 py-2">Hours / week</th><th />
            </tr>
          </thead>
          <tbody>
            {board.lecturers.map((x) => (
              <tr key={x.id} className={clsx('border-t border-slate-100', !x.active && 'text-slate-400')}>
                <td className="px-3 py-2 font-medium">{x.title} {x.full_name}{!x.active && ' (inactive)'}</td>
                <td className="px-3 py-2">{x.staff_number || <span className="text-amber-700">Missing</span>}</td>
                <td className="px-3 py-2">{employmentShort(x.employment_type)}</td>
                <td className="px-3 py-2">{x.phone || <span className="text-amber-700">Missing</span>}</td>
                <td className="px-3 py-2">{x.email}</td>
                <td className="px-3 py-2">{x.classes}</td>
                <td className="px-3 py-2">{x.weekly_hours}{x.max_weekly_hours ? ` / ${x.max_weekly_hours}` : ''}</td>
                <td className="space-x-3 px-3 py-2 text-right">
                  {editable && <button onClick={() => setEditing(x)} className="text-emerald-700">Edit</button>}
                  {editable && (
                    <button onClick={() => { if (window.confirm(`Remove ${x.full_name}?`)) remove.mutate(x.id) }} className="text-red-700">Remove</button>
                  )}
                </td>
              </tr>
            ))}
            {board.lecturers.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-500">No lecturers on the list yet. Add them here, then allocate them on the Units tab.</td></tr>
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

function LecturerForm({ code, lecturer, typed, onClose, onSaved }: {
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
    active: lecturer?.active ?? true,
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = {
      ...form,
      staff_number: form.staff_number?.trim() || null,
      // Editing: an empty limit is sent as 0, which clears it.
      max_weekly_hours: form.max_weekly_hours ?? (lecturer ? 0 : null),
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
          <Field label="Staff number" hint="How SMARTTT knows them, so their classes reach their timetable and attendance.">
            <input required value={form.staff_number ?? ''} onChange={(e) => setForm({ ...form, staff_number: e.target.value })} placeholder="TUN/STF/0123" className={inputClass} />
          </Field>
          <Field label="Full or part time">
            <select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value as LecturerInput['employment_type'] })} className={inputClass}>
              <option value="full_time">Full time (FT)</option><option value="part_time">Part time (PT)</option>
            </select>
          </Field>
          <Field label="Phone" hint="Printed on the allocation form.">
            <input required type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="07…" className={inputClass} />
          </Field>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={inputClass} /></Field>
          <Field label="Max teaching hours a week" hint="Leave blank for no limit.">
            <input type="number" min={1} max={60} value={form.max_weekly_hours ?? ''}
              onChange={(e) => setForm({ ...form, max_weekly_hours: e.target.value === '' ? null : Number(e.target.value) })} className={inputClass} />
          </Field>
          <label className="mt-6 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Active
          </label>
        </div>
        {save.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-emerald-700 px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}
