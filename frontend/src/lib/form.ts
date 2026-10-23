/**
 * What a department enters for a term of the Timetable Generator: its courses
 * (cohorts), its units with the courses that take them, each unit's groups
 * with a lecturer and the form's L / P / CF hours, and its own lecturer list.
 * The COD publishes it to the Director, who adds days, times and rooms.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get } from './api'
import type { DepartmentRoleName, EmploymentType } from './types'

export interface GeneratorTerm {
  id: string
  name: string
  academic_year?: string | null
  semester?: number | null
  published_version?: number | null
}

export type RoomType = 'lecture_hall' | 'lab' | 'seminar'

export const ROOM_TYPES: Record<RoomType, string> = {
  lecture_hall: 'Lecture hall',
  lab: 'Lab',
  seminar: 'Seminar room',
}

export interface FormMeeting {
  day_of_week: string
  start_time: string
  end_time: string
  room: string
}

export interface Course {
  id: string
  department_code: string
  programme: string
  year: number
  semester: number
  sub_class: string
  label: string
  students: number
  mode: CourseMode
}

export interface OwnCourse extends Course {
  /** Units (any department's) that this course takes. */
  used_by: string[]
}

export interface UnitCourse {
  id: string
  label: string
  department_code: string | null
  students: number
}

export interface GroupMember extends UnitCourse {
  /** The group's share when the course is split between groups; null = the whole course. */
  given_students: number | null
}

export interface UnitGroup {
  id: string
  key: string
  label: string
  members: GroupMember[]
  students: number
  lecturer_id: string | null
  lecturer: string | null
  lecture_hours: number | null
  practical_hours: number | null
  cf_hours: number | null
  meetings: FormMeeting[]
}

export interface Unit {
  id: string
  department_code: string
  code: string
  title: string
  weekly_hours: number
  class_length: number
  room_type: RoomType
  courses: UnitCourse[]
  servicing: boolean
  changed_since_published: boolean
  groups: UnitGroup[]
}

export interface FormLecturer {
  id: string
  department_code: string
  title: string
  full_name: string
  staff_number: string | null
  employment_type: EmploymentType
  phone: string
  email: string
  max_weekly_hours: number | null
  max_exam_duties: number | null
  active: boolean
}

export interface BoardLecturer extends FormLecturer {
  display: string
  groups: number
  /** Across every department this person teaches for. */
  weekly_hours: number
}

export interface Problem {
  code: string
  message: string
  unit_id: string | null
}

export interface Publication {
  published_by: string
  published_at: string
  unit_count: number
  group_count: number
  reopened_at: string | null
  reopened_by: string | null
}

export interface FormBoard {
  term: GeneratorTerm
  department: { code: string; name: string }
  role: DepartmentRoleName | null
  can_edit: boolean
  can_publish: boolean
  publication: Publication | null
  published: boolean
  courses: OwnCourse[]
  other_courses: Course[]
  units: Unit[]
  lecturers: BoardLecturer[]
  problems: Problem[]
  times: { published_version: number | null; error: string | null }
  summary: { courses: number; units: number; groups: number; with_lecturer: number; changed: number; problems: number }
}

export interface FormProgressRow {
  code: string
  name: string
  role: DepartmentRoleName | null
  units: number
  groups: number
  with_lecturer: number
  published: boolean
  publication: Publication | null
}

export interface BulkResult {
  created: number
  updated: number
  lecturers_added?: number
  /** Said instead of "added / updated" when that doesn't fit (the groups tab). */
  message?: string
  errors: { line: number; message: string }[]
  error_count: number
}

export interface CourseInput {
  programme: string
  year: number
  semester: number
  sub_class: string
  students: number
  mode: CourseMode
}

export interface UnitInput {
  code: string
  title: string
  weekly_hours: number
  class_length: number
  room_type: RoomType
  course_ids: string[]
}

export interface GroupInput {
  label: string
  members: { course_id: string; students?: number | null }[]
}

export interface GroupPatch {
  lecturer_id?: string | null
  lecture_hours?: number | null
  practical_hours?: number | null
  cf_hours?: number | null
}

export type LecturerInput = Omit<FormLecturer, 'id' | 'department_code'>

