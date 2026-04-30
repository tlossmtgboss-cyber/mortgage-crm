// Perennia iMessage — ChannelBadge
// Tiny pill that shows whether a thread is iMessage or SMS.

import { memo } from "react";
import type { Channel } from "../types";

interface Props {
  channel: Channel | null;
  imessageSupported: boolean | null;
  className?: string;
}

const PERENNIA_BLUE = "#7EB8F7";
const IMESSAGE_BLUE = "#007AFF";
const SMS_GREEN = "#34C759";

export const ChannelBadge = memo(function ChannelBadge({
  channel,
  imessageSupported,
  className = "",
}: Props) {
  const resolved: "imessage" | "sms" | "unknown" =
    channel === "imessage" || imessageSupported === true
      ? "imessage"
      : channel === "sms" || imessageSupported === false
      ? "sms"
      : "unknown";

  const label =
    resolved === "imessage"
      ? "iMessage"
      : resolved === "sms"
      ? "SMS"
      : "Detecting…";

  const dot =
    resolved === "imessage"
      ? IMESSAGE_BLUE
      : resolved === "sms"
      ? SMS_GREEN
      : PERENNIA_BLUE;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-medium tracking-wide uppercase ${className}`}
      style={{
        background: "rgba(126, 184, 247, 0.08)",
        border: "1px solid rgba(126, 184, 247, 0.18)",
        backdropFilter: "blur(8px)",
        color: "rgba(255,255,255,0.8)",
        fontFamily: "var(--font-dm-mono, 'DM Mono', monospace)",
      }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: dot, boxShadow: `0 0 6px ${dot}` }}
        aria-hidden
      />
      {label}
    </span>
  );
});
