import { AlertCircle, FileText, Image as ImageIcon, Loader2, X } from 'lucide-react'
import type { DocumentInfo } from '../api/client'
import { formatBytes } from '../lib/format'

interface Props {
  documents: DocumentInfo[]
  useDocuments: boolean
  onToggleMode: (v: boolean) => void
  onRemove: (id: string) => void
}

/** Shows this chat's documents, their processing status, and the document/general mode switch. */
export function DocumentsBar({ documents, useDocuments, onToggleMode, onRemove }: Props) {
  if (!documents.length) return null
  const ready = documents.filter((d) => d.status === 'ready').length
  return (
    <div className="mb-2 rounded-xl border border-slate-200 bg-slate-50/80 p-2 backdrop-blur dark:border-ink-700 dark:bg-ink-900/80">
      <div className="mb-1.5 flex items-center justify-between gap-2 px-1">
        <span className="text-xs text-slate-500">
          {useDocuments && ready ? `Answering from ${ready} document${ready > 1 ? 's' : ''} (with citations)` : 'General chat — documents are ignored'}
        </span>
        <div role="radiogroup" aria-label="Chat mode" className="flex rounded-lg bg-slate-200/70 p-0.5 text-xs dark:bg-ink-800">
          {[
            { v: true, label: 'Documents' },
            { v: false, label: 'General' },
          ].map((o) => (
            <button key={o.label} id={`mode-${o.label.toLowerCase()}`} role="radio" aria-checked={useDocuments === o.v}
              onClick={() => onToggleMode(o.v)}
              className={`rounded-md px-2.5 py-1 font-medium transition ${useDocuments === o.v
                ? 'bg-white text-slate-900 shadow dark:bg-ink-600 dark:text-white' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'}`}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <ul className="scrollbar-thin flex gap-2 overflow-x-auto pb-0.5">
        {documents.map((d) => (
          <li key={d.id} title={d.error || `${d.pages} page(s), ${d.chunks} chunks indexed`}
            className={`flex max-w-64 shrink-0 items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${
              d.status === 'failed' ? 'border-red-500/40 bg-red-500/10' : 'border-slate-200 bg-white dark:border-ink-700 dark:bg-ink-850'}`}>
            {d.status === 'processing' ? <Loader2 size={14} className="animate-spin text-accent-400" />
              : d.status === 'failed' ? <AlertCircle size={14} className="text-red-400" />
              : d.kind === 'image' ? <ImageIcon size={14} className="text-cyan-glow" /> : <FileText size={14} className="text-accent-400" />}
            <div className="min-w-0">
              <div className="truncate font-medium">{d.filename}</div>
              <div className={`truncate ${d.status === 'failed' ? 'text-red-400' : 'text-slate-400'}`}>
                {d.status === 'processing' ? 'Extracting & indexing…'
                  : d.status === 'failed' ? d.error
                  : `${d.pages} pg · ${d.chunks} chunks · ${formatBytes(d.size_bytes)}`}
              </div>
            </div>
            <button aria-label={`Remove ${d.filename}`} onClick={() => onRemove(d.id)}
              className="ml-1 rounded p-0.5 text-slate-400 hover:bg-slate-200 hover:text-red-400 dark:hover:bg-ink-700"><X size={13} /></button>
          </li>
        ))}
      </ul>
    </div>
  )
}
