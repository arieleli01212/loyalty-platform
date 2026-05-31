import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { getAnalyticsSummary } from '../api/analytics'
import type { AnalyticsSummary } from '../api/types'

interface StatCardProps {
  label: string
  value: number | string
  sub?: string
  color?: string
}

function StatCard({ label, value, sub, color = 'bg-white' }: StatCardProps) {
  return (
    <div className={`${color} rounded-xl shadow-sm border border-gray-100 p-5`}>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-bold text-gray-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

export function DashboardPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAnalyticsSummary()
      .then(setSummary)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="p-8 text-gray-500">Loading analytics…</div>
    )
  }

  if (error || !summary) {
    return (
      <div className="p-8 text-red-600">Error: {error ?? 'No data'}</div>
    )
  }

  const channelData = Object.entries(summary.channel_breakdown).map(([name, count]) => ({
    name,
    count,
  }))

  const BAR_COLORS = [
    '#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6',
  ]

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Analytics Overview</h1>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Customers" value={summary.total_customers} />
        <StatCard label="Total Cards" value={summary.total_cards} />
        <StatCard label="Wallet Installs" value={summary.total_installs} />
        <StatCard label="Stamps Issued" value={summary.stamps_issued} />
        <StatCard label="Rewards Redeemed" value={summary.rewards_redeemed} />
        <StatCard
          label="Active Customers"
          value={summary.active_customers}
          sub="activity in last 30 days"
          color="bg-green-50"
        />
        <StatCard
          label="Drifting Customers"
          value={summary.drifting_customers}
          sub="no activity in 30+ days"
          color="bg-amber-50"
        />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-base font-semibold text-gray-700 mb-4">Enrollment Channel Breakdown</h2>
        {channelData.length === 0 ? (
          <p className="text-gray-400 text-sm">No enrollment data yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={channelData} margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {channelData.map((_entry, index) => (
                  <Cell key={`cell-${index}`} fill={BAR_COLORS[index % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
