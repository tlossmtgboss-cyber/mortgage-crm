import { useState } from "react";

import { useDocumentsTab, useDocumentActions, useClientFile } from "./hooks";
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
                className="pf-cf-btn pf-cf-btn--success pf-cf-btn--sm"
                onClick={() => actions.approve.mutate(doc.id)}
                disabled={actions.approve.isPending}
              >
                {actions.approve.isPending ? "Approving..." : "Approve"}
              </button>
              <button
                type="button"
                className="pf-cf-btn pf-cf-btn--outline pf-cf-btn--sm"
                onClick={() => setShowReject((v) => !v)}
              >
                Reject
              </button>
              <button
                type="button"
                className="pf-cf-btn pf-cf-btn--accent pf-cf-btn--sm"
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

const DOC_CHIPS: { value: string; label: string; esign?: boolean }[] = [
  { value: "LOE", label: "Letter of Explanation", esign: true },
  { value: "GIFT_LETTER", label: "Gift Letter", esign: true },
  { value: "PAYSTUB", label: "Pay Stubs" },
  { value: "BANK_STATEMENT", label: "Bank Statements" },
  { value: "TAX_RETURN", label: "Tax Returns" },
  { value: "W2", label: "W-2 Forms" },
  { value: "DRIVERS_LICENSE", label: "Driver's License" },
  { value: "PURCHASE_CONTRACT", label: "Purchase Contract" },
  { value: "PROFIT_LOSS", label: "Profit & Loss Statement" },
  { value: "HOMEOWNERS_INSURANCE", label: "Homeowners Insurance" },
  { value: "OTHER", label: "Other Document" },
];

const LOE_TEMPLATES: { value: string; label: string; prompt: string }[] = [
  { value: "credit_inquiry", label: "Credit Inquiry Explanation", prompt: "Please explain the recent credit inquiry from {company} on {date}." },
  { value: "late_payment", label: "Late Payment Explanation", prompt: "Please explain the late payment on your {account_type} account in {date}." },
  { value: "employment_gap", label: "Employment Gap Explanation", prompt: "Please explain the gap in employment between {start_date} and {end_date}." },
  { value: "large_deposit", label: "Large Deposit Explanation", prompt: "Please explain the large deposit of {amount} on {date} in your {account} account." },
  { value: "address_discrepancy", label: "Address Discrepancy Explanation", prompt: "Please explain the discrepancy between your current address and the address on your {document}." },
  { value: "name_variation", label: "Name Variation Explanation", prompt: "Please explain the name variation between {name1} and {name2} on your documents." },
  { value: "custom", label: "Custom Letter of Explanation", prompt: "" },
];

const PRIORITY_OPTS = ["LOW", "NORMAL", "HIGH", "URGENT"];

interface QueuedDoc {
  id: number;
  docType: string;
  title: string;
  instructions: string;
  requireEsign: boolean;
  loeTemplate: string;
}

let _nextQId = 0;
function emptyDoc(): QueuedDoc {
  return { id: ++_nextQId, docType: "", title: "", instructions: "", requireEsign: false, loeTemplate: "custom" };
}

