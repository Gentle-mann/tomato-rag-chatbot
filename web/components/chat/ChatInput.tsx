'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Mic } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'
import { useChatStore, type Region } from '@/lib/store'
import { useSpeechRecognition } from '@/lib/useSpeechRecognition'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

type SpeechLang = 'en' | 'ne' | 'ja' | 'id' | 'vi'

const REGION_TO_LANG: Record<Exclude<Region, null>, SpeechLang> = {
  japan: 'ja',
  nepal: 'ne',
  vietnam: 'vi',
  indonesia: 'id',
  philippines: 'en',
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const { t, language } = useTranslation()
  const region = useChatStore((state) => state.region)
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Region takes priority over UI language for speech recognition.
  // A user browsing in English UI with region=Japan is likely speaking Japanese.
  const speechLanguage: SpeechLang = region ? REGION_TO_LANG[region] : language

  const handleTranscript = useCallback((text: string) => {
    setInput((prev) => (prev ? prev.trimEnd() + ' ' + text : text))
  }, [])

  const { isListening, isSupported, toggle, stop } = useSpeechRecognition({
    language: speechLanguage,
    onTranscript: handleTranscript,
  })

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
    }
  }, [input])

  const handleSubmit = () => {
    if (input.trim() && !disabled) {
      if (isListening) stop()
      onSend(input.trim())
      setInput('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="relative flex items-end gap-2 rounded-2xl border bg-background p-2 shadow-sm">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isListening ? t['input.listening'] : t['input.placeholder']}
        disabled={disabled}
        rows={1}
        className={cn(
          'flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none',
          'placeholder:text-muted-foreground',
          'disabled:cursor-not-allowed disabled:opacity-50'
        )}
      />
      {isSupported && (
        <button
          onClick={toggle}
          disabled={disabled}
          aria-label={isListening ? t['input.voiceStop'] : t['input.voiceStart']}
          title={isListening ? t['input.voiceStop'] : t['input.voiceStart']}
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
            'transition-colors',
            'disabled:cursor-not-allowed disabled:opacity-50',
            isListening
              ? 'animate-pulse bg-red-500 text-white hover:bg-red-600'
              : 'bg-muted text-muted-foreground hover:bg-muted/80'
          )}
        >
          <Mic className="h-4 w-4" />
        </button>
      )}
      <button
        onClick={handleSubmit}
        disabled={disabled || !input.trim()}
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          'bg-primary text-primary-foreground',
          'hover:bg-primary/90',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'transition-colors'
        )}
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  )
}