const params = (term: string | undefined) => (term ? { term } : undefined)
const dept = (code: string) => encodeURIComponent(code)

export const formKeys = {
  terms: ['generator-terms'] as const,
  progress: (term: string | undefined) => ['teaching-progress', term] as const,
  board: (code: string, term: string | undefined) => ['teaching', code, term] as const,
}

export const useGeneratorTerms = () =>
  useQuery({ queryKey: formKeys.terms, queryFn: () => get<GeneratorTerm[]>('/generator/terms') })

export const useFormProgress = (term: string | undefined) =>
  useQuery({
    queryKey: formKeys.progress(term),
    queryFn: () => get<{ term: GeneratorTerm; departments: FormProgressRow[] }>('/teaching/progress', params(term)),
  })

export const useFormBoard = (code: string, term: string | undefined) =>
  useQuery({ queryKey: formKeys.board(code, term), queryFn: () => get<FormBoard>(`/teaching/${dept(code)}`, params(term)) })

function useFormMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      // Every department's board: a course or a lecturer's hours can show on another's.
      void qc.invalidateQueries({ queryKey: ['teaching'] })
      void qc.invalidateQueries({ queryKey: ['teaching-progress'] })
    },
  })
}

const at = (code: string, path: string) => `/teaching/${dept(code)}${path}`

export const useSaveCourse = (code: string, term: string | undefined) =>
  useFormMutation(({ id, body }: { id?: string; body: Partial<CourseInput> }) =>
    (id
      ? api.patch<Course>(at(code, `/courses/${id}`), body, { params: params(term) })
      : api.post<Course>(at(code, '/courses'), body, { params: params(term) })
    ).then((r) => r.data))

export const useDeleteCourse = (code: string, term: string | undefined) =>
  useFormMutation((id: string) => api.delete(at(code, `/courses/${id}`), { params: params(term) }).then(() => null))

export const useSaveUnit = (code: string, term: string | undefined) =>
  useFormMutation(({ id, body }: { id?: string; body: Partial<UnitInput> }) =>
    (id
      ? api.patch<{ id: string }>(at(code, `/units/${id}`), body, { params: params(term) })
      : api.post<{ id: string }>(at(code, '/units'), body, { params: params(term) })
    ).then((r) => r.data))

export const useDeleteUnit = (code: string, term: string | undefined) =>
  useFormMutation((id: string) => api.delete(at(code, `/units/${id}`), { params: params(term) }).then(() => null))

export const useSaveGroups = (code: string, term: string | undefined) =>
  useFormMutation(({ unitId, groups }: { unitId: string; groups: GroupInput[] }) =>
    api.put(at(code, `/units/${unitId}/groups`), { groups }, { params: params(term) }).then((r) => r.data))

export const useSaveGroup = (code: string, term: string | undefined) =>
  useFormMutation(({ id, body }: { id: string; body: GroupPatch }) =>
    api.patch(at(code, `/groups/${id}`), body, { params: params(term) }).then((r) => r.data))

export const useBulk = (code: string, term: string | undefined, what: 'courses' | 'units' | 'groups') =>
  useFormMutation((rows: Record<string, string>[]) =>
    api.post<BulkResult>(at(code, `/${what}/bulk`), { rows }, { params: params(term) }).then((r) => r.data))

export const usePublish = (code: string, term: string | undefined) =>
  useFormMutation((action: 'publish' | 'reopen') =>
    api.post<FormBoard>(at(code, `/${action}`), null, { params: params(term) }).then((r) => r.data))

export const useSaveLecturer = (code: string) =>
  useFormMutation(({ id, body }: { id?: string; body: Partial<LecturerInput> }) =>
    (id
      ? api.patch<FormLecturer>(at(code, `/lecturers/${id}`), body)
      : api.post<FormLecturer>(at(code, '/lecturers'), body)
    ).then((r) => r.data))

export const useDeleteLecturer = (code: string) =>
  useFormMutation((id: string) => api.delete(at(code, `/lecturers/${id}`)).then(() => null))

export const useBulkLecturers = (code: string) =>
  useFormMutation((rows: Record<string, string>[]) =>
    api.post<BulkResult>(at(code, '/lecturers/bulk'), { rows }).then((r) => r.data))

