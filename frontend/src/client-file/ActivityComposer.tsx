import { useState } from "react";

import { Pill } from "./primitives/Pill";
import { useAddNote, useSendMessage } from "./hooks";
import type { ComposerChannel } from "./types";

interface Props {
  clientFileId: string;
}

const CHANNELS: { key: ComposerChannel; label: string; placeholder: string }[] = [
  { key: "sms", label: "Text", placeholder: "Send a text…" },
  { key: "email", label: "Email", placeholder: "Send an email…" },
  { key: "note", label: "Note", placeholder: "Add a private note…" },
  { key: "voice_brief", label: "Brief Avery", placeholder: "Goal for the call…" },
];

export function ActivityComposer({ clientFileId }: Props) {
  const [channel, setChannel] = useState<ComposerChannel>("sms");
  const [body, setBody] = useState("");
  const [subject, setSubject] = useState("");
  const [alsoFollowup, setAlsoFollowup] = useState(false);

  const sendMessage = useSendMessage(clientFileId);
  const addNote = useAddNote(clientFileId);

  const def = CHANNELS.find((c) => c.key === channel)!;
  const sending = sendMessage.isPending || addNote.isPending;
  const canSend = body.trim().length > 0 && !sending;

  const handleSend = () => {
    if (!canSend) return;
    if (channel === "note") {
      addNote.mutate(body, {
        onSuccess: () => setBody(""),
      });
    } else {
      sendMessage.mutate(
        {
          channel: channel as "sms" | "email" | "voice_brief",
          body,
          subject: channel === "email" ? subject || undefined : undefined,
          also_start_followup: alsoFollowup,
          followup_goal: alsoFollowup ? "schedule_response_call" : undefined,
        },
        {
          onSuccess: () => {
            setBody("");
            setSubject("");
          },
        },
      );
    }
  };

  return (
    <div className="pf-cf-composer">
      <div className="pf-cf-composer__channels">
        {CHANNELS.map((c) => (
          <Pill
            key={c.key}
            active={channel === c.key}
            onClick={() => setChannel(c.key)}
          >
            {c.label}
          </Pill>
        ))}
      </div>

      <div className="pf-cf-composer__shell">
        {channel === "email" && (
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            style={{
              width: "100%",
              background: "transparent",
              border: "none",
              borderBottom: "1px solid var(--pf-cf-border)",
              color: "var(--pf-cf-text)",
              fontFamily: "inherit",
              fontSize: "13px",
              padding: "0 0 6px",
              marginBottom: "6px",
              outline: "none",
            }}
          />
        )}

        <textarea
          className="pf-cf-composer__textarea"
          placeholder={def.placeholder}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={3}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleSend();
            }
          }}
        />

        <div className="pf-cf-composer__footer">
          <div className="pf-cf-composer__hints">
            {channel !== "note" ? (
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={alsoFollowup}
                  onChange={(e) => setAlsoFollowup(e.target.checked)}
                  style={{ accentColor: "var(--pf-cf-accent)" }}
                />
                <span>Auto follow up if no reply</span>
              </label>
            ) : (
              <span>⌘+Enter to save</span>
            )}
          </div>
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            style={{
              background: canSend
                ? "var(--pf-cf-accent)"
                : "var(--pf-cf-bg-secondary)",
              color: canSend ? "var(--pf-cf-text-on-accent)" : "var(--pf-cf-text-tertiary)",
              border: "none",
              borderRadius: "var(--pf-cf-radius-sm)",
              padding: "5px 14px",
              fontSize: "12px",
              fontWeight: 500,
              cursor: canSend ? "pointer" : "not-allowed",
              fontFamily: "inherit",
            }}
          >
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
