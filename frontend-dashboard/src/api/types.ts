export interface AuthTokens {
  access_token: string
  refresh_token: string
}

export interface Business {
  id: number
  name: string
  slug: string
  owner_user_id: number
  logo_url: string | null
  bg_color: string
  fg_color: string
  label_color: string
  created_at: string
}

export interface BusinessUpdate {
  name?: string
  logo_url?: string | null
  bg_color?: string
  fg_color?: string
  label_color?: string
}

export interface Program {
  id: number
  business_id: number
  name: string
  type: string
  stamps_required: number
  reward_description: string
  active: boolean
  created_at: string
}

export interface ProgramCreate {
  name: string
  type: string
  stamps_required: number
  reward_description: string
}

export interface ProgramUpdate {
  name?: string
  stamps_required?: number
  reward_description?: string
  active?: boolean
}

export interface AnalyticsSummary {
  total_customers: number
  total_cards: number
  total_installs: number
  stamps_issued: number
  rewards_redeemed: number
  active_customers: number
  drifting_customers: number
  channel_breakdown: Record<string, number>
}

export interface CustomerListItem {
  customer_id: number
  name: string
  contact: string
  contact_type: 'email' | 'phone'
  enrolled_at: string
  enrollment_channel: string
  current_stamps: number | null
  rewards_available: number | null
  lifetime_stamps: number | null
  last_activity_at: string | null
  status: 'active' | 'suspended' | 'expired' | null
}
