import React from 'react'

interface AIConfidenceBadgeProps {
  confidence: number
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
  showBar?: boolean
  animate?: boolean
}

const tiers = [
  { max: 30, color: '#dc3545', label: 'Low' },
  { max: 50, color: '#fd7e14', label: 'Learning' },
  { max: 70, color: '#ffc107', label: 'Moderate' },
  { max: 85, color: '#218d8d', label: 'High' },
  { max: 100, color: '#28a745', label: 'Very High' },
] as const

const sizes = {
  sm: { fontSize: 11, px: 6, py: 2, barHeight: 3 },
  md: { fontSize: 13, px: 10, py: 4, barHeight: 4 },
  lg: { fontSize: 15, px: 14, py: 6, barHeight: 5 },
} as const

function getTier(confidence: number) {
  const clamped = Math.max(0, Math.min(100, Math.round(confidence)))
  const tier = tiers.find(t => clamped <= t.max) || tiers[tiers.length - 1]
  return { ...tier, value: clamped }
}

const pulseKeyframes = `
@keyframes aicb-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
`

let styleInjected = false
function injectKeyframes() {
  if (styleInjected) return
  styleInjected = true
  const style = document.createElement('style')
  style.textContent = pulseKeyframes
  document.head.appendChild(style)
}

function AIConfidenceBadge({
  confidence,
  size = 'md',
  showLabel = true,
  showBar = false,
  animate = false,
}: AIConfidenceBadgeProps) {
  const { color, label, value } = getTier(confidence)
  const s = sizes[size]
  const shouldPulse = animate && value > 80

  if (shouldPulse) injectKeyframes()

  const badgeStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: s.px / 2,
    backgroundColor: `${color}18`,
    color,
    border: `1px solid ${color}40`,
    borderRadius: 999,
    padding: `${s.py}px ${s.px}px`,
    fontSize: s.fontSize,
    fontWeight: 600,
    lineHeight: 1,
    whiteSpace: 'nowrap',
    animation: shouldPulse ? 'aicb-pulse 2s ease-in-out infinite' : undefined,
  }

  const barContainerStyle: React.CSSProperties = {
    width: '100%',
    height: s.barHeight,
    backgroundColor: `${color}20`,
    borderRadius: s.barHeight,
    marginTop: s.py,
    overflow: 'hidden',
  }

  const barFillStyle: React.CSSProperties = {
    width: `${value}%`,
    height: '100%',
    backgroundColor: color,
    borderRadius: s.barHeight,
    transition: 'width 0.4s ease',
  }

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'stretch' }}>
      <span style={badgeStyle}>
        {value}%{showLabel && <span style={{ fontWeight: 400, opacity: 0.85 }}>{label}</span>}
      </span>
      {showBar && (
        <div style={barContainerStyle}>
          <div style={barFillStyle} />
        </div>
      )}
    </div>
  )
}

export default React.memo(AIConfidenceBadge)
