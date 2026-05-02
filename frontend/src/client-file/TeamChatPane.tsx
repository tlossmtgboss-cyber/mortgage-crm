import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Avatar, deriveInitials } from "./primitives/Avatar";
import {
  useTeamChatActions,
  useTeamChatMembers,
  useTeamChatMessages,
  useTeamChatPinned,
  useTeamChatTyping,
} from "./hooks";
import { dayKey, formatDayLabel, formatTime } from "./format";
import type {
  TeamChatAuthor,
  TeamChatMessage,
  TeamChatReactionEmoji,
  TeamChatSystemAuthor,
} from "./types";

interface Props {
  clientFileId: string;
  currentUserId: string;
  active: boolean; // whether the pane is currently visible (controls polling)
}

const REACTION_GLYPHS: Record<TeamChatReactionEmoji, string> = {
  thumbs_up: "👍",
  check: "✓",
  fire: "🔥",
  question: "?",
};

const REACTION_OPTIONS: TeamChatReactionEmoji[] = [
  "thumbs_up",
  "check",
  "fire",
  "question",
];

const AGENT_GLYPH: Record<TeamChatSystemAuthor["agent_slug"], string> = {
  cadence: "◇",
  aria: "◐",
  avery: "◑",
  insight: "✦",
  ops_manager: "◈",
  document: "▤",
  milestone: "◆",
  lifecycle: "⇄",
};

// ─────────────────────────────────────────────────────────────────────────
// Pinned banner
// ─────────────────────────────────────────────────────────────────────────

function PinnedBanner({ clientFileId }: { clientFileId: string }) {
  const { data: pinned } = useTeamChatPinned(clientFileId);
  const actions = useTeamChatActions(clientFileId);
  if (!pinned) return null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 16px",
        background: "var(--pf-cf-warning-bg)",
        borderBottom: "1px solid var(--pf-cf-border)",
        fontSize: 12,
      }}
    >
      <span aria-hidden="true" style={{ color: "var(--pf-cf-warning)" }}>📌</span>
      <div style={{ flex: 1, minWidth: 0, color: "var(--pf-cf-text)" }}>
        <strong style={{ fontWeight: 500 }}>Pinned · </strong>
        {pinned.body}
      </div>
      <button
        type="button"
        onClick={() => actions.unpin.mutate(pinned.id)}
        style={{
          background: "transparent",
          border: "none",
          color: "var(--pf-cf-text-tertiary)",
          cursor: "pointer",
          fontSize: 14,
          padding: 0,
        }}
        aria-label="Unpin"
      >
        ×
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// System (agent) message — distinguished visually
// ─────────────────────────────────────────────────────────────────────────

function SystemMessage({ message }: { message: TeamChatMessage }) {
  if (message.author.kind !== "system") return null;
  const author = message.author;

  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "center",
        padding: "8px 12px",
        margin: "6px 0",
        background: "var(--pf-cf-agent-bg)",
        border: "1px solid var(--pf-cf-agent-border)",
        borderRadius: "var(--pf-cf-radius-md)",
        fontSize: 12,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 24,
          height: 24,
          borderRadius: "50%",
          background: "var(--pf-cf-agent-bg)",
          color: "var(--pf-cf-agent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          fontSize: 12,
        }}
      >
        {AGENT_GLYPH[author.agent_slug] ?? "•"}
      </span>
      <div style={{ flex: 1, minWidth: 0, color: "var(--pf-cf-agent)" }}>
        <span style={{ fontWeight: 500 }}>{author.display_name}</span>
        <span style={{ marginLeft: 6 }}>{message.body}</span>
        {author.source_object_label && (
          <span
            style={{
              marginLeft: 6,
              padding: "1px 6px",
              borderRadius: 4,
              background: "var(--pf-cf-bg-secondary)",
              fontSize: 11,
            }}
          >
            {author.source_object_label}
          </span>
        )}
      </div>
      <span style={{ color: "var(--pf-cf-text-tertiary)", fontSize: 11, flexShrink: 0 }}>
        {formatTime(message.created_at)}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Human message bubble
