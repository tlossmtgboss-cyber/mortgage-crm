/**
 * ReconciliationTab.tsx
 *
 * Microsoft 365 reconciliation tab. Lists inbound emails and 1:1 Teams chats
 * awaiting reconciliation, shows suggested CRM links with confidence, and lets
 * the user accept a suggestion, manually pick a record, or dismiss the item.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  microsoftApi,
  type EmailReconciliationItem,
  type ReconciliationLinkType,
  type ReconciliationListResponse,
  type SuggestedLink,
  type TeamsChatReconciliationItem,
} from "./api";

type TabKey = "emails" | "teams" | "all";

type AnyItem =
  | (EmailReconciliationItem & { _kind: "email" })
  | (TeamsChatReconciliationItem & { _kind: "teams" });

export default function ReconciliationTab() {
  const [data, setData] = useState<ReconciliationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabKey>("all");
  const [pickerOpen, setPickerOpen] = useState<{
    kind: "email" | "teams";
    id: number;
  } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await microsoftApi.listReconciliation({ limit: 100 });
      setData(resp as ReconciliationListResponse);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => clearInterval(interval);
  }, [refresh]);

  const items: AnyItem[] = useMemo(() => {
    if (!data) return [];
    const emails: AnyItem[] = data.emails.map((e) => ({ ...e, _kind: "email" }));
    const teams: AnyItem[] = data.teams_chats.map((t) => ({ ...t, _kind: "teams" }));
    if (tab === "emails") return emails;
    if (tab === "teams") return teams;
    return [...emails, ...teams].sort((a, b) => {
      const aDate = a._kind === "email" ? a.received_at : a.sent_at;
      const bDate = b._kind === "email" ? b.received_at : b.sent_at;
      return new Date(bDate).getTime() - new Date(aDate).getTime();
    });
  }, [data, tab]);

  const handleAccept = async (item: AnyItem, suggestion: SuggestedLink) => {
    if (item._kind === "email") {
      await microsoftApi.linkEmail(item.id, {
        link_type: suggestion.link_type,
        link_id: suggestion.link_id,
      });
    } else {
      await microsoftApi.linkTeamsMessage(item.id, {
        link_type: suggestion.link_type,
        link_id: suggestion.link_id,
      });
    }
    await refresh();
  };

  const handleDismiss = async (item: AnyItem) => {
    if (item._kind === "email") {
      await microsoftApi.dismissEmail(item.id);
      await refresh();
    }
  };

  const handleManualLink = async (
    item: AnyItem,
    link: { link_type: ReconciliationLinkType; link_id: number },
  ) => {
    if (item._kind === "email") {
      await microsoftApi.linkEmail(item.id, link);
    } else {
      await microsoftApi.linkTeamsMessage(item.id, link);
    }
    setPickerOpen(null);
    await refresh();
  };

  return (
    <div
      className="min-h-screen p-8"
      style={{
        background:
          "radial-gradient(ellipse at top, rgba(126, 184, 247, 0.04), transparent 60%), #060A10",
        color: "#E6ECF4",
        fontFamily: '"DM Sans", system-ui, sans-serif',
      }}
    >
      <Header
        totalUnmatched={data?.total_unmatched ?? 0}
        totalSuggested={data?.total_suggested ?? 0}
      />

      <Tabs
        active={tab}
        setActive={setTab}
        emailCount={data?.emails.length ?? 0}
        teamsCount={data?.teams_chats.length ?? 0}
      />

      <div className="mt-6 space-y-3">
        {loading && !data ? (
          <SkeletonList />
        ) : items.length === 0 ? (
          <EmptyState />
        ) : (
          items.map((item) => (
            <ItemCard
              key={`${item._kind}:${item.id}`}
              item={item}
              onAcceptSuggestion={(s) => handleAccept(item, s)}
              onDismiss={() => handleDismiss(item)}
              onPickRecord={() =>
                setPickerOpen({ kind: item._kind, id: item.id })
              }
            />
          ))
        )}
      </div>

      {pickerOpen && (
        <RecordPicker
          onCancel={() => setPickerOpen(null)}
          onSelect={(link) => {
            const target = items.find(
              (i) => i._kind === pickerOpen.kind && i.id === pickerOpen.id,
            );
            if (target) handleManualLink(target, link);
          }}
        />
      )}
    </div>
  );
}

function Header({
  totalUnmatched,
  totalSuggested,
}: {
  totalUnmatched: number;
  totalSuggested: number;
}) {
  return (
    <header className="flex items-end justify-between border-b border-white/5 pb-6">
      <div>
        <p
          className="mb-1 text-xs uppercase tracking-[0.18em]"
          style={{ color: "#7EB8F7", fontFamily: '"DM Mono", monospace' }}
        >
          Microsoft 365 / Inbox
        </p>
        <h1
          className="text-5xl font-light leading-none"
          style={{
            fontFamily: '"Cormorant Garamond", serif',
            letterSpacing: "-0.01em",
          }}
        >
          Reconciliation
        </h1>
      </div>
      <div className="flex gap-8">
        <Counter value={totalUnmatched} label="Unmatched" tone="warn" />
        <Counter value={totalSuggested} label="Suggested" tone="accent" />
      </div>
    </header>
  );
}

function Counter({
  value,
  label,
  tone,
}: {
  value: number;
  label: string;
  tone: "warn" | "accent";
}) {
  const color = tone === "warn" ? "#F7B97E" : "#7EB8F7";
  return (
    <div className="text-right">
      <div
        className="text-4xl font-light"
        style={{ fontFamily: '"Cormorant Garamond", serif', color }}
      >
        {value}
      </div>
      <div
        className="text-[10px] uppercase tracking-[0.22em]"
        style={{ color: "rgba(230, 236, 244, 0.5)", fontFamily: '"DM Mono", monospace' }}
      >
        {label}
      </div>
    </div>
  );
}

function Tabs({
  active,
  setActive,
  emailCount,
  teamsCount,
}: {
  active: TabKey;
  setActive: (t: TabKey) => void;
  emailCount: number;
  teamsCount: number;
}) {
  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: "all", label: "All", count: emailCount + teamsCount },
    { key: "emails", label: "Emails", count: emailCount },
    { key: "teams", label: "Teams Chats", count: teamsCount },
  ];
  return (
    <nav className="mt-8 flex gap-1">
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            className="rounded-md px-4 py-2 text-sm transition-all"
            style={{
              background: isActive
                ? "rgba(126, 184, 247, 0.12)"
                : "transparent",
              color: isActive ? "#7EB8F7" : "rgba(230, 236, 244, 0.6)",
              border: isActive
                ? "1px solid rgba(126, 184, 247, 0.3)"
                : "1px solid transparent",
              fontFamily: '"DM Sans", sans-serif',
            }}
          >
            {t.label}
            <span
              className="ml-2 text-xs"
              style={{ fontFamily: '"DM Mono", monospace', opacity: 0.6 }}
            >
              {t.count}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function ItemCard({
  item,
  onAcceptSuggestion,
  onDismiss,
  onPickRecord,
}: {
  item: AnyItem;
  onAcceptSuggestion: (s: SuggestedLink) => void;
  onDismiss: () => void;
  onPickRecord: () => void;
}) {
  const isEmail = item._kind === "email";
  const subject = isEmail ? item.subject : item.chat_topic ?? "Direct message";
  const senderLine = item.sender_name
    ? `${item.sender_name} • ${item.sender_email}`
    : item.sender_email;
  const timestamp = isEmail ? item.received_at : item.sent_at;
  const preview = isEmail ? item.body_preview : item.body_text;

  const top = item.suggested_links?.[0];

  return (
    <article
      className="group relative rounded-xl p-5 transition-all"
      style={{
        background: "rgba(126, 184, 247, 0.04)",
        border: "1px solid rgba(126, 184, 247, 0.08)",
        backdropFilter: "blur(12px)",
      }}
    >
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <KindBadge kind={item._kind} />
            <StatusPill status={item.status} confidence={item.match_confidence} />
            <span
              className="text-xs"
              style={{
                color: "rgba(230, 236, 244, 0.4)",
                fontFamily: '"DM Mono", monospace',
              }}
            >
              {formatRelative(timestamp)}
            </span>
          </div>
          <h3
            className="truncate text-lg font-normal"
            style={{
              fontFamily: '"Cormorant Garamond", serif',
              color: "#E6ECF4",
            }}
            title={subject}
          >
            {subject || "(no subject)"}
          </h3>
          <p
            className="mt-0.5 truncate text-xs"
            style={{
              color: "rgba(230, 236, 244, 0.55)",
              fontFamily: '"DM Mono", monospace',
            }}
          >
            {senderLine}
          </p>
          {preview && (
            <p
              className="mt-2 line-clamp-2 text-sm"
              style={{ color: "rgba(230, 236, 244, 0.7)" }}
            >
              {preview}
            </p>
          )}
        </div>

        {item.web_link && (
          <a
            href={item.web_link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0 text-xs"
            style={{
              color: "rgba(126, 184, 247, 0.7)",
              fontFamily: '"DM Mono", monospace',
            }}
          >
            Open in {isEmail ? "Outlook" : "Teams"} &#8599;
          </a>
        )}
      </div>

      {item.suggested_links && item.suggested_links.length > 0 && (
        <div className="mt-4 space-y-2">
          {item.suggested_links.slice(0, 3).map((s, idx) => (
            <SuggestionRow
              key={`${s.link_type}:${s.link_id}`}
              suggestion={s}
              isPrimary={idx === 0 && s === top}
              onAccept={() => onAcceptSuggestion(s)}
            />
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center gap-2">
        <button
          onClick={onPickRecord}
          className="rounded-md border px-3 py-1.5 text-xs transition-colors"
          style={{
            borderColor: "rgba(126, 184, 247, 0.25)",
            color: "#7EB8F7",
            background: "transparent",
            fontFamily: '"DM Sans", sans-serif',
          }}
        >
          Link manually...
        </button>
        {isEmail && (
          <button
            onClick={onDismiss}
            className="rounded-md px-3 py-1.5 text-xs transition-colors"
            style={{
              color: "rgba(230, 236, 244, 0.45)",
              background: "transparent",
              fontFamily: '"DM Sans", sans-serif',
            }}
          >
            Dismiss
          </button>
        )}
      </div>
    </article>
  );
}

function KindBadge({ kind }: { kind: "email" | "teams" }) {
  const label = kind === "email" ? "EMAIL" : "TEAMS";
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[9px] tracking-[0.15em]"
      style={{
        background: "rgba(126, 184, 247, 0.08)",
        color: "rgba(126, 184, 247, 0.85)",
        fontFamily: '"DM Mono", monospace',
        letterSpacing: "0.18em",
      }}
    >
      {label}
    </span>
  );
}

function StatusPill({ status, confidence }: { status: string; confidence: number | null }) {
  const palette: Record<string, { bg: string; fg: string; label: string }> = {
    unmatched: { bg: "rgba(247, 185, 126, 0.08)", fg: "#F7B97E", label: "Unmatched" },
    suggested: { bg: "rgba(126, 184, 247, 0.1)", fg: "#7EB8F7", label: "Suggested" },
    auto_linked: { bg: "rgba(126, 247, 184, 0.08)", fg: "#7EF7B8", label: "Auto-linked" },
    manually_linked: { bg: "rgba(126, 247, 184, 0.08)", fg: "#7EF7B8", label: "Linked" },
    dismissed: { bg: "rgba(230, 236, 244, 0.05)", fg: "rgba(230, 236, 244, 0.4)", label: "Dismissed" },
  };
  const p = palette[status] || palette.unmatched;
  const conf = confidence != null ? ` · ${Math.round(confidence * 100)}%` : "";
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px]"
      style={{ background: p.bg, color: p.fg, fontFamily: '"DM Mono", monospace' }}
    >
      {p.label}{conf}
    </span>
  );
}

function SuggestionRow({
  suggestion,
  isPrimary,
  onAccept,
}: {
  suggestion: SuggestedLink;
  isPrimary: boolean;
  onAccept: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between rounded-md px-3 py-2"
      style={{
        background: isPrimary ? "rgba(126, 184, 247, 0.08)" : "rgba(126, 184, 247, 0.03)",
        border: isPrimary ? "1px solid rgba(126, 184, 247, 0.25)" : "1px solid transparent",
      }}
    >
      <div className="min-w-0 flex-1">
        <div
          className="text-[10px] uppercase tracking-[0.15em]"
          style={{ color: "rgba(230, 236, 244, 0.5)", fontFamily: '"DM Mono", monospace' }}
        >
          {suggestion.link_type} &middot; {suggestion.strategy} &middot; {Math.round(suggestion.confidence * 100)}%
        </div>
        <div className="mt-0.5 truncate text-sm" style={{ color: "#E6ECF4" }} title={suggestion.label}>
          {suggestion.label}
        </div>
      </div>
      <button
        onClick={onAccept}
        className="ml-3 flex-shrink-0 rounded px-3 py-1 text-xs transition-colors"
        style={{
          background: isPrimary ? "#7EB8F7" : "rgba(126, 184, 247, 0.1)",
          color: isPrimary ? "#060A10" : "#7EB8F7",
          fontFamily: '"DM Sans", sans-serif',
          fontWeight: 500,
        }}
      >
        Link
      </button>
    </div>
  );
}

function SkeletonList() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-32 rounded-xl"
          style={{
            background: "rgba(126, 184, 247, 0.03)",
            border: "1px solid rgba(126, 184, 247, 0.06)",
            animation: `pulse 2s ease-in-out ${i * 0.1}s infinite`,
          }}
        />
      ))}
      <style>{`@keyframes pulse { 0%, 100% { opacity: 0.5 } 50% { opacity: 1 } }`}</style>
    </>
  );
}

function EmptyState() {
  return (
    <div
      className="rounded-xl py-16 text-center"
      style={{
        background: "rgba(126, 184, 247, 0.02)",
        border: "1px solid rgba(126, 184, 247, 0.06)",
      }}
    >
      <h3
        className="text-2xl font-light"
        style={{ fontFamily: '"Cormorant Garamond", serif', color: "rgba(230, 236, 244, 0.7)" }}
      >
        Inbox is reconciled.
      </h3>
      <p
        className="mt-2 text-xs"
        style={{ color: "rgba(230, 236, 244, 0.4)", fontFamily: '"DM Mono", monospace' }}
      >
        Nothing pending — new items will appear here as they arrive.
      </p>
    </div>
  );
}

function RecordPicker({
  onSelect,
  onCancel,
}: {
  onSelect: (link: { link_type: ReconciliationLinkType; link_id: number }) => void;
  onCancel: () => void;
}) {
  const [type, setType] = useState<ReconciliationLinkType>("lead");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ id: number; label: string }[]>([]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const resp = await fetch(
          `/api/v1/search/${type}?q=${encodeURIComponent(query)}&limit=10`,
        );
        if (resp.ok) setResults(await resp.json());
      } catch {
        /* ignore */
      }
    }, 200);
    return () => clearTimeout(t);
  }, [query, type]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(6, 10, 16, 0.85)" }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-xl p-6"
        style={{
          background: "#0B1018",
          border: "1px solid rgba(126, 184, 247, 0.2)",
          boxShadow: "0 24px 48px rgba(0,0,0,0.6)",
        }}
      >
        <h2
          className="mb-4 text-2xl font-light"
          style={{ fontFamily: '"Cormorant Garamond", serif', color: "#E6ECF4" }}
        >
          Link to a record
        </h2>

        <div className="mb-3 flex gap-1">
          {(["lead", "loan", "partner"] as ReconciliationLinkType[]).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className="rounded px-3 py-1 text-xs"
              style={{
                background: t === type ? "rgba(126, 184, 247, 0.15)" : "transparent",
                color: t === type ? "#7EB8F7" : "rgba(230,236,244,0.5)",
                border: t === type ? "1px solid rgba(126, 184, 247, 0.3)" : "1px solid transparent",
                fontFamily: '"DM Mono", monospace',
                textTransform: "uppercase",
                letterSpacing: "0.15em",
              }}
            >
              {t}
            </button>
          ))}
        </div>

        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${type}s...`}
          className="w-full rounded-md px-3 py-2 outline-none"
          style={{
            background: "rgba(126, 184, 247, 0.05)",
            border: "1px solid rgba(126, 184, 247, 0.15)",
            color: "#E6ECF4",
            fontFamily: '"DM Sans", sans-serif',
          }}
        />

        <div className="mt-3 max-h-64 overflow-y-auto">
          {results.map((r) => (
            <button
              key={r.id}
              onClick={() => onSelect({ link_type: type, link_id: r.id })}
              className="block w-full rounded-md px-3 py-2 text-left text-sm transition-colors"
              style={{ background: "transparent", color: "#E6ECF4", fontFamily: '"DM Sans", sans-serif' }}
              onMouseOver={(e) => (e.currentTarget.style.background = "rgba(126, 184, 247, 0.06)")}
              onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {r.label}
            </button>
          ))}
          {query && results.length === 0 && (
            <p
              className="px-3 py-2 text-xs"
              style={{ color: "rgba(230,236,244,0.4)", fontFamily: '"DM Mono", monospace' }}
            >
              No matches.
            </p>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded px-3 py-1.5 text-xs"
            style={{ color: "rgba(230,236,244,0.5)", fontFamily: '"DM Sans", sans-serif' }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}
