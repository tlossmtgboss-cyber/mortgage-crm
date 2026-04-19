import React, { memo, useState } from 'react'

interface CategorySetting {
  category: string
  confidence_score: number
  auto_respond_enabled: boolean
  auto_respond_threshold: number
  total_recommendations: number
  accepted_count: number
  edited_count: number
  rejected_count: number
}

interface AutoPilotSettingsProps {
  settings: CategorySetting[]
  onUpdateSetting: (category: string, enabled: boolean, threshold: number) => Promise<void>
}

const CATEGORY_LABELS: Record<string, string> = {
  scheduling: 'Scheduling',
  question: 'General Questions',
  follow_up: 'Follow-ups',
  rate_inquiry: 'Rate Inquiries',
  document_request: 'Document Requests',
  greeting: 'Greetings',
  complaint: 'Complaints',
  general: 'General',
}

const TEAL = '#218d8d'

function confidenceColor(score: number): string {
  if (score >= 85) return '#22c55e'
  if (score >= 70) return TEAL
  if (score >= 55) return '#eab308'
  if (score >= 40) return '#f97316'
  return '#ef4444'
}

function formatCategory(cat: string): string {
  return CATEGORY_LABELS[cat] || cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function ConfidenceMeter({ score }: { score: number }) {
  const color = confidenceColor(score)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 8, borderRadius: 4, background: '#e5e7eb', overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', borderRadius: 4, background: color, transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 600, color, minWidth: 38, textAlign: 'right' }}>{score}%</span>
    </div>
  )
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      style={{
        width: 44, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer',
        background: checked ? TEAL : '#d1d5db', position: 'relative', transition: 'background 0.2s ease',
        padding: 0, flexShrink: 0,
      }}
      aria-checked={checked}
      role="switch"
    >
      <div style={{
        width: 18, height: 18, borderRadius: '50%', background: '#fff',
        position: 'absolute', top: 3, left: checked ? 23 : 3,
        transition: 'left 0.2s ease', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
      }} />
    </button>
  )
}

function CategoryCard({ setting, onUpdate }: { setting: CategorySetting; onUpdate: AutoPilotSettingsProps['onUpdateSetting'] }) {
  const [enabled, setEnabled] = useState(setting.auto_respond_enabled)
  const [threshold, setThreshold] = useState(setting.auto_respond_threshold)
  const [saving, setSaving] = useState(false)

  const handleToggle = async (val: boolean) => {
    setEnabled(val)
    setSaving(true)
    try { await onUpdate(setting.category, val, threshold) } finally { setSaving(false) }
  }

  const handleThreshold = async (val: number) => {
    setThreshold(val)
    setSaving(true)
    try { await onUpdate(setting.category, enabled, val) } finally { setSaving(false) }
  }

  const meetsThreshold = setting.confidence_score >= threshold
  const neededAccepts = Math.max(0, Math.ceil((threshold - setting.confidence_score) / 5))

  let statusText: string
  let statusColor: string
  if (!meetsThreshold) {
    statusText = `Learning... (need ~${neededAccepts} more accepts to reach threshold)`
    statusColor = '#9ca3af'
  } else if (enabled) {
    statusText = 'Active \u2014 AI is auto-responding'
    statusColor = '#22c55e'
  } else {
    statusText = 'Ready \u2014 toggle on to activate'
    statusColor = TEAL
  }

  return (
    <div style={{
      background: '#fff', borderRadius: 10, padding: '16px 20px', border: '1px solid #e5e7eb',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)', opacity: saving ? 0.7 : 1, transition: 'opacity 0.2s',
    }}>
      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8, color: '#1f2937' }}>
        {formatCategory(setting.category)}
      </div>
      <ConfidenceMeter score={setting.confidence_score} />
      <div style={{ fontSize: 12, color: '#6b7280', margin: '8px 0 12px' }}>
        {setting.accepted_count} accepted / {setting.edited_count} edited / {setting.rejected_count} rejected out of {setting.total_recommendations} total
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: enabled ? 12 : 0 }}>
        <Toggle checked={enabled} onChange={handleToggle} />
        <span style={{ fontSize: 13, color: '#374151' }}>Auto-respond when confident</span>
      </div>
      {enabled && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>
            <span>Aggressive (50%)</span>
            <span>Conservative (99%)</span>
          </div>
          <input
            type="range" min={50} max={99} value={threshold}
            onChange={e => setThreshold(Number(e.target.value))}
            onMouseUp={() => handleThreshold(threshold)}
            onTouchEnd={() => handleThreshold(threshold)}
            style={{ width: '100%', accentColor: TEAL }}
          />
          <div style={{ textAlign: 'center', fontSize: 12, color: TEAL, fontWeight: 600 }}>{threshold}%</div>
        </div>
      )}
      <div style={{ fontSize: 12, fontWeight: 500, color: statusColor, display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', background: statusColor, display: 'inline-block',
          boxShadow: enabled && meetsThreshold ? `0 0 6px ${statusColor}` : 'none',
        }} />
        {statusText}
      </div>
    </div>
  )
}

function AutoPilotSettings({ settings, onUpdateSetting }: AutoPilotSettingsProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{ borderRadius: 12, border: '1px solid #e5e7eb', background: '#f9fafb', overflow: 'hidden' }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px', border: 'none', background: 'none', cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>{'\u2699\uFE0F'}</span>
          <span style={{ fontWeight: 700, fontSize: 15, color: '#1f2937' }}>AI Auto-Pilot</span>
          {settings.filter(s => s.auto_respond_enabled && s.confidence_score >= s.auto_respond_threshold).length > 0 && (
            <span style={{
              fontSize: 11, fontWeight: 600, background: TEAL, color: '#fff',
              borderRadius: 10, padding: '2px 8px',
            }}>
              {settings.filter(s => s.auto_respond_enabled && s.confidence_score >= s.auto_respond_threshold).length} active
            </span>
          )}
        </div>
        <span style={{
          transform: expanded ? 'rotate(180deg)' : 'rotate(0)',
          transition: 'transform 0.2s ease', fontSize: 14, color: '#9ca3af',
        }}>
          {'\u25BC'}
        </span>
      </button>
      {expanded && (
        <div style={{ padding: '0 20px 20px' }}>
          {settings.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#9ca3af', fontSize: 13, padding: '24px 0' }}>
              No AI data yet. As you respond to SMS tasks, AI will learn your preferences and build confidence.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {settings.map(s => (
                <CategoryCard key={s.category} setting={s} onUpdate={onUpdateSetting} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default memo(AutoPilotSettings)
