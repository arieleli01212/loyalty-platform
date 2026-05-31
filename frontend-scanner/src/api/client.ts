const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface ScanResponse {
  card_id: string
  current_stamps: number
  rewards_available: number
  lifetime_stamps: number
  action: string
  message: string
}

export type ScanAction = 'stamp' | 'redeem'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class NetworkError extends Error {
  constructor() {
    super('Network error — check your connection')
    this.name = 'NetworkError'
  }
}

function getStoredTokens(): { accessToken: string | null; refreshToken: string | null } {
  return {
    accessToken: localStorage.getItem('access_token'),
    refreshToken: localStorage.getItem('refresh_token'),
  }
}

export function storeTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem('access_token', accessToken)
  localStorage.setItem('refresh_token', refreshToken)
}

export function clearTokens(): void {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export function hasTokens(): boolean {
  return !!localStorage.getItem('access_token')
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  } catch {
    throw new NetworkError()
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || `Login failed (${res.status})`)
  }
  return res.json() as Promise<LoginResponse>
}

async function refreshAccessToken(): Promise<string> {
  const { refreshToken } = getStoredTokens()
  if (!refreshToken) throw new ApiError(401, 'No refresh token')
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
  } catch {
    throw new NetworkError()
  }
  if (!res.ok) {
    clearTokens()
    throw new ApiError(401, 'Session expired — please log in again')
  }
  const data = (await res.json()) as { access_token: string; refresh_token?: string }
  const newRefresh = data.refresh_token ?? refreshToken
  storeTokens(data.access_token, newRefresh)
  return data.access_token
}

export async function scan(
  barcodeToken: string,
  action: ScanAction,
  idempotencyKey: string,
): Promise<ScanResponse> {
  const { accessToken } = getStoredTokens()
  if (!accessToken) throw new ApiError(401, 'Not authenticated')

  const doRequest = async (token: string): Promise<Response> => {
    try {
      return await fetch(`${API_BASE}/api/v1/scan`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          'X-Idempotency-Key': idempotencyKey,
        },
        body: JSON.stringify({ barcode_token: barcodeToken, action }),
      })
    } catch {
      throw new NetworkError()
    }
  }

  let res = await doRequest(accessToken)

  if (res.status === 401) {
    // Attempt token refresh
    const newToken = await refreshAccessToken()
    res = await doRequest(newToken)
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text)
  }

  return res.json() as Promise<ScanResponse>
}
