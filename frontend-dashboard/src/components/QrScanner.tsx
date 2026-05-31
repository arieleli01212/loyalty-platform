import { useEffect, useRef, useCallback } from 'react'
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode'

interface Props {
  onScan: (text: string) => void
  paused: boolean
}

const SCANNER_ID = 'qr-reader'

export default function QrScanner({ onScan, paused }: Props) {
  const scannerRef = useRef<Html5Qrcode | null>(null)
  const startedRef = useRef(false)
  const onScanRef = useRef(onScan)
  onScanRef.current = onScan

  const startCamera = useCallback(async () => {
    if (startedRef.current) return
    try {
      const scanner = scannerRef.current!
      await scanner.start(
        { facingMode: 'environment' },
        {
          fps: 10,
          qrbox: { width: 260, height: 260 },
          aspectRatio: 1.0,
        },
        (decodedText) => {
          onScanRef.current(decodedText)
        },
        () => {
          // scan error — ignore, normal when no QR in view
        },
      )
      startedRef.current = true
    } catch (err) {
      console.error('Failed to start camera:', err)
    }
  }, [])

  const stopCamera = useCallback(async () => {
    if (!startedRef.current) return
    try {
      await scannerRef.current?.stop()
      startedRef.current = false
    } catch (err) {
      console.error('Failed to stop camera:', err)
    }
  }, [])

  useEffect(() => {
    scannerRef.current = new Html5Qrcode(SCANNER_ID, {
      formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
      verbose: false,
    })
    startCamera()
    return () => {
      stopCamera()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (paused) {
      stopCamera()
    } else {
      startCamera()
    }
  }, [paused, startCamera, stopCamera])

  return (
    <div className="relative w-full overflow-hidden rounded-2xl bg-black">
      <div id={SCANNER_ID} className="w-full" />
      {/* Overlay corners */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="relative h-64 w-64">
          <span className="absolute left-0 top-0 h-8 w-8 border-l-4 border-t-4 border-blue-400 rounded-tl-lg" />
          <span className="absolute right-0 top-0 h-8 w-8 border-r-4 border-t-4 border-blue-400 rounded-tr-lg" />
          <span className="absolute bottom-0 left-0 h-8 w-8 border-b-4 border-l-4 border-blue-400 rounded-bl-lg" />
          <span className="absolute bottom-0 right-0 h-8 w-8 border-b-4 border-r-4 border-blue-400 rounded-br-lg" />
        </div>
      </div>
      {paused && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60">
          <p className="text-lg font-semibold text-slate-300">Camera paused</p>
        </div>
      )}
    </div>
  )
}
