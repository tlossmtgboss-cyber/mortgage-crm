import React from 'react'

interface SMSTaskCardProps {
  task: {
    id: number
    phone_number: string
    contact_name: string | null
    inbound_message: string
    inbound_received_at: string
    status: string
    priority: string
    category: string | null
    ai_confidence: number
    ai_recommendation: string | null
    response_source: string | null
    response_sent_at: string | null
  }
  selected: boolean
  onClick: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  scheduling: '#218d8d',
  question: '#6c63ff',
  follow_up: '#fd7e14',
  rate_inquiry: '#28a745',
  document_request: '#17a2b8',
  greeting: '#6c757d',
  complaint: '#dc3545',
  general: '#495057',
}

const PRIORITY_COLORS: Record<string, string> = {
  urgent: '#dc3545',
  high: '#fd7e14',
  normal: '#28a745',
  low: '#adb5bd',
}

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

function statusLabel(task: SMSTaskCardProps['task']): { text: string; color: string } {
  if (task.status === 'completed') return { text: 'Completed', color: '#28a745' }
  if (task.status === 'dismissed') return { text: 'Dismissed', color: '#6c757d' }
  if (task.response_sent_at) return { text: 'Auto-responded \u2713', color: '#218d8d' }
  if (task.ai_recommendation) return { text: 'AI ready', color: '#6c63ff' }
  return { text: 'Pending', color: '#adb5bd' }
}

function SMSTaskCard({ task, selected, onClick }: SMSTaskCardProps) {
  const [hovered, setHovered] = React.useState(false)
  const preview = task.inbound_message.length > 80
    ? task.inbound_message.slice(0, 80) + '\u2026'
    : task.inbound_message
  const catColor = CATEGORY_COLORS[task.category || 'general'] || '#495057'
  const dotColor = PRIORITY_COLORS[task.priority] || '#adb5bd'
  const status = statusLabel(task)
  const pct = Math.max(0, Math.min(100, Math.round(task.ai_confidence)))

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: '10px 14px',
        cursor: 'pointer',
        borderBottom: '1px solid #eee',
        borderLeft: selected ? '3px solid #218d8d' : '3px solid transparent',
        background: selected ? '#f0fafa' : hovered ? '#fafafa' : '#fff',
        transition: 'background 0.15s, border-color 0.15s',
        minHeight: 68,
        justifyContent: 'center',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
        <span style={{ fontWeight: 600, fontSize: 14, color: '#1a1a1a', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {task.contact_name || task.phone_number}
        </span>
        {task.category && (
          <span style={{ fontSize: 11, padding: '1px 8px', borderRadius: 10, background: catColor + '1a', color: catColor, fontWeight: 500, whiteSpace: 'nowrap' }}>
            {task.category.replace('_', ' ')}
          </span>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <div style={{ width: 40, height: 4, borderRadius: 2, background: '#e9ecef', overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', borderRadius: 2, background: catColor }} />
          </div>
          <span style={{ fontSize: 11, color: '#6c757d', minWidth: 28, textAlign: 'right' }}>{pct}%</span>
        </div>
        <span style={{ fontSize: 11, color: '#adb5bd', flexShrink: 0 }}>{timeAgo(task.inbound_received_at)}</span>
      </div>
      <div style={{ fontSize: 13, color: '#6c757d', paddingLeft: 16, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        &ldquo;{preview}&rdquo;
      </div>
      <div style={{ fontSize: 11, color: status.color, paddingLeft: 16, letterSpacing: 0.2 }}>
        {task.ai_recommendation ? '\u2508\u2508 ' : ''}{status.text}
      </div>
    </div>
  )
}

export default React.memo(SMSTaskCard)
