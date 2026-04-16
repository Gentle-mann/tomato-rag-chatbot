import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Region = 'japan' | 'nepal' | 'vietnam' | 'indonesia' | 'philippines' | null

export interface Citation {
  source_type: string    // "manual" | "transcript"
  source_name: string
  page?: number          // PDF page (undefined for transcript)
  timestamp?: string     // "MM:SS" (undefined for manual)
  section: string
  text_excerpt: string
  relevance_score: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  suggestions?: string[]
  timestamp: Date
  isStreaming?: boolean
}

interface ChatState {
  messages: Message[]
  sessionId: string | null
  language: 'en' | 'ne' | 'ja' | 'id' | 'vi'
  region: Region
  isLoading: boolean
  error: string | null

  // Actions
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void
  updateMessage: (id: string, content: string) => void
  setStreamingComplete: (id: string, citations?: Citation[], suggestions?: string[]) => void
  setLanguage: (lang: 'en' | 'ne' | 'ja' | 'id' | 'vi') => void
  setRegion: (region: Region) => void
  setSessionId: (id: string) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      sessionId: null,
      language: 'en',
      region: null,
      isLoading: false,
      error: null,

      addMessage: (message) => {
        const newMessage: Message = {
          ...message,
          id: crypto.randomUUID(),
          timestamp: new Date(),
        }
        set((state) => ({
          messages: [...state.messages, newMessage],
        }))
        return newMessage.id
      },

      updateMessage: (id, content) => {
        set((state) => ({
          messages: state.messages.map((msg) =>
            msg.id === id ? { ...msg, content: msg.content + content } : msg
          ),
        }))
      },

      setStreamingComplete: (id, citations, suggestions) => {
        set((state) => ({
          messages: state.messages.map((msg) =>
            msg.id === id
              ? { ...msg, isStreaming: false, citations, suggestions }
              : msg
          ),
        }))
      },

      setLanguage: (language) => set({ language }),
      setRegion: (region) => set({ region }),
      setSessionId: (sessionId) => set({ sessionId }),
      setLoading: (isLoading) => set({ isLoading }),
      setError: (error) => set({ error }),

      clearMessages: () => set({ messages: [], sessionId: null }),
    }),
    {
      name: 'tomato-chat-storage',
      partialize: (state) => ({
        language: state.language,
        region: state.region,
        sessionId: state.sessionId,
      }),
    }
  )
)
