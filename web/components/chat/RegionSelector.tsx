'use client'

import { MapPin } from 'lucide-react'
import { useTranslation } from '@/lib/i18n'

type Region = 'japan' | 'nepal' | 'vietnam' | 'indonesia' | 'philippines' | null

interface RegionSelectorProps {
  value: Region
  onChange: (value: Region) => void
}

const regions = [
  { code: null, labelKey: 'region.auto' },
  { code: 'japan' as const, labelKey: 'region.japan' },
  { code: 'nepal' as const, labelKey: 'region.nepal' },
  { code: 'vietnam' as const, labelKey: 'region.vietnam' },
  { code: 'indonesia' as const, labelKey: 'region.indonesia' },
  { code: 'philippines' as const, labelKey: 'region.philippines' },
]

export function RegionSelector({ value, onChange }: RegionSelectorProps) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2">
      <MapPin className="h-4 w-4 text-muted-foreground" />
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value ? (e.target.value as Region) : null)}
        className="rounded-md border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {regions.map((r) => (
          <option key={r.code || 'auto'} value={r.code || ''}>
            {t[r.labelKey as keyof typeof t]}
          </option>
        ))}
      </select>
    </div>
  )
}
