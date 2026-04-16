'use client'

import { Citation } from '@/lib/store'
import { FileText, BookOpen, Video } from 'lucide-react'
import { useTranslation } from '@/lib/i18n'

interface CitationCardProps {
  citation: Citation
}

export function CitationCard({ citation }: CitationCardProps) {
  const { t } = useTranslation()
  const confidencePercent = Math.round(citation.relevance_score * 100)
  const isTranscript = citation.source_type === 'transcript'

  return (
    <div className="rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-start gap-2">
        {isTranscript ? (
          <Video className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />
        ) : (
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-tomato-500" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {isTranscript ? (
                <span className="flex items-center gap-1">
                  <Video className="h-3 w-3" />
                  {t['citation.transcript']} ~{citation.timestamp || '0:00'}
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <BookOpen className="h-3 w-3" />
                  {citation.source_name
                    ? citation.source_name.replace(/\.pdf$/i, '').slice(0, 30)
                    : t['citation.manual']}{' '}
                  {t['citation.page']} {citation.page}
                </span>
              )}
              <span>|</span>
              <span>{citation.section}</span>
            </div>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                confidencePercent >= 70
                  ? 'bg-green-100 text-green-700'
                  : confidencePercent >= 50
                  ? 'bg-yellow-100 text-yellow-700'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {confidencePercent}% {t['citation.match']}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
            {citation.text_excerpt}
          </p>
        </div>
      </div>
    </div>
  )
}
