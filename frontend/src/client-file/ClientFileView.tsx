import { ActivityPane } from "./ActivityPane";
import { Avatar, deriveInitials } from "./primitives/Avatar";
import { IdentityPanel } from "./IdentityPanel";
import { Pill } from "./primitives/Pill";
import { ToolsRail } from "./ToolsRail";
import { useClientFile } from "./hooks";
import { LIFECYCLE_STAGE_LABEL } from "./format";
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
  const fullName = `${client.first_name} ${client.last_name}`;
  return (
    <header className="pf-cf-header">
      <div className="pf-cf-header__identity">
        <Avatar initials={deriveInitials(fullName)} size="lg" />
        <div>
          <div className="pf-cf-header__name">{fullName}</div>
          <div className="pf-cf-header__sub">{formatPropertyLine(client)}</div>
        </div>
      </div>
      <Pill variant="accent">
        {LIFECYCLE_STAGE_LABEL[client.lifecycle_stage]}
      </Pill>
    </header>
  );
}

export function ClientFileView({ clientFileId, currentUserId }: Props) {
  const { data: client, isLoading, error } = useClientFile(clientFileId);

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
        <aside className="pf-cf__pane" aria-label="Identity">
          <IdentityPanel client={client} />
        </aside>
        <main className="pf-cf__pane" aria-label="Activity">
          <ActivityPane
            clientFileId={clientFileId}
            currentUserId={currentUserId}
          />
        </main>
        <aside className="pf-cf__pane" aria-label="Tools">
          <ToolsRail clientFileId={clientFileId} />
        </aside>
      </div>
    </div>
  );
}
