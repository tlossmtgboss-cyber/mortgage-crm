// Perennia iMessage — MessageComposer
// Channel-aware composer matching Perennia's design system.
//
// Features:
//   - Auto-resizing textarea, Enter to send / Shift+Enter for newline
//   - Channel override pill (Auto / iMessage / SMS)
//   - Send-style picker (iMessage only): slam, loud, gentle, invisible,
//     plus screen effects (confetti, fireworks, hearts, lasers, etc.)
//   - Voice memo button — records via MediaRecorder, sends as CAF audio
//     so it renders as an iMessage voice-memo bubble (BB convention)
//   - Reply-quote banner when replying to a specific message
//   - Calls useThread.notifyTyping() on each keystroke for live "..."
//   - SMS character-count awareness (160-char segments)

import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type {
  Channel,
  ConversationMessage,
  SendStyle,
} from "../types";

interface Props {
  /** Detected/last-known channel; used to choose the default theme. */
  detectedChannel: Channel | null;
  /** When set, shows the reply-quote banner above the input. */
  replyTo?: ConversationMessage | null;
  onCancelReply?: () => void;
  /** Send handler — wired from useThread. */
  onSend: (input: {
    body?: string;
    mediaUrl?: string;
    channel?: Channel;
    sendStyle?: SendStyle;
  }) => Promise<void>;
  /** Typing notify hook from useThread. */
  onTyping?: () => void;
  sending: boolean;
  disabled?: boolean;
  /**
   * Upload a Blob and return a URL the backend can ingest. Wire this to
   * your existing media upload endpoint (S3 presign, etc.).
   */
  uploadAttachment: (blob: Blob, filename: string) => Promise<string>;
}

const PERENNIA_BLUE = "#7EB8F7";
const APPLE_BLUE = "#007AFF";
const SMS_GREEN = "#34C759";
const DEEP_SPACE = "#060A10";

const SEND_STYLE_OPTIONS: { value: SendStyle; label: string; group: "bubble" | "screen" }[] = [
  { value: "", label: "Default", group: "bubble" },
  { value: "slam", label: "Slam", group: "bubble" },
  { value: "loud", label: "Loud", group: "bubble" },
  { value: "gentle", label: "Gentle", group: "bubble" },
  { value: "invisible", label: "Invisible Ink", group: "bubble" },
  { value: "confetti", label: "Confetti", group: "screen" },
  { value: "fireworks", label: "Fireworks", group: "screen" },
  { value: "heart", label: "Hearts", group: "screen" },
  { value: "lasers", label: "Lasers", group: "screen" },
  { value: "shooting_star", label: "Shooting Star", group: "screen" },
  { value: "sparkles", label: "Sparkles", group: "screen" },
  { value: "spotlight", label: "Spotlight", group: "screen" },
  { value: "echo", label: "Echo", group: "screen" },
];

