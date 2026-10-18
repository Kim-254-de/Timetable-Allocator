import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AllocatePanel } from './AllocatePanel'
import { fail, fakeApi, ok } from '@/test/fakeApi'
import type { Candidate, Lecturer, Section } from '@/lib/types'

const lecturer = (id: string, name: string): Lecturer => ({
  id, staff_number: id, full_name: name, title: 'Dr.', employment_type: 'full_time', max_weekly_teaching_hours: 12,
  department: { id: 1, code: 'CS', name: 'Computer Science' }, is_active: true,
})

const section: Section = {
  key: '412-GRA', code: 'COSC 103 GR A', group: 'GR A',
  unit: { id: 412, code: 'COSC 103', name: 'Intro to Computing', credit_hours: 3, department_id: 1 },
  class_rows: [{ program_id: 1, program_code: 'BED.MATH/CHEM', program_name: 'BEd', program_department_id: 2,
    year_of_study: 1, study_semester: 1, stream: '' }],
  meetings: [{ day_of_week: 'TUE', start_time: '10:00', end_time: '12:00', room: { id: 'r', code: 'STB 1', capacity: 150 }, session_key: null }],
  weekly_hours: 2, registered_students: 148, lecturer: null, lecturer_conflict: false, lecturer_name_text: '',
  state: 'outstanding', servicing: true, allocation: null,
}

const candidate = (l: Lecturer, extra: Partial<Candidate> = {}): Candidate => ({
  lecturer: l, free: true, current: false, weekly_hours: 4, weekly_hours_after: 6, clashes: [], unavailable: [],
  over_limit: false, ...extra,
})

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <AllocatePanel section={section} departmentId={1} term={undefined} canAllocate onClose={() => {}} />
    </QueryClientProvider>,
  )
}

describe('AllocatePanel', () => {
  it('explains why busy lecturers cannot be picked and saves the chosen one', async () => {
    const jane = lecturer('aaaaaaaa-0000-0000-0000-000000000001', 'Jane Otieno')
    const collins = lecturer('aaaaaaaa-0000-0000-0000-000000000002', 'Collins Mwangi')
    const calls = fakeApi({
      'GET /sessions/412-GRA/free-lecturers': ok({
        term: {}, section,
        candidates: [
          candidate(collins),
          candidate(jane, { free: false, clashes: [{ day_of_week: 'TUE', start_time: '10:00', end_time: '12:00', clashes_with: 'COSC 103 GR B' }] }),
        ],
      }),
      'PUT /sessions/412-GRA/allocation': ok({ section: { ...section, lecturer: collins } }),
    })
    renderPanel()

    expect(await screen.findByText(/Teaches COSC 103 GR B Tue 10:00–12:00/)).toBeInTheDocument()
    const radios = screen.getAllByRole('radio')
    expect(radios[1]).toBeDisabled()

    await userEvent.click(radios[0])
    await userEvent.click(screen.getByRole('button', { name: 'Save allocation' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    const put = calls.find((c) => c.method === 'PUT')!
    expect(put.data).toMatchObject({ lecturer_id: collins.id, expected_lecturer_id: null })
  })

  it('shows SMARTTT refusing a double booking', async () => {
    const collins = lecturer('aaaaaaaa-0000-0000-0000-000000000002', 'Collins Mwangi')
    fakeApi({
      'GET /sessions/412-GRA/free-lecturers': ok({ term: {}, section, candidates: [candidate(collins)] }),
      'PUT /sessions/412-GRA/allocation': fail(409, 'LECTURER_CLASH', 'Collins Mwangi already teaches at this time.',
        { clashes: [{ clashes_with: 'EDFO 111' }] }),
    })
    renderPanel()
    await userEvent.click(await screen.findByRole('radio'))
    await userEvent.click(screen.getByRole('button', { name: 'Save allocation' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already teaches at this time')
    expect(screen.getByRole('alert')).toHaveTextContent('Clashes with EDFO 111')
  })
})
