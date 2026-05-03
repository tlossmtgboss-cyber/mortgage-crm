import React from 'react';

import type { DetectedDocument, DocCategory } from '../hooks/useDocumentDetector';
import { CATEGORY_LABELS, CATEGORY_ORDER } from '../hooks/useDocumentDetector';

export interface DocumentsDrawerProps {
  open: boolean;
  onClose: () => void;
  documents: DetectedDocument[];
}

export const DocumentsDrawer: React.FC<DocumentsDrawerProps> = ({ open, onClose, documents }) => {
  const grouped = CATEGORY_ORDER
    .map(cat => ({
      category: cat,
      label: CATEGORY_LABELS[cat],
      docs: documents.filter(d => d.category === cat),
    }))
    .filter(g => g.docs.length > 0);

  const requiredCount = documents.filter(d => d.priority === 'required').length;

  return (
    <div className={`pos-drawer${open ? ' is-open' : ''}`}>
      <div className="pos-drawer__backdrop" onClick={onClose} />
      <div className="pos-drawer__panel">
        <div className="pos-drawer__header">
          <div>
            <h2 className="pos-drawer__title">Documents Needed</h2>
            <p className="pos-drawer__subtitle">
              {requiredCount} required · {documents.length} total
            </p>
          </div>
          <button type="button" className="pos-drawer__close" onClick={onClose} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <p className="pos-drawer__explainer">
          Based on your answers so far, these are the documents you'll need to provide.
          This list updates automatically as you complete each section.
        </p>

        <div className="pos-drawer__body">
          {documents.length === 0 ? (
            <div className="pos-drawer__empty">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <p>Start filling out your application — documents will appear here as needed.</p>
            </div>
          ) : (
            grouped.map(group => (
              <div key={group.category} className="pos-doc-group">
                <div className="pos-doc-group__header">
                  <CategoryIcon category={group.category} />
                  <span className="pos-doc-group__label">{group.label}</span>
                  <span className="pos-doc-group__count">{group.docs.length}</span>
                </div>
                <ul className="pos-doc-group__list">
                  {group.docs.map(doc => (
                    <li key={doc.id} className="pos-doc-item">
                      <div className="pos-doc-item__left">
                        <span className={`pos-doc-item__priority pos-doc-item__priority--${doc.priority}`}>
                          {doc.priority === 'required' ? 'Required' : 'If applicable'}
                        </span>
                        <span className="pos-doc-item__name">{doc.name}</span>
                        <span className="pos-doc-item__desc">{doc.description}</span>
                      </div>
                      <div className="pos-doc-item__trigger">
                        {doc.triggeredBy}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

const CategoryIcon: React.FC<{ category: DocCategory }> = ({ category }) => {
  const icons: Record<DocCategory, React.ReactNode> = {
    income: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
    assets: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="4" width="20" height="16" rx="2" /><line x1="2" y1="10" x2="22" y2="10" />
      </svg>
    ),
    identity: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
      </svg>
    ),
    property: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
    credit: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22c5.5 0 10-4.5 10-10S17.5 2 12 2 2 6.5 2 12s4.5 10 10 10z" /><path d="M12 8v4l3 3" />
      </svg>
    ),
    compliance: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  };
  return <span className="pos-doc-group__icon">{icons[category]}</span>;
};
