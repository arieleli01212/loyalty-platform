import { apiFetch } from './client'

export interface StaffMember {
  id: number
  email: string
  role: string
  created_at: string
}

export function listStaff(): Promise<StaffMember[]> {
  return apiFetch<StaffMember[]>('/api/v1/business/staff')
}

export function createStaff(email: string, password: string): Promise<StaffMember> {
  return apiFetch<StaffMember>('/api/v1/business/staff', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function deleteStaff(userId: number): Promise<void> {
  return apiFetch<void>(`/api/v1/business/staff/${userId}`, { method: 'DELETE' })
}
