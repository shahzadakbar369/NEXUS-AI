import { BookOpen, Code2, FileSearch, Lightbulb } from 'lucide-react'

const PROMPTS = [
  { icon: Lightbulb, title: 'Explain a concept', prompt: 'Explain retrieval-augmented generation (RAG) in simple terms, with a short example.' },
  { icon: Code2, title: 'Write code', prompt: 'Write a Python function that removes duplicates from a list while preserving order, with tests.' },
  { icon: BookOpen, title: 'Plan & organize', prompt: 'Create a 4-week study plan for learning FastAPI, with weekly goals.' },
  { icon: FileSearch, title: 'Ask your PDFs', prompt: 'Summarize the key points of the uploaded document, with page citations.' },
]

export function Welcome({ onPick, ocrAvailable }: { onPick: (p: string) => void; ocrAvailable: boolean }) {
  return (
    <div className="glow-bg flex flex-1 flex-col items-center justify-center px-4 py-10">
      <img src="/nexus.svg" alt="" className="mb-5 h-14 w-14 rounded-2xl shadow-2xl shadow-accent-500/40" />
      <h1 className="text-center text-3xl font-bold tracking-tight sm:text-4xl">
        How can <span className="brand-text">NEXUS AI</span> help today?
      </h1>
      <p className="mt-3 max-w-lg text-center text-sm text-slate-500 dark:text-slate-400">
        Chat about anything, or attach PDFs{ocrAvailable ? ' and images' : ''} to get answers grounded in your documents with page citations.
      </p>
      <div className="mt-8 grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
        {PROMPTS.map(({ icon: Icon, title, prompt }) => (
          <button key={title} onClick={() => onPick(prompt)}
            className="group rounded-2xl border border-slate-200 bg-white/70 p-4 text-left transition hover:-translate-y-0.5 hover:border-accent-500/50 hover:shadow-lg hover:shadow-accent-500/10 dark:border-ink-700 dark:bg-ink-850/60">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Icon size={16} className="text-accent-400 transition group-hover:scale-110" /> {title}
            </div>
            <p className="line-clamp-2 text-sm text-slate-500 dark:text-slate-400">{prompt}</p>
          </button>
        ))}
      </div>
    </div>
  )
}
