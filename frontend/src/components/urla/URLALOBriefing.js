/**
 * URLA LO Briefing Component
 *
 * Displays the loan officer briefing generated after a URLA voice agent call.
 * Shows executive summary, financial snapshot, red flags, missing items,
 * borrower concerns, recommended talking points, and call metadata.
 *
 * Props:
 *   briefing - The full briefing object from the URLA agent
 *   onPushTasks - Callback to push tasks to CRM
 *   onViewHtml - Callback to view HTML version of the briefing
 */

import React from 'react';

// --- Inline styles matching codebase patterns (summary-card, extraction-card) ---

const styles = {
  container: {
    padding: '20px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },

  // Header
  header: {
    marginBottom: '24px',
    paddingBottom: '16px',
    borderBottom: '2px solid #e5e7eb',
  },
  headerTitle: {
    margin: '0 0 4px',
    fontSize: '22px',
    fontWeight: '700',
    color: '#111827',
  },
  headerMeta: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '16px',
    marginTop: '8px',
    fontSize: '13px',
    color: '#6b7280',
  },
  headerMetaItem: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
  },

  // Shared card
  card: {
    background: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
    marginBottom: '20px',
    overflow: 'hidden',
    transition: 'box-shadow 0.2s',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    background: '#f9fafb',
    borderBottom: '1px solid #e5e7eb',
  },
  cardHeaderIcon: {
    fontSize: '20px',
    flexShrink: 0,
  },
  cardHeaderTitle: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '600',
    color: '#111827',
  },
  cardContent: {
    padding: '16px',
  },

  // Executive summary (highlighted)
  executiveCard: {
    background: '#eff6ff',
    borderLeft: '4px solid #3b82f6',
    borderRadius: '8px',
    padding: '16px 20px',
    marginBottom: '20px',
  },
  executiveTitle: {
    margin: '0 0 8px',
    fontSize: '15px',
    fontWeight: '600',
    color: '#1e40af',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  executiveText: {
    margin: 0,
    fontSize: '0.875rem',
    lineHeight: '1.7',
    color: '#1e3a5f',
  },

  // Financial grid
  financialGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
    gap: '16px',
  },
  financialItem: {
    padding: '12px',
    background: '#f9fafb',
    borderRadius: '6px',
    border: '1px solid #e5e7eb',
  },
  financialLabel: {
    fontSize: '12px',
    fontWeight: '500',
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: '4px',
  },
  financialValue: {
    fontSize: '16px',
    fontWeight: '600',
    color: '#111827',
  },

  // Colored section cards
  redFlagCard: {
    background: '#fef2f2',
    border: '1px solid #fecaca',
    borderLeft: '4px solid #ef4444',
    borderRadius: '8px',
    marginBottom: '20px',
    overflow: 'hidden',
  },
  redFlagHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    background: '#fee2e2',
    borderBottom: '1px solid #fecaca',
  },
  redFlagTitle: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '600',
    color: '#991b1b',
  },

  missingCard: {
    background: '#fff7ed',
    border: '1px solid #fed7aa',
    borderLeft: '4px solid #f97316',
    borderRadius: '8px',
    marginBottom: '20px',
    overflow: 'hidden',
  },
  missingHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    background: '#ffedd5',
    borderBottom: '1px solid #fed7aa',
  },
  missingTitle: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '600',
    color: '#9a3412',
  },

  concernsCard: {
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderLeft: '4px solid #3b82f6',
    borderRadius: '8px',
    marginBottom: '20px',
    overflow: 'hidden',
  },
  concernsHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    background: '#dbeafe',
    borderBottom: '1px solid #bfdbfe',
  },
  concernsTitle: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '600',
    color: '#1e40af',
  },

  talkingPointsCard: {
    background: '#f0fdf4',
    border: '1px solid #bbf7d0',
    borderLeft: '4px solid #22c55e',
    borderRadius: '8px',
    marginBottom: '20px',
    overflow: 'hidden',
  },
  talkingPointsHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    background: '#dcfce7',
    borderBottom: '1px solid #bbf7d0',
  },
  talkingPointsTitle: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '600',
    color: '#166534',
  },

  declarationCard: {
    background: '#fefce8',
    border: '1px solid #fde68a',
    borderLeft: '4px solid #eab308',
    borderRadius: '8px',
    marginBottom: '20px',
    overflow: 'hidden',
  },
  declarationHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    background: '#fef9c3',
    borderBottom: '1px solid #fde68a',
  },
  declarationTitle: {
    margin: 0,
    fontSize: '15px',
    fontWeight: '600',
    color: '#854d0e',
  },

  // List items within colored cards
  listItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    padding: '10px 0',
    borderBottom: '1px solid rgba(0,0,0,0.06)',
    fontSize: '14px',
    lineHeight: '1.5',
  },
  listItemLast: {
    borderBottom: 'none',
  },
  listIcon: {
    flexShrink: 0,
    marginTop: '2px',
  },
  numberedIndex: {
    flexShrink: 0,
    width: '24px',
    height: '24px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '12px',
    fontWeight: '700',
    marginTop: '1px',
  },

  // Call metadata
  metadataGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '12px',
  },
  metadataItem: {
    padding: '10px 12px',
    background: '#f9fafb',
    borderRadius: '6px',
    border: '1px solid #e5e7eb',
  },
  metadataLabel: {
    fontSize: '12px',
    fontWeight: '500',
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  metadataValue: {
    fontSize: '14px',
    fontWeight: '500',
    color: '#111827',
    marginTop: '4px',
  },
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '2px 10px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: '600',
  },
  badgeGreen: {
    background: '#dcfce7',
    color: '#166534',
  },
  badgeGray: {
    background: '#f3f4f6',
    color: '#4b5563',
  },
  sectionList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
    marginTop: '4px',
  },
  sectionChip: {
    display: 'inline-block',
    padding: '3px 10px',
    borderRadius: '12px',
    fontSize: '12px',
    fontWeight: '500',
  },
  sectionChipCompleted: {
    background: '#dcfce7',
    color: '#166534',
  },
  sectionChipRemaining: {
    background: '#fee2e2',
    color: '#991b1b',
  },

  // Actions bar
  actionsBar: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '12px',
    padding: '20px 0 0',
    borderTop: '1px solid #e5e7eb',
    marginTop: '4px',
  },
  btnPrimary: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 20px',
    background: '#3b82f6',
    color: '#ffffff',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  btnSecondary: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 20px',
    background: '#ffffff',
    color: '#374151',
    border: '1px solid #d1d5db',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },

  // Empty state
  emptyState: {
    textAlign: 'center',
    padding: '40px 20px',
    color: '#6b7280',
  },
};

