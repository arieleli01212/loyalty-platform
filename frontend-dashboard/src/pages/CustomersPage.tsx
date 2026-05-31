import { useEffect, useState } from 'react'
import { listCustomers, type CustomerFilter } from '../api/analytics'
import type { CustomerListItem } from '../api/types'

const FILTERS: { value: CustomerFilter; label: string }[] = [
  { value: undefined, label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'drifting', label: 'Drifting' },
  { value: 'top', label: 'Top Customers' },
]

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function StatusBadge({ status }: { status: CustomerListItem['status'] }) {
  if (!status) return <span className="text-gray-400">—</span>
  const styles: Record<string, string> = {
    active: 'bg-green-100 text-green-700',
    suspended: 'bg-red-100 text-red-700',
    expired: 'bg-gray-100 text-gray-500',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[status] ?? ''}`}>
      {status}
    </span>
  )
}

export function CustomersPage() {
  const [filter, setFilter] = useState<CustomerFilter>(undefined)
  const [customers, setCustomers] = useState<CustomerListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const LIMIT = 50

  useEffect(() => {
    setLoading(true)
    setError(null)
    listCustomers(filter, LIMIT, offset)
      .then(setCustomers)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [filter, offset])

  function handleFilterChange(f: CustomerFilter) {
    setFilter(f)
    setOffset(0)
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Customers</h1>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {FILTERS.map((f) => (
          <button
            key={String(f.value)}
            onClick={() => handleFilterChange(f.value)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              filter === f.value
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : customers.length === 0 ? (
        <p className="text-gray-400 text-sm">No customers found.</p>
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left">
                <th className="px-4 py-3 font-semibold text-gray-600">Name</th>
                <th className="px-4 py-3 font-semibold text-gray-600">Contact</th>
                <th className="px-4 py-3 font-semibold text-gray-600">Channel</th>
                <th className="px-4 py-3 font-semibold text-gray-600 text-right">Stamps</th>
                <th className="px-4 py-3 font-semibold text-gray-600 text-right">Rewards</th>
                <th className="px-4 py-3 font-semibold text-gray-600">Last Activity</th>
                <th className="px-4 py-3 font-semibold text-gray-600">Status</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.customer_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                  <td className="px-4 py-3 text-gray-500">
                    <span className="text-xs text-gray-400 mr-1">[{c.contact_type}]</span>
                    {c.contact}
                  </td>
                  <td className="px-4 py-3">
                    <span className="bg-indigo-50 text-indigo-700 text-xs px-2 py-0.5 rounded-full">
                      {c.enrollment_channel}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {c.current_stamps ?? '—'}
                    {c.lifetime_stamps != null && (
                      <span className="text-gray-400 text-xs ml-1">/ {c.lifetime_stamps} lifetime</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    {c.rewards_available ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(c.last_activity_at)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {!loading && customers.length > 0 && (
        <div className="flex items-center gap-3 mt-4">
          <button
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
            className="text-sm text-indigo-600 hover:text-indigo-800 disabled:text-gray-300 font-medium"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500">
            Showing {offset + 1}–{offset + customers.length}
          </span>
          <button
            disabled={customers.length < LIMIT}
            onClick={() => setOffset((o) => o + LIMIT)}
            className="text-sm text-indigo-600 hover:text-indigo-800 disabled:text-gray-300 font-medium"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
