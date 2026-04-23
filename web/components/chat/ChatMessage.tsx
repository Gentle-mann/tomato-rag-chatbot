'use client'

import { useState } from 'react'
import { Message, Citation, useChatStore } from '@/lib/store'
import { cn, formatDate } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'
import { submitFeedback } from '@/lib/api'
import { CitationCard } from './CitationCard'
import { MarkdownRenderer } from './MarkdownRenderer'
import { ChevronDown, ChevronUp, User, Bot, ThumbsUp, ThumbsDown, Lightbulb } from 'lucide-react'

interface ChatMessageProps {
  message: Message
  previousMessage?: Message
  onSuggestionClick?: (suggestion: string) => void
}

export function ChatMessage({ message, previousMessage, onSuggestionClick }: ChatMessageProps) {
  const { t, language } = useTranslation()
  const sessionId = useChatStore((state) => state.sessionId)
  const [showCitations, setShowCitations] = useState(false)
  const [feedbackGiven, setFeedbackGiven] = useState<'positive' | 'negative' | null>(null)
  const isUser = message.role === 'user'
  const hasCitations = !isUser && !!message.citations && message.citations.length > 0
  const isAssistantDone = !isUser && !message.isStreaming

  const handleFeedback = async (rating: 'positive' | 'negative') => {
    if (feedbackGiven) return
    setFeedbackGiven(rating)

    try {
      await submitFeedback({
        session_id: sessionId || '',
        query: previousMessage?.content || '',
        response: message.content,
        language,
        rating,
        citations_count: message.citations?.length || 0,
        had_answer: true,
      })
    } catch {
      // Feedback is best-effort; don't disrupt UX
    }
  }

  return (
    <div
      className={cn(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-tomato-100 text-tomato-700'
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Message Content */}
      <div
        className={cn(
          'flex max-w-[80%] flex-col gap-1',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        <div
          className={cn(
            'rounded-2xl px-4 py-2',
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted'
          )}
        >
          {message.isStreaming ? (
            <div className="flex items-center gap-1">
              <span className="whitespace-pre-wrap">{message.content}</span>
              <span className="flex gap-1">
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
                <span className="typing-dot h-1.5 w-1.5 rounded-full bg-current" />
              </span>
            </div>
          ) : isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>

        {/* Citations Toggle */}
        {hasCitations && !message.isStreaming && (
          <button
            onClick={() => setShowCitations(!showCitations)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {showCitations ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            {message.citations!.length}{' '}
            {message.citations!.length > 1 ? t['message.sources'] : t['message.source']}
          </button>
        )}

        {/* Citations List */}
        {showCitations && hasCitations && (
          <div className="mt-2 space-y-2 w-full">
            {message.citations!.map((citation, index) => (
              <CitationCard key={index} citation={citation} />
            ))}
          </div>
        )}

        {/* Follow-up Suggestion Chips */}
        {isAssistantDone && message.suggestions && message.suggestions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2 w-full">
            {message.suggestions.map((suggestion, index) => (
              <button
                key={index}
                onClick={() => onSuggestionClick?.(suggestion)}
                className="flex items-center gap-1.5 rounded-full border bg-background px-3 py-1.5 text-xs text-foreground hover:bg-muted transition-colors"
              >
                <Lightbulb className="h-3 w-3 text-amber-500" />
                {suggestion}
              </button>
            ))}
          </div>
        )}

        {/* Feedback Buttons */}
        {isAssistantDone && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => handleFeedback('positive')}
              disabled={feedbackGiven !== null}
              className={cn(
                'rounded p-1 transition-colors',
                feedbackGiven === 'positive'
                  ? 'text-green-600'
                  : feedbackGiven !== null
                  ? 'text-muted-foreground/30 cursor-default'
                  : 'text-muted-foreground hover:text-green-600'
              )}
              title={t['feedback.helpful']}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => handleFeedback('negative')}
              disabled={feedbackGiven !== null}
              className={cn(
                'rounded p-1 transition-colors',
                feedbackGiven === 'negative'
                  ? 'text-red-600'
                  : feedbackGiven !== null
                  ? 'text-muted-foreground/30 cursor-default'
                  : 'text-muted-foreground hover:text-red-600'
              )}
              title={t['feedback.unhelpful']}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Timestamp */}
        <span className="text-xs text-muted-foreground">
          {formatDate(new Date(message.timestamp))}
        </span>
      </div>
    </div>
  )
}
