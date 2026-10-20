import type { ContextInfo } from '../api/client'

/** Estimated context usage of the last request (prompt + reserved response tokens). */
export function ContextMeter({ info }: { info: Partial<ContextInfo> | null }) {
  if (!info?.context_window || info.estimated_prompt_tokens == null) return null
  const used = info.estimated_prompt_tokens + (info.max_response_tokens ?? 0)
  const pct = Math.min(100, Math.round((used / info.context_window) * 100))
  const tip = [
    `Estimated prompt: ~${info.estimated_prompt_tokens} tokens`,
    `Reserved for reply: ${info.max_response_tokens} tokens`,
    `Context window (configured): ${info.context_window}`,
    `History messages sent: ${info.history_messages_included}${info.history_messages_dropped ? ` (${info.history_messages_dropped} older not sent)` : ''}`,
    info.has_summary ? 'Older turns included as a summary' : null,
    `Document passages: ${info.document_passages ?? 0}`,
    'Token counts are estimates (~3.5 chars/token).',
  ].filter(Boolean).join('\n')
  const r = 7, c = 2 * Math.PI * r
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-slate-400" title={tip} aria-label={`Estimated context usage ${pct}%`}>
      <svg width="18" height="18" viewBox="0 0 18 18" className="-rotate-90">
        <circle cx="9" cy="9" r={r} fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
        <circle cx="9" cy="9" r={r} fill="none" strokeWidth="2.5" strokeLinecap="round"
          stroke={pct > 85 ? '#f59e0b' : '#8b9cff'} strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} />
      </svg>
      <span>~{pct}% context (est.)</span>
      {info.has_summary && <span className="rounded bg-slate-200 px-1 dark:bg-ink-700">summarized</span>}
    </div>
  )
}
