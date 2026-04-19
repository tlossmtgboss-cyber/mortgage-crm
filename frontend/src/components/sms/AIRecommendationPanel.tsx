import React, { memo, useState } from 'react'
import AIConfidenceBadge from './AIConfidenceBadge'

interface AIRecommendationPanelProps {
  task: {
    id: number
    phone_number: string
    contact_name: string | null
    inbound_message: string
    inbound_received_at: string
    category: string | null
    priority: string
    ai_recommendation: string | null
    ai_confidence: number
    ai_reasoning: string | null
    lead_name?: string
    lead_email?: string
    lead_stage?: string
  }
  onRespond: (responseText: string, responseSource: string) => Promise<void>
  onDismiss: () => Promise<void>
  onRegenerate: (feedback?: string) => Promise<void>
  onFeedback: (rating: string) => void
}

type Mode = 'view' | 'edit' | 'write' | 'sending' | 'sent'

const TEAL = '#218d8d'
const MAX_CHARS = 320
const SEGMENT_BREAK = 160

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function formatPhone(phone: string): string {
  const d = phone.replace(/\D/g, '').replace(/^1/, '')
  if (d.length === 10) return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
  return phone
}

function charCountColor(len: number): string {
  if (len > MAX_CHARS) return '#dc3545'
  if (len > SEGMENT_BREAK) return '#e6a817'
  return '#888'
}

const btn = (filled: boolean, disabled?: boolean): React.CSSProperties => ({
  padding: '8px 16px',
  borderRadius: 6,
  fontSize: 13,
  fontWeight: 600,
  cursor: disabled ? 'not-allowed' : 'pointer',
  border: filled ? 'none' : `1.5px solid ${TEAL}`,
  backgroundColor: filled ? (disabled ? '#93c5c5' : TEAL) : 'transparent',
  color: filled ? '#fff' : TEAL,
  opacity: disabled ? 0.6 : 1,
  transition: 'all 0.15s ease',
})

const textBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#888',
  fontSize: 13,
  cursor: 'pointer',
  padding: '8px 12px',
}

