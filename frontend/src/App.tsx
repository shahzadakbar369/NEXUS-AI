import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, Menu, PanelLeftOpen, RotateCcw, X } from 'lucide-react'
import 'highlight.js/styles/github-dark.css'
import { api, streamMessage, type Chat, type ContextInfo, type DocumentInfo, type Health, type Message } from './api/client'
import { Sidebar } from './components/Sidebar'
import { MessageBubble } from './components/MessageBubble'
import { Composer } from './components/Composer'
import { DocumentsBar } from './components/DocumentsBar'
import { ContextMeter } from './components/ContextMeter'
import { Welcome } from './components/Welcome'

interface ChatError { message: string; retry?: () => void }

const isDesktop = () => window.matchMedia('(min-width: 768px)').matches

export default function App() {
  const [chats, setChats] = useState<Chat[]>([])
  const [chatsLoading, setChatsLoading] = useState(true)
  const [health, setHealth] = useState<Health | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null) // null = new, not-yet-created chat
  const [messages, setMessages] = useState<Message[]>([])
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [useDocuments, setUseDocuments] = useState(true)
  const [chatLoading, setChatLoading] = useState(false)
  const [input, setInput] = useState('')
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<ChatError | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [lastContext, setLastContext] = useState<Partial<ContextInfo> | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(isDesktop())
  const [theme, setTheme] = useState<'dark' | 'light'>(
    document.documentElement.classList.contains('dark') ? 'dark' : 'light')

  const abortRef = useRef<AbortController | null>(null)
  const activeRef = useRef<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  activeRef.current = activeId

  // ---------- bootstrap ----------
  const refreshChats = useCallback(async () => {
    try { setChats(await api.listChats()) } catch (e) { setToast((e as Error).message) } finally { setChatsLoading(false) }
  }, [])

  useEffect(() => {
    refreshChats()
    const check = () => api.health().then(setHealth).catch(() => setHealth(null))
    check()
    const t = setInterval(check, 60_000)
    return () => clearInterval(t)
  }, [refreshChats])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem('nexus-theme', theme)
  }, [theme])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages])

  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(null), 6000); return () => clearTimeout(t) } }, [toast])

  // Poll while any document is still being processed.
  useEffect(() => {
    if (!activeId || !documents.some((d) => d.status === 'processing')) return
    const t = setInterval(async () => {
      try {
        const docs = await api.listDocuments(activeId)
        if (activeRef.current === activeId) setDocuments(docs)
      } catch { /* transient */ }
    }, 1500)
    return () => clearInterval(t)
  }, [activeId, documents])

  // ---------- chat selection ----------
  const loadChat = useCallback(async (id: string) => {
    setChatLoading(true)
    try {
      const d = await api.getChat(id)
      if (activeRef.current !== id) return
      setMessages(d.messages)
      setDocuments(d.documents)
      setUseDocuments(d.use_documents)
      setLastContext([...d.messages].reverse().find((m) => m.role === 'assistant' && m.context_info?.context_window)?.context_info ?? null)
    } catch (e) {
      setToast((e as Error).message)
    } finally {
      setChatLoading(false)
    }
  }, [])

  const selectChat = (id: string) => {
    abortRef.current?.abort()
    setError(null)
    setActiveId(id)
    activeRef.current = id
    loadChat(id)
    if (!isDesktop()) setSidebarOpen(false)
  }

  const newChat = () => {
    abortRef.current?.abort()
    setActiveId(null)
    setMessages([]); setDocuments([]); setUseDocuments(true); setError(null); setLastContext(null); setInput('')
    if (!isDesktop()) setSidebarOpen(false)
  }

  const ensureChat = async (): Promise<string> => {
    if (activeRef.current) return activeRef.current
    const chat = await api.createChat()
    setChats((cs) => [chat, ...cs])
    setActiveId(chat.id)
    activeRef.current = chat.id
    return chat.id
  }

  // ---------- messaging ----------
  const send = async (opts: { content?: string; regenerate?: boolean }) => {
    if (generating) return
    setError(null)
    let chatId: string
    try { chatId = await ensureChat() } catch (e) { setError({ message: (e as Error).message }); return }

    const tempUserId = -Date.now()
    const draftId = tempUserId - 1
    let persisted = !!opts.regenerate
    if (opts.regenerate) {
      // Drop the old assistant reply(ies) after the last user message.
      setMessages((ms) => {
        const lastUser = ms.map((m) => m.role).lastIndexOf('user')
        return ms.slice(0, lastUser + 1)
      })
    } else {
      setMessages((ms) => [...ms, { id: tempUserId, chat_id: chatId, role: 'user', content: opts.content!, status: 'ok', sources: [], context_info: {}, created_at: '' }])
    }
    setMessages((ms) => [...ms, { id: draftId, chat_id: chatId, role: 'assistant', content: '', status: 'ok', sources: [], context_info: {}, created_at: '' }])
    setGenerating(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const patchDraft = (fn: (m: Message) => Message) =>
      setMessages((ms) => ms.map((m) => (m.id === draftId ? fn(m) : m)))

    await streamMessage(chatId, opts, {
      onUserMessage: (m) => { persisted = true; setMessages((ms) => ms.map((x) => (x.id === tempUserId ? m : x))) },
      onContext: (info, sources) => { setLastContext(info); patchDraft((m) => ({ ...m, sources })) },
      onToken: (t) => patchDraft((m) => ({ ...m, content: m.content + t })),
      onDone: (m) => setMessages((ms) => ms.map((x) => (x.id === draftId ? m : x))),
      onError: (message) => {
        setMessages((ms) => ms.filter((x) => x.id !== draftId || x.content))
        const retry = persisted
          ? () => send({ regenerate: true })
          : () => { setMessages((ms) => ms.filter((x) => x.id !== tempUserId)); send(opts) }
        setError({ message, retry })
      },
    }, ctrl.signal)

    const aborted = ctrl.signal.aborted
    setGenerating(false)
    abortRef.current = null
    refreshChats()
    // After Stop, reload so the saved (incomplete) partial reply and real IDs are shown.
    if (aborted && activeRef.current === chatId) setTimeout(() => loadChat(chatId), 400)
  }

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    setInput('')
    send({ content: text })
  }

  // ---------- documents ----------
  const attach = async (files: FileList) => {
    const maxMb = health?.limits.max_upload_mb ?? 15
    let chatId: string
    try { chatId = await ensureChat() } catch (e) { setToast((e as Error).message); return }
    for (const file of Array.from(files)) {
      if (file.size > maxMb * 1024 * 1024) { setToast(`${file.name} is larger than the ${maxMb} MB limit.`); continue }
      try {
        const doc = await api.uploadDocument(chatId, file)
        if (activeRef.current === chatId) setDocuments((ds) => [...ds, doc])
      } catch (e) {
        setToast(`${file.name}: ${(e as Error).message}`)
      }
    }
    refreshChats()
  }

  const removeDocument = async (docId: string) => {
    if (!activeId) return
    try {
      await api.deleteDocument(activeId, docId)
      setDocuments((ds) => ds.filter((d) => d.id !== docId))
    } catch (e) { setToast((e as Error).message) }
  }

  const toggleMode = async (v: boolean) => {
    if (!activeId) return
    setUseDocuments(v)
    try { await api.updateChat(activeId, { use_documents: v }) } catch (e) { setUseDocuments(!v); setToast((e as Error).message) }
  }

  // ---------- sidebar actions ----------
  const renameChat = async (id: string, title: string) => {
    try {
      const c = await api.updateChat(id, { title })
      setChats((cs) => cs.map((x) => (x.id === id ? c : x)))
    } catch (e) { setToast((e as Error).message) }
  }

  const deleteChat = async (id: string) => {
    try {
      await api.deleteChat(id)
      setChats((cs) => cs.filter((c) => c.id !== id))
      if (id === activeId) newChat()
    } catch (e) { setToast((e as Error).message) }
  }

  const activeTitle = chats.find((c) => c.id === activeId)?.title ?? 'New chat'
  const lastAssistantIdx = messages.map((m) => m.role).lastIndexOf('assistant')
  const groqProblem = health && !(health.groq.configured && health.groq.model_available) ? health.groq.error : null

  return (
    <div className="flex h-full overflow-hidden">
      {/* Sidebar: drawer on mobile, collapsible column on desktop */}
      {sidebarOpen && <div className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden" onClick={() => setSidebarOpen(false)} />}
      <div className={`fixed inset-y-0 left-0 z-40 transition-transform duration-200 md:static md:z-auto ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:hidden'}`}>
        <Sidebar chats={chats} activeId={activeId} loading={chatsLoading} health={health} theme={theme}
          onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
          onSelect={selectChat} onNewChat={newChat} onRename={renameChat} onDelete={deleteChat}
          onClose={() => setSidebarOpen(false)} />
      </div>

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-200/70 px-3 dark:border-ink-800/70">
          {!sidebarOpen && (
            <button id="open-sidebar" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-ink-800">
              <span className="md:hidden"><Menu size={18} /></span>
              <span className="hidden md:inline"><PanelLeftOpen size={18} /></span>
            </button>
          )}
          <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{activeTitle}</h2>
          <ContextMeter info={lastContext} />
        </header>

        {groqProblem && (
          <div role="alert" className="mx-auto mt-3 flex w-full max-w-3xl items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-600 dark:text-amber-300">
            <AlertCircle size={16} className="mt-0.5 shrink-0" /> <span>{groqProblem}</span>
          </div>
        )}
        {!health && !chatsLoading && (
          <div role="alert" className="mx-auto mt-3 flex w-full max-w-3xl items-center gap-2 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2.5 text-sm text-red-500 dark:text-red-300">
            <AlertCircle size={16} /> Backend unreachable. Start it with <code className="font-mono">uvicorn app.main:app --port 8000</code>.
          </div>
        )}

        <div className="scrollbar-thin flex flex-1 flex-col overflow-y-auto">
          {chatLoading ? (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-400">Loading conversation…</div>
          ) : messages.length === 0 ? (
            <Welcome onPick={(p) => setInput(p)} ocrAvailable={!!health?.ocr_available} />
          ) : (
            <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
              {messages.map((m, i) => (
                <MessageBubble key={m.id} message={m}
                  streaming={generating && m.id < 0 && m.role === 'assistant'}
                  canRegenerate={!generating && i === lastAssistantIdx && i === messages.length - 1}
                  onRegenerate={() => send({ regenerate: true })} />
              ))}
              {error && (
                <div role="alert" className="animate-fade-up flex items-start gap-3 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-300">
                  <AlertCircle size={18} className="mt-0.5 shrink-0" />
                  <div className="flex-1">
                    <p className="font-medium">The assistant could not respond.</p>
                    <p className="mt-0.5 opacity-90">{error.message}</p>
                  </div>
                  {error.retry && (
                    <button id="retry-button" onClick={error.retry}
                      className="flex shrink-0 items-center gap-1 rounded-lg bg-red-500/15 px-2.5 py-1 font-medium hover:bg-red-500/25">
                      <RotateCcw size={14} /> Retry
                    </button>
                  )}
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="shrink-0 px-3 pt-2 pb-3 sm:px-4">
          <div className="mx-auto w-full max-w-3xl">
            <DocumentsBar documents={documents} useDocuments={useDocuments} onToggleMode={toggleMode} onRemove={removeDocument} />
            <Composer value={input} onChange={setInput} onSend={handleSend} onStop={() => abortRef.current?.abort()}
              onAttach={attach} generating={generating} ocrAvailable={!!health?.ocr_available} />
            <p className="mt-2 text-center text-[11px] text-slate-400">NEXUS AI can make mistakes. Verify important information.</p>
          </div>
        </div>

        {toast && (
          <div role="status" className="animate-fade-up fixed right-4 bottom-4 z-50 flex max-w-sm items-start gap-2 rounded-xl border border-red-500/40 bg-white px-4 py-3 text-sm shadow-2xl dark:bg-ink-850">
            <AlertCircle size={16} className="mt-0.5 shrink-0 text-red-400" />
            <span className="flex-1">{toast}</span>
            <button onClick={() => setToast(null)} aria-label="Dismiss"><X size={14} /></button>
          </div>
        )}
      </main>
    </div>
  )
}
