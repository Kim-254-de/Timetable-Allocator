import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get } from './api'
import type {
  Board,
  Candidates,
  Department,
  DepartmentLecturer,
  Me,
  Period,
  ProgressRow,
  Section,
  Submission,
  Term,
} from './types'

export const keys = {
  me: ['me'] as const,
  terms: ['terms'] as const,
  departments: ['departments'] as const,
  board: (dept: number, term: string | undefined) => ['board', dept, term] as const,
  lecturers: (dept: number, term: string | undefined) => ['lecturers', dept, term] as const,
  candidates: (key: string, term: string | undefined, scope: string) => ['candidates', key, term, scope] as const,
  progress: (term: string | undefined) => ['progress', term] as const,
}

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => get<Me>('/auth/me'), retry: false })

export const useTerms = () => useQuery({ queryKey: keys.terms, queryFn: () => get<Term[]>('/terms') })

export const useDepartments = () =>
  useQuery({ queryKey: keys.departments, queryFn: () => get<Department[]>('/departments') })

export const useBoard = (dept: number, term: string | undefined) =>
  useQuery({
    queryKey: keys.board(dept, term),
    queryFn: () => get<Board>(`/departments/${dept}/sessions`, { term }),
  })

export const useDepartmentLecturers = (dept: number, term: string | undefined) =>
  useQuery({
    queryKey: keys.lecturers(dept, term),
    queryFn: () => get<{ term: Term; lecturers: DepartmentLecturer[] }>(`/departments/${dept}/lecturers`, { term }),
  })

export const useCandidates = (key: string, term: string | undefined, scope: 'department' | 'all') =>
  useQuery({
    queryKey: keys.candidates(key, term, scope),
    queryFn: () => get<Candidates>(`/sessions/${encodeURIComponent(key)}/free-lecturers`, { term, scope }),
  })

export const useProgress = (term: string | undefined, enabled: boolean) =>
  useQuery({
    queryKey: keys.progress(term),
    queryFn: () => get<{ term: Term | null; departments: ProgressRow[] }>('/progress', { term }),
    enabled,
  })

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { identifier: string; password: string }) =>
      api.post<Me>('/auth/login', body).then((r) => r.data),
    onSuccess: (me) => qc.setQueryData(keys.me, me),
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout'),
    onSettled: () => {
      qc.clear()
      qc.setQueryData(keys.me, null)
    },
  })
}

export interface AllocationInput {
  lecturer_id: string | null
  expected_lecturer_id: string | null
  lecture_hours: number | null
  practical_hours: number | null
  cf_hours: number | null
}

export function useSaveAllocation(dept: number, term: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: AllocationInput }) =>
      api
        .put<{ section: Section }>(`/sessions/${encodeURIComponent(key)}/allocation`, body, { params: { term } })
        .then((r) => r.data),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['board', dept] })
      void qc.invalidateQueries({ queryKey: ['candidates'] })
      void qc.invalidateQueries({ queryKey: ['lecturers', dept] })
    },
  })
}

export function useSubmit(dept: number, term: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<{ submission: Submission }>(`/departments/${dept}/submit`, null, { params: { term } }).then((r) => r.data),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['board', dept] }),
  })
}

export function useSaveAvailability(dept: number, term: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ lecturerId, unavailable }: { lecturerId: string; unavailable: Period[] }) =>
      api
        .put<{ affected: string[] }>(`/lecturers/${lecturerId}/availability`, { unavailable }, { params: { term } })
        .then((r) => r.data),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['lecturers', dept] })
      void qc.invalidateQueries({ queryKey: ['candidates'] })
    },
  })
}

export const exportUrl = (dept: number, term: string | undefined) =>
  `${import.meta.env.VITE_API_URL ?? '/api'}/departments/${dept}/allocations/export.pdf${term ? `?term=${encodeURIComponent(term)}` : ''}`
