import { useEffect, useRef, type KeyboardEvent } from 'react'
import { ArrowUp, Paperclip, Square } from 'lucide-react'

interface Props {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  onStop: () => void
  onAttach: (files: FileList) => void
  generating: boolean
  disabled?: boolean
  ocrAvailable: boolean
}

export function Composer({ value, onChange, onSend, onStop, onAttach, generating, disabled, ocrAvailable }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [value])

  useEffect(() => { if (!generating) ref.current?.focus() }, [generating])

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!generating && value.trim()) onSend()
    }
  }

  const accept = ocrAvailable ? '.pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff' : '.pdf'

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-xl shadow-slate-900/5 transition focus-within:border-accent-500/70 focus-within:ring-4 focus-within:ring-accent-500/10 dark:border-ink-700 dark:bg-ink-850 dark:shadow-black/30">
      <textarea
        id="message-input"
        ref={ref}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder="Message NEXUS AI…"
        aria-label="Message"
        className="scrollbar-thin block max-h-[220px] w-full resize-none bg-transparent px-2 pt-1.5 pb-1 text-[15px] outline-none placeholder:text-slate-400"
      />
      <div className="flex items-center justify-between pt-1">
        <input ref={fileRef} type="file" accept={accept} multiple hidden
          onChange={(e) => { if (e.target.files?.length) onAttach(e.target.files); e.target.value = '' }} />
        <button id="attach-button" type="button" onClick={() => fileRef.current?.click()} disabled={disabled}
          title={ocrAvailable ? 'Attach PDF or image (OCR)' : 'Attach PDF (image OCR unavailable: Tesseract not installed)'}
          aria-label="Attach file"
          className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-ink-700 dark:hover:text-white">
          <Paperclip size={17} /> <span className="hidden sm:inline">{ocrAvailable ? 'PDF / image' : 'PDF'}</span>
        </button>
        <div className="flex items-center gap-2">
          <span className="hidden text-[11px] text-slate-400 md:inline">Enter to send · Shift+Enter for newline</span>
          {generating ? (
            <button id="stop-button" onClick={onStop} aria-label="Stop generating"
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-800 text-white transition hover:bg-slate-700 dark:bg-white dark:text-ink-900 dark:hover:bg-slate-200">
              <Square size={14} fill="currentColor" />
            </button>
          ) : (
            <button id="send-button" onClick={onSend} disabled={!value.trim() || disabled} aria-label="Send message"
              className="brand-gradient flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-md shadow-accent-600/30 transition hover:brightness-110 disabled:opacity-35 disabled:shadow-none">
              <ArrowUp size={18} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
