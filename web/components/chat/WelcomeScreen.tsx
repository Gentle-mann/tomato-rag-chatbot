'use client'

import { Sprout, Droplets, Bug, ThermometerSun } from 'lucide-react'
import { useTranslation } from '@/lib/i18n'

interface WelcomeScreenProps {
  onExampleClick: (question: string) => void
}

export function WelcomeScreen({ onExampleClick }: WelcomeScreenProps) {
  const { t } = useTranslation()

  const exampleQuestions = [
    {
      icon: Sprout,
      question: t['welcome.q.seedling'],
      category: t['welcome.cat.seedling'],
    },
    {
      icon: Droplets,
      question: t['welcome.q.irrigation'],
      category: t['welcome.cat.irrigation'],
    },
    {
      icon: Bug,
      question: t['welcome.q.disease'],
      category: t['welcome.cat.disease'],
    },
    {
      icon: ThermometerSun,
      question: t['welcome.q.environment'],
      category: t['welcome.cat.environment'],
    },
  ]

  return (
    <div className="flex h-full flex-col items-center justify-center py-12">
      <div className="text-center">
        <span className="text-6xl">🍅</span>
        <h2 className="mt-4 text-2xl font-semibold">
          {t['welcome.title']}
        </h2>
        <p className="mt-2 max-w-md text-muted-foreground">
          {t['welcome.description']}
        </p>
      </div>

      <div className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-2">
        {exampleQuestions.map((example) => (
          <button
            key={example.question}
            onClick={() => onExampleClick(example.question)}
            className="flex items-start gap-3 rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent"
          >
            <example.icon className="mt-0.5 h-5 w-5 shrink-0 text-tomato-500" />
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                {example.category}
              </p>
              <p className="mt-1 text-sm">{example.question}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="mt-8 rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
        <p>
          {t['welcome.note']}
        </p>
      </div>
    </div>
  )
}
