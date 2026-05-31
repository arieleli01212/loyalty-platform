import { useEffect, useState } from 'react'
import { getEnrollmentQrBlob, getEnrollmentQrPdfUrl } from '../api/analytics'

export function EnrollmentQrPage() {
  const [imgSrc, setImgSrc] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getEnrollmentQrBlob()
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        setImgSrc(url)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load QR'))
      .finally(() => setLoading(false))

    return () => {
      if (imgSrc) URL.revokeObjectURL(imgSrc)
    }
    // intentionally run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Enrollment QR Code</h1>
      <p className="text-gray-500 text-sm mb-6">
        Print and display this QR code for customers to enroll in your loyalty program.
      </p>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 inline-block">
        {loading && <p className="text-gray-400">Loading QR code…</p>}
        {error && <p className="text-red-600">{error}</p>}
        {imgSrc && (
          <img
            src={imgSrc}
            alt="Enrollment QR Code"
            className="max-w-xs"
          />
        )}
      </div>

      {imgSrc && (
        <div className="mt-6 flex gap-3">
          <a
            href={imgSrc}
            download="enrollment-qr.png"
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors inline-block"
          >
            Download PNG
          </a>
          <a
            href={getEnrollmentQrPdfUrl()}
            target="_blank"
            rel="noopener noreferrer"
            className="border border-indigo-600 text-indigo-600 hover:bg-indigo-50 text-sm font-medium px-5 py-2 rounded-lg transition-colors inline-block"
          >
            Download PDF
          </a>
        </div>
      )}
    </div>
  )
}