// --- SVG Icons (matching codebase inline SVG pattern) ---

const WarningIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const CheckCircleIcon = ({ color = '#22c55e' }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);

const CircleIcon = ({ color = '#f97316' }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <circle cx="12" cy="12" r="10" />
  </svg>
);

const MessageIcon = ({ color = '#3b82f6' }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const ClipboardIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
  </svg>
);

const PrinterIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="6 9 6 2 18 2 18 9" />
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
    <rect x="6" y="14" width="12" height="8" />
  </svg>
);

const FileTextIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
    <polyline points="10 9 9 9 8 9" />
  </svg>
);

const UploadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

// --- Helpers ---

const formatCurrency = (value) => {
  if (value === null || value === undefined) return '--';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
};

const formatPercent = (value) => {
  if (value === null || value === undefined) return '--';
  return `${Number(value).toFixed(1)}%`;
};

const formatTimestamp = (dateStr) => {
  if (!dateStr) return '--';
  const date = new Date(dateStr);
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

// --- Component ---

const URLALOBriefing = ({ briefing, onPushTasks, onViewHtml }) => {
  if (!briefing) {
    return (
      <div style={styles.emptyState}>
        <p style={{ color: '#6b7280', fontSize: '14px' }}>
          No briefing data available.
        </p>
      </div>
    );
  }

  const {
    loan_id,
    generated_at,
    borrower_name,
    borrower_phone,
    borrower_email,
    co_borrower_name,
    loan_purpose,
    loan_amount,
    property_address,
    property_value,
    occupancy_type,
    total_monthly_income,
    total_monthly_debts,
    estimated_dti,
    total_assets,
    employment_summary,
    executive_summary,
    red_flags = [],
    missing_items = [],
    stated_concerns = [],
    recommended_talking_points = [],
    va_eligible,
    declaration_flags = [],
    call_duration_minutes,
    sections_completed = [],
    sections_remaining = [],
  } = briefing;

  return (
    <div style={styles.container}>
      {/* 1. Header */}
      <div style={styles.header}>
        <h2 style={styles.headerTitle}>{borrower_name || 'Borrower'}</h2>
        <div style={styles.headerMeta}>
          {loan_id && (
            <span style={styles.headerMetaItem}>
              <FileTextIcon /> Loan #{loan_id}
            </span>
          )}
          {borrower_phone && (
            <span style={styles.headerMetaItem}>{borrower_phone}</span>
          )}
          {borrower_email && (
            <span style={styles.headerMetaItem}>{borrower_email}</span>
          )}
          {co_borrower_name && (
            <span style={styles.headerMetaItem}>Co-Borrower: {co_borrower_name}</span>
          )}
          {generated_at && (
            <span style={styles.headerMetaItem}>Generated: {formatTimestamp(generated_at)}</span>
          )}
        </div>
      </div>

      {/* 2. Executive Summary */}
      {executive_summary && (
        <div style={styles.executiveCard}>
          <h4 style={styles.executiveTitle}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1e40af" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            Executive Summary
          </h4>
          <p style={styles.executiveText}>{executive_summary}</p>
        </div>
      )}

      {/* 3. Financial Snapshot */}
      <div style={styles.card}>
        <div style={styles.cardHeader}>
          <span style={styles.cardHeaderIcon}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111827" strokeWidth="2">
              <line x1="12" y1="1" x2="12" y2="23" />
              <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
            </svg>
          </span>
          <h4 style={styles.cardHeaderTitle}>Financial Snapshot</h4>
        </div>
        <div style={styles.cardContent}>
          <div style={styles.financialGrid}>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Loan Amount</div>
              <div style={styles.financialValue}>{formatCurrency(loan_amount)}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Property Value</div>
              <div style={styles.financialValue}>{formatCurrency(property_value)}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Loan Purpose</div>
              <div style={styles.financialValue}>{loan_purpose || '--'}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Occupancy</div>
              <div style={styles.financialValue}>{occupancy_type || '--'}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Monthly Income</div>
              <div style={styles.financialValue}>{formatCurrency(total_monthly_income)}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Monthly Debts</div>
              <div style={styles.financialValue}>{formatCurrency(total_monthly_debts)}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Est. DTI</div>
              <div style={styles.financialValue}>{formatPercent(estimated_dti)}</div>
            </div>
            <div style={styles.financialItem}>
              <div style={styles.financialLabel}>Total Assets</div>
              <div style={styles.financialValue}>{formatCurrency(total_assets)}</div>
            </div>
          </div>
          {property_address && (
            <div style={{ marginTop: '12px', fontSize: '13px', color: '#6b7280' }}>
              Property: {property_address}
            </div>
          )}
        </div>
      </div>

      {/* 4. Employment */}
      {employment_summary && (
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.cardHeaderIcon}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111827" strokeWidth="2">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
            </span>
            <h4 style={styles.cardHeaderTitle}>Employment</h4>
          </div>
          <div style={styles.cardContent}>
            <p style={{ margin: 0, fontSize: '14px', lineHeight: '1.6', color: '#374151' }}>
              {employment_summary}
            </p>
          </div>
        </div>
      )}

      {/* 5. Red Flags */}
      {red_flags.length > 0 && (
        <div style={styles.redFlagCard}>
          <div style={styles.redFlagHeader}>
            <WarningIcon />
            <h4 style={styles.redFlagTitle}>Red Flags ({red_flags.length})</h4>
          </div>
          <div style={styles.cardContent}>
            {red_flags.map((flag, index) => (
              <div
                key={index}
                style={{
                  ...styles.listItem,
                  color: '#991b1b',
                  ...(index === red_flags.length - 1 ? styles.listItemLast : {}),
                }}
              >
                <span style={styles.listIcon}>
                  <WarningIcon />
                </span>
                <span>{flag}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. Missing Items */}
      {missing_items.length > 0 && (
        <div style={styles.missingCard}>
          <div style={styles.missingHeader}>
            <CircleIcon color="#f97316" />
            <h4 style={styles.missingTitle}>Missing Items ({missing_items.length})</h4>
          </div>
          <div style={styles.cardContent}>
            {missing_items.map((item, index) => (
              <div
                key={index}
                style={{
                  ...styles.listItem,
                  color: '#9a3412',
                  ...(index === missing_items.length - 1 ? styles.listItemLast : {}),
                }}
              >
                <span style={styles.listIcon}>
                  <CircleIcon color="#f97316" />
                </span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 7. Stated Concerns */}
      {stated_concerns.length > 0 && (
        <div style={styles.concernsCard}>
          <div style={styles.concernsHeader}>
            <MessageIcon color="#3b82f6" />
            <h4 style={styles.concernsTitle}>Borrower Concerns ({stated_concerns.length})</h4>
          </div>
          <div style={styles.cardContent}>
            {stated_concerns.map((concern, index) => (
              <div
                key={index}
                style={{
                  ...styles.listItem,
                  color: '#1e40af',
                  ...(index === stated_concerns.length - 1 ? styles.listItemLast : {}),
                }}
              >
                <span style={styles.listIcon}>
                  <MessageIcon color="#3b82f6" />
                </span>
                <span>{concern}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 8. Recommended Talking Points */}
      {recommended_talking_points.length > 0 && (
        <div style={styles.talkingPointsCard}>
          <div style={styles.talkingPointsHeader}>
            <CheckCircleIcon color="#22c55e" />
            <h4 style={styles.talkingPointsTitle}>
              Recommended Talking Points ({recommended_talking_points.length})
            </h4>
          </div>
          <div style={styles.cardContent}>
            {recommended_talking_points.map((point, index) => (
              <div
                key={index}
                style={{
                  ...styles.listItem,
                  color: '#166534',
                  ...(index === recommended_talking_points.length - 1 ? styles.listItemLast : {}),
                }}
              >
                <span
                  style={{
                    ...styles.numberedIndex,
                    background: '#22c55e',
                    color: '#ffffff',
                  }}
                >
                  {index + 1}
                </span>
                <span>{point}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 9. Declaration Flags */}
      {declaration_flags.length > 0 && (
        <div style={styles.declarationCard}>
          <div style={styles.declarationHeader}>
            <ClipboardIcon />
            <h4 style={styles.declarationTitle}>
              Declaration Flags ({declaration_flags.length})
            </h4>
          </div>
          <div style={styles.cardContent}>
            {declaration_flags.map((flag, index) => (
              <div
                key={index}
                style={{
                  ...styles.listItem,
                  color: '#854d0e',
                  ...(index === declaration_flags.length - 1 ? styles.listItemLast : {}),
                }}
              >
                <span style={styles.listIcon}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#eab308" strokeWidth="2">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                </span>
                <span>{flag}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 10. Call Metadata */}
      <div style={styles.card}>
        <div style={styles.cardHeader}>
          <span style={styles.cardHeaderIcon}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111827" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </span>
          <h4 style={styles.cardHeaderTitle}>Call Metadata</h4>
        </div>
        <div style={styles.cardContent}>
          <div style={styles.metadataGrid}>
            <div style={styles.metadataItem}>
              <div style={styles.metadataLabel}>Duration</div>
              <div style={styles.metadataValue}>
                {call_duration_minutes != null ? `${call_duration_minutes} min` : '--'}
              </div>
            </div>
            <div style={styles.metadataItem}>
              <div style={styles.metadataLabel}>VA Eligible</div>
              <div style={styles.metadataValue}>
                {va_eligible != null ? (
                  <span style={{ ...styles.badge, ...(va_eligible ? styles.badgeGreen : styles.badgeGray) }}>
                    {va_eligible ? 'Yes' : 'No'}
                  </span>
                ) : (
                  '--'
                )}
              </div>
            </div>
          </div>

          {/* Sections completed */}
          {sections_completed.length > 0 && (
            <div style={{ marginTop: '16px' }}>
              <div style={styles.metadataLabel}>Sections Completed</div>
              <div style={styles.sectionList}>
                {sections_completed.map((section, i) => (
                  <span key={i} style={{ ...styles.sectionChip, ...styles.sectionChipCompleted }}>
                    {section}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Sections remaining */}
          {sections_remaining.length > 0 && (
            <div style={{ marginTop: '12px' }}>
              <div style={styles.metadataLabel}>Sections Remaining</div>
              <div style={styles.sectionList}>
                {sections_remaining.map((section, i) => (
                  <span key={i} style={{ ...styles.sectionChip, ...styles.sectionChipRemaining }}>
                    {section}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 11. Actions */}
      <div style={styles.actionsBar}>
        {onPushTasks && (
          <button
            style={styles.btnPrimary}
            onClick={onPushTasks}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#2563eb'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#3b82f6'; }}
          >
            <UploadIcon />
            Push Tasks to CRM
          </button>
        )}
        {onViewHtml && (
          <button
            style={styles.btnSecondary}
            onClick={onViewHtml}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#ffffff'; }}
          >
            <FileTextIcon />
            View HTML Briefing
          </button>
        )}
        <button
          style={styles.btnSecondary}
          onClick={() => window.print()}
          onMouseEnter={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = '#ffffff'; }}
        >
          <PrinterIcon />
          Print
        </button>
      </div>
    </div>
  );
};

export default URLALOBriefing;
