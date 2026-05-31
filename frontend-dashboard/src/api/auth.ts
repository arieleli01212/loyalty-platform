import { apiFetch, setTokens } from './client'
import type { AuthTokens } from './types'

export async function register(
  email: string,
  password: string,
  businessName: string,
): Promise<AuthTokens> {
  const data = await apiFetch<AuthTokens>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, business_name: businessName }),
  })
  setTokens(data.access_token, data.refresh_token)
  return data
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const data = await apiFetch<AuthTokens>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setTokens(data.access_token, data.refresh_token)
  return data
}
