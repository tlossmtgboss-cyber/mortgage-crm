import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ActivityPane } from "./ActivityPane";
import { Avatar, deriveInitials } from "./primitives/Avatar";
import { IdentityPanel } from "./IdentityPanel";
import { Pill } from "./primitives/Pill";
import { QuickActionsRail } from "./QuickActionsRail";
import { ToolsRail } from "./ToolsRail";
import { useClientFile } from "./hooks";
import { LIFECYCLE_STAGE_LABEL } from "./format";
import { toast } from "../utils/toast";
import type { ClientFile } from "./types";
import "./styles.css";

interface Props {
  clientFileId: string;
  /** Used to identify "your" mentions, "your" reactions etc. in team chat. */
  currentUserId: string;
}

function formatPropertyLine(client: ClientFile): string {
  const parts: string[] = [];
  if (client.property_address?.city) {
    parts.push(
      [client.property_address.city, client.property_address.state]
        .filter(Boolean)
        .join(" "),
    );
  }
  if (client.active_loan_purpose) {
    parts.push(client.active_loan_purpose.replace(/_/g, " "));
  }
  if (client.active_loan_projected_close_date) {
    parts.push(
      "est close " +
        new Date(client.active_loan_projected_close_date).toLocaleDateString(
          undefined,
          { month: "short", day: "numeric" },
        ),
    );
  }
  return parts.join(" · ");
}

function ClientFileHeader({ client }: { client: ClientFile }) {
  const navigate = useNavigate();
  const fullName = [client.first_name, client.last_name].filter(Boolean).join(" ") || "Unknown";
  return (
    <header className="pf-cf-header">
      <div className="pf-cf-header__identity">
        <Avatar initials={deriveInitials(fullName)} size="lg" />
        <div>
          <div className="pf-cf-header__name">{fullName}</div>
          <div className="pf-cf-header__sub">{formatPropertyLine(client)}</div>
        </div>
      </div>
      <div className="pf-cf-header__actions">
        {client.lead_id && (
          <button
            type="button"
            className="pf-cf-header__lead-btn"
            onClick={() => navigate(`/leads/${client.lead_id}`)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            Lead Details
          </button>
        )}
        <Pill variant="accent">
          {LIFECYCLE_STAGE_LABEL[client.lifecycle_stage]}
        </Pill>
      </div>
    </header>
  );
}

export function ClientFileView({ clientFileId, currentUserId }: Props) {
  const { data: client, isLoading, error } = useClientFile(clientFileId);
  const navigate = useNavigate();

  const handleQuickAction = useCallback((key: string) => {
    if (!client) return;
    const leadId = client.lead_id;
    if (!leadId) {
      toast.error("No linked lead — open Lead Details first");
      return;
    }
    navigate(`/leads/${leadId}`, { state: { openAction: key } });
  }, [client, navigate]);

  if (isLoading) {
    return (
      <div className="pf-cf">
        <div className="pf-cf-loading">Loading client file…</div>
      </div>
    );
  }

  if (error || !client) {
    return (
      <div className="pf-cf">
        <div className="pf-cf-loading" style={{ color: "var(--pf-cf-danger)" }}>
          Could not load client file.
        </div>
      </div>
    );
  }

  return (
    <div className="pf-cf">
      <ClientFileHeader client={client} />
      <div className="pf-cf__grid">
        <aside className="pf-cf__pane" aria-label="Identity & Details">
          <IdentityPanel client={client} />
          <ToolsRail clientFileId={clientFileId} />
        </aside>
        <main className="pf-cf__pane" aria-label="Activity">
          <ActivityPane
            clientFileId={clientFileId}
            currentUserId={currentUserId}
          />
        </main>
        <aside className="pf-cf__pane" aria-label="Quick Actions">
          <QuickActionsRail clientFileId={clientFileId} client={client} onAction={handleQuickAction} />
        </aside>
      </div>
    </div>
  );
}
