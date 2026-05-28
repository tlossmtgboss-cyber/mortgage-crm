// ConversationIntelligencePane — two-column call detail view
//
// Left column: diarized call transcript (speaker-by-speaker chat style)
// Right column: AI feedback — score, scorecard, coaching, suggestions
// Layout modeled after Follow Up Boss "Call Details" view.

import { useEffect, useState } from "react";
import { fetchReportsForLoan, fetchReportsForLead, fetchTranscript, fetchRecordingUrl, fetchStats } from "./cie-api";
import type {
  CIEReport,
  CIEStats,
  ReportListItem,
} from "./cie-types";

// ─────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────

export function useCIEReports(loanId: number | null, leadId: number | null = null) {
  const [items, setItems] = useState<ReportListItem[]>([]);
  const [stats, setStats] = useState<CIEStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loanId && !leadId) return;
    setLoading(true);
    const reportsFetch = loanId
      ? fetchReportsForLoan(loanId)
      : fetchReportsForLead(leadId!);
    const statsFetch = fetchStats({ loanId: loanId ?? undefined, leadId: leadId ?? undefined });
    Promise.all([reportsFetch, statsFetch])
      .then(([list, st]) => {
        setItems(list.items);
        setStats(st);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [loanId, leadId]);

  return { items, stats, loading, error };
}

// ─────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────

