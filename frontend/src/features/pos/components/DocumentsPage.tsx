import React, { useCallback, useMemo, useRef, useState } from 'react';

import type { DetectedDocument, DocCategory } from '../hooks/useDocumentDetector';
import { CATEGORY_LABELS } from '../hooks/useDocumentDetector';

import './documents-page.css';

// ---------- types ----------

type DocStatus = 'action' | 'review' | 'approved' | 'reference';
type FilterKey = 'all' | DocStatus;

interface DocItem {
  id: string;
  name: string;
  status: DocStatus;
  category: DocCategory;
  description?: string;
  filename?: string;
  filesize?: string;
  uploadedAt?: string;
  dueDate?: string;
  dueSeverity?: 'urgent' | 'normal';
  extraction?: { label: string; value: string }[];
  extractionMatch?: boolean;
  reviewedBy?: string;
  clearedAt?: string;
  meta?: string;
  eSignDocs?: string[];
  eSignProgress?: { signed: number; total: number };
}

export interface DocumentsPageProps {
  loName: string;
  loNmls?: string;
  loInitials: string;
  detectedDocs: DetectedDocument[];
  onAskAria?: () => void;
  onBack: () => void;
}

// ---------- demo data ----------
// Real data will come from the API; this seeds the page so the LO sees a complete picture.

const DEMO_DOCS: DocItem[] = [
  {
    id: 'paystubs', name: 'Upload your most recent paystubs', status: 'action', category: 'income',
    description: 'We need your 2 most recent paystubs, dated within the last 30 days. PDF or photo is fine.',
    dueDate: 'Due soon', dueSeverity: 'urgent',
  },
  {
    id: 'bankstmts', name: 'Upload last 60 days of bank statements', status: 'action', category: 'assets',
    description: 'All pages from your checking account. Every page, even the blank ones.',
    dueDate: 'Due soon',
  },
  {
    id: 'esign-docs', name: 'Documents to review & sign', status: 'action', category: 'compliance',
    description: 'Your loan officer has sent documents that need your electronic signature.',
    eSignDocs: [
      'Letter of Explanation — Large Deposit',
      'Credit Inquiry Letter',
      'Gift Letter',
    ],
    eSignProgress: { signed: 0, total: 3 },
  },
  {
    id: 'w2-2023', name: 'W-2 (2023)', status: 'review', category: 'income',
    filename: 'w2_2023.pdf', filesize: '318 KB', uploadedAt: 'Submitted recently',
    extraction: [{ label: 'Employer', value: 'On file' }, { label: 'Box 1 Wages', value: 'Verified' }, { label: 'Tax Year', value: '2023' }],
    extractionMatch: true, reviewedBy: 'Reviewed by Aria',
  },
  {
    id: 'gift-letter', name: 'Gift letter', status: 'review', category: 'assets',
    filename: 'gift_letter_signed.pdf', filesize: '124 KB', uploadedAt: 'Submitted recently',
    extraction: [{ label: 'Donors', value: 'On file' }, { label: 'Amount', value: 'Verified' }, { label: 'Relationship', value: 'On file' }],
    extractionMatch: true, reviewedBy: 'Awaiting LO review',
  },
  { id: 'tax-2022', name: 'Tax returns — 2022', status: 'approved', category: 'income', clearedAt: 'Cleared', meta: '1040 + Schedules' },
  { id: 'tax-2023', name: 'Tax returns — 2023', status: 'approved', category: 'income', clearedAt: 'Cleared', meta: '1040 + Schedules' },
  { id: 'dl', name: "Driver's license", status: 'approved', category: 'identity', clearedAt: 'Cleared', meta: 'Verified' },
  { id: 'app-1003', name: 'Loan application (signed)', status: 'approved', category: 'compliance', clearedAt: 'Cleared', meta: 'URLA 1003' },
  { id: 'voided-check', name: 'Voided check', status: 'approved', category: 'assets', clearedAt: 'Cleared', meta: 'ACH verification' },
  { id: 'ho-insurance', name: 'Homeowners insurance quote', status: 'approved', category: 'compliance', clearedAt: 'Cleared' },
  { id: 'purchase-contract', name: 'Purchase contract', status: 'approved', category: 'property', clearedAt: 'Cleared' },
  { id: 'emd', name: 'Earnest money deposit', status: 'approved', category: 'assets', clearedAt: 'Cleared' },
  { id: 'le', name: 'Loan Estimate', status: 'reference', category: 'compliance', meta: 'PDF · 6 pages' },
  { id: 'preapproval', name: 'Pre-approval letter', status: 'reference', category: 'compliance', meta: 'PDF · valid 90 days' },
  { id: 'initial-1003', name: 'Initial 1003 application copy', status: 'reference', category: 'compliance', meta: 'PDF · 12 pages' },
  { id: 'rate-lock', name: 'Rate lock confirmation', status: 'reference', category: 'compliance', meta: '30-day lock' },
];

// ---------- filter config ----------

