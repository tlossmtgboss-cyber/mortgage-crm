// Perennia iMessage — BlueBubbleThread
// Authentic blue-bubble UI matched to Perennia's design tokens.
//
// Color choices:
//   - Outbound iMessage: Apple's authentic #007AFF gradient (so borrowers
//     recognize it instantly when read aloud / screenshotted).
//   - Outbound SMS: SMS green (#34C759 / #65C466 gradient) for visual parity
//     with native Messages.app.
//   - Inbound: glassmorphism over deep space dark to match Perennia chrome.
//   - Read receipts, delivery state, tapbacks: small DM Mono labels in the
//     Perennia electric-blue accent.

import { memo, useEffect, useMemo, useRef } from "react";
import type {
  ConversationMessage,
  ConversationThread,
  TapbackType,
} from "../types";

interface Props {
  thread: ConversationThread;
  remoteIsTyping?: boolean;
  /** Resolve a seat/user id to a display name (LO, processor, etc.) */
  resolveSenderName?: (seatId: number | null | undefined) => string;
}

const APPLE_BLUE = "#007AFF";
const APPLE_BLUE_DARK = "#0051D5";
const SMS_GREEN = "#34C759";
const SMS_GREEN_DARK = "#1F8E3A";
const PERENNIA_BLUE = "#7EB8F7";

export const BlueBubbleThread = memo(function BlueBubbleThread({
  thread,
  remoteIsTyping = false,
  resolveSenderName,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages or typing change
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [thread.messages.length, remoteIsTyping]);

  const grouped = useMemo(() => groupByDay(thread.messages), [thread.messages]);

  return (
    <div
      ref={scrollRef}
      className="flex h-full flex-col gap-1 overflow-y-auto px-4 pb-4 pt-2"
      style={{
        background: "linear-gradient(180deg, #060A10 0%, #0A1018 100%)",
        fontFamily: "var(--font-dm-sans, 'DM Sans', system-ui, sans-serif)",
      }}
    >
      {grouped.map((group) => (
        <div key={group.label} className="flex flex-col gap-1">
          <DayDivider label={group.label} />
          {group.messages.map((m, i) => {
            const prev = group.messages[i - 1];
            const next = group.messages[i + 1];
            const showTail = !next || next.direction !== m.direction;
            const isStart = !prev || prev.direction !== m.direction;
            return m.tapback ? null : (
              <Bubble
                key={m.id}
                message={m}
                tapbacks={collectTapbacks(thread.messages, m)}
                showTail={showTail}
                isGroupStart={isStart}
                resolveSenderName={resolveSenderName}
              />
            );
          })}
        </div>
      ))}
      {remoteIsTyping && <TypingBubble />}
    </div>
  );
});

// ---------------------------------------------------------------------------
// Bubble
// ---------------------------------------------------------------------------
interface BubbleProps {
  message: ConversationMessage;
  tapbacks: ConversationMessage[];
  showTail: boolean;
  isGroupStart: boolean;
  resolveSenderName?: (seatId: number | null | undefined) => string;
}

const Bubble = memo(function Bubble({
  message,
  tapbacks,
  showTail,
  isGroupStart,
  resolveSenderName,
}: BubbleProps) {
  const isOutbound = message.direction === "outbound";
  const isSms = message.channel === "sms";
  const senderName =
    isOutbound && resolveSenderName
      ? resolveSenderName(message.sender_seat_id)
      : null;

  const bubbleStyle: React.CSSProperties = isOutbound
    ? {
        background: isSms
          ? `linear-gradient(180deg, ${SMS_GREEN} 0%, ${SMS_GREEN_DARK} 100%)`
          : `linear-gradient(180deg, ${APPLE_BLUE} 0%, ${APPLE_BLUE_DARK} 100%)`,
        color: "#FFFFFF",
        boxShadow: `0 1px 1px rgba(0,0,0,0.18), 0 1px 12px ${
          isSms ? "rgba(52,199,89,0.18)" : "rgba(0,122,255,0.22)"
        }`,
      }
    : {
        background: "rgba(255,255,255,0.04)",
        color: "rgba(255,255,255,0.92)",
        border: "1px solid rgba(126,184,247,0.10)",
        backdropFilter: "blur(10px)",
      };

  const failed = message.status === "failed";

  return (
    <div
      className={`flex w-full flex-col ${
        isOutbound ? "items-end" : "items-start"
      } ${isGroupStart ? "mt-2" : "mt-0.5"}`}
    >
      {isOutbound && senderName && isGroupStart && (
        <span
          className="mb-0.5 mr-2 text-[10px]"
          style={{
            color: PERENNIA_BLUE,
            fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
            opacity: 0.7,
          }}
        >
          {senderName}
        </span>
      )}
      <div
        className="relative max-w-[75%] rounded-[18px] px-3.5 py-2 text-[15px] leading-snug"
        style={bubbleStyle}
      >
        {message.body && <span className="whitespace-pre-wrap">{message.body}</span>}
        {message.media_urls.length > 0 && (
          <div className="mt-1 flex flex-col gap-1">
            {message.media_urls.map((url, i) => (
              <img
                key={i}
                src={url}
                alt=""
                className="max-w-full rounded-xl"
                loading="lazy"
              />
            ))}
          </div>
        )}
        {showTail && (
          <BubbleTail
            side={isOutbound ? "right" : "left"}
            color={
              isOutbound
                ? isSms
                  ? SMS_GREEN_DARK
                  : APPLE_BLUE_DARK
                : "rgba(255,255,255,0.04)"
            }
          />
        )}
        {tapbacks.length > 0 && (
          <TapbackCluster tapbacks={tapbacks} side={isOutbound ? "right" : "left"} />
        )}
      </div>
      {failed && (
        <span
          className="mr-2 mt-1 text-[10px]"
          style={{
            color: "#FF6E6E",
            fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
          }}
        >
          ! Not delivered — tap to retry
        </span>
      )}
      {isOutbound && !failed && <ReadReceipt message={message} />}
    </div>
  );
});