export const MessageComposer = memo(function MessageComposer({
  detectedChannel,
  replyTo,
  onCancelReply,
  onSend,
  onTyping,
  sending,
  disabled = false,
  uploadAttachment,
}: Props) {
  const [body, setBody] = useState("");
  const [channelOverride, setChannelOverride] = useState<Channel>("auto");
  const [sendStyle, setSendStyle] = useState<SendStyle>("");
  const [showStylePicker, setShowStylePicker] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recordIntervalRef = useRef<number | null>(null);

  // Effective channel — what we'll actually pass to the backend
  const effectiveChannel: Channel =
    channelOverride !== "auto"
      ? channelOverride
      : detectedChannel ?? "auto";

  const isImessage = effectiveChannel === "imessage";

  // ---- Auto-resize textarea -------------------------------------------------
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [body]);

  // ---- Submit ---------------------------------------------------------------
  const submit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = body.trim();
      if (!trimmed || sending || disabled) return;
      const payload = {
        body: trimmed,
        channel: channelOverride,
        sendStyle: isImessage && sendStyle ? sendStyle : undefined,
      };
      setBody("");
      setSendStyle("");
      setShowStylePicker(false);
      onCancelReply?.();
      await onSend(payload);
    },
    [body, channelOverride, isImessage, sendStyle, sending, disabled, onSend, onCancelReply],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void submit();
      }
    },
    [submit],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setBody(e.target.value);
      onTyping?.();
    },
    [onTyping],
  );

  // ---- Voice memo recording -------------------------------------------------
  const startRecording = useCallback(async () => {
    if (recording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Prefer AAC/CAF when supported so it lands as a voice-memo bubble
      const preferredMime =
        MediaRecorder.isTypeSupported("audio/mp4;codecs=mp4a.40.2")
          ? "audio/mp4;codecs=mp4a.40.2"
          : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: preferredMime });
      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const ext = preferredMime.includes("mp4") ? "m4a" : "webm";
        const blob = new Blob(chunksRef.current, { type: preferredMime });
        if (blob.size === 0) return;
        try {
          const url = await uploadAttachment(blob, `voice-${Date.now()}.${ext}`);
          await onSend({
            mediaUrl: url,
            channel: channelOverride,
            sendStyle: undefined,
          });
        } catch (err) {
          console.error("voice-memo upload failed", err);
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
      setRecordSeconds(0);
      recordIntervalRef.current = window.setInterval(
        () => setRecordSeconds((s) => s + 1),
        1000,
      );
    } catch (err) {
      console.error("mic permission denied", err);
    }
  }, [recording, channelOverride, onSend, uploadAttachment]);

  const stopRecording = useCallback(() => {
    if (!recording) return;
    recorderRef.current?.stop();
    if (recordIntervalRef.current) {
      window.clearInterval(recordIntervalRef.current);
      recordIntervalRef.current = null;
    }
    setRecording(false);
    setRecordSeconds(0);
  }, [recording]);

  useEffect(
    () => () => {
      if (recordIntervalRef.current) window.clearInterval(recordIntervalRef.current);
      recorderRef.current?.stream?.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  // ---- SMS segment counter --------------------------------------------------
  const smsInfo = useMemo(() => {
    if (effectiveChannel !== "sms") return null;
    const len = body.length;
    const segLen = /[^\u0000-\u007F]/.test(body) ? 70 : 160;
    const segments = Math.max(1, Math.ceil(len / segLen));
    return { len, segLen, segments };
  }, [body, effectiveChannel]);

  // ---- Render ---------------------------------------------------------------
  const accent = isImessage ? APPLE_BLUE : effectiveChannel === "sms" ? SMS_GREEN : PERENNIA_BLUE;

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-2 px-4 pb-4 pt-2"
      style={{
        background: `linear-gradient(180deg, transparent 0%, ${DEEP_SPACE} 100%)`,
        fontFamily: "var(--font-dm-sans, 'DM Sans', system-ui, sans-serif)",
      }}
    >
      {replyTo && (
        <ReplyQuote message={replyTo} onCancel={onCancelReply} accent={accent} />
      )}

      <div className="flex items-end gap-2">
        {/* Voice memo */}
        <button
          type="button"
          aria-label={recording ? "Stop recording" : "Record voice memo"}
          onMouseDown={startRecording}
          onMouseUp={stopRecording}
          onMouseLeave={recording ? stopRecording : undefined}
          onTouchStart={startRecording}
          onTouchEnd={stopRecording}
          disabled={disabled}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition"
          style={{
            background: recording
              ? "rgba(255, 79, 79, 0.18)"
              : "rgba(126, 184, 247, 0.08)",
            border: `1px solid ${
              recording ? "rgba(255, 79, 79, 0.4)" : "rgba(126, 184, 247, 0.2)"
            }`,
            color: recording ? "#FF6E6E" : PERENNIA_BLUE,
          }}
        >
          {recording ? (
            <span className="text-[10px] font-mono">{recordSeconds}s</span>
          ) : (
            <MicIcon />
          )}
        </button>

        {/* Textarea */}
        <div
          className="relative flex-1 rounded-2xl"
          style={{
            background: "rgba(255, 255, 255, 0.04)",
            border: `1px solid ${
              effectiveChannel === "sms"
                ? "rgba(52, 199, 89, 0.18)"
                : "rgba(126, 184, 247, 0.18)"
            }`,
            backdropFilter: "blur(10px)",
          }}
        >
          <textarea
            ref={textareaRef}
            value={body}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled || sending}
            placeholder={
              effectiveChannel === "sms"
                ? "SMS — keep it short, no effects"
                : effectiveChannel === "imessage"
                ? "iMessage — full-fat available"
                : "Message…"
            }
            rows={1}
            className="w-full resize-none bg-transparent px-3.5 py-2.5 pr-20 text-[15px] leading-snug outline-none placeholder:text-white/30"
            style={{ color: "rgba(255,255,255,0.95)", maxHeight: 160 }}
          />

          {/* Send-style picker (iMessage only) */}
          {isImessage && (
            <button
              type="button"
              onClick={() => setShowStylePicker((v) => !v)}
              aria-label="Send style"
              className="absolute right-12 top-1/2 -translate-y-1/2 rounded-full p-1 text-xs"
              style={{
                color: sendStyle ? APPLE_BLUE : "rgba(255,255,255,0.4)",
              }}
            >
              <SparklesIcon />
            </button>
          )}

          {/* Submit */}
          <button
            type="submit"
            aria-label="Send"
            disabled={!body.trim() || sending || disabled}
            className="absolute right-1.5 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full transition disabled:opacity-30"
            style={{
              background: accent,
              color: "#FFFFFF",
              boxShadow: `0 0 12px ${accent}40`,
            }}
          >
            <ArrowUpIcon />
          </button>
        </div>

        {/* Channel override */}
        <ChannelOverridePill
          value={channelOverride}
          onChange={setChannelOverride}
          detected={detectedChannel}
        />
      </div>

      {/* SMS counter / send-style indicator */}
      <div className="flex items-center justify-between px-1 text-[10px]">
        <div
          style={{
            color: "rgba(255,255,255,0.45)",
            fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
          }}
        >
          {smsInfo &&
            `${smsInfo.len} chars · ${smsInfo.segments} segment${
              smsInfo.segments > 1 ? "s" : ""
            }`}
          {!smsInfo && sendStyle && `Send style: ${sendStyle}`}
        </div>
        <div
          style={{
            color: "rgba(255,255,255,0.35)",
            fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
          }}
        >
          Enter to send · Shift+Enter for new line
        </div>
      </div>

      {/* Send-style picker popover */}
      {showStylePicker && isImessage && (
        <SendStylePicker
          value={sendStyle}
          onChange={(v) => {
            setSendStyle(v);
            setShowStylePicker(false);
          }}
          onClose={() => setShowStylePicker(false)}
        />
      )}
    </form>
  );
});

