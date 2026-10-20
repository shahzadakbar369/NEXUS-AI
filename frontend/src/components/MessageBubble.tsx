import { memo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { AlertTriangle, Check, ChevronDown, Copy, FileText, RefreshCw, User } from 'lucide-react'
import type { Message, Source } from '../api/client'

function CopyButton({ text, label = 'Copy', className = '' }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      aria-label={label}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-ink-700 dark:hover:text-white ${className}`}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : label}
    </button>
  )
}

function nodeText(node: unknown): string {
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(nodeText).join('')
  if (node && typeof node === 'object' && 'props' in node) return nodeText((node as { props: { children?: unknown } }).props.children)
  return ''
}

const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
      components={{
        pre({ children }) {
          const child = Array.isArray(children) ? children[0] : children
          const cls: string = (child as { props?: { className?: string } })?.props?.className ?? ''
          const lang = /language-(\w+)/.exec(cls)?.[1] ?? 'code'
          return (
            <div className="not-prose my-4 overflow-hidden rounded-xl border border-ink-700 bg-[#0b0d14]">
              <div className="flex items-center justify-between border-b border-ink-700 bg-ink-850 px-3 py-1.5">
                <span className="font-mono text-xs text-slate-400">{lang}</span>
                <CopyButton text={nodeText(children).replace(/\n$/, '')} label="Copy code" />
              </div>
              <pre className="scrollbar-thin overflow-x-auto p-4 font-mono text-[13px] leading-relaxed text-slate-200">{children}</pre>
            </div>
          )
        },
        a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
      }}
    >
      {content}
    </ReactMarkdown>
  )
})

function Sources({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false)
  if (!sources.length) return null
  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 text-sm dark:border-ink-700 dark:bg-ink-850/60">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400">
        <FileText size={14} className="text-accent-400" />
        {sources.length} retrieved passage{sources.length > 1 ? 's' : ''} sent to the model
        <ChevronDown size={14} className={`ml-auto transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <ol className="space-y-2 border-t border-slate-200 p-3 dark:border-ink-700">
          {sources.map((s) => (
            <li key={`${s.document_id}-${s.n}`} className="rounded-lg bg-white p-2.5 dark:bg-ink-900">
              <div className="mb-1 flex items-center gap-2 text-xs">
                <span className="rounded bg-accent-500/15 px-1.5 py-0.5 font-semibold text-accent-500 dark:text-accent-300">[{s.n}]</span>
                <span className="truncate font-medium">{s.filename}</span>
                <span className="text-slate-400">p. {s.page}</span>
                <span className="ml-auto text-slate-400" title="Cosine similarity">sim {s.score.toFixed(2)}</span>
              </div>
              <p className="line-clamp-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{s.text}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

interface Props {
  message: Message
  streaming?: boolean
  canRegenerate?: boolean
  onRegenerate?: () => void
}

export function MessageBubble({ message, streaming, canRegenerate, onRegenerate }: Props) {
  if (message.role === 'user') {
    return (
      <div className="animate-fade-up flex justify-end gap-3">
        <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-accent-600 px-4 py-2.5 whitespace-pre-wrap text-white shadow-md shadow-accent-600/20 sm:max-w-[75%]">
          {message.content}
        </div>
        <div className="mt-0.5 hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 sm:flex dark:bg-ink-700">
          <User size={16} />
        </div>
      </div>
    )
  }
  const empty = streaming && !message.content
  return (
    <div className="animate-fade-up group flex gap-3">
      <img src="/nexus.svg" alt="NEXUS AI" className="mt-0.5 h-8 w-8 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1">
        {empty ? (
          <div className="flex h-8 items-center gap-1" aria-label="Thinking">
            {[0, 1, 2].map((i) => (
              <span key={i} className="typing-dot h-2 w-2 rounded-full bg-accent-400" style={{ animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        ) : (
          <div className={`prose prose-slate max-w-none prose-p:leading-relaxed dark:prose-invert ${streaming ? 'caret' : ''}`}>
            <Markdown content={message.content} />
          </div>
        )}
        {message.status === 'incomplete' && !streaming && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-amber-500">
            <AlertTriangle size={13} /> Response incomplete (stopped or interrupted). It is not used as context.
          </p>
        )}
        <Sources sources={message.sources ?? []} />
        {!streaming && message.content && (
          <div className="mt-1.5 flex gap-1 opacity-100 transition sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
            <CopyButton text={message.content} />
            {canRegenerate && (
              <button onClick={onRegenerate} aria-label="Regenerate response"
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-ink-700 dark:hover:text-white">
                <RefreshCw size={13} /> Regenerate
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