const FILTERS: { key: FilterKey; label: string; pulse?: boolean }[] = [
  { key: 'all', label: 'All Documents' },
  { key: 'action', label: 'Action Required', pulse: true },
  { key: 'review', label: 'In Review' },
  { key: 'approved', label: 'Approved' },
  { key: 'reference', label: 'Reference Library' },
];

// ---------- component ----------

export const DocumentsPage: React.FC<DocumentsPageProps> = ({
  loName,
  loInitials,
  onAskAria,
  onBack,
}) => {
  const [filter, setFilter] = useState<FilterKey>('all');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const docs = DEMO_DOCS;

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: docs.length };
    for (const d of docs) c[d.status] = (c[d.status] || 0) + 1;
    return c;
  }, [docs]);

  const visible = useMemo(
    () => (filter === 'all' ? docs : docs.filter(d => d.status === filter)),
    [docs, filter],
  );

  const grouped = useMemo(() => {
    const order: DocStatus[] = ['action', 'review', 'approved', 'reference'];
    return order
      .map(s => ({ status: s, items: visible.filter(d => d.status === s) }))
      .filter(g => g.items.length > 0);
  }, [visible]);

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <div className="docs-page">
      {/* Back button */}
      <button type="button" className="docs-page__back" onClick={onBack}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to application
      </button>

      {/* Header */}
      <div className="docs-page__header">
        <div className="docs-page__header-left">
          <div className="docs-page__badge-row">
            <span className="docs-chip">Smart Docs</span>
          </div>
          <h1 className="docs-page__title">Documents</h1>
          <p className="docs-page__subtitle">
            Everything {loName} and the underwriter need from you, all in one place.
            Drop a document and we'll handle the rest.
          </p>
        </div>
        <input ref={fileInputRef} type="file" className="docs-page__file-input" multiple accept=".pdf,.png,.jpg,.jpeg" />
      </div>

      {/* Stats */}
      <div className="docs-stats">
        <StatCard label="Action Required" value={counts.action || 0} sub={`${counts.action || 0} items need attention`} variant="action" />
        <StatCard label="In Review" value={counts.review || 0} sub={`Awaiting ${loName}`} variant="review" />
        <StatCard label="Approved" value={counts.approved || 0} sub="Cleared by underwriting" variant="approved" />
        <StatCard label="Reference Library" value={counts.reference || 0} sub="Always available to download" />
      </div>

      {/* Aria banner */}
      <div className="docs-banner">
        <span className="docs-banner__seal">{loInitials.charAt(0) || 'A'}</span>
        <div className="docs-banner__content">
          <div className="docs-banner__title">Aria reads your documents the moment they upload</div>
          <p className="docs-banner__desc">
            Drop a paystub, tax return, or bank statement and Aria classifies it, extracts the key numbers,
            and cross-checks them against your application — usually within 30 seconds.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="docs-filters" role="tablist">
        {FILTERS.map(f => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            className={`docs-filter${filter === f.key ? ' is-active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.pulse && f.key !== filter && <span className="docs-filter__pulse" />}
            {f.label}
            <span className="docs-filter__count">{counts[f.key] || 0}</span>
          </button>
        ))}
      </div>

      {/* Sections */}
      {grouped.map(group => (
        <section key={group.status} className="docs-section">
          <div className="docs-section__header">
            <h2 className="docs-section__title">{SECTION_TITLES[group.status]}</h2>
            <span className={`docs-chip docs-chip--${group.status === 'approved' ? 'success' : group.status === 'action' ? 'gold' : 'neutral'}`}>
              {group.items.length} {group.items.length === 1 ? 'item' : 'items'}
            </span>
            <div className="docs-section__line" />
          </div>

          {group.status === 'approved' ? (
            <div className="docs-approved-grid">
              {group.items.map(doc => (
                <button key={doc.id} type="button" className="docs-approved-row">
                  <div className="docs-approved-row__icon"><CheckIcon /></div>
                  <div className="docs-approved-row__main">
                    <p className="docs-approved-row__title">{doc.name}</p>
                    <p className="docs-approved-row__sub">{doc.clearedAt}{doc.meta ? ` · ${doc.meta}` : ''}</p>
                  </div>
                  <span className="docs-approved-row__cta">View &rarr;</span>
                </button>
              ))}
            </div>
          ) : group.status === 'reference' ? (
            <div className="docs-ref-grid">
              {group.items.map(doc => (
                <button key={doc.id} type="button" className="docs-ref-card">
                  <div className="docs-ref-card__icon"><DocFileIcon /></div>
                  <div className="docs-ref-card__body">
                    <p className="docs-ref-card__title">{doc.name}</p>
                    <p className="docs-ref-card__meta">{doc.meta}</p>
                  </div>
                  <span className="docs-ref-card__action"><DownloadIcon /></span>
                </button>
              ))}
            </div>
          ) : (
            <div className="docs-card-list">
              {group.items.map(doc => (
                <DocCard key={doc.id} doc={doc} onUpload={handleUploadClick} onAskAria={onAskAria} />
              ))}
            </div>
          )}
        </section>
      ))}

      {/* Footer */}
      <div className="docs-page__footer">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        <span>Bank-grade encryption · We never sell your data · Equal Housing Lender</span>
      </div>
    </div>
  );
};

// ---------- sub-components ----------

const SECTION_TITLES: Record<DocStatus, string> = {
  action: 'Action Required',
  review: 'In Review',
  approved: 'Approved',
  reference: 'Reference Library',
};

const StatCard: React.FC<{
  label: string; value: number; sub: string; variant?: 'action' | 'review' | 'approved';
}> = ({ label, value, sub, variant }) => (
  <div className={`docs-stat${variant ? ` docs-stat--${variant}` : ''}`}>
    <p className="docs-stat__label">{label}</p>
    <p className="docs-stat__value">{value}</p>
    <p className="docs-stat__sub">{sub}</p>
  </div>
);

const DocCard: React.FC<{
  doc: DocItem; onUpload: () => void; onAskAria?: () => void;
}> = ({ doc, onUpload, onAskAria }) => (
  <article className={`docs-card${doc.status === 'action' ? ' docs-card--action' : ''}`}>
    <div className="docs-card__top">
      <div className="docs-card__info">
        <h3 className="docs-card__name">{doc.name}</h3>
        {doc.description && <p className="docs-card__desc">{doc.description}</p>}
        {doc.filename && (
          <p className="docs-card__file">
            {doc.uploadedAt} · <span className="docs-card__filename">{doc.filename}</span> · {doc.filesize}
          </p>
        )}
      </div>
      <div className="docs-card__status-col">
        <span className={`docs-status-pill docs-status-pill--${doc.status}`}>
          <span className="docs-status-pill__dot" /> {doc.status === 'action' ? (doc.eSignDocs ? 'Awaiting eSign' : 'Action Required') : 'In Review'}
        </span>
        {doc.dueDate && (
          <span className={`docs-card__due${doc.dueSeverity === 'urgent' ? ' docs-card__due--urgent' : ''}`}>
            {doc.dueDate}
          </span>
        )}
        {doc.reviewedBy && <span className="docs-card__reviewed">{doc.reviewedBy}</span>}
      </div>
    </div>

    {/* Upload zone for action items */}
    {doc.status === 'action' && !doc.eSignDocs && (
      <div className="docs-upload-zone" onClick={onUpload}>
        <div className="docs-upload-zone__icon"><UploadIcon /></div>
        <div className="docs-upload-zone__text">
          <p className="docs-upload-zone__primary">Drop your files here</p>
          <p className="docs-upload-zone__hint">or click to browse · PDF, PNG, JPG up to 25 MB each</p>
        </div>
        <button type="button" className="docs-upload-cta">Browse files</button>
      </div>
    )}

    {/* eSign panel */}
    {doc.eSignDocs && (
      <div className="docs-esign">
        <div className="docs-esign__header">
          <span className="docs-esign__count">
            {doc.eSignProgress?.total} documents · {doc.eSignProgress?.signed} of {doc.eSignProgress?.total} signed
          </span>
        </div>
        <div className="docs-esign__list">
          {doc.eSignDocs.map(name => (
            <div key={name} className="docs-esign__item">
              <DocFileIcon /> {name}
            </div>
          ))}
        </div>
        <div className="docs-esign__actions">
          <button type="button" className="docs-btn docs-btn--primary">
            Review &amp; Sign
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
          <button type="button" className="docs-btn docs-btn--ghost">Download all as PDF</button>
        </div>
      </div>
    )}

    {/* Extraction preview for in-review items */}
    {doc.extraction && (
      <div className="docs-extraction">
        <div className="docs-extraction__body">
          <p className="docs-extraction__label">
            <SparkIcon /> Extracted by Aria
          </p>
          <div className="docs-extraction__fields">
            {doc.extraction.map(f => (
              <div key={f.label} className="docs-extraction__field">
                <p className="docs-extraction__key">{f.label}</p>
                <p className="docs-extraction__val">{f.value}</p>
              </div>
            ))}
          </div>
        </div>
        {doc.extractionMatch && (
          <div className="docs-extraction__check"><CheckIcon /></div>
        )}
      </div>
    )}

    {/* AI hint */}
    {doc.status === 'action' && onAskAria && (
      <div className="docs-ai-hint">
        <SparkIcon />
        <span>
          Aria will cross-check this against your application —{' '}
          <button type="button" className="docs-ai-hint__action" onClick={onAskAria}>
            ask about acceptable formats
          </button>
        </span>
      </div>
    )}
  </article>
);

// ---------- icons ----------

const UploadIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const CheckIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const DocFileIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
  </svg>
);

const DownloadIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const SparkIcon: React.FC = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" className="docs-spark">
    <path d="M12 2L13.5 8.5 20 10 13.5 11.5 12 18 10.5 11.5 4 10 10.5 8.5z" />
  </svg>
);
