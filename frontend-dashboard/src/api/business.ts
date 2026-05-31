import { apiFetch } from './client'
import type { Business, BusinessUpdate } from './types'

export async function getBusiness(): Promise<Business> {
  return apiFetch<Business>('/api/v1/business')
}

export async function updateBusiness(data: BusinessUpdate): Promise<Business> {
  return apiFetch<Business>('/api/v1/business', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}
