import type { ClassRow, Day, EmploymentType, Meeting } from './types'

export const DAYS: Day[] = ['MON', 'TUE', 'WED', 'THU', 'FRI']
const DAY_NAMES: Record<Day, string> = { MON: 'Mon', TUE: 'Tue', WED: 'Wed', THU: 'Thu', FRI: 'Fri' }

export const dayName = (d: Day) => DAY_NAMES[d] ?? d

export const meetingText = (m: Pick<Meeting, 'day_of_week' | 'start_time' | 'end_time'>) =>
  `${dayName(m.day_of_week)} ${m.start_time}–${m.end_time}`

export const classRowText = (r: ClassRow) => {
  const sem = r.study_semester ? `S${r.study_semester}` : ''
  const stream = r.stream ? ` (${r.stream})` : ''
  return `${r.program_code ?? r.program_name ?? 'Unknown'} Y${r.year_of_study}${sem}${stream}`
}

export const employment = (t: EmploymentType | null | undefined) =>
  t === 'part_time' ? 'PT' : t === 'full_time' ? 'FT' : ''

export const termText = (t: { academic_year: string; semester: number }) => `${t.academic_year} · Semester ${t.semester}`

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-KE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Nairobi' })
