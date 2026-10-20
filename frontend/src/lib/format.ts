import type { Chat } from '../api/client'

const DAY = 86_400_000

/** Groups chats (already sorted newest first) into Today / Yesterday / Previous 7 days / ... */
export function groupChatsByDate(chats: Chat[]): { label: string; chats: Chat[] }[] {
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)
  const t0 = startOfToday.getTime()
  const groups = new Map<string, Chat[]>()
  for (const c of chats) {
    const ts = new Date(c.updated_at).getTime()
    const label =
      ts >= t0 ? 'Today'
      : ts >= t0 - DAY ? 'Yesterday'
      : ts >= t0 - 7 * DAY ? 'Previous 7 days'
      : ts >= t0 - 30 * DAY ? 'Previous 30 days'
      : new Date(ts).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
    if (!groups.has(label)) groups.set(label, [])
    groups.get(label)!.push(c)
  }
  return [...groups].map(([label, chats]) => ({ label, chats }))
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
