import { useState } from "react";

import { ActivityComposer } from "./ActivityComposer";
import { TeamChatPane } from "./TeamChatPane";
import { UnifiedTimeline } from "./UnifiedTimeline";
import { useTeamChatBadge } from "./hooks";

interface Props {
  clientFileId: string;
  currentUserId: string;
}

type Tab = "activity" | "team_chat";

export function ActivityPane({ clientFileId, currentUserId }: Props) {
  const [tab, setTab] = useState<Tab>("activity");
  const badge = useTeamChatBadge(clientFileId);

  return (
    <div className="pf-cf-activity">
      {/* Tab strip */}
      <div
        role="tablist"
        aria-label="Activity views"
        style={{
          display: "flex",
          padding: "0 20px",
          borderBottom: "1px solid var(--pf-cf-border)",
          background: "var(--pf-cf-bg-glass)",
          flexShrink: 0,
        }}
      >
        <button
          role="tab"
          aria-selected={tab === "activity"}
          onClick={() => setTab("activity")}
          style={{
            padding: "12px 14px",
            background: "transparent",
            border: "none",
            fontSize: 12,
            color:
              tab === "activity"
                ? "var(--pf-cf-text)"
                : "var(--pf-cf-text-secondary)",
            fontWeight: tab === "activity" ? 500 : 400,
            cursor: "pointer",
            borderBottom:
              tab === "activity"
                ? "2px solid var(--pf-cf-accent)"
                : "2px solid transparent",
            fontFamily: "inherit",
          }}
        >
          Activity
        </button>
        <button
          role="tab"
          aria-selected={tab === "team_chat"}
          onClick={() => setTab("team_chat")}
          style={{
            padding: "12px 14px",
            background: "transparent",
            border: "none",
            fontSize: 12,
            color:
              tab === "team_chat"
                ? "var(--pf-cf-text)"
                : "var(--pf-cf-text-secondary)",
            fontWeight: tab === "team_chat" ? 500 : 400,
            cursor: "pointer",
            borderBottom:
              tab === "team_chat"
                ? "2px solid var(--pf-cf-accent)"
                : "2px solid transparent",
            fontFamily: "inherit",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          Team chat
          {badge.show && (
            <span
              aria-label={`${badge.unread} unread${badge.mentions > 0 ? `, ${badge.mentions} mentions` : ""}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                minWidth: 16,
                height: 16,
                padding: "0 5px",
                borderRadius: 8,
                background:
                  badge.mentions > 0
                    ? "var(--pf-cf-danger)"
                    : "var(--pf-cf-accent)",
                color: "var(--pf-cf-text-on-accent)",
                fontSize: 10,
                fontWeight: 500,
              }}
            >
              {badge.mentions > 0 ? badge.mentions : badge.unread}
            </span>
          )}
        </button>
      </div>

      {/* Content */}
      {tab === "activity" ? (
        <>
          <ActivityComposer clientFileId={clientFileId} />
          <UnifiedTimeline clientFileId={clientFileId} />
        </>
      ) : (
        <TeamChatPane
          clientFileId={clientFileId}
          currentUserId={currentUserId}
          active={tab === "team_chat"}
        />
      )}
    </div>
  );
}
