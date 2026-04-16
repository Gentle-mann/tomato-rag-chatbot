const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface ChatRequest {
  message: string
  session_id?: string
  language: string
  region?: string | null
  stream?: boolean
}

export interface ChatResponse {
  message: string
  session_id: string
  language: string
  citations: Citation[]
  has_answer: boolean
  confidence: number
  suggestions: string[]
}

export interface Citation {
  source_type: string
  source_name: string
  page?: number
  timestamp?: string
  section: string
  text_excerpt: string
  relevance_score: number
}

export async function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/api/v1/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.statusText}`)
  }

  return response.json()
}

export async function* streamChatMessage(
  request: ChatRequest
): AsyncGenerator<{ type: string; content: string }> {
  const response = await fetch(`${API_URL}/api/v1/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...request, stream: true }),
  })

  if (!response.ok) {
    throw new Error(`Stream request failed: ${response.statusText}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)

        if (data.startsWith('[CITATIONS]')) {
          yield { type: 'citations', content: data.slice(11) }
        } else if (data.startsWith('[SUGGESTIONS]')) {
          yield { type: 'suggestions', content: data.slice(13) }
        } else if (data.startsWith('[DONE]')) {
          yield { type: 'done', content: data.slice(6) }
        } else if (data.startsWith('[ERROR]')) {
          throw new Error(data.slice(7))
        } else {
          try {
            yield { type: 'token', content: JSON.parse(data) }
          } catch {
            yield { type: 'token', content: data }
          }
        }
      }
    }
  }
}

export async function searchSources(
  query: string,
  topK: number = 5
): Promise<{ query: string; results: Citation[] }> {
  const response = await fetch(
    `${API_URL}/api/v1/sources/search?query=${encodeURIComponent(query)}&top_k=${topK}`
  )

  if (!response.ok) {
    throw new Error(`Search request failed: ${response.statusText}`)
  }

  return response.json()
}

export async function clearChatHistory(sessionId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/chat/history/${sessionId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error(`Clear history failed: ${response.statusText}`)
  }
}

export interface FeedbackRequest {
  session_id: string
  query: string
  response: string
  language: string
  region?: string | null
  rating: 'positive' | 'negative'
  comment?: string
  citations_count: number
  had_answer: boolean
}

export async function submitFeedback(request: FeedbackRequest): Promise<{ id: string }> {
  const response = await fetch(`${API_URL}/api/v1/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(`Feedback submission failed: ${response.statusText}`)
  }

  return response.json()
}

export async function checkHealth(): Promise<{ status: string; version: string }> {
  const response = await fetch(`${API_URL}/health`)

  if (!response.ok) {
    throw new Error('Health check failed')
  }

  return response.json()
}