// ---------------------------------------------------------------------------
function ReadReceipt({ message }: { message: ConversationMessage }) {
  const label = message.read_at
    ? `Read ${formatTime(message.read_at)}`
    : message.delivered_at
    ? "Delivered"
    : message.status === "sending" || message.status === "queued"
    ? "Sending…"
    : null;
  if (!label) return null;
  return (
    <span
      className="mr-2 mt-0.5 text-[10px]"
      style={{
        color: PERENNIA_BLUE,
        opacity: 0.65,
        fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
      }}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
function BubbleTail({
  side,
  color,
}: {
  side: "left" | "right";
  color: string;
}) {
  const common = "absolute bottom-0 h-3 w-3";
  return (
    <span
      className={common}
      style={{
        [side === "right" ? "right" : "left"]: -2,
        background: color,
        clipPath:
          side === "right"
            ? "polygon(0 0, 100% 100%, 0 100%)"
            : "polygon(100% 0, 100% 100%, 0 100%)",
      }}
      aria-hidden
    />
  );
}

// ---------------------------------------------------------------------------
const TAPBACK_GLYPH: Record<TapbackType, string> = {
  love: "❤️",
  like: "👍",
  dislike: "👎",
  laugh: "😂",
  emphasize: "‼️",
  question: "❓",
};

function TapbackCluster({
  tapbacks,
  side,
}: {
  tapbacks: ConversationMessage[];
  side: "left" | "right";
}) {
  return (
    <div
      className={`absolute -top-3 flex gap-0.5 ${
        side === "right" ? "-left-2" : "-right-2"
      }`}
    >
      {tapbacks.map((t) => (
        <span
          key={t.id}
          className="rounded-full px-1 py-0.5 text-[10px]"
          style={{
            background: "rgba(255,255,255,0.08)",
            border: "1px solid rgba(126,184,247,0.20)",
            backdropFilter: "blur(6px)",
          }}
        >
          {TAPBACK_GLYPH[t.tapback as TapbackType]}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
function TypingBubble() {
  return (
    <div className="mt-1 flex justify-start">
      <div
        className="flex items-center gap-1 rounded-[18px] px-3.5 py-2.5"
        style={{
          background: "rgba(255,255,255,0.04)",
          border: "1px solid rgba(126,184,247,0.10)",
          backdropFilter: "blur(10px)",
        }}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: "rgba(255,255,255,0.55)",
              animation: `imessage-dot 1.2s ease-in-out ${i * 0.2}s infinite`,
            }}
          />
        ))}
      </div>
      <style>{`
        @keyframes imessage-dot {
          0%, 80%, 100% { opacity: 0.3; transform: translateY(0); }
          40% { opacity: 1; transform: translateY(-2px); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
function DayDivider({ label }: { label: string }) {
  return (
    <div className="mb-1 mt-3 flex items-center justify-center">
      <span
        className="text-[10px] uppercase tracking-[0.2em]"
        style={{
          color: "rgba(255,255,255,0.35)",
          fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
        }}
      >
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
function groupByDay(
  messages: ConversationMessage[],
): { label: string; messages: ConversationMessage[] }[] {
  const groups = new Map<string, ConversationMessage[]>();
  for (const m of messages) {
    const d = new Date(m.created_at);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(m);
  }
  const out: { label: string; messages: ConversationMessage[] }[] = [];
  for (const [, msgs] of groups) {
    const d = new Date(msgs[0].created_at);
    out.push({ label: formatDayLabel(d), messages: msgs });
  }
  return out;
}

function formatDayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  if (sameDay(d, today)) {
    return `Today, ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  }
  if (sameDay(d, yesterday)) {
    return `Yesterday, ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  }
  return d.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function collectTapbacks(
  all: ConversationMessage[],
  m: ConversationMessage,
): ConversationMessage[] {
  if (!m.bb_message_guid) return [];
  return all.filter(
    (t) => !!t.tapback && t.associated_message_guid === m.bb_message_guid,
  );
}
