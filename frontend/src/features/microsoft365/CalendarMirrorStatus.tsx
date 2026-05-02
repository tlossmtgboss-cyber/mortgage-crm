/**
 * CalendarMirrorStatus.tsx
 *
 * Compact widget for settings/sidebar. Shows MS 365 account status,
 * subscription health, calendar sync stats, and connect/disconnect actions.
 */
import { useCallback, useEffect, useState } from "react";
import {
  microsoftApi,
  type CalendarSyncStatus,
  type MSAccountStatus,
  type SubscriptionKind,
} from "./api";

const SUBSCRIPTION_LABELS: Record<SubscriptionKind, string> = {
  calendar: "Calendar",
  email: "Email",
  teams_chats: "Teams chats",
};

export default function CalendarMirrorStatus() {
  const [account, setAccount] = useState<MSAccountStatus | null>(null);
  const [calStatus, setCalStatus] = useState<CalendarSyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const acc = (await microsoftApi.getAccount()) as MSAccountStatus | null;
      setAccount(acc);
      if (acc?.is_active) {
        const cs = (await microsoftApi.calendarStatus()) as CalendarSyncStatus;
        setCalStatus(cs);
      } else {
        setCalStatus(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleConnect = async () => {
    setBusy(true);
    try {
      const resp = (await microsoftApi.initOAuth()) as { authorization_url: string; state: string };
      window.location.href = resp.authorization_url;
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Disconnect Microsoft 365? Your CRM data stays — only sync stops.")) return;
    setBusy(true);
    try {
      await microsoftApi.disconnect();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="rounded-xl p-6"
      style={{
        background: "rgba(126, 184, 247, 0.04)",
        border: "1px solid rgba(126, 184, 247, 0.1)",
        backdropFilter: "blur(12px)",
        color: "#E6ECF4",
        fontFamily: '"DM Sans", system-ui, sans-serif',
      }}
    >
      <div className="mb-4 flex items-start justify-between">
        <div>
          <p
            className="mb-1 text-[10px] uppercase tracking-[0.18em]"
            style={{ color: "#7EB8F7", fontFamily: '"DM Mono", monospace' }}
          >
            Integration
          </p>
          <h3
            className="text-2xl font-light leading-none"
            style={{ fontFamily: '"Cormorant Garamond", serif' }}
          >
            Microsoft 365
          </h3>
        </div>
        <StatusDot connected={account?.is_active === true} />
      </div>

      {loading ? (
        <p className="text-xs" style={{ color: "rgba(230,236,244,0.4)", fontFamily: '"DM Mono", monospace' }}>
          Loading...
        </p>
      ) : !account ? (
        <NotConnected onConnect={handleConnect} busy={busy} />
      ) : !account.is_active ? (
        <ReconnectRequired
          upn={account.upn}
          lastError={account.last_error}
          onConnect={handleConnect}
          busy={busy}
        />
      ) : (
        <Connected account={account} calStatus={calStatus} onDisconnect={handleDisconnect} busy={busy} />
      )}
    </div>
  );
}

function StatusDot({ connected }: { connected: boolean }) {
  const color = connected ? "#7EF7B8" : "rgba(230,236,244,0.3)";
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{
        background: color,
        boxShadow: connected ? `0 0 8px ${color}` : "none",
      }}
      title={connected ? "Connected" : "Not connected"}
    />
  );
}

function NotConnected({ onConnect, busy }: { onConnect: () => void; busy: boolean }) {
  return (
    <div>
      <p className="text-sm" style={{ color: "rgba(230,236,244,0.7)" }}>
        Mirror your Outlook calendar into the CRM. Inbound emails and 1:1 Teams
        chats will appear in the Reconciliation tab, auto-matched to leads,
        loans, and partners.
      </p>
      <button
        onClick={onConnect}
        disabled={busy}
        className="mt-4 rounded-md px-4 py-2 text-sm transition-opacity disabled:opacity-50"
        style={{
          background: "#7EB8F7",
          color: "#060A10",
          fontFamily: '"DM Sans", sans-serif',
          fontWeight: 500,
        }}
      >
        {busy ? "Redirecting..." : "Connect Microsoft 365"}
      </button>
    </div>
  );
}

function ReconnectRequired({
  upn,
  lastError,
  onConnect,
  busy,
}: {
  upn: string;
  lastError: string | null;
  onConnect: () => void;
  busy: boolean;
}) {
  return (
    <div>
      <p
        className="mb-1 text-xs uppercase tracking-[0.15em]"
        style={{ color: "#F7B97E", fontFamily: '"DM Mono", monospace' }}
      >
        Reconnect required
      </p>
      <p className="text-sm" style={{ color: "rgba(230,236,244,0.7)" }}>
        Token for <strong>{upn}</strong> is no longer valid.
      </p>
      {lastError && (
        <p
          className="mt-2 truncate text-xs"
          style={{ color: "rgba(247, 185, 126, 0.7)", fontFamily: '"DM Mono", monospace' }}
        >
          {lastError}
        </p>
      )}
      <button
        onClick={onConnect}
        disabled={busy}
        className="mt-4 rounded-md px-4 py-2 text-sm"
        style={{
          background: "#7EB8F7",
          color: "#060A10",
          fontFamily: '"DM Sans", sans-serif',
          fontWeight: 500,
        }}
      >
        {busy ? "Redirecting..." : "Reconnect"}
      </button>
    </div>
  );
}

function Connected({
  account,
  calStatus,
  onDisconnect,
  busy,
}: {
  account: MSAccountStatus;
  calStatus: CalendarSyncStatus | null;
  onDisconnect: () => void;
  busy: boolean;
}) {
  return (
    <div>
      <p className="mb-1 text-sm" style={{ color: "rgba(230,236,244,0.85)" }}>
        {account.display_name || account.upn}
      </p>
      <p className="text-xs" style={{ color: "rgba(230,236,244,0.5)", fontFamily: '"DM Mono", monospace' }}>
        {account.upn}
      </p>

      <div className="mt-4 space-y-1.5 border-t border-white/5 pt-4">
        {(["calendar", "email", "teams_chats"] as SubscriptionKind[]).map((kind) => {
          const sub = account.subscriptions.find((s) => s.kind === kind);
          const healthy = sub && sub.failure_count < 3;
          return (
            <div key={kind} className="flex items-center justify-between text-xs">
              <span style={{ color: "rgba(230,236,244,0.7)" }}>
                {SUBSCRIPTION_LABELS[kind]}
              </span>
              <span
                style={{
                  fontFamily: '"DM Mono", monospace',
                  color: !sub ? "rgba(230,236,244,0.35)" : healthy ? "#7EF7B8" : "#F7B97E",
                }}
              >
                {!sub ? "—" : healthy ? "active" : `degraded (${sub.failure_count} failures)`}
              </span>
            </div>
          );
        })}
      </div>

      {calStatus && (
        <div className="mt-4 grid grid-cols-3 gap-3 border-t border-white/5 pt-4">
          <Stat label="Mapped" value={calStatus.total_mapped_events.toString()} />
          <Stat
            label="Last in"
            value={calStatus.last_inbound_sync_at ? formatRelative(calStatus.last_inbound_sync_at) : "—"}
          />
          <Stat
            label="Last out"
            value={calStatus.last_outbound_sync_at ? formatRelative(calStatus.last_outbound_sync_at) : "—"}
          />
        </div>
      )}

      <button
        onClick={onDisconnect}
        disabled={busy}
        className="mt-5 text-xs"
        style={{
          color: "rgba(230,236,244,0.45)",
          background: "transparent",
          fontFamily: '"DM Sans", sans-serif',
          textDecoration: "underline",
          textUnderlineOffset: "3px",
        }}
      >
        {busy ? "..." : "Disconnect"}
      </button>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        className="text-[9px] uppercase tracking-[0.18em]"
        style={{ color: "rgba(230,236,244,0.4)", fontFamily: '"DM Mono", monospace' }}
      >
        {label}
      </div>
      <div
        className="mt-0.5 truncate text-sm"
        style={{ color: "#E6ECF4", fontFamily: '"DM Mono", monospace' }}
      >
        {value}
      </div>
    </div>
  );
}

function formatRelative(iso: string): string {
  const diffSec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h`;
  return `${Math.floor(diffSec / 86400)}d`;
}