// ─────────────────────────────────────────────────────────────────────────

function renderBodyWithMentions(body: string, mentionedUserIds: string[]): ReactNode {
  // Simple @-mention highlighter. Production would use a proper parser
  // tied to mentioned_user_ids; this renders @anything as accent.
  const parts = body.split(/(@\w+)/g);
  return parts.map((p, i) =>
    p.startsWith("@") ? (
      <span
        key={i}
        style={{
          background: "var(--pf-cf-accent-bg)",
          color: "var(--pf-cf-accent)",
          padding: "1px 6px",
          borderRadius: 4,
          fontWeight: 500,
        }}
      >
        {p}
      </span>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

function HumanMessage({
  message,
  clientFileId,
  currentUserId,
}: {
  message: TeamChatMessage;
  clientFileId: string;
  currentUserId: string;
}) {
  if (message.author.kind !== "human") return null;
  const author = message.author;
  const actions = useTeamChatActions(clientFileId);
  const [showReactionPicker, setShowReactionPicker] = useState(false);
  const isOwn = author.user_id === currentUserId;

  return (
    <div
      style={{ display: "flex", gap: 10, padding: "8px 0" }}
      onMouseLeave={() => setShowReactionPicker(false)}
    >
      <Avatar initials={author.initials} size="md" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 8,
            marginBottom: 2,
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--pf-cf-text)" }}>
            {author.display_name}
          </span>
          <span
            style={{
              fontSize: 10,
              color: "var(--pf-cf-text-tertiary)",
              textTransform: "lowercase",
              fontFamily: "var(--pf-cf-font-mono)",
            }}
          >
            {author.role.replace(/_/g, " ")}
          </span>
          <span style={{ fontSize: 11, color: "var(--pf-cf-text-tertiary)" }}>
            {formatTime(message.created_at)}
          </span>
          {message.edited_at && (
            <span style={{ fontSize: 10, color: "var(--pf-cf-text-faint)" }}>
              edited
            </span>
          )}
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--pf-cf-text)" }}>
          {renderBodyWithMentions(message.body, message.mentioned_user_ids)}
        </div>

        {/* Attachments */}
        {message.attachments.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
            {message.attachments.map((att) => (
              <div
                key={att.document_upload_id}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "4px 10px",
                  background: "var(--pf-cf-bg-secondary)",
                  border: "1px solid var(--pf-cf-border)",
                  borderRadius: "var(--pf-cf-radius-sm)",
                  fontSize: 12,
                  color: "var(--pf-cf-text-secondary)",
                  width: "fit-content",
                  maxWidth: "100%",
                }}
              >
                <span aria-hidden="true">▤</span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                  {att.filename}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Reactions */}
        <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
          {message.reactions.map((r) => (
            <button
              key={r.emoji}
              type="button"
              onClick={() =>
                r.current_user_reacted
                  ? actions.unreact.mutate({ messageId: message.id, emoji: r.emoji })
                  : actions.react.mutate({ messageId: message.id, emoji: r.emoji })
              }
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "2px 8px",
                background: r.current_user_reacted
                  ? "var(--pf-cf-accent-bg)"
                  : "var(--pf-cf-bg-secondary)",
                border: r.current_user_reacted
                  ? "1px solid var(--pf-cf-accent-border)"
                  : "1px solid var(--pf-cf-border)",
                borderRadius: 12,
                fontSize: 11,
                cursor: "pointer",
                color: r.current_user_reacted ? "var(--pf-cf-accent)" : "var(--pf-cf-text-secondary)",
                fontFamily: "inherit",
              }}
            >
              <span>{REACTION_GLYPHS[r.emoji]}</span>
              <span>{r.count}</span>
            </button>
          ))}
          {showReactionPicker ? (
            <div
              style={{
                display: "inline-flex",
                gap: 2,
                padding: "2px 4px",
                background: "var(--pf-cf-bg-glass-strong)",
                border: "1px solid var(--pf-cf-border-strong)",
                borderRadius: 12,
              }}
            >
              {REACTION_OPTIONS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  onClick={() => {
                    actions.react.mutate({ messageId: message.id, emoji });
                    setShowReactionPicker(false);
                  }}
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: "2px 6px",
                    fontSize: 13,
                    fontFamily: "inherit",
                    color: "var(--pf-cf-text)",
                  }}
                >
                  {REACTION_GLYPHS[emoji]}
                </button>
              ))}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowReactionPicker(true)}
              style={{
                background: "transparent",
                border: "1px solid var(--pf-cf-border)",
                borderRadius: 12,
                fontSize: 11,
                color: "var(--pf-cf-text-tertiary)",
                cursor: "pointer",
                padding: "2px 8px",
                fontFamily: "inherit",
              }}
              aria-label="Add reaction"
            >
              +
            </button>
          )}
          {!message.is_pinned && isOwn && (
            <button
              type="button"
              onClick={() => actions.pin.mutate(message.id)}
              style={{
                background: "transparent",
                border: "none",
                color: "var(--pf-cf-text-faint)",
                cursor: "pointer",
                fontSize: 11,
                fontFamily: "inherit",
                marginLeft: 4,
              }}
            >
              pin
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Composer
// ─────────────────────────────────────────────────────────────────────────

function Composer({ clientFileId }: { clientFileId: string }) {
  const [body, setBody] = useState("");
  const actions = useTeamChatActions(clientFileId);
  const typingDebounce = useRef<number | null>(null);

  const handleChange = (value: string) => {
    setBody(value);
    if (typingDebounce.current) window.clearTimeout(typingDebounce.current);
    typingDebounce.current = window.setTimeout(() => {
      actions.setTyping.mutate();
    }, 250);
  };

  const handleSend = () => {
    const trimmed = body.trim();
    if (!trimmed) return;
    // Extract @mentions from body (simple parsing — backend will resolve).
    const mentions = (trimmed.match(/@(\w+)/g) ?? []).map((s) => s.slice(1));
    actions.send.mutate(
      { body: trimmed, mentioned_user_ids: mentions },
      { onSuccess: () => setBody("") },
    );
  };

  return (
    <div
      style={{
        padding: "12px 16px",
        borderTop: "1px solid var(--pf-cf-border)",
        background: "var(--pf-cf-bg-glass)",
      }}
    >
      <div
        style={{
          background: "var(--pf-cf-bg-glass-strong)",
          border: "1px solid var(--pf-cf-border)",
          borderRadius: "var(--pf-cf-radius-md)",
          padding: "10px 12px",
        }}
      >
        <textarea
          value={body}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Message the team about this client…"
          rows={2}
          style={{
            width: "100%",
            background: "transparent",
            border: "none",
            color: "var(--pf-cf-text)",
            fontFamily: "inherit",
            fontSize: 13,
            lineHeight: 1.5,
            resize: "none",
            minHeight: 36,
            maxHeight: 200,
            outline: "none",
            padding: 0,
          }}
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginTop: 8,
            paddingTop: 8,
            borderTop: "1px solid var(--pf-cf-border)",
          }}
        >
          <span style={{ fontSize: 11, color: "var(--pf-cf-text-tertiary)" }}>
            @ to mention · Enter to send · Shift+Enter for newline
          </span>
          <div style={{ flex: 1 }} />
          <button
            type="button"
            onClick={handleSend}
            disabled={!body.trim() || actions.send.isPending}
            style={{
              background: body.trim() ? "var(--pf-cf-accent)" : "var(--pf-cf-bg-secondary)",
              color: body.trim() ? "var(--pf-cf-text-on-accent)" : "var(--pf-cf-text-tertiary)",
              border: "none",
              borderRadius: "var(--pf-cf-radius-sm)",
              padding: "5px 12px",
              fontSize: 12,
              fontWeight: 500,
              cursor: body.trim() ? "pointer" : "not-allowed",
              fontFamily: "inherit",
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Main pane
// ─────────────────────────────────────────────────────────────────────────

export function TeamChatPane({ clientFileId, currentUserId, active }: Props) {
  const { data: messages, isLoading } = useTeamChatMessages(clientFileId, active);
  const { data: members } = useTeamChatMembers(clientFileId);
  const { data: typing } = useTeamChatTyping(clientFileId, active);
  const actions = useTeamChatActions(clientFileId);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current && messages?.length) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages?.length]);

  // Mark read when pane becomes active or new messages arrive
  useEffect(() => {
    if (active && messages?.length) {
      const last = messages[messages.length - 1];
      actions.markRead.mutate(last.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, messages?.length]);

  const grouped = useMemo(() => {
    if (!messages) return [];
    const days = new Map<string, { label: string; messages: TeamChatMessage[] }>();
    for (const m of messages) {
      const k = dayKey(m.created_at);
      if (!days.has(k)) {
        days.set(k, { label: formatDayLabel(m.created_at), messages: [] });
      }
      days.get(k)!.messages.push(m);
    }
    return Array.from(days.values());
  }, [messages]);

  const typingNames = useMemo(() => {
    if (!typing || !members) return [];
    const map = new Map(members.map((m) => [m.user_id, m.display_name]));
    return typing.typing_user_ids
      .filter((id) => id !== currentUserId)
      .map((id) => map.get(id) ?? "Someone");
  }, [typing, members, currentUserId]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Member strip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "8px 16px",
          borderBottom: "1px solid var(--pf-cf-border)",
          background: "var(--pf-cf-bg-glass)",
        }}
      >
        <div style={{ display: "flex" }}>
          {(members ?? []).slice(0, 5).map((m, i) => (
            <span
              key={m.user_id}
              style={{
                marginLeft: i === 0 ? 0 : -8,
                border: "1.5px solid var(--pf-cf-bg-deep)",
                borderRadius: "50%",
                position: "relative",
              }}
            >
              <Avatar
                initials={m.initials || deriveInitials(m.display_name)}
                size="sm"
                online={m.is_online}
              />
            </span>
          ))}
        </div>
        <span style={{ fontSize: 11, color: "var(--pf-cf-text-tertiary)" }}>
          {members?.length ?? 0} {members?.length === 1 ? "member" : "members"}
        </span>
      </div>

      <PinnedBanner clientFileId={clientFileId} />

      {/* Messages scroll area */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 16px 8px",
          minHeight: 0,
        }}
      >
        {isLoading ? (
          <div className="pf-cf-loading">Loading chat…</div>
        ) : grouped.length === 0 ? (
          <div className="pf-cf-empty" style={{ padding: 32 }}>
            No messages yet. Start a conversation with the team about this client.
          </div>
        ) : (
          grouped.map((day) => (
            <div key={day.label}>
              <div
                style={{
                  textAlign: "center",
                  margin: "12px 0 8px",
                  fontSize: 10,
                  color: "var(--pf-cf-text-tertiary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                {day.label}
              </div>
              {day.messages.map((m) =>
                m.author.kind === "system" ? (
                  <SystemMessage key={m.id} message={m} />
                ) : (
                  <HumanMessage
                    key={m.id}
                    message={m}
                    clientFileId={clientFileId}
                    currentUserId={currentUserId}
                  />
                ),
              )}
            </div>
          ))
        )}

        {typingNames.length > 0 && (
          <div
            style={{
              fontSize: 11,
              color: "var(--pf-cf-text-tertiary)",
              fontStyle: "italic",
              padding: "4px 0 4px 42px",
            }}
          >
            {typingNames.join(", ")} {typingNames.length === 1 ? "is" : "are"} typing…
          </div>
        )}
      </div>

      <Composer clientFileId={clientFileId} />
    </div>
  );
}
