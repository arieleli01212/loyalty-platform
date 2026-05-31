import { apiFetch, apiFetchBlob, API_BASE, getAccessToken } from './client'
import type { AnalyticsSummary, CustomerListItem } from './types'

export async function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return apiFetch<AnalyticsSummary>('/api/v1/analytics/summary')
}

export type CustomerFilter = 'active' | 'drifting' | 'top' | undefined

export async function listCustomers(
  filter?: CustomerFilter,
  limit = 100,
  offset = 0,
): Promise<CustomerListItem[]> {
  const params = new URLSearchParams()
  if (filter) params.set('filter', filter)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return apiFetch<CustomerListItem[]>(`/api/v1/customers?${params.toString()}`)
}

export async function getEnrollmentQrBlob(): Promise<Blob> {
  return apiFetchBlob('/api/v1/enrollment-qr')
}

export function getEnrollmentQrPdfUrl(): string {
  const token = getAccessToken()
  return `${API_BASE}/api/v1/enrollment-qr?format=pdf${token ? `&token=${token}` : ''}`
}