export const formExportUrl = (code: string, format: 'pdf' | 'docx' | 'xlsx', term: string | undefined) =>
  `${import.meta.env.VITE_API_URL ?? '/api'}/teaching/${dept(code)}/export.${format}${term ? `?term=${encodeURIComponent(term)}` : ''}`

export const employmentShort = (t: EmploymentType) => (t === 'part_time' ? 'PT' : 'FT')

export const meetingText = (m: FormMeeting) => `${m.day_of_week} ${m.start_time}–${m.end_time}${m.room ? ` ${m.room}` : ''}`

/** 'A', 'B', … for splitting a unit into n groups. */
export const groupLetters = (n: number) => Array.from({ length: n }, (_, i) => String.fromCharCode(65 + i))

/**
 * Each course's share in each group when a unit is split: a course in one
 * group goes whole; a course in several is divided as evenly as possible.
 */
export function evenSplit(students: number, parts: number): number[] {
  const base = Math.floor(students / parts)
  return Array.from({ length: parts }, (_, i) => base + (i < students % parts ? 1 : 0))
}

const TITLE = /^(dr|prof|mr|mrs|ms|miss|eng|rev)\.?\s+/i
const KIND = /\s*\((ft|pt)\)\s*$/i

/** "Dr. Jane Otieno (PT)" -> title, name and FT/PT, as typed in the lecturer box. */
export function splitTyped(typed: string): Pick<LecturerInput, 'title' | 'full_name' | 'employment_type'> {
  let text = typed.trim()
  const kind = KIND.exec(text)
  text = text.replace(KIND, '')
  const title = TITLE.exec(text)
  return {
    title: title ? `${title[1][0].toUpperCase()}${title[1].slice(1).toLowerCase()}.` : 'Dr.',
    full_name: text.replace(TITLE, '').trim(),
    employment_type: kind?.[1].toLowerCase() === 'pt' ? 'part_time' : 'full_time',
  }
}

// -- exams --------------------------------------------------------------------------------------

export type CourseMode = 'regular' | 'odel' | 'weekend' | 'evening' | 'school_based' | 'part_time'

export const COURSE_MODES: Record<CourseMode, string> = {
  regular: 'Regular',
  odel: 'ODEL',
  weekend: 'Weekend',
  evening: 'Evening',
  school_based: 'School-based',
  part_time: 'Part-time',
}

export interface ExamPaper {
  id: string
  department_code: string
  codes: string
  units: { id: string; code: string; department_code: string }[]
  title: string
  examiner_id: string | null
  examiner: string | null
  notes: string
  class_rows: string[]
  students: number
  changed_since_published: boolean
}

export interface ExamUnit {
  id: string
  code: string
  title: string
  no_written_exam: boolean
  paper_id: string | null
  paper_codes: string | null
  paper_department: string | null
  default_examiner_id: string | null
}

export interface PracticalRow {
  id: string
  unit_id: string
  unit_code: string
  unit_title: string
  date: string
  start_time: string
  end_time: string
}

export interface ExamBoard {
  term: GeneratorTerm
  department: { code: string; name: string }
  role: DepartmentRoleName | null
  can_edit: boolean
  can_publish: boolean
  publication: Publication | null
  published: boolean
  papers: ExamPaper[]
  units: ExamUnit[]
  other_units: { id: string; code: string; title: string; department_code: string }[]
  practicals: PracticalRow[]
  lecturers: { id: string; display: string; staff_number: string | null; active: boolean }[]
  problems: Problem[]
  summary: { papers: number; students: number; changed: number; problems: number }
}

export interface PaperInput {
  unit_ids: string[]
  title: string
  examiner_id: string | null
  notes: string
}

export interface PracticalInput {
  unit_id: string
  date: string
  start_time: string
  end_time: string
}

export const useExamBoard = (code: string, term: string | undefined) =>
  useQuery({ queryKey: ['teaching', code, term, 'exams'], queryFn: () => get<ExamBoard>(at(code, '/exams'), params(term)) })

export const useSavePaper = (code: string, term: string | undefined) =>
  useFormMutation(({ id, body }: { id?: string; body: Partial<PaperInput> }) =>
    (id
      ? api.patch<{ id: string }>(at(code, `/exam-papers/${id}`), body, { params: params(term) })
      : api.post<{ id: string }>(at(code, '/exam-papers'), body, { params: params(term) })
    ).then((r) => r.data))

