import { useState } from "react";

import { useTasks, useTaskMutations } from "./hooks";
import { Pill } from "./primitives/Pill";
import { formatRelativeTime } from "./format";
import type { Task, TaskPriority } from "./types";

type TaskTab = "open" | "completed" | "all";

const PRIORITY_VARIANT: Record<TaskPriority, "danger" | "warning" | "default" | "accent"> = {
  urgent: "danger",
  high: "warning",
  normal: "default",
  low: "default",
};

const PRIORITY_OPTIONS: TaskPriority[] = ["low", "normal", "high", "urgent"];

function dueDateClass(dueAt: string | null | undefined): string {
  if (!dueAt) return "";
  const due = new Date(dueAt);
  const now = new Date();
  const diffMs = due.getTime() - now.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  if (diffDays < 0) return "pf-cf-taskcard__due--overdue";
  if (diffDays < 2) return "pf-cf-taskcard__due--soon";
  return "";
}

// ─────────────────────────────────────────────────────────────────────────
// Task Card
// ─────────────────────────────────────────────────────────────────────────

function TaskCard({
  task,
  clientFileId,
}: {
  task: Task;
  clientFileId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(task.title);
  const [editBody, setEditBody] = useState(task.body || "");
  const [editPriority, setEditPriority] = useState(task.priority);
  const [editDue, setEditDue] = useState(task.due_at?.split("T")[0] || "");
  const mutations = useTaskMutations(clientFileId);
  const done = task.status === "done";

  function handleSave() {
    mutations.patch.mutate({
      taskId: task.id,
      title: editTitle,
      body: editBody || undefined,
      priority: editPriority,
      due_at: editDue ? new Date(editDue).toISOString() : undefined,
    });
    setEditing(false);
  }

  return (
    <div className={`pf-cf-taskcard${done ? " pf-cf-taskcard--done" : ""}`}>
      <div className="pf-cf-taskcard__head">
        <button
          type="button"
          className={`pf-cf-taskcard__check${done ? " pf-cf-taskcard__check--done" : ""}`}
          onClick={() => done ? mutations.reopen.mutate(task.id) : mutations.complete.mutate(task.id)}
          aria-label={done ? "Reopen task" : "Complete task"}
        >
          {done && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
        </button>

        <button
          type="button"
          className="pf-cf-taskcard__main"
          onClick={() => setExpanded((v) => !v)}
        >
          <div className="pf-cf-taskcard__info">
            <div className={`pf-cf-taskcard__title${done ? " pf-cf-taskcard__title--done" : ""}`}>
              {task.title}
            </div>
            <div className="pf-cf-taskcard__meta">
              {task.due_at && (
                <span className={`pf-cf-taskcard__due ${dueDateClass(task.due_at)}`}>
                  {new Date(task.due_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })}
                </span>
              )}
              {task.assigned_to_user_name && (
                <span className="pf-cf-taskcard__assignee">
                  {task.assigned_to_user_name}
                </span>
              )}
              {done && task.completed_at && (
                <span className="pf-cf-taskcard__completed">
                  completed {formatRelativeTime(task.completed_at)}
                </span>
              )}
            </div>
          </div>
          <div className="pf-cf-taskcard__badges">
            {(task.priority === "high" || task.priority === "urgent") && (
              <Pill variant={PRIORITY_VARIANT[task.priority]}>{task.priority}</Pill>
            )}
          </div>
          <span className="pf-cf-taskcard__chevron">{expanded ? "▾" : "▸"}</span>
        </button>
      </div>

      {expanded && (
        <div className="pf-cf-taskcard__body">
          {!editing ? (
            <>
              {task.body && (
                <div className="pf-cf-taskcard__desc">{task.body}</div>
              )}
              <div className="pf-cf-taskcard__details">
                <div className="pf-cf-taskcard__detail">
                  <span className="pf-cf-taskcard__detail-label">Priority</span>
                  <Pill variant={PRIORITY_VARIANT[task.priority]}>{task.priority}</Pill>
                </div>
                {task.due_at && (
                  <div className="pf-cf-taskcard__detail">
                    <span className="pf-cf-taskcard__detail-label">Due</span>
                    <span>{new Date(task.due_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</span>
                  </div>
                )}
                {task.assigned_to_user_name && (
                  <div className="pf-cf-taskcard__detail">
                    <span className="pf-cf-taskcard__detail-label">Assigned to</span>
                    <span>{task.assigned_to_user_name}</span>
                  </div>
                )}
              </div>
              <div className="pf-cf-taskcard__actions">
                <button
                  type="button"
                  className="pf-cf-btn pf-cf-btn--outline pf-cf-btn--sm"
                  onClick={() => {
                    setEditTitle(task.title);
                    setEditBody(task.body || "");
                    setEditPriority(task.priority);
                    setEditDue(task.due_at?.split("T")[0] || "");
                    setEditing(true);
                  }}
                >
                  Edit
                </button>
                {!done && (
                  <button
                    type="button"
                    className="pf-cf-btn pf-cf-btn--accent pf-cf-btn--sm"
                    onClick={() => mutations.complete.mutate(task.id)}
                  >
                    Complete
                  </button>
                )}
                {done && (
                  <button
                    type="button"
                    className="pf-cf-btn pf-cf-btn--ghost pf-cf-btn--sm"
                    onClick={() => mutations.reopen.mutate(task.id)}
                  >
                    Reopen
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="pf-cf-taskcard__edit">
              <div className="pf-cf-newreq__row">
                <label className="pf-cf-newreq__label">Title</label>
                <input
                  className="pf-cf-newreq__input"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </div>
              <div className="pf-cf-newreq__row">
                <label className="pf-cf-newreq__label">Description</label>
                <textarea
                  className="pf-cf-newreq__textarea"
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={2}
                />
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <div className="pf-cf-newreq__row" style={{ flex: 1 }}>
                  <label className="pf-cf-newreq__label">Priority</label>
                  <select
                    className="pf-cf-newreq__select"
                    value={editPriority}
                    onChange={(e) => setEditPriority(e.target.value as TaskPriority)}
                  >
                    {PRIORITY_OPTIONS.map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </div>
                <div className="pf-cf-newreq__row" style={{ flex: 1 }}>
                  <label className="pf-cf-newreq__label">Due date</label>
                  <input
                    type="date"
                    className="pf-cf-newreq__input"
                    value={editDue}
                    onChange={(e) => setEditDue(e.target.value)}
                  />
                </div>
              </div>
              <div className="pf-cf-newreq__actions">
                <button
                  type="button"
                  className="pf-cf-btn pf-cf-btn--accent pf-cf-btn--sm"
                  disabled={!editTitle.trim() || mutations.patch.isPending}
                  onClick={handleSave}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="pf-cf-btn pf-cf-btn--ghost pf-cf-btn--sm"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// New Task Form
// ─────────────────────────────────────────────────────────────────────────

function NewTaskForm({
  clientFileId,
  onClose,
}: {
  clientFileId: string;
  onClose: () => void;
}) {
  const mutations = useTaskMutations(clientFileId);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("normal");
  const [dueDate, setDueDate] = useState("");

  return (
    <div className="pf-cf-newreq">
      <div className="pf-cf-newreq__row">
        <label className="pf-cf-newreq__label">Title</label>
        <input
          className="pf-cf-newreq__input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What needs to be done?"
          autoFocus
        />
      </div>
      <div className="pf-cf-newreq__row">
        <label className="pf-cf-newreq__label">Description (optional)</label>
        <textarea
          className="pf-cf-newreq__textarea"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Additional details..."
          rows={2}
        />
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <div className="pf-cf-newreq__row" style={{ flex: 1 }}>
          <label className="pf-cf-newreq__label">Priority</label>
          <select
            className="pf-cf-newreq__select"
            value={priority}
            onChange={(e) => setPriority(e.target.value as TaskPriority)}
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <div className="pf-cf-newreq__row" style={{ flex: 1 }}>
          <label className="pf-cf-newreq__label">Due date</label>
          <input
            type="date"
            className="pf-cf-newreq__input"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </div>
      </div>
      <div className="pf-cf-newreq__actions">
        <button
          type="button"
          className="pf-cf-btn pf-cf-btn--accent"
          disabled={!title.trim() || mutations.create.isPending}
          onClick={() => {
            mutations.create.mutate({
              title: title.trim(),
              body: body || undefined,
              priority,
              due_at: dueDate ? new Date(dueDate).toISOString() : undefined,
            });
            onClose();
          }}
        >
          Create Task
        </button>
        <button type="button" className="pf-cf-btn pf-cf-btn--ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Main Tasks Pane
// ─────────────────────────────────────────────────────────────────────────

interface Props {
  clientFileId: string;
}

export function TasksPane({ clientFileId }: Props) {
  const [subTab, setSubTab] = useState<TaskTab>("open");
  const [showNewTask, setShowNewTask] = useState(false);

  const includeDone = subTab === "completed" || subTab === "all";
  const { data: tasks, isLoading } = useTasks(clientFileId, { includeDone });

  const tabs: { key: TaskTab; label: string }[] = [
    { key: "open", label: "Open" },
    { key: "completed", label: "Completed" },
    { key: "all", label: "All" },
  ];

  const filtered = (tasks ?? []).filter((t) => {
    if (subTab === "open") return t.status !== "done";
    if (subTab === "completed") return t.status === "done";
    return true;
  });

  const openCount = (tasks ?? []).filter((t) => t.status !== "done").length;

  return (
    <div className="pf-cf-docs">
      {/* Sub-tab strip */}
      <div className="pf-cf-docs__tabs" role="tablist" aria-label="Task views">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={subTab === t.key}
            className={`pf-cf-docs__tab${subTab === t.key ? " pf-cf-docs__tab--active" : ""}`}
            onClick={() => setSubTab(t.key)}
          >
            {t.label}
            {t.key === "open" && openCount > 0 && (
              <span className="pf-cf-activity__badge" style={{ marginLeft: 4 }}>
                {openCount}
              </span>
            )}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          type="button"
          className="pf-cf-btn pf-cf-btn--accent pf-cf-btn--sm"
          onClick={() => setShowNewTask((v) => !v)}
        >
          + Task
        </button>
      </div>

      {/* New task form */}
      {showNewTask && (
        <NewTaskForm
          clientFileId={clientFileId}
          onClose={() => setShowNewTask(false)}
        />
      )}

      {/* Content */}
      <div className="pf-cf-docs__content">
        {isLoading ? (
          <div className="pf-cf-empty">Loading tasks...</div>
        ) : filtered.length === 0 ? (
          <div className="pf-cf-empty">
            {subTab === "open"
              ? "No open tasks."
              : subTab === "completed"
              ? "No completed tasks."
              : "No tasks yet."}
          </div>
        ) : (
          filtered.map((task) => (
            <TaskCard key={task.id} task={task} clientFileId={clientFileId} />
          ))
        )}
      </div>
    </div>
  );
}
