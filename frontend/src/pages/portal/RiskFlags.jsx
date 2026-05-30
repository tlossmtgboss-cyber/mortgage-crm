/**
 * RiskFlags — borrower-facing "Attention Needed" panel.
 *
 * Renders the `risks` array from the PURL-authed borrower dashboard
 * (GET /api/v1/portal/borrower/{crmLoanId}/dashboard) in a borrower-friendly
 * card. Returns null when there are no risks so the Overview stays clean.
 *
 * Self-contained: inline styles only, no dependency on the (deleted) portal CSS.
 * Severity is mapped to a calm, non-alarming chip vocabulary — no red sirens
 * for a borrower. Copy stays jargon-free; we prefer the backend's
 * borrower_label / borrower_action / recommended_action fields when present and
 * fall back to title/description otherwise.
 */
import React from 'react';

const SEVERITY_STYLES = {
  high: { chipBg: '#fef3c7', chipColor: '#92400e', label: 'Needs your attention', accent: '#f59e0b' },
  critical: { chipBg: '#fef3c7', chipColor: '#92400e', label: 'Needs your attention', accent: '#f59e0b' },
  medium: { chipBg: '#dbeafe', chipColor: '#1e40af', label: 'Heads up', accent: '#3b82f6' },
  low: { chipBg: '#f1f5f9', chipColor: '#475569', label: 'FYI', accent: '#94a3b8' },
  info: { chipBg: '#f1f5f9', chipColor: '#475569', label: 'FYI', accent: '#94a3b8' },
};

const severityStyle = (severity) => {
  const key = (severity || 'medium').toString().toLowerCase();
  return SEVERITY_STYLES[key] || SEVERITY_STYLES.medium;
};

const card = {
  background: '#fff',
  borderRadius: 12,
  padding: 20,
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  marginBottom: 16,
};
const headerRow = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 14,
};
const titleStyle = { margin: 0, fontSize: 16, fontWeight: 600, color: '#1a202c' };
const badge = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 0.4,
  color: '#92400e',
  background: '#fef3c7',
  borderRadius: 999,
  padding: '3px 10px',
};
const item = (accent) => ({
  display: 'flex',
  gap: 12,
  alignItems: 'flex-start',
  padding: '12px 0',
  borderTop: '1px solid #f1f5f9',
  borderLeft: `3px solid ${accent}`,
  paddingLeft: 12,
});
const itemContent = { flex: 1, minWidth: 0 };
const itemTitle = { fontSize: 14, fontWeight: 600, color: '#1a202c', display: 'block' };
const itemDesc = { fontSize: 13, color: '#64748b', display: 'block', marginTop: 2 };
const itemAction = { fontSize: 13, color: '#334155', display: 'block', marginTop: 6, fontWeight: 500 };
const chip = (s) => ({
  fontSize: 11,
  fontWeight: 700,
  color: s.chipColor,
  background: s.chipBg,
  borderRadius: 999,
  padding: '2px 8px',
  whiteSpace: 'nowrap',
});
const metaCol = { display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 };
const viewLink = {
  fontSize: 12,
  fontWeight: 600,
  color: '#2563eb',
  background: 'none',
  border: 'none',
  padding: 0,
  cursor: 'pointer',
};

const AlertIcon = ({ color }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    width="22"
    height="22"
    style={{ flexShrink: 0, marginTop: 1 }}
    aria-hidden="true"
  >
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

export default function RiskFlags({ risks }) {
  if (!Array.isArray(risks) || risks.length === 0) {
    return null;
  }

  return (
    <div style={card} className="risk-flags-card">
      <div style={headerRow}>
        <h3 style={titleStyle}>Attention Needed</h3>
        <span style={badge}>{risks.length} {risks.length === 1 ? 'ITEM' : 'ITEMS'}</span>
      </div>

      <div>
        {risks.map((risk, idx) => {
          const s = severityStyle(risk?.severity);
          const title = risk?.borrower_label || risk?.title || risk?.label || 'Item needs review';
          const description = risk?.borrower_description || risk?.description || risk?.message || '';
          const action = risk?.borrower_action || risk?.recommended_action || risk?.action || '';
          const key = risk?.id != null ? risk.id : `${title}-${idx}`;

          return (
            <div key={key} style={item(s.accent)}>
              <AlertIcon color={s.accent} />
              <div style={itemContent}>
                <span style={itemTitle}>{title}</span>
                {description && <span style={itemDesc}>{description}</span>}
                {action && <span style={itemAction}>What to do: {action}</span>}
              </div>
              <div style={metaCol}>
                <span style={chip(s)}>{s.label}</span>
                {risk?.link && (
                  <a
                    href={risk.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={viewLink}
                  >
                    View &rsaquo;
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
