import { apiFetch } from './client'
import type { Program, ProgramCreate, ProgramUpdate } from './types'

export async function listPrograms(): Promise<Program[]> {
  return apiFetch<Program[]>('/api/v1/programs')
}

export async function createProgram(data: ProgramCreate): Promise<Program> {
  return apiFetch<Program>('/api/v1/programs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateProgram(id: number, data: ProgramUpdate): Promise<Program> {
  return apiFetch<Program>(`/api/v1/programs/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}
