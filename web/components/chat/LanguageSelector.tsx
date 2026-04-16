'use client'

import { Globe } from 'lucide-react'

interface LanguageSelectorProps {
  value: 'en' | 'ne' | 'ja' | 'id' | 'vi'
  onChange: (value: 'en' | 'ne' | 'ja' | 'id' | 'vi') => void
}

const languages = [
  { code: 'en' as const, label: 'English', flag: 'EN' },
  { code: 'ne' as const, label: 'नेपाली', flag: 'NE' },
  { code: 'ja' as const, label: '日本語', flag: 'JA' },
  { code: 'id' as const, label: 'Indonesia', flag: 'ID' },
  { code: 'vi' as const, label: 'Tiếng Việt', flag: 'VI' },
]

export function LanguageSelector({ value, onChange }: LanguageSelectorProps) {
  return (
    <div className="flex items-center gap-2">
      <Globe className="h-4 w-4 text-muted-foreground" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as 'en' | 'ne' | 'ja' | 'id' | 'vi')}
        className="rounded-md border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {languages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.flag} {lang.label}
          </option>
        ))}
      </select>
    </div>
  )
}
