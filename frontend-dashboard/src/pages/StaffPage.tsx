import { useEffect, useState, FormEvent } from 'react'
import { listStaff, createStaff, deleteStaff, StaffMember } from '../api/staff'

export function StaffPage() {
  const [staff, setStaff] = useState<StaffMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  useEffect(() => {
    listStaff()
      .then(setStaff)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    setAddError(null)
    setAdding(true)
    try {
      const member = await createStaff(email, password)
      setStaff((prev) => [...prev, member])
      setEmail('')
      setPassword('')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create'
      setAddError(msg.includes('409') ? 'Email already in use' : msg)
    } finally {
      setAdding(false)
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteStaff(id)
      setStaff((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete')
    }
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Staff Accounts</h1>

      {/* Add staff form */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-8">
        <h2 className="text-base font-semibold text-gray-700 mb-4">Add Staff Member</h2>
        <form onSubmit={handleAdd} className="flex flex-col gap-3">
          <div className="flex gap-3">
            <input
              type="email"
              required
              placeholder="staff@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <input
              type="password"
              required
              minLength={8}
              placeholder="Password (min 8 chars)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="submit"
              disabled={adding}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60 transition"
            >
              {adding ? 'Adding…' : 'Add'}
            </button>
          </div>
          {addError && (
            <p className="text-sm text-red-600">{addError}</p>
          )}
        </form>
      </div>

      {/* Staff list */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-700">Current Staff</h2>
        </div>

        {loading && <p className="px-6 py-4 text-sm text-gray-400">Loading…</p>}
        {error && <p className="px-6 py-4 text-sm text-red-600">{error}</p>}
        {!loading && !error && staff.length === 0 && (
          <p className="px-6 py-4 text-sm text-gray-400">No staff accounts yet.</p>
        )}

        {staff.map((member) => (
          <div
            key={member.id}
            className="flex items-center justify-between px-6 py-4 border-b border-gray-50 last:border-0"
          >
            <div>
              <p className="text-sm font-medium text-gray-900">{member.email}</p>
              <p className="text-xs text-gray-400 mt-0.5">
                Added {new Date(member.created_at).toLocaleDateString()}
              </p>
            </div>
            <button
              onClick={() => handleDelete(member.id)}
              className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition"
            >
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
