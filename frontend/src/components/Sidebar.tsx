import { useMemo, useState } from 'react'
import { Check, MessageSquare, Moon, PanelLeftClose, Pencil, Plus, Search, Sun, Trash2, X } from 'lucide-react'
import type { Chat, Health } from '../api/client'
import { groupChatsByDate } from '../lib/format'

interface Props {
  chats: Chat[]
  activeId: string | null
  loading: boolean
  health: Health | null
  theme: 'dark' | 'light'
  onToggleTheme: () => void
  onSelect: (id: string) => void
  onNewChat: () => void
  onRename: (id: string, title: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onClose: () => void
}

export function Sidebar(p: Props) {
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [confirmId, setConfirmId] = useState<string | null>(null)

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    return groupChatsByDate(q ? p.chats.filter((c) => c.title.toLowerCase().includes(q)) : p.chats)
  }, [p.chats, query])

  const commitRename = async (id: string) => {
    const title = draft.trim()
    setEditingId(null)
    if (title) await p.onRename(id, title)
  }

  const g = p.health?.groq
  const statusOk = g?.configured && g.model_available
  const statusText = !p.health ? 'Backend offline' : statusOk ? g!.model! : g?.error ?? 'Groq not ready'

  return (
    <aside className="flex h-full w-72 flex-col border-r border-slate-200 bg-slate-50 dark:border-ink-800 dark:bg-ink-900">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <img src="/nexus.svg" alt="" className="h-8 w-8 rounded-lg shadow-lg shadow-accent-500/30" />
          <span className="text-lg font-bold tracking-tight">
            NEXUS <span className="brand-text">AI</span>
          </span>
        </div>
        <button id="close-sidebar" onClick={p.onClose} aria-label="Close sidebar"
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 dark:hover:bg-ink-800">
          <PanelLeftClose size={18} />
        </button>
      </div>

      <div className="px-3">
        <button id="new-chat-button" onClick={p.onNewChat}
          className="brand-gradient flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-accent-600/25 transition hover:brightness-110 active:scale-[0.98]">
          <Plus size={18} /> New chat
        </button>
        <label className="relative mt-3 block">
          <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400" />
          <input id="chat-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search chats"
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pr-3 pl-9 text-sm outline-none placeholder:text-slate-400 focus:border-accent-500 dark:border-ink-700 dark:bg-ink-850" />
        </label>
      </div>

      <nav className="scrollbar-thin mt-3 flex-1 overflow-y-auto px-2 pb-3" aria-label="Conversations">
        {p.loading && <p className="px-3 py-2 text-sm text-slate-400">Loading chats…</p>}
        {!p.loading && p.chats.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-slate-400">No conversations yet.<br />Start one with New chat.</p>
        )}
        {!p.loading && p.chats.length > 0 && groups.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-slate-400">No chats match “{query}”.</p>
        )}
        {groups.map((grp) => (
          <div key={grp.label} className="mb-3">
            <h3 className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">{grp.label}</h3>
            <ul>
              {grp.chats.map((c) => {
                const active = c.id === p.activeId
                return (
                  <li key={c.id}>
                    <div className={`group relative flex items-center rounded-lg text-sm transition ${active
                      ? 'bg-accent-500/12 text-slate-900 ring-1 ring-accent-500/40 dark:bg-accent-500/15 dark:text-white'
                      : 'text-slate-600 hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-ink-800'}`}>
                      {editingId === c.id ? (
                        <form className="flex w-full items-center gap-1 p-1" onSubmit={(e) => { e.preventDefault(); commitRename(c.id) }}>
                          <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={120}
                            onKeyDown={(e) => e.key === 'Escape' && setEditingId(null)} aria-label="Chat title"
                            className="min-w-0 flex-1 rounded-md border border-accent-500 bg-white px-2 py-1 outline-none dark:bg-ink-850" />
                          <button type="submit" aria-label="Save title" className="rounded p-1 hover:text-accent-400"><Check size={15} /></button>
                          <button type="button" aria-label="Cancel rename" onClick={() => setEditingId(null)} className="rounded p-1 hover:text-red-400"><X size={15} /></button>
                        </form>
                      ) : confirmId === c.id ? (
                        <div className="flex w-full items-center gap-2 px-3 py-2">
                          <span className="flex-1 truncate text-red-400">Delete this chat?</span>
                          <button onClick={async () => { setConfirmId(null); await p.onDelete(c.id) }}
                            className="rounded bg-red-500/90 px-2 py-0.5 text-xs font-medium text-white hover:bg-red-500">Delete</button>
                          <button onClick={() => setConfirmId(null)} className="text-xs text-slate-400 hover:text-slate-200">Cancel</button>
                        </div>
                      ) : (
                        <>
                          <button onClick={() => p.onSelect(c.id)} aria-current={active ? 'page' : undefined}
                            className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2 text-left">
                            <MessageSquare size={15} className={active ? 'text-accent-400' : 'text-slate-400'} />
                            <span className="truncate">{c.title}</span>
                          </button>
                          <div className={`mr-1 flex shrink-0 gap-0.5 ${active ? 'flex' : 'hidden group-focus-within:flex group-hover:flex'}`}>
                            <button aria-label={`Rename ${c.title}`} onClick={() => { setDraft(c.title); setEditingId(c.id) }}
                              className="rounded p-1.5 text-slate-400 hover:bg-slate-300/60 hover:text-slate-700 dark:hover:bg-ink-700 dark:hover:text-white"><Pencil size={13} /></button>
                            <button aria-label={`Delete ${c.title}`} onClick={() => setConfirmId(c.id)}
                              className="rounded p-1.5 text-slate-400 hover:bg-red-500/15 hover:text-red-400"><Trash2 size={13} /></button>
                          </div>
                        </>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-2 border-t border-slate-200 px-4 py-3 dark:border-ink-800">
        <span className={`h-2 w-2 shrink-0 rounded-full ${statusOk ? 'bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400' : 'bg-amber-400'}`} />
        <span className="min-w-0 flex-1 truncate text-xs text-slate-500" title={statusText}>{statusText}</span>
        <button id="theme-toggle" onClick={p.onToggleTheme} aria-label="Toggle light/dark theme"
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-200 dark:hover:bg-ink-800">
          {p.theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </aside>
  )
}
