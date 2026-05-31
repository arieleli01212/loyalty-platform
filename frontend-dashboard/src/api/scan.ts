import { apiFetch } from './client'

export type ScanAction = 'stamp' | 'redeem'

export interface ScanResponse {
  card_id: string
  current_stamps: number
  rewards_available: number
  lifetime_stamps: number
  action: string
  message: string
}

export async function scan(
  barcodeToken: string,
  action: ScanAction,
  idempotencyKey: string,
): Promise<ScanResponse> {
  return apiFetch<ScanResponse>('/api/v1/scan', {
    method: 'POST',
    headers: { 'X-Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ barcode_token: barcodeToken, action }),
  })
}