// ---------------------------------------------------------------------------
function ReplyQuote({
  message,
  onCancel,
  accent,
}: {
  message: ConversationMessage;
  onCancel?: () => void;
  accent: string;
}) {
  return (
    <div
      className="flex items-start gap-2 rounded-lg px-3 py-2"
      style={{
        background: "rgba(255,255,255,0.03)",
        borderLeft: `2px solid ${accent}`,
      }}
    >
      <div className="flex-1 overflow-hidden">
        <div
          className="text-[10px] uppercase tracking-wider"
          style={{
            color: accent,
            fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
          }}
        >
          Replying to
        </div>
        <div
          className="truncate text-[12px]"
          style={{ color: "rgba(255,255,255,0.7)" }}
        >
          {message.body || "(media)"}
        </div>
      </div>
      <button
        type="button"
        onClick={onCancel}
        aria-label="Cancel reply"
        className="text-white/40 hover:text-white/80"
      >
        ✕
      </button>
    </div>
  );
}

function ChannelOverridePill({
  value,
  onChange,
  detected,
}: {
  value: Channel;
  onChange: (v: Channel) => void;
  detected: Channel | null;
}) {
  const cycle: Channel[] = ["auto", "imessage", "sms"];
  const labels: Record<Channel, string> = {
    auto: "Auto",
    imessage: "iMessage",
    sms: "SMS",
  };
  const next = () => {
    const i = cycle.indexOf(value);
    onChange(cycle[(i + 1) % cycle.length]);
  };
  return (
    <button
      type="button"
      onClick={next}
      title={detected ? `Detected: ${detected}` : undefined}
      className="h-9 shrink-0 rounded-full px-3 text-[10px] uppercase tracking-wide"
      style={{
        background: "rgba(126, 184, 247, 0.08)",
        border: "1px solid rgba(126, 184, 247, 0.2)",
        color: PERENNIA_BLUE,
        fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
      }}
    >
      {labels[value]}
    </button>
  );
}

function SendStylePicker({
  value,
  onChange,
  onClose,
}: {
  value: SendStyle;
  onChange: (v: SendStyle) => void;
  onClose: () => void;
}) {
  return (
    <div
      role="dialog"
      className="absolute bottom-20 right-4 z-20 grid w-72 gap-1 rounded-2xl p-3"
      style={{
        background: "rgba(10, 16, 24, 0.95)",
        border: "1px solid rgba(126, 184, 247, 0.2)",
        backdropFilter: "blur(20px)",
        boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
      }}
    >
      <div
        className="mb-1 text-[10px] uppercase tracking-wider"
        style={{
          color: PERENNIA_BLUE,
          fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
        }}
      >
        Bubble effect
      </div>
      <div className="grid grid-cols-2 gap-1">
        {SEND_STYLE_OPTIONS.filter((o) => o.group === "bubble").map((o) => (
          <button
            key={o.value || "default"}
            type="button"
            onClick={() => onChange(o.value)}
            className="rounded-lg px-2 py-1.5 text-left text-[12px]"
            style={{
              background:
                value === o.value
                  ? "rgba(0, 122, 255, 0.18)"
                  : "rgba(255,255,255,0.03)",
              color: "rgba(255,255,255,0.85)",
              border:
                value === o.value
                  ? "1px solid rgba(0, 122, 255, 0.4)"
                  : "1px solid transparent",
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      <div
        className="mb-1 mt-2 text-[10px] uppercase tracking-wider"
        style={{
          color: PERENNIA_BLUE,
          fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
        }}
      >
        Screen effect
      </div>
      <div className="grid grid-cols-2 gap-1">
        {SEND_STYLE_OPTIONS.filter((o) => o.group === "screen").map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className="rounded-lg px-2 py-1.5 text-left text-[12px]"
            style={{
              background:
                value === o.value
                  ? "rgba(0, 122, 255, 0.18)"
                  : "rgba(255,255,255,0.03)",
              color: "rgba(255,255,255,0.85)",
              border:
                value === o.value
                  ? "1px solid rgba(0, 122, 255, 0.4)"
                  : "1px solid transparent",
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="mt-2 rounded-lg py-1 text-[11px]"
        style={{
          background: "rgba(255,255,255,0.04)",
          color: "rgba(255,255,255,0.6)",
        }}
      >
        Close
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline icons (no external deps)
// ---------------------------------------------------------------------------
function MicIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M19 11a7 7 0 0 1-14 0M12 18v3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 19V5M5 12l7-7 7 7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SparklesIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
