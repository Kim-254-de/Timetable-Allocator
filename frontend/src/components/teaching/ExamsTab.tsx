import { useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { Download } from 'lucide-react'
import { BulkPaste, type BulkColumn } from '@/components/BulkPaste'
import { Dialog, Field, inputClass } from '@/components/Dialog'
import { errorMessage } from '@/lib/api'
import {
  letterUrl,
  useDeletePaper,
  useDeletePractical,
  useExamBoard,
  useExamBulk,
  useNoWrittenExam,
  usePapersFromUnits,
  usePublishExams,
  useSavePaper,
  useSavePractical,
  type ExamBoard,
  type ExamPaper,
  type PaperInput,
  type PracticalInput,
  type PracticalRow,
} from '@/lib/form'

const PAPER_COLUMNS: BulkColumn[] = [
  { key: 'codes', label: 'Codes', example: 'BITE 131/COSC 130', required: true,
    hint: 'One code, or several units sitting one shared paper, separated by "/".' },
  { key: 'title', label: 'Title', example: 'Introduction to Programming' },
  { key: 'written_exam', label: 'Written exam', example: 'Yes', hint: 'No: the units have no written exam this term.' },
  { key: 'examiner', label: 'Examiner', example: 'Dr. Jane Otieno', hint: 'Blank: the unit\'s lecturer.' },
  { key: 'staff_no', label: 'Staff no.', example: 'TUN/STF/0123' },
  { key: 'notes', label: 'Notes', example: '' },
]

const PRACTICAL_COLUMNS: BulkColumn[] = [
  { key: 'unit_code', label: 'Unit code', example: 'COSC 200', required: true },
  { key: 'date', label: 'Date', example: '2026-11-20', required: true },
  { key: 'start', label: 'Start', example: '09:00', required: true },
  { key: 'end', label: 'End', example: '11:00', required: true },
]

/**
 * The department's written exam papers (built from its units, a shared paper
 * carrying several codes), its practicals, and the moderation letter. The COD
 * publishes the paper list to the Director.
 */
export function ExamsTab({ code, term }: { code: string; term: string | undefined }) {
  const board = useExamBoard(code, term)
  const publish = usePublishExams(code, term)
  const fromUnits = usePapersFromUnits(code, term)
  const remove = useDeletePaper(code, term)
  const noExam = useNoWrittenExam(code, term)
  const bulk = useExamBulk(code, term, 'exam-papers')
  const [editing, setEditing] = useState<ExamPaper | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const [letter, setLetter] = useState(false)

  if (board.isPending) return <p className="text-sm text-muted">Loading exam papers…</p>
  if (board.isError) return <p role="alert" className="text-sm text-danger">{errorMessage(board.error)}</p>
  const data = board.data
  const editable = data.can_edit
  const unexamined = data.units.filter((u) => !u.paper_id)
  const failure = publish.error ?? fromUnits.error ?? remove.error ?? noExam.error

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">
          {data.summary.papers} papers · {data.summary.students} student entries
          {data.published && data.publication && ` · published to the Director on ${new Date(data.publication.published_at).toLocaleDateString()}`}
        </p>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={() => setLetter(true)} disabled={data.papers.length === 0}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-card px-3 py-2 disabled:opacity-50">
            <Download size={16} aria-hidden /> Moderation letter
          </button>
          {editable && <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>}
          {editable && unexamined.some((u) => !u.no_written_exam) && (
            <button onClick={() => fromUnits.mutate()} disabled={fromUnits.isPending} className="rounded-md border border-line bg-card px-3 py-2">
              A paper for each unit
            </button>
          )}
          {editable && <button onClick={() => setEditing('new')} className="rounded-md bg-brand px-3 py-2 text-white">+ Add a paper</button>}
          {data.can_publish && (
            data.published ? (
              <button onClick={() => publish.mutate('reopen')} disabled={publish.isPending} className="rounded-md border border-line bg-card px-3 py-2">Reopen papers</button>
            ) : (
              <button onClick={() => publish.mutate('publish')} disabled={publish.isPending || data.problems.length > 0}
                title={data.problems.length ? 'Fix the items listed first' : undefined}
                className="rounded-md bg-brand px-3 py-2 font-medium text-white disabled:opacity-50">Publish papers</button>
            )
          )}
        </div>
      </div>
      {failure && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{errorMessage(failure)}</p>}
      {!data.published && data.problems.length > 0 && (
        <details className="rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning" open={data.problems.length <= 5}>
          <summary className="cursor-pointer font-medium">{data.problems.length} to finish before publishing the papers</summary>
          <ul className="mt-1 list-disc pl-5">{data.problems.map((p, i) => <li key={`${p.code}${i}`}>{p.message}</li>)}</ul>
        </details>
      )}

      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Codes</th><th className="px-3 py-2">Title</th><th className="px-3 py-2">Class rows</th>
              <th className="px-3 py-2">Students</th><th className="px-3 py-2">Examiner</th><th /></tr>
          </thead>
          <tbody>
            {data.papers.map((p) => (
              <tr key={p.id} className="border-t border-line align-top">
                <td className="px-3 py-2 font-medium whitespace-nowrap">
                  {p.codes}
                  {p.changed_since_published && <span className="ml-1 rounded bg-warning-soft px-1 text-xs text-warning">changed</span>}
                </td>
                <td className="px-3 py-2">{p.title}{p.notes && <span className="block text-xs text-muted">{p.notes}</span>}</td>
                <td className="px-3 py-2 text-xs text-muted">{p.class_rows.join(', ')}</td>
                <td className="px-3 py-2">{p.students}</td>
                <td className="px-3 py-2">{p.examiner ?? <span className="text-warning">None</span>}</td>
                <td className="space-x-3 px-3 py-2 text-right whitespace-nowrap">
                  {editable && <button onClick={() => setEditing(p)} className="text-brand-ink">Edit</button>}
                  {editable && <button onClick={() => { if (window.confirm(`Remove ${p.codes}?`)) remove.mutate(p.id) }} className="text-danger">Remove</button>}
                </td>
              </tr>
            ))}
            {data.papers.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-muted">No papers yet. Start with “A paper for each unit”, then join shared papers.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {unexamined.length > 0 && (
        <div className="rounded-lg border border-line bg-card p-3 text-sm">
          <p className="font-medium">Units on no paper</p>
          <ul className="mt-1 space-y-1">
            {unexamined.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center justify-between gap-2">
                <span className={clsx(u.no_written_exam && 'text-muted')}>{u.code} {u.title}</span>
                {editable && (
                  <label className="flex items-center gap-1 text-xs">
                    <input type="checkbox" checked={u.no_written_exam}
                      onChange={(e) => noExam.mutate({ unitId: u.id, value: e.target.checked })} />
                    No written exam
                  </label>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Practicals code={code} term={term} board={data} />

      {editing && <PaperForm code={code} term={term} board={data} paper={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste exam papers" columns={PAPER_COLUMNS} templateName="exam-papers.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
      {letter && <LetterForm code={code} term={term} onClose={() => setLetter(false)} />}
    </section>
  )
}

function PaperForm({ code, term, board, paper, onClose }: {
  code: string; term: string | undefined; board: ExamBoard; paper: ExamPaper | null; onClose: () => void
}) {
  const save = useSavePaper(code, term)
  const [form, setForm] = useState<PaperInput>({
    unit_ids: paper?.units.map((u) => u.id) ?? [],
    title: paper?.title ?? '',
    examiner_id: paper?.examiner_id ?? null,
    notes: paper?.notes ?? '',
  })
  const [query, setQuery] = useState('')
  const chosen = new Set(form.unit_ids)
  const toggle = (id: string) =>
    setForm({ ...form, unit_ids: chosen.has(id) ? form.unit_ids.filter((u) => u !== id) : [...form.unit_ids, id] })
  // Units this paper may take: on no paper yet, or already on this one.
  const own = board.units.filter((u) => !u.no_written_exam && (!u.paper_id || u.paper_id === paper?.id))
  const q = query.trim().toLowerCase()
  const others = [
    ...(paper?.units.filter((u) => u.department_code !== board.department.code)
      .map((u) => ({ ...u, title: '' })) ?? []),
    ...board.other_units.filter((u) => q && `${u.code} ${u.title} ${u.department_code}`.toLowerCase().includes(q)),
  ]

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: paper?.id, body: { ...form, examiner_id: form.examiner_id || null } }, { onSuccess: onClose })
  }

  return (
    <Dialog title={paper ? `Edit ${paper.codes}` : 'Add a paper'} onClose={onClose} wide>
      <form onSubmit={submit} className="mt-3 space-y-3 text-sm">
        <fieldset>
          <legend className="font-medium text-ink">Units sitting this paper</legend>
          <p className="text-xs text-muted">Tick several for a shared paper (e.g. BITE 131/COSC 130). All groups of a unit sit one paper.</p>
          <div className="mt-1 grid gap-1 sm:grid-cols-2">
            {own.map((u) => (
              <label key={u.id} className="flex items-center gap-2">
                <input type="checkbox" checked={chosen.has(u.id)} onChange={() => toggle(u.id)} /> {u.code} <span className="text-xs text-muted">{u.title}</span>
              </label>
            ))}
          </div>
          <p className="mt-2 font-medium text-ink">Another department's unit on the same paper</p>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search their units, e.g. BITE"
            aria-label="Search other departments' units" className={inputClass} />
          <div className="mt-1 grid max-h-40 gap-1 overflow-y-auto sm:grid-cols-2">
            {others.map((u) => (
              <label key={u.id} className="flex items-center gap-2">
                <input type="checkbox" checked={chosen.has(u.id)} onChange={() => toggle(u.id)} /> {u.code}
                <span className="text-xs text-muted">{u.department_code}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Title" hint="Blank: the first unit's title.">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={inputClass} />
        </Field>
        <Field label="Examiner" hint="Blank: the unit's lecturer.">
          <select value={form.examiner_id ?? ''} onChange={(e) => setForm({ ...form, examiner_id: e.target.value || null })} className={inputClass}>
            <option value="">The unit's lecturer</option>
            {board.lecturers.filter((x) => x.active || x.id === form.examiner_id).map((x) => <option key={x.id} value={x.id}>{x.display}</option>)}
          </select>
        </Field>
        <Field label="Notes">
          <input value={form.notes} maxLength={500} onChange={(e) => setForm({ ...form, notes: e.target.value })} className={inputClass} />
        </Field>
        {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2">Cancel</button>
          <button type="submit" disabled={save.isPending || form.unit_ids.length === 0}
            className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}

function Practicals({ code, term, board }: { code: string; term: string | undefined; board: ExamBoard }) {
  const [editing, setEditing] = useState<PracticalRow | 'new' | null>(null)
  const [pasting, setPasting] = useState(false)
  const remove = useDeletePractical(code, term)
  const bulk = useExamBulk(code, term, 'practicals')
  const editable = board.can_edit
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Practicals</h3>
        {editable && (
          <div className="flex gap-2 text-sm">
            <button onClick={() => setPasting(true)} className="rounded-md border border-line bg-card px-3 py-2">Paste from Excel</button>
            <button onClick={() => setEditing('new')} className="rounded-md border border-line bg-card px-3 py-2">+ Add a practical</button>
          </div>
        )}
      </div>
      <p className="text-xs text-muted">On dates you set; the exam timetable shows them but doesn't move them.</p>
      {remove.isError && <p role="alert" className="text-sm text-danger">{errorMessage(remove.error)}</p>}
      <div className="overflow-x-auto rounded-lg border border-line bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs uppercase text-muted">
            <tr><th className="px-3 py-2">Unit</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Time</th><th /></tr>
          </thead>
          <tbody>
            {board.practicals.map((p) => (
              <tr key={p.id} className="border-t border-line">
                <td className="px-3 py-2">{p.unit_code} {p.unit_title}</td>
                <td className="px-3 py-2">{new Date(`${p.date}T00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}</td>
                <td className="px-3 py-2">{p.start_time}–{p.end_time}</td>
                <td className="space-x-3 px-3 py-2 text-right">
                  {editable && <button onClick={() => setEditing(p)} className="text-brand-ink">Edit</button>}
                  {editable && <button onClick={() => remove.mutate(p.id)} className="text-danger">Remove</button>}
                </td>
              </tr>
            ))}
            {board.practicals.length === 0 && <tr><td colSpan={4} className="px-3 py-4 text-center text-muted">No practicals.</td></tr>}
          </tbody>
        </table>
      </div>
      {editing && <PracticalForm code={code} term={term} board={board} practical={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {pasting && (
        <BulkPaste title="Paste practicals" columns={PRACTICAL_COLUMNS} templateName="practicals.csv"
          submit={(rows) => bulk.mutateAsync(rows)} onClose={() => setPasting(false)} />
      )}
    </div>
  )
}

function PracticalForm({ code, term, board, practical, onClose }: {
  code: string; term: string | undefined; board: ExamBoard; practical: PracticalRow | null; onClose: () => void
}) {
  const save = useSavePractical(code, term)
  const [form, setForm] = useState<PracticalInput>({
    unit_id: practical?.unit_id ?? board.units[0]?.id ?? '',
    date: practical?.date ?? '',
    start_time: practical?.start_time ?? '09:00',
    end_time: practical?.end_time ?? '11:00',
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id: practical?.id, body: form }, { onSuccess: onClose })
  }
  return (
    <Dialog title={practical ? 'Edit the practical' : 'Add a practical'} onClose={onClose}>
      <form onSubmit={submit} className="mt-3 space-y-3 text-sm">
        <Field label="Unit">
          <select required value={form.unit_id} onChange={(e) => setForm({ ...form, unit_id: e.target.value })} className={inputClass}>
            {board.units.map((u) => <option key={u.id} value={u.id}>{u.code} {u.title}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Date"><input required type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className={inputClass} /></Field>
          <Field label="Start"><input required type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} className={inputClass} /></Field>
          <Field label="End"><input required type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} className={inputClass} /></Field>
        </div>
        {save.isError && <p role="alert" className="text-danger">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2">Cancel</button>
          <button type="submit" disabled={save.isPending} className="rounded-md bg-brand px-4 py-2 text-white disabled:opacity-50">Save</button>
        </div>
      </form>
    </Dialog>
  )
}

function LetterForm({ code, term, onClose }: { code: string; term: string | undefined; onClose: () => void }) {
  const [moderator, setModerator] = useState('')
  const [date, setDate] = useState(new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }))
  return (
    <Dialog title="Moderation letter" onClose={onClose}>
      <div className="mt-3 space-y-3 text-sm">
        <Field label="External moderator" hint="Name, then the address, one line each.">
          <textarea rows={4} value={moderator} onChange={(e) => setModerator(e.target.value)} className={inputClass}
            placeholder={'Prof. A. Moderator\nDepartment of Computing\nP.O. Box 123, Nairobi'} />
        </Field>
        <Field label="Date"><input value={date} onChange={(e) => setDate(e.target.value)} className={inputClass} /></Field>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-2">Close</button>
          {(['docx', 'pdf'] as const).map((format) => (
            <a key={format} href={letterUrl(code, format, term, moderator, date)}
              className="inline-flex items-center gap-1 rounded-md bg-brand px-3 py-2 text-white">
              <Download size={16} aria-hidden /> {format === 'docx' ? 'Word' : 'PDF'}
            </a>
          ))}
        </div>
      </div>
    </Dialog>
  )
}
