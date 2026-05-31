import React, { useEffect, useState } from 'react'
import { listPrograms, createProgram, updateProgram } from '../api/programs'
import type { Program } from '../api/types'

interface ProgramFormData {
  name: string
  stamps_required: number
  reward_description: string
}

function ProgramForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<ProgramFormData>
  onSave: (data: ProgramFormData) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [stampsRequired, setStampsRequired] = useState(initial?.stamps_required ?? 10)
  const [rewardDescription, setRewardDescription] = useState(initial?.reward_description ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await onSave({ name, stamps_required: stampsRequired, reward_description: rewardDescription })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-5 bg-gray-50 rounded-xl border border-gray-200">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Program Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Coffee Loyalty"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Stamps Required</label>
        <input
          type="number"
          min={1}
          max={100}
          value={stampsRequired}
          onChange={(e) => setStampsRequired(parseInt(e.target.value, 10))}
          required
          className="w-32 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Reward Description</label>
        <input
          value={rewardDescription}
          onChange={(e) => setRewardDescription(e.target.value)}
          required
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Free coffee after 10 stamps"
        />
      </div>

      {error && (
        <p className="text-red-600 text-sm">{error}</p>
      )}

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={saving}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-gray-600 hover:text-gray-900 text-sm font-medium px-5 py-2 rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

export function ProgramsPage() {
  const [programs, setPrograms] = useState<Program[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      const data = await listPrograms()
      setPrograms(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function handleCreate(data: ProgramFormData) {
    const prog = await createProgram({ ...data, type: 'stamp' })
    setPrograms((prev) => [...prev, prog])
    setShowCreate(false)
  }

  async function handleUpdate(id: number, data: ProgramFormData) {
    const updated = await updateProgram(id, data)
    setPrograms((prev) => prev.map((p) => (p.id === id ? updated : p)))
    setEditingId(null)
  }

  async function handleToggleActive(program: Program) {
    const updated = await updateProgram(program.id, { active: !program.active })
    setPrograms((prev) => prev.map((p) => (p.id === program.id ? updated : p)))
  }

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Reward Programs</h1>
        {!showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            + New Program
          </button>
        )}
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {showCreate && (
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">New Program</h2>
          <ProgramForm
            onSave={handleCreate}
            onCancel={() => setShowCreate(false)}
          />
        </div>
      )}

      <div className="space-y-4">
        {programs.length === 0 && !showCreate && (
          <p className="text-gray-400 text-sm">No programs yet. Create one above.</p>
        )}
        {programs.map((prog) => (
          <div key={prog.id} className="bg-white rounded-xl border border-gray-100 shadow-sm p-5">
            {editingId === prog.id ? (
              <ProgramForm
                initial={{
                  name: prog.name,
                  stamps_required: prog.stamps_required,
                  reward_description: prog.reward_description,
                }}
                onSave={(data) => handleUpdate(prog.id, data)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{prog.name}</h3>
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        prog.active
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {prog.active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    {prog.stamps_required} stamps → {prog.reward_description}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => setEditingId(prog.id)}
                    className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => void handleToggleActive(prog)}
                    className="text-gray-500 hover:text-gray-800 text-sm font-medium"
                  >
                    {prog.active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

