'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Upload, FileText, Trash2, RefreshCw, CheckCircle, XCircle, Clock } from 'lucide-react'
import { useTranslation } from '@/lib/i18n'

interface Document {
  id: string
  filename: string
  status: string
  region: string
  page_count: number | null
  chunk_count: number | null
  created_at: string
  processed_at: string | null
  error_message: string | null
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function DocumentsPage() {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState<Document[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [uploadRegion, setUploadRegion] = useState('global')
  const [error, setError] = useState<string | null>(null)

  const fetchDocuments = async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/documents`)
      if (response.ok) {
        const data = await response.json()
        setDocuments(data.documents)
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err)
    }
  }

  useEffect(() => {
    fetchDocuments()
    const interval = setInterval(fetchDocuments, 5000) // Poll every 5s
    return () => clearInterval(interval)
  }, [])

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const ext = file.name.toLowerCase()
    if (!ext.endsWith('.pdf') && !ext.endsWith('.csv')) {
      setError(t['admin.pdfOnly'])
      return
    }

    setIsUploading(true)
    setError(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('region', uploadRegion)

    try {
      const response = await fetch(`${API_URL}/api/v1/documents/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Upload failed')
      }

      fetchDocuments()
    } catch (err) {
      setError(t['admin.uploadFailed'])
    } finally {
      setIsUploading(false)
      event.target.value = ''
    }
  }

  const handleDelete = async (documentId: string) => {
    if (!confirm(t['admin.deleteConfirm'])) return

    try {
      const response = await fetch(`${API_URL}/api/v1/documents/${documentId}`, {
        method: 'DELETE',
      })

      if (response.ok) {
        fetchDocuments()
      }
    } catch (err) {
      setError(t['admin.deleteFailed'])
    }
  }

  const handleReprocess = async (documentId: string) => {
    try {
      await fetch(`${API_URL}/api/v1/documents/${documentId}/reprocess`, {
        method: 'POST',
      })
      fetchDocuments()
    } catch (err) {
      setError(t['admin.reprocessFailed'])
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />
      case 'pending':
      case 'extracting':
      case 'chunking':
      case 'embedding':
        return <Clock className="h-5 w-5 text-yellow-500 animate-spin" />
      default:
        return null
    }
  }

  return (
    <div className="container py-8">
      <div className="mb-4">
        <Link
          href="/"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          &larr; {t['admin.back']}
        </Link>
      </div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">{t['admin.title']}</h1>
          <p className="text-muted-foreground mt-1">
            {t['admin.subtitle']}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={uploadRegion}
            onChange={(e) => setUploadRegion(e.target.value)}
            className="rounded-md border bg-background px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="global">{t['region.auto']} (Global)</option>
            <option value="japan">{t['region.japan']}</option>
            <option value="nepal">{t['region.nepal']}</option>
            <option value="vietnam">{t['region.vietnam']}</option>
            <option value="indonesia">{t['region.indonesia']}</option>
            <option value="philippines">{t['region.philippines']}</option>
          </select>
          <label className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-primary-foreground cursor-pointer hover:bg-primary/90 transition-colors">
            <Upload className="h-4 w-4" />
            {isUploading ? t['admin.uploading'] : t['admin.upload']}
            <input
              type="file"
              accept=".pdf,.csv"
              onChange={handleUpload}
              disabled={isUploading}
              className="hidden"
            />
          </label>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
          {error}
        </div>
      )}

      <div className="rounded-lg border">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-3 text-left text-sm font-medium">{t['admin.colStatus']}</th>
              <th className="px-4 py-3 text-left text-sm font-medium">{t['admin.colFilename']}</th>
              <th className="px-4 py-3 text-left text-sm font-medium">Region</th>
              <th className="px-4 py-3 text-left text-sm font-medium">{t['admin.colPages']}</th>
              <th className="px-4 py-3 text-left text-sm font-medium">{t['admin.colChunks']}</th>
              <th className="px-4 py-3 text-left text-sm font-medium">{t['admin.colUploaded']}</th>
              <th className="px-4 py-3 text-left text-sm font-medium">{t['admin.colActions']}</th>
            </tr>
          </thead>
          <tbody>
            {documents.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                  {t['admin.empty']}
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr key={doc.id} className="border-b">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(doc.status)}
                      <span className="text-sm capitalize">{doc.status}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium">{doc.filename}</span>
                    </div>
                    {doc.error_message && (
                      <p className="mt-1 text-xs text-red-500">{doc.error_message}</p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 capitalize">
                      {doc.region || 'global'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {doc.page_count ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {doc.chunk_count ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {doc.status === 'failed' && (
                        <button
                          onClick={() => handleReprocess(doc.id)}
                          className="p-1 hover:bg-muted rounded"
                          title="Reprocess"
                        >
                          <RefreshCw className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(doc.id)}
                        className="p-1 hover:bg-red-100 rounded text-red-500"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
