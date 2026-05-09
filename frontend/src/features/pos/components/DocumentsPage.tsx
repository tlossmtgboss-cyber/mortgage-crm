import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { DetectedDocument, DocCategory } from '../hooks/useDocumentDetector';
import { CATEGORY_LABELS } from '../hooks/useDocumentDetector';
import { posApi } from '../api';
import type { DocumentsResponse } from '../types';

import './documents-page.css';

// ---------- types ----------

type DocStatus = 'action' | 'review' | 'approved' | 'reference';
type FilterKey = 'all' | DocStatus;

interface DocItem {
  id: string;
  name: string;
  status: DocStatus;
  category: DocCategory;
  priority?: 'required' | 'conditional';
  description?: string;
  reason?: string;
  triggeredBy?: string;
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
  rejectionReason?: string;
  fixInstructions?: string;
  eSignDocs?: string[];
  eSignProgress?: { signed: number; total: number };
}

export interface DocumentsPageProps {
  loanId?: number | null;
  detectedDocs: DetectedDocument[];
  onAskAria?: () => void;
  onBack: () => void;
}

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
  loanId,
  detectedDocs,
  onAskAria,
  onBack,
}) => {
  const [filter, setFilter] = useState<FilterKey>('all');
  const [backendDocs, setBackendDocs] = useState<DocItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch any existing uploaded/reviewed docs from the backend
  useEffect(() => {
    if (loanId == null) return;
    let cancelled = false;
    setDocsLoading(true);

    posApi
      .getDocuments(loanId)
      .then((resp: DocumentsResponse) => {
        if (cancelled) return;
        if (resp.documents && resp.documents.length > 0) {
          const mapped: DocItem[] = resp.documents.map(d => ({
            id: d.id,
            name: d.name,
            status: d.status as DocStatus,
            category: (d.category || 'compliance') as DocCategory,
            description: d.description ?? undefined,
            filename: d.filename ?? undefined,
            filesize: d.filesize ?? undefined,
            uploadedAt: d.uploadedAt ?? undefined,
            dueDate: d.dueDate ?? undefined,
            dueSeverity: d.dueSeverity ?? undefined,
            extraction: d.extraction ?? undefined,
            reviewedBy: d.reviewedBy ?? undefined,
            clearedAt: d.clearedAt ?? undefined,
            meta: d.meta ?? undefined,
            rejectionReason: d.rejectionReason ?? undefined,
            fixInstructions: d.fixInstructions ?? undefined,
          }));
          setBackendDocs(mapped);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setDocsLoading(false);
      });

    return () => { cancelled = true; };
  }, [loanId]);

  // Merge detected docs (from application answers) with backend docs.
  // Backend docs (uploaded/reviewed) take precedence — if a detected doc
  // has a matching backend doc, use the backend version (it has review status).
  // Remaining detected docs become "action" items.
  const docs = useMemo<DocItem[]>(() => {
    const backendNames = new Set(backendDocs.map(d => d.name.toLowerCase()));

    const actionItems: DocItem[] = detectedDocs
      .filter(d => !backendNames.has(d.name.toLowerCase()))
      .map(d => ({
        id: d.id,
        name: d.name,
        status: 'action' as DocStatus,
        category: d.category,
        priority: d.priority,
        description: d.description,
        reason: d.reason,
        triggeredBy: d.triggeredBy,
      }));

    return [...actionItems, ...backendDocs];
  }, [detectedDocs, backendDocs]);

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

  if (docsLoading) {
    return (
      <div className="docs-page" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 320, gap: 12 }}>
        <div className="pos-loading__spinner" />
        <p style={{ color: 'var(--text-secondary, #666)', fontSize: 14 }}>Loading documents...</p>
      </div>
    );
  }

  if (docs.length === 0) {
    return (
      <div className="docs-page">
        <button type="button" className="docs-page__back" onClick={onBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          Back to application
        </button>
        <div className="docs-page__header">
          <h1 className="docs-page__title">Documents</h1>
        </div>
        <div className="docs-empty">
          <div className="docs-empty__icon"><DocFileIcon /></div>
          <h2 className="docs-empty__title">No documents needed yet</h2>
          <p className="docs-empty__desc">
            As you fill out your application, required documents will appear here
            based on your answers. Keep going — we'll tell you exactly what's needed.
          </p>
          <button type="button" className="docs-btn docs-btn--primary" onClick={onBack}>
            Continue application
          </button>
        </div>
      </div>
    );
  }

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
            Everything your lending team and the underwriter need from you, all in one place.
            Drop a document and we'll handle the rest.
          </p>
        </div>
        <input ref={fileInputRef} type="file" className="docs-page__file-input" multiple accept=".pdf,.png,.jpg,.jpeg" />
      </div>

      {/* Stats */}
      <div className="docs-stats">
        <StatCard label="Action Required" value={counts.action || 0} sub={`${counts.action || 0} items need attention`} variant="action" />
        <StatCard label="In Review" value={counts.review || 0} sub="Awaiting your team" variant="review" />
        <StatCard label="Approved" value={counts.approved || 0} sub="Cleared by underwriting" variant="approved" />
        <StatCard label="Reference Library" value={counts.reference || 0} sub="Always available to download" />
      </div>

      {/* Aria banner */}
      <div className="docs-banner">
        <span className="docs-banner__seal">A</span>
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
        {doc.triggeredBy && (
          <p className="docs-card__triggered">
            <SparkIcon /> {doc.triggeredBy}
          </p>
        )}
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
        {doc.priority === 'required' && doc.status === 'action' && (
          <span className="docs-card__due docs-card__due--urgent">Required</span>
        )}
        {doc.priority === 'conditional' && doc.status === 'action' && (
          <span className="docs-card__due">If applicable</span>
        )}
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
