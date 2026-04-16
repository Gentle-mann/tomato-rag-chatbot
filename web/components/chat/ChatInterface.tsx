'use client'

import { useRef, useEffect, useState } from 'react'
import { useChatStore } from '@/lib/store'
import { useTranslation } from '@/lib/i18n'
import { streamChatMessage, sendChatMessage } from '@/lib/api'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { WelcomeScreen } from './WelcomeScreen'

export function ChatInterface() {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const {
    messages,
    sessionId,
    language,
    region,
    isLoading,
    addMessage,
    updateMessage,
    setStreamingComplete,
    setSessionId,
    setLoading,
    setError,
  } = useChatStore()

  const { t } = useTranslation()
  const [useStreaming, setUseStreaming] = useState(true)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || isLoading) return

    // Add user message
    addMessage({ role: 'user', content })
    setLoading(true)
    setError(null)

    try {
      if (useStreaming) {
        // Add empty assistant message for streaming
        const assistantId = crypto.randomUUID()
        useChatStore.setState((state) => ({
          messages: [
            ...state.messages,
            {
              id: assistantId,
              role: 'assistant' as const,
              content: '',
              timestamp: new Date(),
              isStreaming: true,
            },
          ],
        }))

        // Stream response
        const stream = streamChatMessage({
          message: content,
          session_id: sessionId || undefined,
          language,
          region,
        })

        let streamCitations: any[] | undefined
        let streamSuggestions: string[] | undefined

        for await (const chunk of stream) {
          if (chunk.type === 'token') {
            updateMessage(assistantId, chunk.content)
          } else if (chunk.type === 'citations') {
            streamCitations = JSON.parse(chunk.content)
          } else if (chunk.type === 'suggestions') {
            streamSuggestions = JSON.parse(chunk.content)
          } else if (chunk.type === 'done') {
            setStreamingComplete(assistantId, streamCitations, streamSuggestions)
            if (!sessionId) {
              setSessionId(chunk.content)
            }
          }
        }
      } else {
        // Non-streaming response
        const response = await sendChatMessage({
          message: content,
          session_id: sessionId || undefined,
          language,
          region,
        })

        addMessage({
          role: 'assistant',
          content: response.message,
          citations: response.citations,
        })

        if (!sessionId) {
          setSessionId(response.session_id)
        }
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'An error occurred'
      setError(errorMessage)
      addMessage({
        role: 'assistant',
        content: t['chat.error'],
      })
    } finally {
      setLoading(false)
    }
  }

  const handleExampleClick = (question: string) => {
    handleSendMessage(question)
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4">
        {messages.length === 0 ? (
          <WelcomeScreen onExampleClick={handleExampleClick} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-4 py-4">
            {messages.map((message, index) => (
              <ChatMessage
                key={message.id}
                message={message}
                previousMessage={index > 0 ? messages[index - 1] : undefined}
                onSuggestionClick={handleSendMessage}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="border-t bg-background p-4">
        <div className="mx-auto max-w-3xl">
          <ChatInput onSend={handleSendMessage} disabled={isLoading} />
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={useStreaming}
                onChange={(e) => setUseStreaming(e.target.checked)}
                className="rounded"
              />
              {t['chat.stream']}
            </label>
            <span>
              {t['chat.session']}: {sessionId ? sessionId.slice(0, 8) + '...' : t['chat.sessionNew']}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