function AIRecommendationPanel({
  task,
  onRespond,
  onDismiss,
  onRegenerate,
  onFeedback,
}: AIRecommendationPanelProps) {
  const [mode, setMode] = useState<Mode>(task.ai_recommendation ? 'view' : 'write')
  const [draft, setDraft] = useState('')
  const [regenOpen, setRegenOpen] = useState(false)
  const [regenFeedback, setRegenFeedback] = useState('')
  const [feedbackGiven, setFeedbackGiven] = useState<string | null>(null)

  const hasRec = !!task.ai_recommendation

  const handleSendAI = async () => {
    if (!task.ai_recommendation) return
    setMode('sending')
    try {
      await onRespond(task.ai_recommendation, 'ai_accepted')
      setMode('sent')
    } catch {
      setMode('view')
    }
  }

  const handleSendDraft = async (source: string) => {
    if (!draft.trim() || draft.length > MAX_CHARS) return
    setMode('sending')
    try {
      await onRespond(draft, source)
      setMode('sent')
    } catch {
      setMode('edit')
    }
  }

  const handleRegenerate = async () => {
    setRegenOpen(false)
    await onRegenerate(regenFeedback || undefined)
    setRegenFeedback('')
  }

  const handleFeedback = (rating: string) => {
    setFeedbackGiven(rating)
    onFeedback(rating)
  }

  const enterEdit = () => {
    setDraft(task.ai_recommendation || '')
    setMode('edit')
  }

  const enterWrite = () => {
    setDraft('')
    setMode('write')
  }

  const cancelEdit = () => setMode(hasRec ? 'view' : 'write')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #e8e8e8' }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#1a1a1a' }}>
          {task.contact_name || 'Unknown'} <span style={{ fontWeight: 400, color: '#666', fontSize: 14 }}>{formatPhone(task.phone_number)}</span>
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 13, color: '#666' }}>
          {task.category && <span>Category: <b style={{ color: '#444' }}>{task.category}</b></span>}
          <span>Priority: <b style={{ color: task.priority === 'urgent' ? '#dc3545' : '#444' }}>{task.priority.charAt(0).toUpperCase() + task.priority.slice(1)}</b></span>
          {task.lead_stage && <span>Lead Stage: <b style={{ color: TEAL }}>{task.lead_stage}</b></span>}
        </div>
      </div>

      <div style={{ padding: '16px 20px', borderBottom: '1px solid #e8e8e8' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: '#999', textTransform: 'uppercase' }}>Inbound Message</span>
          <span style={{ fontSize: 12, color: '#999' }}>{timeAgo(task.inbound_received_at)}</span>
        </div>
        <div style={{ background: '#f5f5f5', borderRadius: 8, padding: '12px 14px', fontSize: 14, color: '#333', lineHeight: 1.5, fontStyle: 'italic' }}>
          "{task.inbound_message}"
        </div>
      </div>

      <div style={{ flex: 1, padding: '16px 20px', overflowY: 'auto' }}>
        {mode === 'sent' ? (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>&#10003;</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#28a745', marginBottom: 16 }}>Response Sent</div>
            {!feedbackGiven && (
              <div>
                <div style={{ fontSize: 13, color: '#888', marginBottom: 10 }}>Was this AI recommendation helpful?</div>
                <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
                  <button onClick={() => handleFeedback('positive')} style={{ ...textBtn, fontSize: 24 }} title="Helpful">&#128077;</button>
                  <button onClick={() => handleFeedback('negative')} style={{ ...textBtn, fontSize: 24 }} title="Not helpful">&#128078;</button>
                </div>
              </div>
            )}
            {feedbackGiven && <div style={{ fontSize: 13, color: '#888' }}>Thanks for your feedback!</div>}
          </div>
        ) : mode === 'sending' ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <div style={{ width: 28, height: 28, border: `3px solid ${TEAL}20`, borderTopColor: TEAL, borderRadius: '50%', animation: 'airp-spin 0.8s linear infinite', margin: '0 auto 12px' }} />
            <div style={{ fontSize: 14, color: '#888' }}>Sending response...</div>
            <style>{`@keyframes airp-spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        ) : (
          <>
            {hasRec && mode === 'view' && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: '#999', textTransform: 'uppercase' }}>
                    &#129302; AI Recommendation
                  </span>
                  <AIConfidenceBadge confidence={task.ai_confidence} size="sm" showBar />
                </div>
                <div style={{ background: 'linear-gradient(135deg, #f0fafa 0%, #f7fdfd 100%)', borderRadius: 8, padding: '14px 16px', fontSize: 14, color: '#1a1a1a', lineHeight: 1.55, border: '1px solid #d4eded', marginBottom: 10 }}>
                  "{task.ai_recommendation}"
                </div>
                {task.ai_reasoning && (
                  <div style={{ fontSize: 13, color: '#777', lineHeight: 1.5, marginBottom: 16 }}>
                    <b style={{ color: '#555' }}>Why:</b> {task.ai_reasoning}
                  </div>
                )}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                  <button onClick={handleSendAI} style={btn(true)}>Send AI Response</button>
                  <button onClick={enterEdit} style={btn(false)}>Edit &amp; Send</button>
                  <button onClick={enterWrite} style={btn(false)}>Write Own</button>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button onClick={onDismiss} style={textBtn}>Dismiss</button>
                  <button onClick={() => setRegenOpen(!regenOpen)} style={{ ...textBtn, color: TEAL, fontSize: 12 }}>
                    Not quite right? Regenerate
                  </button>
                </div>
                {regenOpen && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
                    <input
                      value={regenFeedback}
                      onChange={e => setRegenFeedback(e.target.value)}
                      placeholder="What should change?"
                      style={{ flex: 1, padding: '6px 10px', borderRadius: 6, border: '1px solid #ccc', fontSize: 13, outline: 'none' }}
                      onKeyDown={e => e.key === 'Enter' && handleRegenerate()}
                    />
                    <button onClick={handleRegenerate} style={{ ...btn(true), padding: '6px 12px', fontSize: 12 }}>Regenerate</button>
                  </div>
                )}
              </>
            )}

            {!hasRec && mode !== 'edit' && mode !== 'write' && (
              <div style={{ textAlign: 'center', padding: '24px 0' }}>
                <div style={{ fontSize: 14, color: '#999', marginBottom: 12 }}>AI couldn't generate a recommendation for this message.</div>
                <button onClick={enterWrite} style={btn(true)}>Write Own Response</button>
                <div style={{ marginTop: 8 }}>
                  <button onClick={onDismiss} style={textBtn}>Dismiss</button>
                </div>
              </div>
            )}

            {(mode === 'edit' || mode === 'write') && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: '#999', textTransform: 'uppercase', marginBottom: 8 }}>
                  {mode === 'edit' ? 'Edit Response' : 'Write Response'}
                </div>
                <textarea
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  rows={5}
                  style={{ width: '100%', padding: '12px 14px', borderRadius: 8, border: '1px solid #ccc', fontSize: 14, lineHeight: 1.5, resize: 'vertical', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }}
                  onFocus={e => (e.target.style.borderColor = TEAL)}
                  onBlur={e => (e.target.style.borderColor = '#ccc')}
                  placeholder="Type your response..."
                  autoFocus
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
                  <span style={{ fontSize: 12, color: charCountColor(draft.length), fontWeight: draft.length > SEGMENT_BREAK ? 600 : 400 }}>
                    {draft.length}/{MAX_CHARS}
                    {draft.length > SEGMENT_BREAK && draft.length <= MAX_CHARS && ' (2 segments)'}
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={cancelEdit} style={textBtn}>Cancel</button>
                    <button
                      onClick={() => handleSendDraft(mode === 'edit' ? 'ai_edited' : 'manual')}
                      disabled={!draft.trim() || draft.length > MAX_CHARS}
                      style={btn(true, !draft.trim() || draft.length > MAX_CHARS)}
                    >
                      {mode === 'edit' ? 'Send Edited Response' : 'Send Response'}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default memo(AIRecommendationPanel)
