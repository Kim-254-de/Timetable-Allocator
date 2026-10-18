export type Day = 'MON' | 'TUE' | 'WED' | 'THU' | 'FRI'
export type DepartmentRoleName = 'cod' | 'admin' | 'editor'
export type EmploymentType = 'full_time' | 'part_time'

export interface Me {
  account_id: string
  full_name: string
  university_id: string | null
  timetabling_office: boolean
  departments: { id: number; code: string; name: string; role: DepartmentRoleName }[]
}

export interface Term {
  id: string
  academic_year: string
  semester: number
  start_date: string
  end_date: string
  is_current: boolean
}

export interface Department {
  id: number
  code: string
  name: string
  faculty: string | null
  cod: { id: string; full_name: string } | null
  role: DepartmentRoleName | null
}

export interface Lecturer {
  id: string
  staff_number: string | null
  full_name: string
  title: string | null
  employment_type: EmploymentType
  max_weekly_teaching_hours: number
  department: { id: number; code: string; name: string }
  is_active: boolean
  weekly_hours?: number
}

export interface Meeting {
  day_of_week: Day
  start_time: string
  end_time: string
  room: { id: string; code: string; capacity: number }
  session_key: string | null
}

export interface ClassRow {
  program_id: number | null
  program_code: string | null
  program_name: string | null
  program_department_id: number | null
  year_of_study: number
  study_semester: number | null
  stream: string
}

export interface AllocationMeta {
  lecturer_id: string | null
  lecturer_name: string | null
  employment_type: EmploymentType | null
  lecture_hours: number | null
  practical_hours: number | null
  cf_hours: number | null
  entered_by: string
  entered_at: string
  synced_to_smarttt_at: string | null
  status: 'saved' | 'submitted'
}

export type SectionState = 'allocated' | 'outstanding' | 'unmatched' | 'conflict'

export interface Section {
  key: string
  code: string
  group: string | null
  unit: { id: number; code: string; name: string; credit_hours: number; department_id: number }
  class_rows: ClassRow[]
  meetings: Meeting[]
  weekly_hours: number
  registered_students: number
  lecturer: Lecturer | null
  lecturer_conflict: boolean
  lecturer_name_text: string
  state: SectionState
  servicing: boolean
  allocation: AllocationMeta | null
}

export interface Submission {
  submitted_by: string
  submitted_at: string
  section_count: number
  allocated_count: number
  superseded_at: string | null
  is_current: boolean
}

export interface Summary {
  sections: number
  allocated: number
  outstanding: number
  conflicts: number
}

export interface Board {
  term: Term
  department_id: number
  role: DepartmentRoleName | null
  can_allocate: boolean
  can_submit: boolean
  sections: Section[]
  summary: Summary
  submission: Submission | null
}

export interface Period {
  day_of_week: Day
  start_time: string
  end_time: string
  reason: string
}

export interface Candidate {
  lecturer: Lecturer
  free: boolean
  current: boolean
  weekly_hours: number
  weekly_hours_after: number
  clashes: { day_of_week: Day; start_time: string; end_time: string; clashes_with: string }[]
  unavailable: { day_of_week: Day; start_time: string; end_time: string; reason: string }[]
  over_limit: boolean
}

export interface Candidates {
  term: Term
  section: Section
  candidates: Candidate[]
}

export interface DepartmentLecturer extends Lecturer {
  classes: string[]
  unavailable: Period[]
}

export interface ProgressRow extends Summary {
  department: Department
  department_id: number
  submission: Submission | null
}

export interface ApiErrorBody {
  message: string
  code?: string
  details?: unknown
}
