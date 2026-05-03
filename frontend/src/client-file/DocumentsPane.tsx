import { useState } from "react";

import { useDocumentsTab, useDocumentActions } from "./hooks";
import { Pill } from "./primitives/Pill";
import { formatRelativeTime } from "./format";
import type { SmartDocRequest, SmartDocument } from "./types";

type DocTab = "requested" | "received" | "archived";

const DOC_TYPE_LABELS: Record<string, string> = {
  DRIVERS_LICENSE: "Driver's License",
  PAYSTUB: "Paystub",
  W2: "W-2",
  TAX_RETURN: "Tax Return",
  BUSINESS_TAX_RETURN: "Business Tax Return",
  PROFIT_LOSS: "Profit & Loss",
  BALANCE_SHEET: "Balance Sheet",
  BANK_STATEMENT: "Bank Statement",
  INVESTMENT_STATEMENT: "Investment Statement",
  GIFT_LETTER: "Gift Letter",
  LOE: "Letter of Explanation",
  LEASE_AGREEMENT: "Lease Agreement",
  FHA_CERT: "FHA Certificate",
  VA_COE: "VA Certificate of Eligibility",
  DD214: "DD-214",
  BANKRUPTCY_DISCHARGE: "Bankruptcy Discharge",
  PURCHASE_CONTRACT: "Purchase Contract",
  APPRAISAL: "Appraisal",
  TITLE_REPORT: "Title Report",
  HOMEOWNERS_INSURANCE: "Homeowners Insurance",
  OTHER: "Other",
};

