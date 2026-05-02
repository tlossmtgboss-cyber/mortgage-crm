import { useState } from "react";

import { Pill } from "./primitives/Pill";
import { useSetLifecycleStage, useSetStickyNote } from "./hooks";
import { LIFECYCLE_STAGE_LABEL, LIFECYCLE_STAGE_ORDER } from "./format";
import type { ClientFile, LifecycleStage } from "./types";

interface Props {
  client: ClientFile;
}

function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  if (digits.length === 11 && digits[0] === "1") {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return phone;
}

function formatLoanAmount(amount?: number | null): string | null {
  if (!amount) return null;
  return `$${(amount / 1000).toFixed(0)}k`;
}

export function IdentityPanel({ client }: Props) {
  const [editingNote, setEditingNote] = useState(false);
  const [noteDraft, setNoteDraft] = useState(client.sticky_note ?? "");
  const setStickyNote = useSetStickyNote(client.id);
  const setStage = useSetLifecycleStage(client.id);

  const fullAddress = client.property_address
    ? [
        client.property_address.street,
        client.property_address.city,
        client.property_address.state,
      ].filter(Boolean).join(", ")
    : null;

  const handleSaveNote = () => {
    setStickyNote.mutate(noteDraft || null);
    setEditingNote(false);
  };

  return (
    <div className="pf-cf-identity">
      <div className="pf-cf-identity__contact">
        {client.primary_phone && (
          <div className="pf-cf-identity__contact-row">
            <a href={`tel:${client.primary_phone}`}>{formatPhone(client.primary_phone)}</a>
          </div>
        )}
        {client.primary_email && (
          <div className="pf-cf-identity__contact-row">
            <a href={`mailto:${client.primary_email}`}>{client.primary_email}</a>
          </div>
        )}
        {fullAddress && (
          <div
            className="pf-cf-identity__contact-row"
            style={{ color: "var(--pf-cf-text-tertiary)" }}
          >
            {fullAddress}
          </div>
        )}
      </div>

      <div className="pf-cf-identity__sticky">
        <div className="pf-cf-identity__sticky-label">sticky note</div>
        {editingNote ? (
          <>
            <textarea
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              autoFocus
              rows={4}
              style={{
                width: "100%",
                background: "transparent",
                border: "1px solid var(--pf-cf-border)",
                borderRadius: "var(--pf-cf-radius-sm)",
                color: "var(--pf-cf-text)",
                padding: "8px",
                fontSize: "13px",
                fontFamily: "inherit",
                resize: "vertical",
              }}
            />
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <button
                type="button"
                onClick={handleSaveNote}
                style={{
                  background: "var(--pf-cf-accent)",
                  color: "var(--pf-cf-text-on-accent)",
                  border: "none",
                  borderRadius: "var(--pf-cf-radius-sm)",
                  padding: "4px 10px",
                  fontSize: "11px",
                  cursor: "pointer",
                }}
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditingNote(false);
                  setNoteDraft(client.sticky_note ?? "");
                }}
                style={{
                  background: "transparent",
                  color: "var(--pf-cf-text-secondary)",
                  border: "1px solid var(--pf-cf-border)",
                  borderRadius: "var(--pf-cf-radius-sm)",
                  padding: "4px 10px",
                  fontSize: "11px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <div
            onClick={() => setEditingNote(true)}
            style={{ cursor: "pointer", minHeight: 20 }}
          >
            {client.sticky_note || (
              <span style={{ color: "var(--pf-cf-text-tertiary)", fontStyle: "italic" }}>
                Add a note about this client…
              </span>
            )}
          </div>
        )}
      </div>

      <div>
        <div className="pf-cf-identity__section-label">details</div>
        <dl className="pf-cf-identity__details">
          {client.source && (
            <>
              <dt>Source</dt>
              <dd>{client.source}</dd>
            </>
          )}
          <dt>Stage</dt>
          <dd>
            <select
              value={client.lifecycle_stage}
              onChange={(e) => setStage.mutate(e.target.value as LifecycleStage)}
              style={{
                background: "transparent",
                color: "var(--pf-cf-text)",
                border: "1px solid var(--pf-cf-border)",
                borderRadius: "var(--pf-cf-radius-sm)",
                fontSize: "11px",
                padding: "1px 4px",
                fontFamily: "inherit",
              }}
            >
              {LIFECYCLE_STAGE_ORDER.map((s) => (
                <option key={s} value={s}>
                  {LIFECYCLE_STAGE_LABEL[s]}
                </option>
              ))}
            </select>
          </dd>
          {client.assigned_loan_officer_name && (
            <>
              <dt>LO</dt>
              <dd>{client.assigned_loan_officer_name}</dd>
            </>
          )}
          {client.active_loan_program && (
            <>
              <dt>Program</dt>
              <dd style={{ textTransform: "uppercase", fontFamily: "var(--pf-cf-font-mono)" }}>
                {client.active_loan_program}
              </dd>
            </>
          )}
          {client.active_loan_amount && (
            <>
              <dt>Amount</dt>
              <dd style={{ fontFamily: "var(--pf-cf-font-mono)" }}>
                {formatLoanAmount(client.active_loan_amount)}
              </dd>
            </>
          )}
          {client.active_loan_fico && (
            <>
              <dt>FICO</dt>
              <dd style={{ fontFamily: "var(--pf-cf-font-mono)" }}>{client.active_loan_fico}</dd>
            </>
          )}
          {client.active_loan_lock_expires_at && (
            <>
              <dt>Lock</dt>
              <dd style={{ fontFamily: "var(--pf-cf-font-mono)" }}>
                {new Date(client.active_loan_lock_expires_at).toLocaleDateString()}
              </dd>
            </>
          )}
          {client.active_loan_projected_close_date && (
            <>
              <dt>Close</dt>
              <dd style={{ fontFamily: "var(--pf-cf-font-mono)" }}>
                {new Date(client.active_loan_projected_close_date).toLocaleDateString()}
              </dd>
            </>
          )}
        </dl>
      </div>

      {client.tags.length > 0 && (
        <div>
          <div className="pf-cf-identity__section-label">tags</div>
          <div className="pf-cf-identity__tags">
            {client.tags.map((t) => (
              <Pill key={t}>{t}</Pill>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
