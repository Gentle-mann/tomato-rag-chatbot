'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

type Language = 'en' | 'ne' | 'ja' | 'id' | 'vi'

const LANG_MAP: Record<Language, string> = {
  en: 'en-US',
  ja: 'ja-JP',
  ne: 'ne-NP',
  id: 'id-ID',
  vi: 'vi-VN',
}

interface SpeechRecognitionAlternative {
  transcript: string
  confidence: number
}

interface SpeechRecognitionResult {
  isFinal: boolean
  length: number
  [index: number]: SpeechRecognitionAlternative
}

interface SpeechRecognitionResultList {
  length: number
  [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionEventLike extends Event {
  results: SpeechRecognitionResultList
  resultIndex: number
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string
  message: string
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start(): void
  stop(): void
  abort(): void
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null
  onerror: ((ev: SpeechRecognitionErrorEventLike) => void) | null
  onend: ((ev: Event) => void) | null
  onstart: ((ev: Event) => void) | null
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

interface UseSpeechRecognitionProps {
  language: Language
  onTranscript: (text: string) => void
  onError?: (error: string) => void
}

export function useSpeechRecognition({
  language,
  onTranscript,
  onError,
}: UseSpeechRecognitionProps) {
  const [isListening, setIsListening] = useState(false)
  const [isSupported, setIsSupported] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const onTranscriptRef = useRef(onTranscript)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onTranscriptRef.current = onTranscript
    onErrorRef.current = onError
  }, [onTranscript, onError])

  useEffect(() => {
    setIsSupported(!!getSpeechRecognition())
  }, [])

  const start = useCallback(() => {
    const Ctor = getSpeechRecognition()
    if (!Ctor) {
      onErrorRef.current?.('not-supported')
      return
    }

    if (recognitionRef.current) {
      recognitionRef.current.abort()
    }

    const recognition = new Ctor()
    recognition.lang = LANG_MAP[language] || 'en-US'
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onstart = () => setIsListening(true)
    recognition.onend = () => setIsListening(false)
    recognition.onerror = (event) => {
      onErrorRef.current?.(event.error)
      setIsListening(false)
    }
    recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          const transcript = result[0].transcript.trim()
          if (transcript) onTranscriptRef.current(transcript)
        }
      }
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch {
      onErrorRef.current?.('start-failed')
      setIsListening(false)
    }
  }, [language])

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  const toggle = useCallback(() => {
    if (isListening) stop()
    else start()
  }, [isListening, start, stop])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
    }
  }, [])

  return { isListening, isSupported, start, stop, toggle }
}
