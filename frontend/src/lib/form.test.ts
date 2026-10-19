import { splitTyped } from './form'

describe('splitTyped', () => {
  it('reads a title, name and FT/PT as typed in the lecturer box', () => {
    expect(splitTyped('Dr. Jane Otieno (PT)')).toEqual({ title: 'Dr.', full_name: 'Jane Otieno', employment_type: 'part_time' })
    expect(splitTyped('prof Peter Kamau')).toEqual({ title: 'Prof.', full_name: 'Peter Kamau', employment_type: 'full_time' })
  })

  it('defaults to Dr. and full time when only a name is typed', () => {
    expect(splitTyped('  Jane  ')).toEqual({ title: 'Dr.', full_name: 'Jane', employment_type: 'full_time' })
  })
})
