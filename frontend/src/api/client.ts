// Typed client for the NEXUS AI backend. All requests go to /api (proxied by Vite).

export interface Chat {
  id: string
  title: string
  created_at: string
  updated_at: string
  use_documents: boolean
  has_summary: boolean
}

export interface Source {
  n: number
  document_id: string
  filename: string
  page: number
  score: number
  text: string
}

export interface ContextInfo {
  estimated_prompt_tokens: number
  max_response_tokens: number
  context_window: number
  history_messages_included: number
  history_messages_dropped: number
  has_summary: boolean
  document_passages: number
  estimate: boolean
}

export interface Message {
  id: number
  chat_id: string
  role: 'user' | 'assistant'
  content: string
  status: 'ok' | 'incomplete' | string
  sources: Source[]
  context_info: Partial<ContextInfo>
  created_at: string
}

export interface DocumentInfo {
  id: string
  chat_id: string
  filename: string
  kind: 'pdf' | 'image'
  size_bytes: number
  status: 'processing' | 'ready' | 'failed'
  error: string
  pages: number
  chunks: number
  created_at: string
}

export interface ChatDetail extends Chat {
  messages: Message[]
  documents: DocumentInfo[]
}

export interface Health {
  status: string
  groq: { configured: boolean; model: string | null; model_available: boolean | null; error: string | null }
  ocr_available: boolean
  vector_backend: string
  embedding_model: string
  limits: { context_window: number; max_response_tokens: number; max_upload_mb: number }
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the NEXUS AI backend. Is it running on port 8000?', 0)
  }
  if (!res.ok) throw new ApiError(await errorText(res), res.status)
  return res.status === 204 ? (undefined as T) : res.json()
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    /* not JSON */
  }
  return res.status === 502 || res.status === 504
    ? 'Cannot reach the NEXUS AI backend. Is it running on port 8000?'
    : `Request failed (HTTP ${res.status})`
}

const json = (body: unknown): RequestInit => ({
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/health'),
  listChats: () => request<Chat[]>('/chats'),
  createChat: () => request<Chat>('/chats', { method: 'POST', ...json({}) }),
  getChat: (id: string) => request<ChatDetail>(`/chats/${id}`),
  updateChat: (id: string, patch: Partial<Pick<Chat, 'title' | 'use_documents'>>) =>
    request<Chat>(`/chats/${id}`, { method: 'PATCH', ...json(patch) }),
  deleteChat: (id: string) => request<void>(`/chats/${id}`, { method: 'DELETE' }),
  listDocuments: (id: string) => request<DocumentInfo[]>(`/chats/${id}/documents`),
  uploadDocument: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentInfo>(`/chats/${id}/documents`, { method: 'POST', body: form })
  },
  deleteDocument: (chatId: string, docId: string) =>
    request<void>(`/chats/${chatId}/documents/${docId}`, { method: 'DELETE' }),
}

export interface StreamHandlers {
  onUserMessage?: (m: Message) => void
  onContext?: (info: ContextInfo, sources: Source[]) => void
  onToken?: (t: string) => void
  onDone?: (m: Message) => void
  onError?: (message: string, code: string) => void
}

/** POST a message and consume the Server-Sent-Events reply stream. */
export async function streamMessage(
  chatId: string,
  body: { content?: string; regenerate?: boolean },
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`/api/chats/${chatId}/messages`, { method: 'POST', signal, ...json(body) })
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    handlers.onError?.('Cannot reach the NEXUS AI backend. Is it running on port 8000?', 'network_error')
    return
  }
  if (!res.ok || !res.body) {
    handlers.onError?.(await errorText(res), 'http_error')
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        let event = 'message'
        let data = ''
        for (const line of block.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7)
          else if (line.startsWith('data: ')) data += line.slice(6)
        }
        if (!data) continue
        const payload = JSON.parse(data)
        if (event === 'user_message') handlers.onUserMessage?.(payload)
        else if (event === 'context') handlers.onContext?.(payload.context_info, payload.sources)
        else if (event === 'token') handlers.onToken?.(payload.t)
        else if (event === 'done') { finished = true; handlers.onDone?.(payload) }
        else if (event === 'error') { finished = true; handlers.onError?.(payload.message, payload.code) }
      }
    }
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    handlers.onError?.('The connection was interrupted while streaming the reply.', 'stream_interrupted')
    return
  }
  if (!finished) handlers.onError?.('The reply stream ended unexpectedly.', 'stream_interrupted')
}
