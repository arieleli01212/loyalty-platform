import React, { useEffect, useState } from 'react'
import { getBusiness, updateBusiness } from '../api/business'
import type { Business } from '../api/types'

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <div className="flex items-center gap-3">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-10 h-10 rounded border border-gray-300 cursor-pointer"
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-32 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
          pattern="^#[0-9A-Fa-f]{6}$"
        />
      </div>
    </div>
  )
}

interface CardPreviewProps {
  name: string
  bgColor: string
  fgColor: string
  labelColor: string
  logoUrl: string | null
}

function CardPreview({ name, bgColor, fgColor, labelColor, logoUrl }: CardPreviewProps) {
  return (
    <div
      className="rounded-2xl shadow-lg p-6 w-80 relative overflow-hidden"
      style={{ backgroundColor: bgColor, color: fgColor }}
    >
      <div className="flex items-center justify-between mb-4">
        {logoUrl ? (
          <img src={logoUrl} alt="Logo" className="h-10 object-contain" />
        ) : (
          <div
            className="text-lg font-bold"
            style={{ color: fgColor }}
          >
            {name || 'Your Business'}
          </div>
        )}
        <div
          className="text-xs font-medium px-2 py-1 rounded"
          style={{ color: labelColor, borderColor: labelColor, border: '1px solid' }}
        >
          Loyalty Card
        </div>
      </div>

      <div className="mt-4 flex gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="w-7 h-7 rounded-full border-2"
            style={{ borderColor: labelColor, backgroundColor: i < 3 ? labelColor : 'transparent' }}
          />
        ))}
      </div>

      <div className="mt-4 text-xs" style={{ color: labelColor }}>
        3 / 8 stamps
      </div>
    </div>
  )
}

export function BrandingPage() {
  const [business, setBusiness] = useState<Business | null>(null)
  const [name, setName] = useState('')
  const [logoUrl, setLogoUrl] = useState('')
  const [bgColor, setBgColor] = useState('#FFFFFF')
  const [fgColor, setFgColor] = useState('#000000')
  const [labelColor, setLabelColor] = useState('#000000')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getBusiness().then((b) => {
      setBusiness(b)
      setName(b.name)
      setLogoUrl(b.logo_url ?? '')
      setBgColor(b.bg_color)
      setFgColor(b.fg_color)
      setLabelColor(b.label_color)
    })
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await updateBusiness({
        name,
        logo_url: logoUrl || null,
        bg_color: bgColor,
        fg_color: fgColor,
        label_color: labelColor,
      })
      setBusiness(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (!business) return <div className="p-8 text-gray-500">Loading…</div>

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Branding Editor</h1>

      <div className="flex flex-col lg:flex-row gap-10">
        {/* Form */}
        <form onSubmit={handleSave} className="flex-1 space-y-5 max-w-md">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Business Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Logo URL</label>
            <input
              type="url"
              value={logoUrl}
              onChange={(e) => setLogoUrl(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="https://example.com/logo.png"
            />
          </div>

          <ColorField label="Background Color" value={bgColor} onChange={setBgColor} />
          <ColorField label="Foreground / Text Color" value={fgColor} onChange={setFgColor} />
          <ColorField label="Label / Accent Color" value={labelColor} onChange={setLabelColor} />

          {error && (
            <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {saved && (
            <p className="text-green-700 text-sm bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              Saved successfully!
            </p>
          )}

          <button
            type="submit"
            disabled={saving}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium px-6 py-2 rounded-lg transition-colors"
          >
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </form>

        {/* Live preview */}
        <div>
          <p className="text-sm font-medium text-gray-600 mb-3">Live Preview</p>
          <CardPreview
            name={name}
            bgColor={bgColor}
            fgColor={fgColor}
            labelColor={labelColor}
            logoUrl={logoUrl || null}
          />
        </div>
      </div>
    </div>
  )
}
