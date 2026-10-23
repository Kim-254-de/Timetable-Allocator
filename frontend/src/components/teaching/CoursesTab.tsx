import { useState, type FormEvent } from 'react'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import { useBulk, useDeleteCourse, useSaveCourse, type CourseInput, type FormBoard, type OwnCourse } from '@/lib/form'

export const COURSE_COLUMNS: BulkColumn[] = [
  { key: 'programme', label: 'Programme', example: 'BSC.COMP SCI', required: true },
  { key: 'year', label: 'Year', example: '1', required: true },
  { key: 'semester', label: 'Semester', example: '1', required: true },
  { key: 'sub_class', label: 'Sub-class', example: '', hint: 'Only when a year is taught as separate classes (A, B…).' },
  { key: 'students', label: 'Students', example: '120', required: true },
]

/**
 * The department's courses (each becomes a class row on the timetable), and
 * every other department's, read-only, to choose for units this department services.
 */
export function CoursesTab({ code, term, board }: { code: string; term: string | undefined; board: FormBoard }) {
  const [editing, setEditing] = useState<OwnCourse | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const [query, setQuery] = useState('')
  const remove = useDeleteCourse(code, term)
  const bulk = useBulk(code, term, 'courses')
  const editable = board.can_edit
  const q = query.trim().toLowerCase()
  const others = board.other_courses.filter((c) => !q || `${c.label} ${c.department_code}`.toLowerCase().includes(q))

  return (
    <section className="space-y-3">
      {editable && (
        <div className="flex flex-wrap justify-end gap-2 text-sm">
          <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>
          <button onClick={() => setEditing('new')} className="rounded-md bg-brand px-3 py-2 text-white">+ Add a course</button>
        </div>
      )}
      {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Course</th><th className="px-3 py-2">Students</th>
              <th className="px-3 py-2">Units taking it</th><th />
            </tr>
          </thead>
          <tbody>
            {board.courses.map((c) => (
              <tr key={c.id} className="border-t border-line">
                <td className="px-3 py-2 font-medium">{c.label}</td>
                <td className="px-3 py-2">{c.students}</td>
                <td className="px-3 py-2 text-xs text-muted">{c.used_by.join(', ') || 'None yet'}</td>
                <td className="space-x-3 px-3 py-2 text-right whitespace-nowrap">
                  {editable && <button onClick={() => setEditing(c)} className="text-brand-ink">Edit</button>}
                  {editable && (
                    <button onClick={() => { if (window.confirm(`Remove ${c.label}?`)) remove.mutate(c.id) }} className="text-danger">Remove</button>
                  )}
                </td>
              </tr>
            ))}
            {board.courses.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-muted">
                No courses yet. Add each programme, year and semester you teach this term, with its number of students.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <details className="rounded-lg border border-line bg-card">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
          Other departments' courses ({board.other_courses.length})
        </summary>
        <div className="space-y-2 border-t border-line p-3">
          <p className="text-xs text-muted">
            For units you teach to another department's students: choose their course on the unit. Only that department can change it.
          </p>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search courses or departments"
            aria-label="Search other departments' courses" className={inputClass} />
          <ul className="max-h-64 overflow-y-auto text-sm">
            {others.map((c) => (
              <li key={c.id} className="flex justify-between border-b border-line py-1 last:border-0">
                <span>{c.label}</span><span className="text-xs text-muted">{c.department_code} · {c.students} students</span>
              </li>
            ))}
            {others.length === 0 && <li className="py-1 text-muted">None.</li>}
          </ul>
        </div>
      </details>

      {editing && <CourseForm code={code} term={term} course={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste courses" columns={COURSE_COLUMNS} templateName="courses.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </section>
  )
}

function CourseForm({ code, term, course, onClose }: {
  code: string; term: string | undefined; course: OwnCourse | null; onClose: () => void
}) {
  const save = useSaveCourse(code, term)
  const [form, setForm] = useState<CourseInput>({
    programme: course?.programme ?? '',
    year: course?.year ?? 1,
    semester: course?.semester ?? 1,
    sub_class: course?.sub_class ?? '',
    students: course?.students ?? 0,
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: course?.id, body: form }, { onSuccess: onClose })
  }
  return (
    <Dialog title={course ? `Edit ${course.label}` : 'Add a course'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <Field label="Programme" hint="As printed on the timetable, e.g. BSC.COMP SCI">
          <input required value={form.programme} onChange={(e) => setForm({ ...form, programme: e.target.value })} className={inputClass} />
        </Field>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Year">
            <input required type="number" min={1} max={7} value={form.year} onChange={(e) => setForm({ ...form, year: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Semester">
            <input required type="number" min={1} max={3} value={form.semester} onChange={(e) => setForm({ ...form, semester: Number(e.target.value) })} className={inputClass} />
          </Field>
          <Field label="Sub-class">
            <input value={form.sub_class} maxLength={10} onChange={(e) => setForm({ ...form, sub_class: e.target.value })} placeholder="A" className={inputClass} />
          </Field>
          <Field label="Students">
            <input required type="number" min={1} max={5000} value={form.students || ''} onChange={(e) => setForm({ ...form, students: Number(e.target.value) })} className={inputClass} />
          </Field>
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