function docTypeLabel(dt: string | null | undefined): string {
  if (!dt) return "Document";
  return DOC_TYPE_LABELS[dt] || dt.replace(/_/g, " ");
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusVariant(status: string): "success" | "warning" | "danger" | "default" | "accent" {
  switch (status) {
    case "APPROVED":
    case "ACCEPTED":
      return "success";
    case "NEEDS_REVIEW":
    case "PENDING_REVIEW":
    case "SCANNING":
    case "PROCESSING":
      return "warning";
    case "REJECTED":
    case "EXPIRED":
      return "danger";
    default:
      return "default";
  }
}

function priorityVariant(priority: string): "danger" | "warning" | "default" {
  switch (priority) {
    case "CRITICAL":
      return "danger";
    case "HIGH":
      return "warning";
    default:
      return "default";
  }
}

// ─────────────────────────────────────────────────────────────────────────
// AI Review Badge
// ─────────────────────────────────────────────────────────────────────────

function AiReviewBadge({ doc }: { doc: SmartDocument }) {
  if (!doc.decision && !doc.detected_is_screenshot && !doc.is_expired) return null;

  const items: { label: string; variant: "success" | "warning" | "danger" }[] = [];

  if (doc.decision === "ACCEPT") items.push({ label: "AI Approved", variant: "success" });
  if (doc.decision === "REJECT") items.push({ label: "AI Rejected", variant: "danger" });
  if (doc.decision === "NEEDS_REVIEW") items.push({ label: "Needs Review", variant: "warning" });
  if (doc.detected_is_screenshot) items.push({ label: "Screenshot detected", variant: "danger" });
  if (doc.is_expired) items.push({ label: "Expired", variant: "danger" });

  return (
    <div className="pf-cf-doc-ai">
      {items.map((item, i) => (
        <Pill key={i} variant={item.variant}>{item.label}</Pill>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Document Card (received documents)
// ─────────────────────────────────────────────────────────────────────────

function DocumentCard({
  doc,
  clientFileId,
}: {
  doc: SmartDocument;
  clientFileId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const actions = useDocumentActions(clientFileId);
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);

  const canReview = doc.status === "PENDING_REVIEW" || doc.status === "NEEDS_REVIEW" || doc.status === "UPLOADED";

  return (
    <div className="pf-cf-doccard">
      <button
        type="button"
        className="pf-cf-doccard__head"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="pf-cf-doccard__icon">
          {doc.mime_type?.includes("pdf") ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--pf-cf-danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--pf-cf-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          )}
        </div>
        <div className="pf-cf-doccard__info">
          <div className="pf-cf-doccard__name">
            {doc.display_name || doc.original_filename || doc.file_name}
          </div>
          <div className="pf-cf-doccard__meta">
            {docTypeLabel(doc.doc_type)} · {fileSize(doc.file_size)}
            {doc.page_count ? ` · ${doc.page_count} pg` : ""}
            {doc.uploaded_at && ` · ${formatRelativeTime(doc.uploaded_at)}`}
          </div>
        </div>
        <div className="pf-cf-doccard__status">
          <Pill variant={statusVariant(doc.status)}>
            {doc.status.replace(/_/g, " ").toLowerCase()}
          </Pill>
        </div>
        <span className="pf-cf-doccard__chevron">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <div className="pf-cf-doccard__body">
          <AiReviewBadge doc={doc} />

          {doc.decision_reasons && doc.decision_reasons.length > 0 && (
            <div className="pf-cf-doccard__reasons">
              <div className="pf-cf-doccard__reasons-title">AI Review Notes</div>
              <ul>
                {doc.decision_reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}

          {doc.rejection_reason && (
            <div className="pf-cf-doccard__rejection">
              <strong>Rejected:</strong> {doc.rejection_reason}
              {doc.fix_instructions && (
                <div className="pf-cf-doccard__fix">
                  <strong>How to fix:</strong> {doc.fix_instructions}
                </div>
              )}
            </div>
          )}

          {doc.extracted_employer && (
            <div className="pf-cf-doccard__extracted">
              Employer: {doc.extracted_employer}
              {doc.extracted_amount != null && ` · $${doc.extracted_amount.toLocaleString()}`}
              {doc.extraction_confidence != null && (
                <span className="pf-cf-doccard__confidence">
                  {Math.round(doc.extraction_confidence * 100)}% confidence
                </span>
              )}
            </div>
          )}

          {canReview && (
            <div className="pf-cf-doccard__actions">
              <button
                type="button"
                className="pf-cf-btn pf-cf-btn--accent"
                onClick={() => actions.approve.mutate(doc.id)}
                disabled={actions.approve.isPending}
              >
                Approve
              </button>
              <button
                type="button"
                className="pf-cf-btn pf-cf-btn--outline"
                onClick={() => setShowReject((v) => !v)}
              >
                Reject
              </button>
              <button
                type="button"
                className="pf-cf-btn pf-cf-btn--ghost"
                onClick={() => actions.aiReview.mutate(doc.id)}
                disabled={actions.aiReview.isPending}
              >
                {actions.aiReview.isPending ? "Running..." : "AI Review"}
              </button>
            </div>
          )}

          {showReject && (
            <div className="pf-cf-doccard__reject-form">
              <textarea
                className="pf-cf-doccard__reject-input"
                placeholder="Rejection reason..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={2}
              />
              <button
                type="button"
                className="pf-cf-btn pf-cf-btn--danger"
                disabled={!rejectReason.trim() || actions.reject.isPending}
                onClick={() => {
                  actions.reject.mutate({
                    documentId: doc.id,
                    reason: rejectReason,
                  });
                  setShowReject(false);
                  setRejectReason("");
                }}
              >
                Confirm Rejection
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Request Row (requested documents)
// ─────────────────────────────────────────────────────────────────────────

function RequestRow({ req }: { req: SmartDocRequest }) {
  return (
    <div className="pf-cf-docreq">
      <div className="pf-cf-docreq__info">
        <div className="pf-cf-docreq__title">{req.title}</div>
        <div className="pf-cf-docreq__meta">
          {docTypeLabel(req.doc_type)}
          {req.due_date && ` · due ${new Date(req.due_date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`}
          {req.created_at && ` · requested ${formatRelativeTime(req.created_at)}`}
        </div>
        {req.description && (
          <div className="pf-cf-docreq__desc">{req.description}</div>
        )}
        {req.instructions && (
          <div className="pf-cf-docreq__instructions">{req.instructions}</div>
        )}
      </div>
      <div className="pf-cf-docreq__badges">
        <Pill variant={statusVariant(req.status)}>
          {req.status.replace(/_/g, " ").toLowerCase()}
        </Pill>
        {(req.priority === "CRITICAL" || req.priority === "HIGH") && (
          <Pill variant={priorityVariant(req.priority)}>
            {req.priority.toLowerCase()}
          </Pill>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// New Request Form
// ─────────────────────────────────────────────────────────────────────────

const DOC_TYPES = [
  "PAYSTUB", "W2", "TAX_RETURN", "BANK_STATEMENT", "DRIVERS_LICENSE",
  "PURCHASE_CONTRACT", "HOMEOWNERS_INSURANCE", "APPRAISAL", "TITLE_REPORT",
  "GIFT_LETTER", "LOE", "VA_COE", "DD214", "OTHER",
];

function NewRequestForm({
  clientFileId,
  onClose,
}: {
  clientFileId: string;
  onClose: () => void;
}) {
  const actions = useDocumentActions(clientFileId);
  const [docType, setDocType] = useState("PAYSTUB");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  return (
    <div className="pf-cf-newreq">
      <div className="pf-cf-newreq__row">
        <label className="pf-cf-newreq__label">Document Type</label>
        <select
          className="pf-cf-newreq__select"
          value={docType}
          onChange={(e) => {
            setDocType(e.target.value);
            if (!title) setTitle(docTypeLabel(e.target.value));
          }}
        >
          {DOC_TYPES.map((dt) => (
            <option key={dt} value={dt}>{docTypeLabel(dt)}</option>
          ))}
        </select>
      </div>
      <div className="pf-cf-newreq__row">
        <label className="pf-cf-newreq__label">Title</label>
        <input
          className="pf-cf-newreq__input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={docTypeLabel(docType)}
        />
      </div>
      <div className="pf-cf-newreq__row">
        <label className="pf-cf-newreq__label">Description (optional)</label>
        <textarea
          className="pf-cf-newreq__textarea"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Instructions for the borrower..."
          rows={2}
        />
      </div>
      <div className="pf-cf-newreq__actions">
        <button
          type="button"
          className="pf-cf-btn pf-cf-btn--accent"
          disabled={!title.trim() || actions.createRequest.isPending}
          onClick={() => {
            actions.createRequest.mutate({
              doc_type: docType,
              title: title.trim() || docTypeLabel(docType),
              description: description || undefined,
            });
            onClose();
          }}
        >
          Request Document
        </button>
        <button type="button" className="pf-cf-btn pf-cf-btn--ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Main Documents Pane
// ─────────────────────────────────────────────────────────────────────────

interface Props {
  clientFileId: string;
}

export function DocumentsPane({ clientFileId }: Props) {
  const [subTab, setSubTab] = useState<DocTab>("requested");
  const [showNewRequest, setShowNewRequest] = useState(false);
  const { data, isLoading } = useDocumentsTab(clientFileId, subTab);

  const tabs: { key: DocTab; label: string }[] = [
    { key: "requested", label: "Requested" },
    { key: "received", label: "Received" },
    { key: "archived", label: "Archived" },
  ];

  const requestCount = data?.requests?.length ?? 0;
  const docCount = data?.documents?.length ?? 0;

  return (
    <div className="pf-cf-docs">
      {/* Sub-tab strip */}
      <div className="pf-cf-docs__tabs" role="tablist" aria-label="Document views">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={subTab === t.key}
            className={`pf-cf-docs__tab${subTab === t.key ? " pf-cf-docs__tab--active" : ""}`}
            onClick={() => setSubTab(t.key)}
          >
            {t.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          type="button"
          className="pf-cf-btn pf-cf-btn--accent pf-cf-btn--sm"
          onClick={() => setShowNewRequest((v) => !v)}
        >
          + Request
        </button>
      </div>

      {/* New request form */}
      {showNewRequest && (
        <NewRequestForm
          clientFileId={clientFileId}
          onClose={() => setShowNewRequest(false)}
        />
      )}

      {/* Content */}
      <div className="pf-cf-docs__content">
        {isLoading ? (
          <div className="pf-cf-empty">Loading documents...</div>
        ) : requestCount === 0 && docCount === 0 ? (
          <div className="pf-cf-empty">
            {subTab === "requested" ? (
              <>
                <div>No outstanding document requests.</div>
                <button
                  type="button"
                  className="pf-cf-btn pf-cf-btn--accent pf-cf-btn--sm"
                  style={{ marginTop: 10 }}
                  onClick={() => setShowNewRequest(true)}
                >
                  + Request a Document
                </button>
              </>
            ) : subTab === "received"
              ? "No documents received yet."
              : "No archived documents."}
          </div>
        ) : (
          <>
            {/* Document requests */}
            {data?.requests && data.requests.length > 0 && (
              <div className="pf-cf-docs__section">
                {subTab !== "received" && (
                  <div className="pf-cf-docs__section-title">
                    Requests ({data.requests.length})
                  </div>
                )}
                {data.requests.map((req) => (
                  <RequestRow key={req.id} req={req} />
                ))}
              </div>
            )}

            {/* Uploaded documents */}
            {data?.documents && data.documents.length > 0 && (
              <div className="pf-cf-docs__section">
                <div className="pf-cf-docs__section-title">
                  Documents ({data.documents.length})
                </div>
                {data.documents.map((doc) => (
                  <DocumentCard
                    key={doc.id}
                    doc={doc}
                    clientFileId={clientFileId}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