interface Props {
  loanId: number | null;
  leadId?: number | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────

export function ConversationIntelligencePane({ loanId, leadId }: Props) {
  const { items, stats, loading, error } = useCIEReports(loanId, leadId ?? null);
  const [selectedIdx, setSelectedIdx] = useState(0);

  if (!loanId && !leadId) {
    return (
      <div className="cie-view">
        <div className="pf-cf-empty">
          No lead or loan linked — call intelligence will appear here once calls are associated with this client.
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="cie-view">
        <div className="pf-cf-empty">Loading call intelligence...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="cie-view">
        <div className="pf-cf-empty">Error: {error}</div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="cie-view">
        <div className="pf-cf-empty">No calls analyzed yet.</div>
      </div>
    );
  }

  const selected = items[selectedIdx];
  const call = selected?.call;
  const report = selected?.report;

  return (
    <div className="cie-view">
      {/* Stats bar */}
      {stats && <StatsBar stats={stats} />}

      {/* Call selector */}
      {items.length > 1 && (
        <div className="cie-call-selector">
          {items.map((item, i) => (
            <button
              key={item.call.id}
              className={`cie-call-chip ${i === selectedIdx ? "cie-call-chip--active" : ""}`}
              onClick={() => setSelectedIdx(i)}
            >
              {formatDate(item.call.started_at)} · {item.call.duration_seconds ?? 0}s
              <StatusBadge status={item.call.processing_status} />
            </button>
          ))}
        </div>
      )}

      {/* Status gates */}
      {call.processing_status === "pending" && (
        <div className="pf-cf-empty">Analysis pending...</div>
      )}
      {call.processing_status === "too_short" && (
        <div className="pf-cf-empty">Call too short for analysis.</div>
      )}
      {call.processing_status === "failed" && (
        <div className="pf-cf-empty">Analysis failed. Will retry.</div>
      )}

      {/* Two-column call detail: transcript left, AI feedback right */}
      {report && call.processing_status === "completed" && (
        <CallDetailView report={report} call={call} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Two-column call detail
// Left: diarized transcript   Right: AI feedback + score
// ─────────────────────────────────────────────────────────────────────────

function CallDetailView({
  report,
  call,
}: {
  report: CIEReport;
  call: ReportListItem["call"];
}) {
  return (
    <div className="cie-detail">
      {/* Left: Call transcript (diarized) + recording */}
      <div className="cie-detail__left">
        <CallHeader call={call} />
        <RecordingBlock reportId={report.id} />
        <TranscriptBlock reportId={report.id} />
      </div>

      {/* Right: AI feedback — score + analysis */}
      <div className="cie-detail__right">
        <ScoreBanner report={report} />
        <ScorecardBlock report={report} />
        <SummaryBlock report={report} />
        {report.conversion_probability != null && (
          <ConversionBlock report={report} />
        )}
        <CoachingBlock report={report} />
        <OpportunitiesRisksBlock report={report} />
        <ObjectionsBlock report={report} />
        <ComplianceBlock report={report} />
        <TasksDraftsBlock report={report} />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Left column: Transcript
// ─────────────────────────────────────────────────────────────────────────

function CallHeader({ call }: { call: ReportListItem["call"] }) {
  const direction = call.direction === "inbound" ? "Inbound" : "Outbound";
  const duration = call.duration_seconds
    ? `${Math.floor(call.duration_seconds / 60)}m ${call.duration_seconds % 60}s`
    : null;

  return (
    <div className="cie-call-header">
      <div className="cie-call-header__row">
        <span className="cie-call-header__direction">{direction} Call</span>
        {duration && <span className="cie-call-header__duration">{duration}</span>}
        <span className="cie-call-header__provider">{call.provider}</span>
        <span className="cie-call-header__date">{formatDate(call.started_at)}</span>
      </div>
    </div>
  );
}

function RecordingBlock({ reportId }: { reportId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    fetchRecordingUrl(reportId)
      .then((r) => setUrl(r.recording_url))
      .catch(() => setUrl(null))
      .finally(() => setLoading(false));
  };

  return (
    <div className="cie-block cie-block--compact">
      {url ? (
        <audio controls src={url} className="cie-audio" />
      ) : (
        <button onClick={load} disabled={loading} className="cie-load-btn">
          {loading ? "Loading..." : "Load Recording"}
        </button>
      )}
    </div>
  );
}

interface TranscriptTurn {
  speaker: string;
  time: string;
  text: string;
  isLO: boolean;
}

function parseTranscript(raw: string): TranscriptTurn[] {
  const turns: TranscriptTurn[] = [];
  const lines = raw.split("\n");
  let current: TranscriptTurn | null = null;

  for (const line of lines) {
    const speakerMatch = line.match(/^\[?(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]m)?)\]?\s*[-–—]?\s*(.+?):\s*$/i)
      || line.match(/^(.+?)\s+(\d{1,2}:\d{2}(?:\s*[ap]m)?)\s*$/i);

    if (speakerMatch) {
      if (current && current.text.trim()) turns.push(current);
      const [, g1, g2] = speakerMatch;
      const hasTime = /\d{1,2}:\d{2}/.test(g1);
      const time = hasTime ? g1 : g2;
      const speaker = hasTime ? g2 : g1;
      const loKeywords = ["tim", "lo", "loan officer", "agent"];
      const isLO = loKeywords.some((k) => speaker.toLowerCase().includes(k));
      current = { speaker: speaker.trim(), time: time.trim(), text: "", isLO };
      continue;
    }

    if (current) {
      const trimmed = line.trim();
      if (trimmed) {
        current.text += (current.text ? " " : "") + trimmed;
      }
    } else if (line.trim()) {
      if (turns.length === 0) {
        current = { speaker: "", time: "", text: line.trim(), isLO: false };
      } else {
        const last = turns[turns.length - 1];
        last.text += " " + line.trim();
      }
    }
  }
  if (current && current.text.trim()) turns.push(current);
  return turns;
}

function TranscriptBlock({ reportId }: { reportId: string }) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoLoaded, setAutoLoaded] = useState(false);

  useEffect(() => {
    if (autoLoaded) return;
    setAutoLoaded(true);
    setLoading(true);
    fetchTranscript(reportId)
      .then((r) => setText(r.transcript))
      .catch(() => setText(null))
      .finally(() => setLoading(false));
  }, [reportId, autoLoaded]);

  if (loading) {
    return (
      <div className="cie-block cie-block--transcript">
        <h3 className="cie-block__title">Call Transcript</h3>
        <div className="pf-cf-empty" style={{ padding: "24px 0" }}>Loading transcript...</div>
      </div>
    );
  }

  if (text == null) {
    return (
      <div className="cie-block cie-block--transcript">
        <h3 className="cie-block__title">Call Transcript</h3>
        <div className="pf-cf-empty" style={{ padding: "24px 0" }}>Transcript not available.</div>
      </div>
    );
  }

  const turns = parseTranscript(text);
  const hasParsedSpeakers = turns.some((t) => t.speaker);

  return (
    <div className="cie-block cie-block--transcript">
      <h3 className="cie-block__title">Call Transcript</h3>
      <div className="cie-transcript-chat">
        {hasParsedSpeakers ? (
          turns.map((turn, i) => (
            <div key={i} className={`cie-turn ${turn.isLO ? "cie-turn--lo" : "cie-turn--borrower"}`}>
              <div className="cie-turn__header">
                <span className="cie-turn__speaker">{turn.speaker}</span>
                {turn.time && <span className="cie-turn__time">{turn.time}</span>}
              </div>
              <div className="cie-turn__text">{turn.text}</div>
            </div>
          ))
        ) : (
          <pre className="cie-transcript-raw">{text}</pre>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Right column: AI Feedback
// ─────────────────────────────────────────────────────────────────────────

function ScoreBanner({ report }: { report: CIEReport }) {
  const score = report.cis_composite != null ? (report.cis_composite / 10).toFixed(1) : null;
  const color = report.cis_composite != null
    ? report.cis_composite >= 80 ? "var(--pf-cf-success)" : report.cis_composite >= 60 ? "var(--pf-cf-warning)" : "var(--pf-cf-danger)"
    : "var(--pf-cf-text-tertiary)";

  return (
    <div className="cie-score-banner">
      <div className="cie-score-banner__circle" style={{ borderColor: color }}>
        <span className="cie-score-banner__value" style={{ color }}>
          {score ?? "--"}
        </span>
        <span className="cie-score-banner__max">/ 10</span>
      </div>
      <div className="cie-score-banner__label">AI Call Score</div>
    </div>
  );
}

function ScorecardBlock({ report }: { report: CIEReport }) {
  const dimensions = [
    { label: "Engagement", value: report.engagement_score },
    { label: "Info Quality", value: report.information_quality_score },
    { label: "Objection Handling", value: report.objection_handling_score },
    { label: "Compliance", value: report.compliance_score },
    { label: "Rapport", value: report.rapport_score },
    { label: "Closing", value: report.closing_effectiveness_score },
  ];

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Scorecard</h3>
      <div className="cie-score-bars">
        {dimensions.map((d) => (
          <div key={d.label} className="cie-score-row">
            <span className="cie-score-label">{d.label}</span>
            <div className="cie-score-track">
              <div
                className="cie-score-fill"
                style={{ width: `${d.value ?? 0}%` }}
              />
            </div>
            <span className="cie-score-num">{d.value != null ? (d.value / 10).toFixed(1) : "--"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SummaryBlock({ report }: { report: CIEReport }) {
  if (!report.summary && (!report.summary_bullets || report.summary_bullets.length === 0)) {
    return null;
  }

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Summary</h3>
      {report.summary && <p className="cie-block__text">{report.summary}</p>}
      {report.summary_bullets && report.summary_bullets.length > 0 && (
        <ul className="cie-block__bullets">
          {report.summary_bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
      {report.primary_intent && (
        <div className="cie-intent">
          Intent: <strong>{report.primary_intent.replace(/_/g, " ")}</strong>
          {report.intent_confidence != null && (
            <span className="cie-confidence">
              {(report.intent_confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function ConversionBlock({ report }: { report: CIEReport }) {
  const pct = ((report.conversion_probability ?? 0) * 100).toFixed(0);
  const low = report.conversion_ci_low != null ? (report.conversion_ci_low * 100).toFixed(0) : "?";
  const high = report.conversion_ci_high != null ? (report.conversion_ci_high * 100).toFixed(0) : "?";

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Conversion Probability</h3>
      <div className="cie-conversion">
        <span className="cie-conversion-value">{pct}%</span>
        <span className="cie-conversion-ci">CI: {low}% - {high}%</span>
      </div>
    </div>
  );
}

function CoachingBlock({ report }: { report: CIEReport }) {
  const suggestions = report.coaching_suggestions ?? [];
  if (suggestions.length === 0) return null;

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Coaching Suggestions</h3>
      {suggestions.map((s, i) => (
        <div key={i} className="cie-coaching">
          <strong>{s.area}</strong>
          <p>{s.suggestion}</p>
          {s.example && <p className="cie-coaching__example">{s.example}</p>}
        </div>
      ))}
    </div>
  );
}

function OpportunitiesRisksBlock({ report }: { report: CIEReport }) {
  const opps = report.opportunities ?? [];
  const risks = report.risks ?? [];
  if (opps.length === 0 && risks.length === 0) return null;

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Opportunities & Risks</h3>
      {opps.length > 0 && (
        <div style={{ marginBottom: risks.length > 0 ? 12 : 0 }}>
          <h4>Opportunities</h4>
          {opps.map((o, i) => (
            <div key={i} className="cie-card cie-card--opp">
              <strong>{o.label}</strong>
              <p>{o.description}</p>
              <span className={`cie-priority cie-priority--${o.priority}`}>{o.priority}</span>
            </div>
          ))}
        </div>
      )}
      {risks.length > 0 && (
        <div>
          <h4>Risks</h4>
          {risks.map((r, i) => (
            <div key={i} className="cie-card cie-card--risk">
              <strong>{r.label}</strong>
              <p>{r.description}</p>
              <span className={`cie-severity cie-severity--${r.severity}`}>{r.severity}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ObjectionsBlock({ report }: { report: CIEReport }) {
  const objections = report.objections ?? [];
  if (objections.length === 0) return null;

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Objections</h3>
      {objections.map((o, i) => (
        <div key={i} className="cie-objection">
          <div className="cie-objection__text">{o.objection}</div>
          {o.lo_response && <div className="cie-objection__response">LO: {o.lo_response}</div>}
          <span className={`cie-effectiveness cie-effectiveness--${o.effectiveness}`}>
            {o.effectiveness}
          </span>
        </div>
      ))}
    </div>
  );
}

function ComplianceBlock({ report }: { report: CIEReport }) {
  const flags = report.compliance_flags ?? [];
  if (flags.length === 0) return null;

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Compliance</h3>
      {flags.map((f, i) => (
        <div key={i} className={`cie-flag cie-flag--${f.severity}`}>
          <span className="cie-flag__type">{f.type.replace(/_/g, " ")}</span>
          <span className="cie-flag__msg">{f.message}</span>
        </div>
      ))}
    </div>
  );
}

function TasksDraftsBlock({ report }: { report: CIEReport }) {
  const tasks = report.generated_tasks ?? [];
  const drafts = report.draft_messages ?? [];
  if (tasks.length === 0 && drafts.length === 0) return null;

  return (
    <div className="cie-block">
      <h3 className="cie-block__title">Tasks & Drafts</h3>
      {tasks.length > 0 && (
        <div>
          <h4>Generated Tasks</h4>
          {tasks.map((t, i) => (
            <div key={i} className="cie-task">
              <span className={`cie-priority cie-priority--${t.priority}`}>{t.priority}</span>
              <span>{t.title}</span>
              <span className="cie-task__meta">{t.owner} · {t.due_days}d</span>
            </div>
          ))}
        </div>
      )}
      {drafts.length > 0 && (
        <div style={{ marginTop: tasks.length > 0 ? 12 : 0 }}>
          <h4>Draft Messages</h4>
          {drafts.map((d, i) => (
            <div key={i} className="cie-draft">
              <span className="cie-draft__channel">{d.channel}</span>
              <p>{d.body}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: CIEStats }) {
  return (
    <div className="cie-stats-bar">
      <span>{stats.total_calls} calls</span>
      <span>{stats.analyzed} analyzed</span>
      {stats.avg_cis != null && <span>Avg Score: {(stats.avg_cis / 10).toFixed(1)}/10</span>}
      {stats.avg_conversion != null && (
        <span>Avg Conv: {(stats.avg_conversion * 100).toFixed(0)}%</span>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "cie-badge--ok"
      : status === "failed"
        ? "cie-badge--err"
        : "cie-badge--pending";
  return <span className={`cie-badge ${cls}`}>{status}</span>;
}

function formatDate(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
