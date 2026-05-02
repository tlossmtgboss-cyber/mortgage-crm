import { useState } from "react";

import { Card } from "./primitives/Card";
import { Pill } from "./primitives/Pill";
import {
  useActionPlanRuns,
  useCadenceLifecycle,
  useCadenceSequences,
  useDocumentSets,
  useInsight,
  useRelationships,
  useTaskMutations,
  useTasks,
} from "./hooks";
import { formatRelativeTime } from "./format";
import type {
  CadenceSequenceStatus,
  ClientInsight,
  DocumentRequestStatus,
  DocumentSet,
  EngagementTrajectory,
  FollowupSequence,
  NextBestAction,
  Relationship,
  Task,
} from "./types";

// ─────────────────────────────────────────────────────────────────────────
// Insights — engagement score + NBA
// ─────────────────────────────────────────────────────────────────────────

const NBA_LABEL: Record<NextBestAction, string> = {
  call_now: "Call now",
  send_followup_sms: "Send a follow-up text",
  send_followup_email: "Send a follow-up email",
  request_document: "Request a document",
  schedule_call: "Schedule a call",
  send_rate_update: "Share a rate update",
  request_referral: "Request a referral",
  check_in_post_close: "Check in post-close",
  escalate_to_manager: "Escalate to manager",
  no_action_needed: "No action needed",
  lo_handoff: "Hand off to LO",
};

const TRAJECTORY_GLYPH: Record<EngagementTrajectory, string> = {
  rising: "↑",
  flat: "→",
  falling: "↓",
};