function EsignSetup({ onFileSelect }: { onFileSelect: (file: File) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(f: File) {
    if (f.type !== "application/pdf") return;
    if (f.size > 25 * 1024 * 1024) return;
    setFile(f);
    onFileSelect(f);
  }

  return (
    <div className="pf-cf-esign-setup">
      <div className="pf-cf-esign-setup__header">
        <span className="pf-cf-esign-setup__icon">&#9997;</span>
        <span className="pf-cf-esign-setup__title">E-Signature Setup</span>
      </div>
      <div className="pf-cf-esign-setup__label">Upload Document for Signing</div>
      <div
        className={`pf-cf-esign-setup__dropzone${dragging ? " pf-cf-esign-setup__dropzone--active" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files[0];
          if (f) handleFile(f);
        }}
        onClick={() => {
          const input = document.createElement("input");
          input.type = "file";
          input.accept = ".pdf";
          input.onchange = () => {
            const f = input.files?.[0];
            if (f) handleFile(f);
          };
          input.click();
        }}
      >
        {file ? (
          <div className="pf-cf-esign-setup__file">
            <span className="pf-cf-esign-setup__file-icon">&#128196;</span>
            <span>{file.name}</span>
            <span className="pf-cf-esign-setup__file-size">
              ({(file.size / 1024).toFixed(0)} KB)
            </span>
          </div>
        ) : (
          <>
            <div className="pf-cf-esign-setup__upload-icon">&#8593;</div>
            <div>
              Drag &amp; drop a PDF here, or{" "}
              <span className="pf-cf-esign-setup__browse">click to browse</span>
            </div>
            <div className="pf-cf-esign-setup__hint">PDF only, max 25 MB</div>
          </>
        )}
      </div>
    </div>
  );
}

function NewRequestForm({
  clientFileId,
  onClose,
}: {
  clientFileId: string;
  onClose: () => void;
}) {
  const actions = useDocumentActions(clientFileId);
  const { data: clientFile } = useClientFile(clientFileId);
  const borrowerEmail = clientFile?.primary_email ?? null;

  const [queue, setQueue] = useState<QueuedDoc[]>(() => [emptyDoc()]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [priority, setPriority] = useState("NORMAL");
  const [dueDate, setDueDate] = useState("");
  const [sendNotification, setSendNotification] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const active = queue[activeIdx] ?? queue[0];

  function updateActive(patch: Partial<QueuedDoc>) {
    setQueue((q) => q.map((d, i) => (i === activeIdx ? { ...d, ...patch } : d)));
  }

  function selectDocType(value: string) {
    const chip = DOC_CHIPS.find((c) => c.value === value);
    updateActive({
      docType: value,
      title: active.title || chip?.label || docTypeLabel(value),
    });
  }

  function handleLoeTemplateChange(templateValue: string) {
    const template = LOE_TEMPLATES.find((t) => t.value === templateValue);
    updateActive({
      loeTemplate: templateValue,
      instructions: template?.prompt || active.instructions,
    });
  }

  function addDocument() {
    const doc = emptyDoc();
    setQueue((q) => [...q, doc]);
    setActiveIdx(queue.length);
  }

  function removeDocument(idx: number) {
    if (queue.length <= 1) return;
    setQueue((q) => q.filter((_, i) => i !== idx));
    setActiveIdx((prev) => (prev >= idx && prev > 0 ? prev - 1 : prev));
  }

  const validCount = queue.filter((d) => d.title.trim() && d.docType).length;

  const [submitError, setSubmitError] = useState("");

  async function handleSubmit() {
    const toSend = queue.filter((d) => d.title.trim() && d.docType);
    if (toSend.length === 0) return;
    setSubmitting(true);
    setSubmitError("");
    let succeeded = 0;
    for (const doc of toSend) {
      try {
        await actions.createRequest.mutateAsync({
          doc_type: doc.docType,
          title: doc.title.trim(),
          instructions: doc.instructions || undefined,
          priority,
          due_date: dueDate ? new Date(dueDate).toISOString() : undefined,
          require_esign: doc.requireEsign || undefined,
          send_notification: sendNotification,
        });
        succeeded++;
      } catch (err: any) {
        const detail = (err?.body as any)?.detail;
        setSubmitError(detail || err?.message || "Request failed");
      }
    }
    setSubmitting(false);
    if (succeeded > 0) onClose();
  }

  return (
    <div className="pf-cf-docreq-modal">
      <div className="pf-cf-docreq-modal__top">
        {/* Left: document queue */}
        <div className="pf-cf-docreq-modal__queue">
          <div className="pf-cf-docreq-modal__queue-title">Documents to Request</div>
          {queue.map((doc, idx) => (
            <div
              key={doc.id}
              className={`pf-cf-docreq-modal__queue-item${idx === activeIdx ? " pf-cf-docreq-modal__queue-item--active" : ""}`}
            >
              <button
                type="button"
                className="pf-cf-docreq-modal__queue-btn"
                onClick={() => setActiveIdx(idx)}
              >
                <span className="pf-cf-docreq-modal__queue-num">{idx + 1}</span>
                <span className="pf-cf-docreq-modal__queue-label">
                  {doc.title || "New Document"}
                </span>
              </button>
              {queue.length > 1 && (
                <button
                  type="button"
                  className="pf-cf-docreq-modal__queue-remove"
                  onClick={() => removeDocument(idx)}
                  aria-label="Remove"
                >
                  &times;
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            className="pf-cf-docreq-modal__add-btn"
            onClick={addDocument}
          >
            + Add Document
          </button>
        </div>

        {/* Right: active document form */}
        <div className="pf-cf-docreq-modal__form">
          <div className="pf-cf-newreq__row">
            <label className="pf-cf-newreq__label">Document Type</label>
            <div className="pf-cf-docreq-modal__chips">
              {DOC_CHIPS.map((chip) => (
                <button
                  key={chip.value}
                  type="button"
                  className={`pf-cf-docreq-modal__chip${active.docType === chip.value ? " pf-cf-docreq-modal__chip--active" : ""}`}
                  onClick={() => selectDocType(chip.value)}
                >
                  {chip.label}
                  {chip.esign && (
                    <span className="pf-cf-docreq-modal__esign-badge">E-SIGN</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {active.docType === "LOE" && (
            <div className="pf-cf-newreq__row">
              <label className="pf-cf-newreq__label">LOE Template</label>
              <select
                className="pf-cf-newreq__select"
                value={active.loeTemplate}
                onChange={(e) => handleLoeTemplateChange(e.target.value)}
              >
                {LOE_TEMPLATES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
          )}

          <div className="pf-cf-newreq__row">
            <label className="pf-cf-newreq__label">Title *</label>
            <input
              className="pf-cf-newreq__input"
              value={active.title}
              onChange={(e) => updateActive({ title: e.target.value })}
              placeholder="Document title"
            />
          </div>

          <div className="pf-cf-newreq__row">
            <label className="pf-cf-newreq__label">Instructions for Borrower</label>
            <textarea
              className="pf-cf-newreq__textarea"
              value={active.instructions}
              onChange={(e) => updateActive({ instructions: e.target.value })}
              placeholder="What should the borrower include in this document?"
              rows={3}
            />
          </div>

          <div className="pf-cf-newreq__row">
            <label className="pf-cf-newreq__checkbox-label">
              <input
                type="checkbox"
                checked={active.requireEsign}
                onChange={(e) => updateActive({ requireEsign: e.target.checked })}
              />
              <span>Require E-Signature</span>
            </label>
          </div>

          {active.requireEsign && (
            <EsignSetup
              onFileSelect={(file) => updateActive({ esignFile: file } as any)}
            />
          )}
        </div>
      </div>

      {/* Footer: shared settings + actions */}
      <div className="pf-cf-docreq-modal__footer">
        <div className="pf-cf-docreq-modal__settings">
          <div className="pf-cf-docreq-modal__setting">
            <label className="pf-cf-newreq__label">Priority</label>
            <select
              className="pf-cf-newreq__select"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              {PRIORITY_OPTS.map((p) => (
                <option key={p} value={p}>{p.charAt(0) + p.slice(1).toLowerCase()}</option>
              ))}
            </select>
          </div>
          <div className="pf-cf-docreq-modal__setting">
            <label className="pf-cf-newreq__label">Due Date</label>
            <input
              type="date"
              className="pf-cf-newreq__input"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              min={new Date().toISOString().split("T")[0]}
            />
          </div>
        </div>
        <div className="pf-cf-docreq-modal__notification">
          <label className="pf-cf-newreq__checkbox-label">
            <input
              type="checkbox"
              checked={sendNotification}
              onChange={(e) => setSendNotification(e.target.checked)}
            />
            <span>Send Email Notification</span>
            <span className="pf-cf-newreq__checkbox-hint">
              {borrowerEmail
                ? `Notify ${borrowerEmail}`
                : "No email on file — notification will not be sent"}
            </span>
          </label>
        </div>
        <div className="pf-cf-docreq-modal__actions">
          <button
            type="button"
            className="pf-cf-btn pf-cf-btn--ghost"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="pf-cf-btn pf-cf-btn--accent"
            disabled={validCount === 0 || submitting}
            onClick={handleSubmit}
          >
            {submitting
              ? "Sending..."
              : `Send ${validCount} Request${validCount !== 1 ? "s" : ""}`}
          </button>
        </div>
        {submitError && (
          <div className="pf-cf-docreq-modal__error">{submitError}</div>
        )}
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
