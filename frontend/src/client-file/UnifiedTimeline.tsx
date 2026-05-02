import { useMemo, useState } from "react";

import { Glyph } from "./primitives/Glyph";
import { Pill } from "./primitives/Pill";
import { useStarEvent, useTimeline } from "./hooks";
import { dayKey, formatDayLabel, formatTime } from "./format";
import type { ActivityCategory, TimelineEvent } from "./types";

interface Props {
  clientFileId: string;
}

const FILTERS: { key: ActivityCategory; label: string }[] = [
  { key: "all", label: "All" },
  { key: "notes", label: "Notes" },
  { key: "calls", label: "Calls" },
  { key: "texts", label: "Texts" },
  { key: "emails", label: "Emails" },
  { key: "documents", label: "Docs" },
  { key: "milestones", label: "Milestones" },
  { key: "follow_ups", label: "Follow-ups" },
  { key: "starred", label: "Starred" },
];

function eventActorLabel(event: TimelineEvent): string {
  if (event.actor_user_name) return event.actor_user_name;
  if (event.actor_agent_slug) {
    const slug = event.actor_agent_slug;
    return slug.charAt(0).toUpperCase() + slug.slice(1);
  }
  return "System";
}

function isAgentEvent(event: TimelineEvent): boolean {
  return !!event.actor_agent_slug;
}

function EventRow({
  event,
  clientFileId,
}: {
  event: TimelineEvent;
  clientFileId: string;
}) {
  const star = useStarEvent(clientFileId);
  const agent = isAgentEvent(event);

  return (
    <div className="pf-cf-event">
      <Glyph kind={event.kind} />
      <div className="pf-cf-event__body">
        <div className="pf-cf-event__head">
          <span className="pf-cf-event__actor">{eventActorLabel(event)}</span>
          <span className="pf-cf-event__verb">{event.headline}</span>
          {agent && event.actor_agent_skill && (
            <Pill variant="agent">
              {event.actor_agent_skill}
              {event.actor_agent_skill_version && (
                <span style={{ opacity: 0.7, marginLeft: 3 }}>
                  {event.actor_agent_skill_version}
                </span>
              )}
            </Pill>
          )}
        </div>
        {event.body && (
          <div className="pf-cf-event__preview">{event.body}</div>
        )}
        <div className="pf-cf-event__meta">
          {formatTime(event.occurred_at)}
          {agent && (
            <>
              <span className="pf-cf-event__meta-divider">·</span>
              <span>agent</span>
            </>
          )}
          {event.compliance_review_passed && (
            <>
              <span className="pf-cf-event__meta-divider">·</span>
              <span style={{ color: "var(--pf-cf-success)" }}>compliance reviewed ✓</span>
            </>
          )}
          {event.related_thread_id && (
            <>
              <span className="pf-cf-event__meta-divider">·</span>
              <span>thread</span>
            </>
          )}
        </div>
      </div>
      <button
        type="button"
        className={
          "pf-cf-event__star" +
          (event.is_starred ? " pf-cf-event__star--starred" : "")
        }
        onClick={() =>
          star.mutate({ eventId: event.id, starred: event.is_starred })
        }
        aria-label={event.is_starred ? "Unstar event" : "Star event"}
      >
        {event.is_starred ? "★" : "☆"}
      </button>
    </div>
  );
}

export function UnifiedTimeline({ clientFileId }: Props) {
  const [filter, setFilter] = useState<ActivityCategory>("all");
  const { data, isLoading } = useTimeline(clientFileId, filter);

  const grouped = useMemo(() => {
    if (!data) return [];
    const days = new Map<string, { label: string; events: TimelineEvent[] }>();
    for (const e of data) {
      const k = dayKey(e.occurred_at);
      if (!days.has(k)) {
        days.set(k, { label: formatDayLabel(e.occurred_at), events: [] });
      }
      days.get(k)!.events.push(e);
    }
    return Array.from(days.values());
  }, [data]);

  return (
    <>
      <div className="pf-cf-filters" role="tablist" aria-label="Activity filters">
        {FILTERS.map((f) => (
          <Pill
            key={f.key}
            active={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </Pill>
        ))}
      </div>

      <div className="pf-cf-timeline">
        {isLoading ? (
          <div className="pf-cf-loading">Loading activity…</div>
        ) : grouped.length === 0 ? (
          <div className="pf-cf-empty">No activity for this filter.</div>
        ) : (
          grouped.map((day) => (
            <div key={day.label}>
              <div className="pf-cf-timeline__day-label">{day.label}</div>
              {day.events.map((e) => (
                <EventRow key={e.id} event={e} clientFileId={clientFileId} />
              ))}
            </div>
          ))
        )}
      </div>
    </>
  );
}
