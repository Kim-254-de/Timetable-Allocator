import { api, errorCode, errorMessage } from './api'
import { fail, fakeApi, ok } from '@/test/fakeApi'

describe('api envelope', () => {
  it('unwraps success data', async () => {
    fakeApi({ 'GET /terms': ok([{ id: 't1' }]) })
    const res = await api.get('/terms')
    expect(res.data).toEqual([{ id: 't1' }])
  })

  it('turns error envelopes into code + message', async () => {
    fakeApi({ 'PUT /x': fail(409, 'LECTURER_CLASH', 'Jane already teaches then.') })
    const err = await api.put('/x', {}).catch((e: unknown) => e)
    expect(errorCode(err)).toBe('LECTURER_CLASH')
    expect(errorMessage(err)).toBe('Jane already teaches then.')
  })
})
