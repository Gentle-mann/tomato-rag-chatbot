'use client'

import { ChatInterface } from '@/components/chat/ChatInterface'
import { LanguageSelector } from '@/components/chat/LanguageSelector'
import { RegionSelector } from '@/components/chat/RegionSelector'
import { useChatStore } from '@/lib/store'
import { useTranslation } from '@/lib/i18n'

export default function Home() {
  const { language, setLanguage, region, setRegion, clearMessages } = useChatStore()
  const { t } = useTranslation()

  return (
    <main className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center justify-between">
          <button
            onClick={clearMessages}
            className="flex items-center gap-2 hover:opacity-80 transition-opacity"
          >
            <span className="text-2xl">🍅</span>
            <h1 className="text-lg font-semibold">{t['app.title']}</h1>
          </button>
          <div className="flex items-center gap-4">
            <RegionSelector value={region} onChange={setRegion} />
            <LanguageSelector value={language} onChange={setLanguage} />
          </div>
        </div>
      </header>

      {/* Main Chat Area */}
      <div className="flex-1 container py-4">
        <ChatInterface />
      </div>

      {/* Footer */}
      <footer className="border-t py-4">
        <div className="container text-center text-sm text-muted-foreground">
          <p>{t['app.footer1']}</p>
          <p className="mt-1">
            {t['app.footer2']}
          </p>
        </div>
      </footer>
    </main>
  )
}
