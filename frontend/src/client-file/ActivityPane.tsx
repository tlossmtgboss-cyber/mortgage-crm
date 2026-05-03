import { useState } from "react";

import { ActivityComposer } from "./ActivityComposer";
import { DocumentsPane } from "./DocumentsPane";
import { TasksPane } from "./TasksPane";
import { TeamChatPane } from "./TeamChatPane";
import { UnifiedTimeline } from "./UnifiedTimeline";
import { useTeamChatBadge, useTasks } from "./hooks";

interface Props {
  clientFileId: string;
  currentUserId: string;
}

type Tab = "activity" | "tasks" | "documents" | "team_chat";

function TabButton({
  label,
  active,
  onClick,
  badge,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  badge?: { count: number; urgent: boolean } | null;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`pf-cf-activity__tab${active ? " pf-cf-activity__tab--active" : ""}`}
    >
      {label}
      {badge && badge.count > 0 && (
        <span
          aria-label={`${badge.count} unread`}
          className={`pf-cf-activity__badge${badge.urgent ? " pf-cf-activity__badge--urgent" : ""}`}
        >
          {badge.count}
        </span>
      )}
    </button>
  );
}

export function ActivityPane({ clientFileId, currentUserId }: Props) {
  const [tab, setTab] = useState<Tab>("activity");
  const badge = useTeamChatBadge(clientFileId);
  const { data: allTasks } = useTasks(clientFileId);
  const openTaskCount = (allTasks ?? []).filter((t) => t.status !== "done").length;

  return (
    <div className="pf-cf-activity">
      {/* Tab strip */}
      <div
        role="tablist"
        aria-label="Activity views"
        className="pf-cf-activity__tabs"
      >
        <TabButton label="Activity" active={tab === "activity"} onClick={() => setTab("activity")} />
        <TabButton
          label="Tasks"
          active={tab === "tasks"}
          onClick={() => setTab("tasks")}
          badge={openTaskCount > 0 ? { count: openTaskCount, urgent: false } : null}
        />
        <TabButton label="Documents" active={tab === "documents"} onClick={() => setTab("documents")} />
        <TabButton
          label="Team chat"
          active={tab === "team_chat"}
          onClick={() => setTab("team_chat")}
          badge={badge.show ? { count: badge.mentions > 0 ? badge.mentions : badge.unread, urgent: badge.mentions > 0 } : null}
        />
      </div>

      {/* Content */}
      {tab === "activity" ? (
        <>
          <ActivityComposer clientFileId={clientFileId} />
          <UnifiedTimeline clientFileId={clientFileId} />
        </>
      ) : tab === "tasks" ? (
        <TasksPane clientFileId={clientFileId} />
      ) : tab === "documents" ? (
        <DocumentsPane clientFileId={clientFileId} />
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
