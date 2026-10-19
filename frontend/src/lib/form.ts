/**
 * The allocation form: units and groups come from the Timetable Generator,
 * each department keeps its own lecturer list and fills in the lecturer and
 * L / P / CF hours for every unit (or group), then downloads it.
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

export interface FormMeeting {
  day_of_week: string
  start_time: string
  end_time: string
  room: string
}

export interface FormEntry {
  id: string
  lecturer_id: string | null
  lecturer: string | null
  lecture_hours: number | null
  practical_hours: number | null
  cf_hours: number | null
  entered_by: string
  entered_at: string
}

export interface FormRow {
  key: string
  unit_code: string
  unit_title: string
  group: string
  class_rows: { label: string; students: number | null; department_code: string | null }[]
  students: number | null
  weekly_hours: number | null
  meetings: FormMeeting[]
  servicing: boolean
  in_timetable: boolean
  entry: FormEntry | null
  problems: { code: string; message: string }[]
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
  active: boolean
}

export interface BoardLecturer extends FormLecturer {
  display: string
  classes: number
  weekly_hours: number
  lecture_hours: number
  practical_hours: number
}

export interface FormBoard {
  term: GeneratorTerm
  published_version: number | null
  department: { code: string; name: string }
  role: DepartmentRoleName | null
  can_edit: boolean
  can_submit: boolean
  rows: FormRow[]
  summary: { classes: number; allocated: number; not_in_timetable: number; problems: number }
  lecturers: BoardLecturer[]
  submission: { submitted_by: string; submitted_at: string; entry_count: number; allocated_count: number } | null
}

export interface FormProgressRow {
  code: string
  name: string
  role: DepartmentRoleName | null
  classes: number
  allocated: number
  submitted_at: string | null
  submitted_by: string | null
}

export interface BulkResult {
  created: number
  updated: number
  lecturers_added?: number
  errors: { line: number; message: string }[]
  error_count: number
}

export interface EntryInput {
  unit_code: string
  group_label: string
  unit_title?: string
  lecturer_id: string | null
  lecture_hours: number | null
  practical_hours: number | null
  cf_hours: number | null
}

export type LecturerInput = Omit<FormLecturer, 'id' | 'department_code'>

const params = (term: string | undefined) => (term ? { term } : undefined)
const dept = (code: string) => encodeURIComponent(code)

export const formKeys = {
  terms: ['generator-terms'] as const,
  progress: (term: string | undefined) => ['form-progress', term] as const,
  board: (code: string, term: string | undefined) => ['form', code, term] as const,
}

export const useGeneratorTerms = () =>
  useQuery({ queryKey: formKeys.terms, queryFn: () => get<GeneratorTerm[]>('/generator/terms') })

export const useFormProgress = (term: string | undefined) =>
  useQuery({
    queryKey: formKeys.progress(term),
    queryFn: () => get<{ term: GeneratorTerm; departments: FormProgressRow[] }>('/form/progress', params(term)),
  })

export const useFormBoard = (code: string, term: string | undefined) =>
  useQuery({ queryKey: formKeys.board(code, term), queryFn: () => get<FormBoard>(`/form/${dept(code)}`, params(term)) })

function useFormMutation<TVars, TResult>(code: string, fn: (vars: TVars) => Promise<TResult>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['form', code] })
      void qc.invalidateQueries({ queryKey: ['form-progress'] })
    },
  })
}

export const useSaveEntry = (code: string, term: string | undefined) =>
  useFormMutation(code, (body: EntryInput) =>
    api.put<FormRow>(`/form/${dept(code)}/entries`, body, { params: params(term) }).then((r) => r.data))

export const useDeleteEntry = (code: string, term: string | undefined) =>
  useFormMutation(code, (id: string) =>
    api.delete(`/form/${dept(code)}/entries/${id}`, { params: params(term) }).then(() => null))

export const useBulkEntries = (code: string, term: string | undefined) =>
  useFormMutation(code, (rows: Record<string, string>[]) =>
    api.post<BulkResult>(`/form/${dept(code)}/entries/bulk`, { rows }, { params: params(term) }).then((r) => r.data))

export const useSubmitForm = (code: string, term: string | undefined) =>
  useFormMutation(code, (action: 'submit' | 'reopen') =>
    api.post<FormBoard>(`/form/${dept(code)}/${action}`, null, { params: params(term) }).then((r) => r.data))

export const useSaveLecturer = (code: string) =>
  useFormMutation(code, ({ id, body }: { id?: string; body: Partial<LecturerInput> }) =>
    (id
      ? api.patch<FormLecturer>(`/form/${dept(code)}/lecturers/${id}`, body)
      : api.post<FormLecturer>(`/form/${dept(code)}/lecturers`, body)
    ).then((r) => r.data))

export const useDeleteLecturer = (code: string) =>
  useFormMutation(code, (id: string) => api.delete(`/form/${dept(code)}/lecturers/${id}`).then(() => null))

export const useBulkLecturers = (code: string) =>
  useFormMutation(code, (rows: Record<string, string>[]) =>
    api.post<BulkResult>(`/form/${dept(code)}/lecturers/bulk`, { rows }).then((r) => r.data))

export const formExportUrl = (code: string, format: 'pdf' | 'docx' | 'xlsx', term: string | undefined) =>
  `${import.meta.env.VITE_API_URL ?? '/api'}/form/${dept(code)}/export.${format}${term ? `?term=${encodeURIComponent(term)}` : ''}`

export const employmentShort = (t: EmploymentType) => (t === 'part_time' ? 'PT' : 'FT')
