'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownRendererProps {
  content: string
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => (
          <p className="mb-2 last:mb-0">{children}</p>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold">{children}</strong>
        ),
        h3: ({ children }) => (
          <h3 className="mt-3 mb-1 text-sm font-semibold">{children}</h3>
        ),
        h4: ({ children }) => (
          <h4 className="mt-2 mb-1 text-sm font-medium">{children}</h4>
        ),
        ul: ({ children }) => (
          <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed">{children}</li>
        ),
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-muted/50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="border px-2 py-1 text-left text-xs font-medium">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border px-2 py-1 text-xs">{children}</td>
        ),
        code: ({ children, className }) => {
          const isBlock = className?.includes('language-')
          if (isBlock) {
            return (
              <pre className="my-2 overflow-x-auto rounded bg-muted/50 p-2 text-xs">
                <code>{children}</code>
              </pre>
            )
          }
          return (
            <code className="rounded bg-muted/50 px-1 py-0.5 text-xs">
              {children}
            </code>
          )
        },
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-2 border-muted-foreground/30 pl-3 italic">
            {children}
          </blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
