import { useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import {
  ROOM_TYPES,
  evenSplit,
  groupLetters,
  meetingText,
  useBulk,
  useDeleteUnit,
  useSaveGroup,
  useSaveGroups,
  useSaveUnit,
  type FormBoard,
  type GroupInput,
  type RoomType,
  type Unit,
  type UnitGroup,
  type UnitInput,
} from '@/lib/form'
import { LecturerForm, LecturerPicker } from './Lecturers'

export const UNIT_COLUMNS: BulkColumn[] = [
  { key: 'code', label: 'Code', example: 'COSC 103', required: true },
  { key: 'title', label: 'Title', example: 'Introduction to Programming', required: true },
  { key: 'hours_per_week', label: 'Hours per week', example: '3', required: true },
  { key: 'class_length', label: 'Class length', example: '3', hint: 'Hours per class. 3 hours a week in 2-hour classes is one 2 h and one 1 h class.' },
  { key: 'room_type', label: 'Room type', example: 'Lecture hall', hint: 'Lecture hall, Lab or Seminar room.' },
  { key: 'courses', label: 'Courses', example: 'BSC.COMP SCI Y1S1; BED.SCI Y1S1', required: true,
    hint: 'Separated by ";". Another department\'s course can be listed for a unit you teach them.' },
]

export const GROUP_COLUMNS: BulkColumn[] = [
  { key: 'unit_code', label: 'Unit code', example: 'COSC 103', required: true,
    hint: 'All of a unit\'s rows together replace its groups.' },
  { key: 'group', label: 'Group', example: 'A', hint: 'Blank for a whole class.' },
  { key: 'courses', label: 'Courses', example: 'BSC.COMP SCI Y1S1', hint: 'Blank: every course taking the unit.' },
  { key: 'students', label: 'Students', example: '60', hint: 'Only when a course is split: one number per course listed.' },
  { key: 'lecturer', label: 'Lecturer', example: 'Dr. Jane Otieno (FT)', hint: 'A lecturer not on your list yet is added to it.' },
  { key: 'staff_no', label: 'Staff no.', example: 'TUN/STF/0123' },
  { key: 'l', label: 'L', example: '30' },
  { key: 'p', label: 'P', example: '' },
  { key: 'cf', label: 'CF', example: '15' },
]

const hours = (v: number | null | undefined) => (v == null ? '' : String(v))
const toNumber = (v: string) => (v.trim() === '' ? null : Number(v))
const groupName = (g: UnitGroup) => g.label || 'Whole class'

export function UnitsTab({ code, term, board }: { code: string; term: string | undefined; board: FormBoard }) {
  const [editing, setEditing] = useState<Unit | 'new' | null>(null)
  const [splitting, setSplitting] = useState<Unit | null>(null)
  const [teaching, setTeaching] = useState<{ unit: Unit; group: UnitGroup } | null>(null)
  const [pasting, setPasting] = useState<'units' | 'groups' | null>(null)
  const remove = useDeleteUnit(code, term)
  const bulkUnits = useBulk(code, term, 'units')
  const bulkGroups = useBulk(code, term, 'groups')
  const editable = board.can_edit
  const problemUnits = new Set(board.problems.map((p) => p.unit_id).filter(Boolean))

  return (
    <section className="space-y-3">
      {editable && (
        <div className="flex flex-wrap justify-end gap-2 text-sm">
          <button onClick={() => setPasting('units')} className="rounded-md border border-line bg-card px-3 py-2">Paste units</button>
          <button onClick={() => setPasting('groups')} className="rounded-md border border-line bg-card px-3 py-2">Paste groups and lecturers</button>
          <button onClick={() => setEditing('new')} disabled={board.courses.length + board.other_courses.length === 0}
            title={board.courses.length + board.other_courses.length === 0 ? 'Add your courses first' : undefined}
            className="rounded-md bg-brand px-3 py-2 text-white disabled:opacity-50">+ Add a unit</button>
        </div>
      )}
      {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Unit</th><th className="px-3 py-2">Group</th><th className="px-3 py-2">Courses</th>
              <th className="px-3 py-2">Students</th><th className="px-3 py-2">Lecturer</th>
              <th className="px-3 py-2">L</th><th className="px-3 py-2">P</th><th className="px-3 py-2">CF</th>
              <th className="px-3 py-2">When</th><th />
            </tr>
          </thead>
          {board.units.map((u) => (
            <tbody key={u.id} className={clsx('border-t-2 border-line', problemUnits.has(u.id) && 'bg-danger-soft')}>
              {u.groups.map((g, i) => (
                <tr key={g.id} className="align-top">
                  {i === 0 && (
                    <td rowSpan={u.groups.length} className="px-3 py-2">
                      <p className="font-medium whitespace-nowrap">{u.code}</p>
                      <p>{u.title}</p>
                      <p className="text-xs text-muted">
                        {u.weekly_hours} h a week in {u.class_length} h classes · {ROOM_TYPES[u.room_type]}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1 text-xs">
                        {u.servicing && <span className="rounded bg-brand-soft px-1 text-brand-ink">servicing</span>}
                        {u.changed_since_published && <span className="rounded bg-warning-soft px-1 text-warning">changed since published</span>}
                      </div>
                      {editable && (
                        <div className="mt-1 space-x-3 text-xs">
                          <button onClick={() => setEditing(u)} className="text-brand-ink">Edit</button>
                          <button onClick={() => setSplitting(u)} className="text-brand-ink">Groups</button>
                          <button onClick={() => { if (window.confirm(`Remove ${u.code}?`)) remove.mutate(u.id) }} className="text-danger">Remove</button>
                        </div>
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2 whitespace-nowrap">{groupName(g)}</td>
                  <td className="px-3 py-2 text-xs text-muted">
                    {g.members.map((m) => (
                      <div key={m.id}>
                        {m.label}{m.given_students != null && ` (${m.given_students})`}
                        {m.department_code && m.department_code !== u.department_code && ` · ${m.department_code}`}
                      </div>
                    ))}
                  </td>
                  <td className="px-3 py-2">{g.students}</td>
                  <td className="px-3 py-2">
                    {g.lecturer ?? <span className="text-warning">No lecturer</span>}
                    {editable && (
                      <button onClick={() => setTeaching({ unit: u, group: g })} className="ml-2 text-xs text-brand-ink">
                        {g.lecturer ? 'Change' : 'Choose'}
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2">{hours(g.lecture_hours)}</td>
                  <td className="px-3 py-2">{hours(g.practical_hours)}</td>
                  <td className="px-3 py-2">{hours(g.cf_hours)}</td>
                  <td className="px-3 py-2 text-xs whitespace-nowrap text-muted">
                    {g.meetings.map((m) => <div key={`${m.day_of_week}${m.start_time}`}>{meetingText(m)}</div>)}
                  </td>
                  <td />
                </tr>
              ))}
            </tbody>
          ))}
          {board.units.length === 0 && (
            <tbody><tr><td colSpan={10} className="px-3 py-6 text-center text-muted">
              No units yet. Add each unit you teach this term, with the courses that take it.
            </td></tr></tbody>
          )}
        </table>
      </div>
      {editing && <UnitForm code={code} term={term} board={board} unit={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {splitting && <GroupsForm code={code} term={term} unit={splitting} onClose={() => setSplitting(null)} />}
      {teaching && <GroupForm code={code} term={term} board={board} {...teaching} onClose={() => setTeaching(null)} />}
      {pasting === 'units' && (
        <BulkPaste title="Paste units" columns={UNIT_COLUMNS} templateName="units.csv"
          submit={(rows) => bulkUnits.mutateAsync(rows)} onClose={() => setPasting(null)} />
      )}
      {pasting === 'groups' && (
        <BulkPaste title="Paste groups and lecturers" columns={GROUP_COLUMNS} templateName="groups-and-lecturers.csv"
          submit={(rows) => bulkGroups.mutateAsync(rows)} onClose={() => setPasting(null)} />
      )}
    </section>
  )
}

function UnitForm({ code, term, board, unit, onClose }: {
  code: string; term: string | undefined; board: FormBoard; unit: Unit | null; onClose: () => void
}) {
  const save = useSaveUnit(code, term)
  const [form, setForm] = useState<UnitInput>({
    code: unit?.code ?? '',
    title: unit?.title ?? '',
    weekly_hours: unit?.weekly_hours ?? 3,
    class_length: unit?.class_length ?? 3,
    room_type: unit?.room_type ?? 'lecture_hall',
    course_ids: unit?.courses.map((c) => c.id) ?? [],
  })
  const [query, setQuery] = useState('')
  const chosen = new Set(form.course_ids)
  const toggle = (id: string) =>
    setForm({ ...form, course_ids: chosen.has(id) ? form.course_ids.filter((c) => c !== id) : [...form.course_ids, id] })
  const q = query.trim().toLowerCase()
  const others = board.other_courses.filter((c) => chosen.has(c.id) || (q && `${c.label} ${c.department_code}`.toLowerCase().includes(q)))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: unit?.id, body: form }, { onSuccess: onClose })
  }

  return (
    <Dialog title={unit ? `Edit ${unit.code}` : 'Add a unit'} onClose={onClose} wide>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Code"><input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="COSC 103" className={inputClass} /></Field>
          <div className="sm:col-span-2">
            <Field label="Title"><input required minLength={2} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={inputClass} /></Field>
          </div>
          <Field label="Hours per week">
            <input required type="number" min={1} max={20} value={form.weekly_hours} onChange={(e) => setForm({ ...form, weekly_hours: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Class length (hours)" hint="3 h a week in 2 h classes: one 2 h and one 1 h class.">
            <input required type="number" min={1} max={Math.min(6, form.weekly_hours || 6)} value={form.class_length} onChange={(e) => setForm({ ...form, class_length: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Room type">
            <select value={form.room_type} onChange={(e) => setForm({ ...form, room_type: e.target.value as RoomType })} className={inputClass}>
              {Object.entries(ROOM_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </Field>
        </div>
        <fieldset className="text-sm">
          <legend className="font-medium text-ink">Courses taking it</legend>
          <div className="mt-1 grid gap-1 sm:grid-cols-2">
            {board.courses.map((c) => (
              <label key={c.id} className="flex items-center gap-2">
                <input type="checkbox" checked={chosen.has(c.id)} onChange={() => toggle(c.id)} /> {c.label} <span className="text-xs text-muted">({c.students})</span>
              </label>
            ))}
            {board.courses.length === 0 && <p className="text-muted">Your department has no courses yet.</p>}
          </div>
          <p className="mt-3 font-medium text-ink">Another department's students</p>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search their courses, e.g. BED"
            aria-label="Search other departments' courses" className={inputClass} />
          <div className="mt-1 grid max-h-48 gap-1 overflow-y-auto sm:grid-cols-2">
            {others.map((c) => (
              <label key={c.id} className="flex items-center gap-2">
                <input type="checkbox" checked={chosen.has(c.id)} onChange={() => toggle(c.id)} /> {c.label}
                <span className="text-xs text-muted">{c.department_code} · {c.students}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
          <button type="submit" disabled={save.isPending || form.course_ids.length === 0}
            className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}

/** Which groups each course is in, and its share of students in each. */
type Split = Record<string, Record<string, string>>

const letterOf = (label: string) => label.replace(/^GR\s*/i, '') || 'A'

function startingSplit(unit: Unit): { count: number; split: Split } {
  const split: Split = {}
  for (const c of unit.courses) split[c.id] = {}
  for (const g of unit.groups) {
    for (const m of g.members) {
      split[m.id] = { ...split[m.id], [letterOf(g.label)]: String(m.given_students ?? m.students) }
    }
  }
  return { count: unit.groups.length === 1 && unit.groups[0].label === '' ? 1 : unit.groups.length, split }
}

/**
 * The unit as one whole class, or split into groups A, B, C…: tick which
 * courses are in each group, and when a course is in several, how many of
 * its students go to each.
 */
function GroupsForm({ code, term, unit, onClose }: { code: string; term: string | undefined; unit: Unit; onClose: () => void }) {
  const save = useSaveGroups(code, term)
  const start = startingSplit(unit)
  const [count, setCount] = useState(start.count)
  const [split, setSplit] = useState<Split>(start.split)
  const letters = groupLetters(count)

  const changeCount = (n: number) => {
    setCount(n)
    // Every course in every group, divided evenly; adjust from there.
    const next: Split = {}
    for (const c of unit.courses) {
      const shares = evenSplit(c.students, n)
      next[c.id] = Object.fromEntries(groupLetters(n).map((l, i) => [l, String(shares[i])]))
    }
    setSplit(next)
  }
  const toggle = (courseId: string, letter: string) => {
    const row = { ...split[courseId] }
    if (letter in row) delete row[letter]
    else row[letter] = ''
    setSplit({ ...split, [courseId]: row })
  }
  const setShare = (courseId: string, letter: string, value: string) =>
    setSplit({ ...split, [courseId]: { ...split[courseId], [letter]: value } })

  const totals = Object.fromEntries(unit.courses.map((c) => [
    c.id, Object.values(split[c.id] ?? {}).reduce((sum, v) => sum + (Number(v) || 0), 0),
  ]))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const groups: GroupInput[] = letters.map((l) => ({
      label: count === 1 ? '' : l,
      members: unit.courses
        .filter((c) => count === 1 || l in (split[c.id] ?? {}))
        .map((c) => {
          const inGroups = Object.keys(split[c.id] ?? {}).length
          return { course_id: c.id, students: count > 1 && inGroups > 1 ? Number(split[c.id][l]) || null : null }
        }),
    }))
    save.mutate({ unitId: unit.id, groups }, { onSuccess: onClose })
  }

  return (
    <Dialog title={`${unit.code}: groups`} onClose={onClose} wide>
      <form onSubmit={submit} className="mt-3 space-y-3 text-sm">
        <Field label="Taught as">
          <select value={count} onChange={(e) => changeCount(Number(e.target.value))} className={inputClass}>
            <option value={1}>One whole class</option>
            {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n} groups ({groupLetters(n).join(', ')})</option>)}
          </select>
        </Field>
        {count > 1 && (
          <div className="overflow-x-auto rounded-md border border-line">
            <table className="w-full text-left">
              <thead className="bg-surface text-xs uppercase text-muted">
                <tr>
                  <th className="px-2 py-1">Course</th>
                  {letters.map((l) => <th key={l} className="px-2 py-1">Group {l}</th>)}
                  <th className="px-2 py-1">Total</th>
                </tr>
              </thead>
              <tbody>
                {unit.courses.map((c) => {
                  const inGroups = Object.keys(split[c.id] ?? {}).length
                  return (
                    <tr key={c.id} className="border-t border-line">
                      <td className="px-2 py-1">{c.label} <span className="text-xs text-muted">({c.students})</span></td>
                      {letters.map((l) => (
                        <td key={l} className="px-2 py-1">
                          <label className="flex items-center gap-1">
                            <input type="checkbox" checked={l in (split[c.id] ?? {})} onChange={() => toggle(c.id, l)}
                              aria-label={`${c.label} in group ${l}`} />
                            {l in (split[c.id] ?? {}) && inGroups > 1 && (
                              <input type="number" min={1} max={c.students} required value={split[c.id][l]}
                                onChange={(e) => setShare(c.id, l, e.target.value)} aria-label={`${c.label} students in group ${l}`}
                                className="w-20 rounded border border-line px-1" />
                            )}
                          </label>
                        </td>
                      ))}
                      <td className={clsx('px-2 py-1', inGroups > 1 && totals[c.id] !== c.students && 'font-medium text-danger')}>
                        {inGroups > 1 ? `${totals[c.id]} of ${c.students}` : inGroups === 1 ? 'whole' : <span className="text-danger">in no group</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-muted">Groups keep their lecturer and hours when you change the split. Give lecturers to new groups on the unit's rows.</p>
        {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}

/** A group's lecturer (from the department's list, or added here) and its L / P / CF hours. */
function GroupForm({ code, term, board, unit, group, onClose }: {
  code: string; term: string | undefined; board: FormBoard; unit: Unit; group: UnitGroup; onClose: () => void
}) {
  const save = useSaveGroup(code, term)
  const [lecturer, setLecturer] = useState(group.lecturer_id ?? '')
  const [l, setL] = useState(hours(group.lecture_hours))
  const [p, setP] = useState(hours(group.practical_hours))
  const [cf, setCf] = useState(hours(group.cf_hours))
  const [adding, setAdding] = useState<string | null>(null)
  const active = board.lecturers.filter((x) => x.active || x.id === lecturer)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({
      id: group.id,
      body: { lecturer_id: lecturer || null, lecture_hours: toNumber(l), practical_hours: toNumber(p), cf_hours: toNumber(cf) },
    }, { onSuccess: onClose })
  }

  return (
    <>
      <Dialog title={`${unit.code} ${group.label}`.trim()} onClose={onClose}>
        <form onSubmit={submit} className="mt-3 space-y-3">
          <p className="text-sm text-muted">{unit.title} · {group.members.map((m) => m.label).join(', ')} · {group.students} students</p>
          <LecturerPicker lecturers={active} value={lecturer} onChange={setLecturer} onAddNew={setAdding} />
          <div className="grid grid-cols-3 gap-3">
            <Field label="L"><input type="number" min={0} step={0.5} value={l} onChange={(e) => setL(e.target.value)} className={inputClass} /></Field>
            <Field label="P"><input type="number" min={0} step={0.5} value={p} onChange={(e) => setP(e.target.value)} className={inputClass} /></Field>
            <Field label="CF"><input type="number" min={0} step={0.5} value={cf} onChange={(e) => setCf(e.target.value)} className={inputClass} /></Field>
          </div>
          {save.isError && <p role="alert" className="text-sm text-danger">{errorMessage(save.error)}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2 text-sm">Cancel</button>
            <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-50">Save</button>
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
