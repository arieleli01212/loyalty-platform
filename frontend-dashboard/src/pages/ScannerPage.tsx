import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { v4 as uuidv4 } from 'uuid'
import { useAuth } from '../contexts/AuthContext'
import { scan, ScanAction, ScanResponse } from '../api/scan'
import QrScanner from '../components/QrScanner'

type ScanState =
  | { kind: 'scanning' }
  | { kind: 'loading' }
  | { kind: 'success'; result: ScanResponse }
  | { kind: 'error'; message: string }

const AUTO_RESUME_MS = 4000

export function ScannerPage() {
  const { logout, role } = useAuth()
  const navigate = useNavigate()
  const [action, setAction] = useState<ScanAction>('stamp')
  const [state, setState] = useState<ScanState>({ kind: 'scanning' })
  const autoResumeRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearAutoResume = () => {
    if (autoResumeRef.current !== null) {
      clearTimeout(autoResumeRef.current)
      autoResumeRef.current = null
    }
  }

  const resumeScanning = useCallback(() => {
    clearAutoResume()
    setState({ kind: 'scanning' })
  }, [])

  const handleLogout = useCallback(() => {
    clearAutoResume()
    logout()
    navigate('/login')
  }, [logout, navigate])

  const handleScan = useCallback(
    async (barcodeToken: string) => {
      setState((prev) => {
        if (prev.kind !== 'scanning') return prev
        return { kind: 'loading' }
      })

      const idempotencyKey = uuidv4()
      try {
        const result = await scan(barcodeToken, action, idempotencyKey)
        setState({ kind: 'success', result })
        clearAutoResume()
        autoResumeRef.current = setTimeout(resumeScanning, AUTO_RESUME_MS)
      } catch (err) {
        const msg = errorMessage(err)
        setState({ kind: 'error', message: msg })
        clearAutoResume()
        autoResumeRef.current = setTimeout(resumeScanning, AUTO_RESUME_MS)
      }
    },
    [action, resumeScanning],
  )

  useEffect(() => () => clearAutoResume(), [])

  const paused = state.kind !== 'scanning'

  return (
    <div className="flex min-h-screen flex-col bg-slate-900">
      <header className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 font-bold text-white text-lg">
            L
          </div>
          <h1 className="text-lg font-semibold text-white">Loyalty Scanner</h1>
        </div>
        <div className="flex items-center gap-3">
          {role === 'owner' && (
            <button
              onClick={() => navigate('/')}
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-700 transition"
            >
              Dashboard
            </button>
          )}
          <button
            onClick={handleLogout}
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-700 transition"
          >
            Logout
          </button>
        </div>
      </header>

      <div className="px-4 pt-5 pb-2">
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">Mode</p>
        <div className="flex gap-3">
          <button
            onClick={() => setAction('stamp')}
            className={`flex-1 rounded-2xl py-5 text-xl font-bold transition ${
              action === 'stamp'
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            ☕ Stamp
          </button>
          <button
            onClick={() => setAction('redeem')}
            className={`flex-1 rounded-2xl py-5 text-xl font-bold transition ${
              action === 'redeem'
                ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/30'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            🎁 Redeem
          </button>
        </div>
      </div>

      <div className="px-4 pt-3 pb-2">
        <QrScanner onScan={handleScan} paused={paused} />
      </div>

      {state.kind === 'scanning' && (
        <p className="text-center text-sm text-slate-500 pb-2">
          Point the camera at a customer&apos;s QR code
        </p>
      )}

      {state.kind === 'loading' && (
        <div className="mx-4 mt-3 rounded-2xl bg-slate-800 border border-slate-700 px-6 py-6 text-center">
          <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
          <p className="text-slate-300 font-medium">Processing…</p>
        </div>
      )}

      {state.kind === 'success' && (
        <SuccessCard result={state.result} action={action} onNext={resumeScanning} />
      )}

      {state.kind === 'error' && (
        <ErrorCard message={state.message} onNext={resumeScanning} />
      )}
    </div>
  )
}

function errorMessage(err: unknown): string {
  if (err instanceof Error) {
    const text = err.message
    if (text.includes('429')) return 'Too soon — wait before stamping again'
    if (text.includes('400')) return 'No reward available to redeem'
    if (text.includes('404')) return 'Card not recognized'
    if (text.includes('403')) return 'Card belongs to another business'
  }
  return 'Unexpected error — please try again'
}

function SuccessCard({
  result,
  action,
  onNext,
}: {
  result: ScanResponse
  action: ScanAction
  onNext: () => void
}) {
  return (
    <div className="mx-4 mt-3 rounded-2xl border border-emerald-700 bg-emerald-900/40 px-6 py-6">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-600 text-3xl shadow-lg shadow-emerald-600/40">
        {action === 'stamp' ? '☕' : '🎁'}
      </div>
      <h2 className="text-center text-2xl font-bold text-emerald-400 mb-1">
        {action === 'stamp' ? 'Stamped!' : 'Redeemed!'}
      </h2>
      <p className="text-center text-slate-300 text-base mb-5">{result.message}</p>
      <div className="flex gap-3 mb-6">
        <div className="flex-1 rounded-xl bg-slate-800 py-4 text-center">
          <p className="text-3xl font-bold text-white">{result.current_stamps}</p>
          <p className="text-xs text-slate-400 mt-1">Current Stamps</p>
        </div>
        <div className="flex-1 rounded-xl bg-slate-800 py-4 text-center">
          <p className="text-3xl font-bold text-emerald-400">{result.rewards_available}</p>
          <p className="text-xs text-slate-400 mt-1">Rewards Ready</p>
        </div>
        <div className="flex-1 rounded-xl bg-slate-800 py-4 text-center">
          <p className="text-3xl font-bold text-blue-400">{result.lifetime_stamps}</p>
          <p className="text-xs text-slate-400 mt-1">Lifetime</p>
        </div>
      </div>
      <button
        onClick={onNext}
        className="w-full rounded-xl bg-emerald-600 py-4 text-lg font-semibold text-white hover:bg-emerald-500 transition"
      >
        Scan next
      </button>
    </div>
  )
}

function ErrorCard({ message, onNext }: { message: string; onNext: () => void }) {
  return (
    <div className="mx-4 mt-3 rounded-2xl border border-red-700 bg-red-900/40 px-6 py-6">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-600 text-3xl shadow-lg shadow-red-600/40">
        ✕
      </div>
      <h2 className="text-center text-2xl font-bold text-red-400 mb-2">Error</h2>
      <p className="text-center text-slate-300 text-base mb-6">{message}</p>
      <button
        onClick={onNext}
        className="w-full rounded-xl bg-slate-700 py-4 text-lg font-semibold text-white hover:bg-slate-600 transition"
      >
        Try again
      </button>
    </div>
  )
}