export function InsightsPanel({ clientFileId }: { clientFileId: string }) {
  const { data: insight, isLoading } = useInsight(clientFileId);

  return (
    <Card title="insights" variant="strong">
      {isLoading ? (
        <div className="pf-cf-empty">Loading insight…</div>
      ) : !insight ? (
        <div className="pf-cf-empty">No insight computed yet.</div>
      ) : (
        <>
          <div className="pf-cf-insights__score">
            <span className="pf-cf-insights__score-value">
              {Math.round(insight.engagement_score)}
            </span>
            <span className="pf-cf-insights__score-label">engagement</span>
            <span style={{ flex: 1 }} />
            <span
              className={`pf-cf-insights__trajectory pf-cf-insights__trajectory--${insight.engagement_trajectory}`}
            >
              {TRAJECTORY_GLYPH[insight.engagement_trajectory]} {insight.engagement_trajectory}
            </span>
          </div>

          <div className="pf-cf-insights__nba">
            <div className="pf-cf-insights__nba-label">next best action</div>
            <div className="pf-cf-insights__nba-action">
              {NBA_LABEL[insight.next_best_action]}
            </div>
            <div className="pf-cf-insights__nba-reason">
              {insight.next_best_action_reason}
            </div>
          </div>

          {Object.keys(insight.risk_signals).filter((k) => insight.risk_signals[k]).length > 0 && (
            <div className="pf-cf-insights__signals">
              {Object.entries(insight.risk_signals)
                .filter(([, v]) => v)
                .map(([k]) => (
                  <Pill key={k} variant="warning">
                    {k.replace(/_/g, " ")}
                  </Pill>
                ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Follow-ups — cadence sequences
// ─────────────────────────────────────────────────────────────────────────

const STATUS_VARIANT: Record<CadenceSequenceStatus, "success" | "warning" | "default" | "danger"> = {
  active: "success",
  paused: "warning",
  won: "success",
  lost: "default",
  expired: "default",
  cancelled: "default",
};

function FollowupRow({
  seq,
  clientFileId,
}: {
  seq: FollowupSequence;
  clientFileId: string;
}) {
  const lifecycle = useCadenceLifecycle(clientFileId);
  const isTerminal =
    seq.status === "won" ||
    seq.status === "lost" ||
    seq.status === "expired" ||
    seq.status === "cancelled";

  return (
    <div className="pf-cf-followup">
      <div className="pf-cf-followup__head">
        <span className="pf-cf-followup__goal">
          {seq.goal.replace(/_/g, " ")}
        </span>
        <Pill variant={STATUS_VARIANT[seq.status]}>{seq.status}</Pill>
      </div>
      <div className="pf-cf-followup__meta">
        {seq.attempts_made}/{seq.max_attempts} · {seq.selected_arm} arm
        {seq.last_skill_used && ` · ${seq.last_skill_used}`}
        {seq.next_check_at && seq.status === "active" && (
          <> · next {formatRelativeTime(seq.next_check_at)}</>
        )}
      </div>
      {!isTerminal && (
        <div className="pf-cf-followup__actions">
          {seq.status === "active" && (
            <button
              type="button"
              className="pf-cf-followup__action"
              onClick={() => lifecycle.pause.mutate(seq.id)}
            >
              Pause
            </button>
          )}
          {seq.status === "paused" && (
            <button
              type="button"
              className="pf-cf-followup__action"
              onClick={() => lifecycle.resume.mutate(seq.id)}
            >
              Resume
            </button>
          )}
          <button
            type="button"
            className="pf-cf-followup__action pf-cf-followup__action--danger"
            onClick={() => {
              if (confirm(`Cancel follow-up "${seq.goal}"?`)) {
                lifecycle.cancel.mutate({
                  sequenceId: seq.id,
                  reason: "lo_cancelled",
                });
              }
            }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

export function FollowUpsPanel({ clientFileId }: { clientFileId: string }) {
  const { data: sequences, isLoading } = useCadenceSequences(clientFileId);
  const active = (sequences ?? []).filter(
    (s) => s.status === "active" || s.status === "paused",
  );
  const recent = (sequences ?? [])
    .filter((s) => s.status !== "active" && s.status !== "paused")
    .slice(0, 3);

  return (
    <Card title={`follow-ups${active.length > 0 ? ` · ${active.length} active` : ""}`}>
      {isLoading ? (
        <div className="pf-cf-empty">Loading…</div>
      ) : active.length === 0 && recent.length === 0 ? (
        <div className="pf-cf-empty">
          No autonomous follow-ups running for this client.
        </div>
      ) : (
        <>
          {active.map((s) => (
            <FollowupRow key={s.id} seq={s} clientFileId={clientFileId} />
          ))}
          {recent.length > 0 && (
            <>
              <div
                style={{
                  fontSize: 10,
                  color: "var(--pf-cf-text-tertiary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  marginTop: 10,
                  marginBottom: 4,
                }}
              >
                Recent
              </div>
              {recent.map((s) => (
                <FollowupRow key={s.id} seq={s} clientFileId={clientFileId} />
              ))}
            </>
          )}
        </>
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

function TaskRow({ task, clientFileId }: { task: Task; clientFileId: string }) {
  const { complete, reopen } = useTaskMutations(clientFileId);
  const done = task.status === "done";
  return (
    <div className="pf-cf-task">
      <button
        type="button"
        className={"pf-cf-task__check" + (done ? " pf-cf-task__check--done" : "")}
        onClick={() =>
          done ? reopen.mutate(task.id) : complete.mutate(task.id)
        }
        aria-label={done ? "Reopen task" : "Complete task"}
      >
        {done && (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        )}
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className={"pf-cf-task__title" + (done ? " pf-cf-task__title--done" : "")}>
          {task.title}
        </div>
        {task.due_at && (
          <div className="pf-cf-task__due">
            {new Date(task.due_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
            {task.priority === "high" || task.priority === "urgent" ? " · " + task.priority : ""}
          </div>
        )}
      </div>
    </div>
  );
}

export function TasksPanel({ clientFileId }: { clientFileId: string }) {
  const { data: tasks, isLoading } = useTasks(clientFileId);
  const open = (tasks ?? []).filter((t) => t.status !== "done");
  return (
    <Card title={`tasks${open.length > 0 ? ` · ${open.length}` : ""}`}>
      {isLoading ? (
        <div className="pf-cf-empty">Loading…</div>
      ) : open.length === 0 ? (
        <div className="pf-cf-empty">No open tasks.</div>
      ) : (
        open.map((t) => <TaskRow key={t.id} task={t} clientFileId={clientFileId} />)
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Documents
// ─────────────────────────────────────────────────────────────────────────

const DOC_STATUS_CLASS: Partial<Record<DocumentRequestStatus, string>> = {
  fulfilled: "pf-cf-doc__status--fulfilled",
  rejected: "pf-cf-doc__status--rejected",
  expired: "pf-cf-doc__status--rejected",
};

function DocumentSetRow({ set: ds }: { set: DocumentSet }) {
  const [expanded, setExpanded] = useState(ds.open_count > 0);
  return (
    <div className="pf-cf-doc-group">
      <button
        type="button"
        className="pf-cf-doc-group__head"
        onClick={() => setExpanded((v) => !v)}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
          <span>{ds.title}</span>
        </span>
        <span className="pf-cf-doc-group__count">
          {ds.fulfilled_count} / {ds.fulfilled_count + ds.open_count}
        </span>
      </button>
      {expanded &&
        ds.requests.map((req) => (
          <div key={req.id} className="pf-cf-doc">
            <div className="pf-cf-doc__title">{req.title}</div>
            <div
              className={`pf-cf-doc__status ${
                req.is_stale
                  ? "pf-cf-doc__status--stale"
                  : DOC_STATUS_CLASS[req.status] || ""
              }`}
            >
              {req.is_stale ? "stale" : req.status}
            </div>
          </div>
        ))}
    </div>
  );
}

export function DocumentsPanel({ clientFileId }: { clientFileId: string }) {
  const { data: sets, isLoading } = useDocumentSets(clientFileId);
  const totalOpen = (sets ?? []).reduce((sum, s) => sum + s.open_count, 0);
  const totalFulfilled = (sets ?? []).reduce((sum, s) => sum + s.fulfilled_count, 0);
  return (
    <Card
      title={
        sets && sets.length > 0
          ? `documents · ${totalFulfilled} / ${totalFulfilled + totalOpen}`
          : "documents"
      }
    >
      {isLoading ? (
        <div className="pf-cf-empty">Loading…</div>
      ) : !sets || sets.length === 0 ? (
        <div className="pf-cf-empty">No documents required yet.</div>
      ) : (
        sets.map((s) => <DocumentSetRow key={s.id} set={s} />)
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Relationships
// ─────────────────────────────────────────────────────────────────────────

const REL_TYPE_LABEL: Record<Relationship["relationship_type"], string> = {
  spouse: "spouse",
  co_borrower: "co-borrower",
  buyers_agent: "buyer's agent",
  listing_agent: "listing agent",
  settlement_agent: "settlement agent",
  attorney: "attorney",
  gift_donor: "gift donor",
  power_of_attorney: "POA",
  referrer: "referrer",
  family_decision_maker: "decision-maker",
  past_client_referrer: "past client",
  employer: "employer",
  other: "other",
};

export function RelationshipsPanel({ clientFileId }: { clientFileId: string }) {
  const { data, isLoading } = useRelationships(clientFileId);
  return (
    <Card title="relationships">
      {isLoading ? (
        <div className="pf-cf-empty">Loading…</div>
      ) : !data || data.length === 0 ? (
        <div className="pf-cf-empty">No relationships on file.</div>
      ) : (
        data.map((rel) => (
          <div key={rel.id} className="pf-cf-relationship">
            <span className="pf-cf-relationship__name">
              {rel.display_name}
              {rel.is_decision_maker && (
                <span style={{ color: "var(--pf-cf-warning)", marginLeft: 4 }}>★</span>
              )}
            </span>
            <span className="pf-cf-relationship__type">
              {REL_TYPE_LABEL[rel.relationship_type]}
            </span>
          </div>
        ))
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Action plans
// ─────────────────────────────────────────────────────────────────────────

export function ActionPlansPanel({ clientFileId }: { clientFileId: string }) {
  const { data, isLoading } = useActionPlanRuns(clientFileId);
  const active = (data ?? []).filter(
    (r) => r.status === "active" || r.status === "paused",
  );
  if (!isLoading && active.length === 0) return null;
  return (
    <Card title="action plans">
      {isLoading ? (
        <div className="pf-cf-empty">Loading…</div>
      ) : (
        active.map((r) => (
          <div key={r.id} className="pf-cf-followup">
            <div className="pf-cf-followup__head">
              <span className="pf-cf-followup__goal">{r.action_plan_name}</span>
              <Pill variant={r.status === "active" ? "success" : "warning"}>
                {r.status}
              </Pill>
            </div>
            <div className="pf-cf-followup__meta">
              step {r.current_step_index + 1} of {r.total_steps}
              {r.next_step_at && r.status === "active" &&
                ` · next ${formatRelativeTime(r.next_step_at)}`}
            </div>
          </div>
        ))
      )}
    </Card>
  );
}