export const useDeletePaper = (code: string, term: string | undefined) =>
  useFormMutation((id: string) => api.delete(at(code, `/exam-papers/${id}`), { params: params(term) }).then(() => null))

export const usePapersFromUnits = (code: string, term: string | undefined) =>
  useFormMutation(() => api.post<{ created: number }>(at(code, '/exam-papers/from-units'), null, { params: params(term) }).then((r) => r.data))

export const useNoWrittenExam = (code: string, term: string | undefined) =>
  useFormMutation(({ unitId, value }: { unitId: string; value: boolean }) =>
    api.put(at(code, `/units/${unitId}/no-written-exam`), { no_written_exam: value }, { params: params(term) }).then(() => null))

export const useSavePractical = (code: string, term: string | undefined) =>
  useFormMutation(({ id, body }: { id?: string; body: PracticalInput }) =>
    (id
      ? api.put(at(code, `/practicals/${id}`), body, { params: params(term) })
      : api.post(at(code, '/practicals'), body, { params: params(term) })
    ).then((r) => r.data))

export const useDeletePractical = (code: string, term: string | undefined) =>
  useFormMutation((id: string) => api.delete(at(code, `/practicals/${id}`), { params: params(term) }).then(() => null))

export const useExamBulk = (code: string, term: string | undefined, what: 'exam-papers' | 'practicals') =>
  useFormMutation((rows: Record<string, string>[]) =>
    api.post<BulkResult>(at(code, `/${what}/bulk`), { rows }, { params: params(term) }).then((r) => r.data))

export const usePublishExams = (code: string, term: string | undefined) =>
  useFormMutation((action: 'publish' | 'reopen') =>
    api.post<ExamBoard>(at(code, `/exams/${action}`), null, { params: params(term) }).then((r) => r.data))

export const letterUrl = (code: string, format: 'docx' | 'pdf', term: string | undefined, moderator: string, date: string) => {
  const q = new URLSearchParams({ moderator, date, ...(term ? { term } : {}) })
  return `${import.meta.env.VITE_API_URL ?? '/api'}/teaching/${dept(code)}/moderation-letter.${format}?${q}`
}

export interface InvigilationRow {
  paper_id: string
  codes: string
  title: string
  date: string | null
  session: number | null
  start_time: string | null
  end_time: string | null
  rooms: string[]
  /** The main invigilator sits in the main room and collects the scripts from every room. */
  main_room: string | null
  main: NamedInvigilator | null
  /** Each room but the main one needs an invigilator of its own. */
  extras: { room: string; invigilator: NamedInvigilator | null }[]
}

export interface NamedInvigilator {
  id: string
  display: string
  department_code: string
}

export interface InvigilatorChoice {
  id: string
  display: string
  department_code: string
  staff_number: string | null
  duties: number
  max_exam_duties: number | null
  own: boolean
}

export interface InvigilationBoard {
  term: GeneratorTerm
  department: { code: string; name: string }
  role: DepartmentRoleName | null
  draft: { id: string; name: string; shared_at: string | null; status: string } | null
  can_edit: boolean
  can_publish: boolean
  publication: Publication | null
  published: boolean
  papers: InvigilationRow[]
  lecturers: InvigilatorChoice[]
  problems: Problem[]
}

export const useInvigilationBoard = (code: string, term: string | undefined) =>
  useQuery({
    queryKey: ['teaching', code, term, 'invigilators'],
    queryFn: () => get<InvigilationBoard>(at(code, '/invigilators'), params(term)),
  })

export const useSetInvigilator = (code: string, term: string | undefined) =>
  useFormMutation(({ paperId, lecturerId, room }: { paperId: string; lecturerId: string | null; room: string }) =>
    api.put(at(code, `/invigilators/${paperId}`), { lecturer_id: lecturerId, room }, { params: params(term) }).then((r) => r.data))

export const usePublishInvigilators = (code: string, term: string | undefined) =>
  useFormMutation((action: 'publish' | 'reopen') =>
    api.post<InvigilationBoard>(at(code, `/invigilators/${action}`), null, { params: params(term) }).then((r) => r.data))
