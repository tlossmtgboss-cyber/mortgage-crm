/**
 * AIActivityTab.tsx
 * Perennia AI — Client Profile AI Activity Tab
 *
 * Drop into any client/loan profile page as:
 *   <AIActivityTab loanId={loan.id} borrowerName={loan.borrower_name} loanNumber={loan.loan_number} loanAmount={loan.loan_amount} loanStatus={loan.status} />
 *
 * Backend contract:
 *   GET /api/loans/:loanId/ai-activity
 *   Returns: AIActivityEvent[]
 *
 * Install deps (if not already present):
 *   npm install lucide-react
 */

import React, { useState, useEffect, useCallback } from "react";

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

export type AgentType =
  | "guidelines"
  | "deal-breaker"
  | "call-intel"
  | "marketing"
  | "bulletin"
  | "smart-docs"
  | "turn-down"
  | "aria"
  | "underwriting"
  | "lead-assignment";

export type OutcomeType =
  | "success"
  | "warning"
  | "critical"
  | "info"
  | "pending";

export interface AIActivityEvent {
  id: string;
  agent_type: AgentType;
  agent_label: string;
  action_title: string;
  summary: string;
  outcome: OutcomeType;
  outcome_label: string;
  created_at: string; // ISO string
  metadata?: Record<string, unknown>;
  detail_sections?: DetailSection[];
  stats?: StatItem[];
  is_live?: boolean;
}

interface DetailSection {
  label: string;
  content: string;
}

interface StatItem {
  value: string;
  label: string;
}

interface DayGroup {
  label: string;
  events: AIActivityEvent[];
}

// ─────────────────────────────────────────────
// Mock data — replace with real API call
// ─────────────────────────────────────────────

const MOCK_EVENTS: AIActivityEvent[] = [
  {
    id: "evt-001",
    agent_type: "call-intel",
    agent_label: "Call Intelligence",
    action_title: "Analyzed 18-min call — identified 3 action items",
    summary:
      "Borrower expressed concern about rate lock expiration. Agent extracted commitments: LO to send updated rate sheet by EOD, schedule appraisal follow-up, confirm employment verification receipt.",
    outcome: "success",
    outcome_label: "3 Tasks Created",
    created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    is_live: true,
    stats: [
      { value: "94%", label: "Sentiment" },
      { value: "3", label: "Action Items" },
      { value: "18:22", label: "Duration" },
    ],
    detail_sections: [
      {
        label: "Key Topics Detected",
        content:
          "Rate lock expiration · Appraisal scheduling · Employment verification · Closing timeline concerns",
      },
      {
        label: "Auto-Created Tasks",
        content:
          "1. Send updated rate sheet to borrower by EOD\n2. Schedule appraisal follow-up call for Wed 4/8\n3. Confirm receipt of employment verification docs",
      },
    ],
  },
  {
    id: "evt-002",
    agent_type: "deal-breaker",
    agent_label: "Deal Breaker Radar",
    action_title: "Flagged DTI risk — ratio at 43.2%, approaching limit",
    summary:
      "Updated income analysis triggered a re-evaluation. Conventional conforming DTI cap of 45% leaves 1.8% margin. Agent recommends verifying all non-recurring debt and reviewing co-borrower option before underwriting submission.",
    outcome: "warning",
    outcome_label: "Flagged for Review",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 3).toISOString(),
    stats: [
      { value: "43.2%", label: "Current DTI" },
      { value: "45.0%", label: "DTI Cap" },
      { value: "1.8%", label: "Margin" },
    ],
    detail_sections: [
      {
        label: "Agent Reasoning",
        content:
          "Base income: $9,200/mo · Monthly obligations: $3,974 · DTI: 43.2%\nConventional limit (Fannie DU): 45.0% · Buffer: $165/mo\n\nRisk factors: New car payment added 11/2025, student loan IDR payment increasing Q2 2026",
      },
      {
        label: "Recommended Actions",
        content:
          "1. Verify $340 auto payment — confirm payoff date (possibly <10 months)\n2. Explore co-borrower addition if needed\n3. Pull AUS before final submission",
      },
    ],
  },
  {
    id: "evt-003",
    agent_type: "guidelines",
    agent_label: "Guidelines Agent",
    action_title: "Answered LO query — Conventional gift fund eligibility",
    summary:
      "LO asked whether gift funds can cover the full down payment on a 90% LTV conventional loan. Agent retrieved Fannie Mae B3-4.3-04 and confirmed: gifts allowed for primary residence, donor relationship documented, no repayment requirement verified.",
    outcome: "info",
    outcome_label: "Guideline Cited",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 22).toISOString(),
    stats: [
      { value: "98%", label: "Confidence" },
      { value: "3", label: "Sources" },
      { value: "1.2s", label: "Latency" },
    ],
    detail_sections: [
      {
        label: "Sources Queried",
        content:
          "Fannie Mae Selling Guide · Freddie Mac Single-Family Guide · Lender overlay database",
      },
      {
        label: "Relevant Guideline",
        content:
          "Per Fannie B3-4.3-04: Gifts from relatives acceptable for primary 1-unit. 90% LTV — no minimum borrower contribution required. Letter of gift required; no repayment terms permitted. Lender overlay: none applicable for this investor.",
      },
    ],
  },
  {
    id: "evt-004",
    agent_type: "smart-docs",
    agent_label: "Smart Docs",
    action_title: "Rejected 2 documents — screenshot detected, stale paystub",
    summary:
      "Borrower submitted bank statement via mobile upload. Agent flagged document 1 as a screen capture (metadata inconsistent with native PDF) and document 2 as a paystub dated 67 days ago, exceeding the 60-day freshness threshold.",
    outcome: "critical",
    outcome_label: "Action Required",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 25).toISOString(),
    stats: [
      { value: "2", label: "Rejected" },
      { value: "1", label: "Accepted" },
      { value: "67d", label: "Doc Age" },
    ],
    detail_sections: [
      {
        label: "Rejection Log",
        content:
          "Doc 1: Chase_Statement_Feb.pdf — FAIL: Screenshot metadata detected. Action: Borrower notified via portal message.\n\nDoc 2: Paystub_Jan30.pdf — FAIL: Date 01/30/2026 exceeds 60-day freshness rule. Action: Borrower requested to resubmit current pay period.",
      },
    ],
  },
  {
    id: "evt-005",
    agent_type: "bulletin",
    agent_label: "Bulletin Ingestion",
    action_title: "Flagged loan impact — Fannie Mae SEL-2026-03 affects this file",
    summary:
      "New Fannie Mae selling guide bulletin published. Agent assessed all 41 active pipeline loans and flagged this file — updated student loan payment calculation methodology may affect qualifying income by approximately -$180/mo.",
    outcome: "warning",
    outcome_label: "Pipeline Alert",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 28).toISOString(),
    detail_sections: [
      {
        label: "Impact Summary",
        content:
          "Effective Date: May 1, 2026\nChange: IDR student loan payment calculation — must use 1% of balance if payment < 1% regardless of IBR plan\nImpact on this file: Qualifying payment increases from $0 → ~$180/mo\nNew DTI projection: 45.1% (over limit by 0.1%)",
      },
      {
        label: "Recommended Action",
        content:
          "Submit to underwriting before May 1 or re-evaluate qualifying with updated DTI. Consult Deal Breaker Radar output from today.",
      },
    ],
  },
  {
    id: "evt-006",
    agent_type: "marketing",
    agent_label: "Marketing Agent",
    action_title: "Sent personalized rate lock expiration reminder",
    summary:
      "Auto-triggered 14-day pre-expiration email sequence. Agent personalized copy with borrower name, property address, and current estimated closing date. Email delivered; open confirmed 10:47 AM.",
    outcome: "success",
    outcome_label: "Opened ✓",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 50).toISOString(),
    stats: [
      { value: "100%", label: "Delivered" },
      { value: "1", label: "Opens" },
      { value: "4/17", label: "Lock Exp." },
    ],
  },
  {
    id: "evt-007",
    agent_type: "guidelines",
    agent_label: "Guidelines Agent",
    action_title: "Proactively flagged — investor overlay requires additional gift documentation",
    summary:
      "Following gift fund approval query, agent cross-referenced lender overlay database and identified that this file's investor (UWM) requires a bank withdrawal verification letter in addition to the standard gift letter.",
    outcome: "warning",
    outcome_label: "Overlay Found",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 52).toISOString(),
    detail_sections: [
      {
        label: "Overlay Detail",
        content:
          "Investor: UWM (United Wholesale Mortgage)\nRequirement: Bank withdrawal letter showing funds leaving donor account + gift letter\nNot required by Fannie Mae base guidelines — UWM-specific overlay only\nStatus: Task created for LO to collect from borrower",
      },
    ],
  },
  {
    id: "evt-008",
    agent_type: "underwriting",
    agent_label: "AI Operations Manager",
    action_title: "SLA alert — appraisal ordered, 3 days past target",
    summary:
      "Appraisal was ordered on 3/29. Internal SLA target for receipt is 7 business days. As of today (4/5) the file is 3 days past target. Agent escalated to processing team and added pipeline flag.",
    outcome: "warning",
    outcome_label: "SLA Breached",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 72).toISOString(),
    stats: [
      { value: "10d", label: "Days Out" },
      { value: "7d", label: "SLA Target" },
      { value: "+3d", label: "Overdue" },
    ],
    detail_sections: [
      {
        label: "Escalation Log",
        content:
          "04/02: Auto-reminder sent to appraisal vendor\n04/04: Second reminder + processor notification\n04/05: SLA breach escalated to ops manager\nVendor response: ETA confirmed 04/07",
      },
    ],
  },
];

// ─────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────

const AGENT_CONFIG: Record<
  AgentType,
  { color: string; bgColor: string; borderColor: string; icon: string; accentHex: string }
> = {
  guidelines:      { color: "#1D6FCC", bgColor: "#EFF6FF", borderColor: "#BFDBFE", icon: "📐", accentHex: "#1D6FCC" },
  "deal-breaker":  { color: "#DC2626", bgColor: "#FEF2F2", borderColor: "#FECACA", icon: "🔍", accentHex: "#DC2626" },
  "call-intel":    { color: "#059669", bgColor: "#ECFDF5", borderColor: "#A7F3D0", icon: "🎙", accentHex: "#059669" },
  marketing:       { color: "#7C3AED", bgColor: "#F5F3FF", borderColor: "#DDD6FE", icon: "✉️", accentHex: "#7C3AED" },
  bulletin:        { color: "#D97706", bgColor: "#FFFBEB", borderColor: "#FDE68A", icon: "📡", accentHex: "#D97706" },
  "smart-docs":    { color: "#0891B2", bgColor: "#ECFEFF", borderColor: "#A5F3FC", icon: "📄", accentHex: "#0891B2" },
  "turn-down":     { color: "#EA580C", bgColor: "#FFF7ED", borderColor: "#FED7AA", icon: "⛔", accentHex: "#EA580C" },
  aria:            { color: "#1D6FCC", bgColor: "#EFF6FF", borderColor: "#BFDBFE", icon: "✦", accentHex: "#1D6FCC" },
  underwriting:    { color: "#475569", bgColor: "#F8FAFC", borderColor: "#CBD5E1", icon: "⚖️", accentHex: "#475569" },
  "lead-assignment":{ color: "#0891B2", bgColor: "#ECFEFF", borderColor: "#A5F3FC", icon: "👤", accentHex: "#0891B2" },
};

const OUTCOME_CONFIG: Record<
  OutcomeType,
  { color: string; bgColor: string; borderColor: string }
> = {
  success: { color: "#059669", bgColor: "#ECFDF5", borderColor: "#A7F3D0" },
  warning: { color: "#D97706", bgColor: "#FFFBEB", borderColor: "#FDE68A" },
  critical: { color: "#DC2626", bgColor: "#FEF2F2", borderColor: "#FECACA" },
  info:    { color: "#1D6FCC", bgColor: "#EFF6FF", borderColor: "#BFDBFE" },
  pending: { color: "#64748B", bgColor: "#F8FAFC", borderColor: "#CBD5E1" },
};

const ALL_AGENT_TYPES: AgentType[] = [
  "guidelines", "deal-breaker", "call-intel", "marketing",
  "bulletin", "smart-docs", "turn-down", "underwriting",
];

const AGENT_FILTER_LABELS: Partial<Record<AgentType, string>> = {
  guidelines: "Guidelines",
  "deal-breaker": "Deal Breaker",
  "call-intel": "Call Intel",
  marketing: "Marketing",
  bulletin: "Bulletins",
  "smart-docs": "Smart Docs",
  "turn-down": "Turn Down",
  underwriting: "Operations",
};

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function groupEventsByDay(events: AIActivityEvent[]): DayGroup[] {
  const groups: Record<string, AIActivityEvent[]> = {};
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  events.forEach((event) => {
    const d = new Date(event.created_at);
    const isToday = d.toDateString() === today.toDateString();
    const isYesterday = d.toDateString() === yesterday.toDateString();
    const label = isToday
      ? `Today · ${d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`
      : isYesterday
      ? `Yesterday · ${d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`
      : d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

    if (!groups[label]) groups[label] = [];
    groups[label].push(event);
  });

  return Object.entries(groups).map(([label, evts]) => ({ label, events: evts }));
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
}

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

const OutcomePill: React.FC<{ outcome: OutcomeType; label: string }> = ({ outcome, label }) => {
  const cfg = OUTCOME_CONFIG[outcome];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        borderRadius: 20,
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "'DM Mono', monospace",
        letterSpacing: "0.04em",
        color: cfg.color,
        background: cfg.bgColor,
        border: `1px solid ${cfg.borderColor}`,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
};

const MetaTag: React.FC<{ label: string; color: string; bg: string; border: string }> = ({
  label, color, bg, border,
}) => (
  <span
    style={{
      display: "inline-flex",
      padding: "2px 8px",
      borderRadius: 4,
      fontSize: 10,
      fontFamily: "'DM Mono', monospace",
      letterSpacing: "0.04em",
      color,
      background: bg,
      border: `1px solid ${border}`,
    }}
  >
    {label}
  </span>
);

const StatBlock: React.FC<{ stats: StatItem[]; accentColor: string }> = ({ stats, accentColor }) => (
  <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
    {stats.map((s, i) => (
      <div
        key={i}
        style={{
          flex: 1,
          background: "#F8FAFC",
          border: "1px solid #E2E8F0",
          borderRadius: 8,
          padding: "10px 12px",
          textAlign: "center",
        }}
      >
        <span
          style={{
            display: "block",
            fontFamily: "'Cormorant Garamond', serif",
            fontSize: 22,
            fontWeight: 600,
            color: accentColor,
            lineHeight: 1.2,
          }}
        >
          {s.value}
        </span>
        <span
          style={{
            display: "block",
            fontFamily: "'DM Mono', monospace",
            fontSize: 9,
            color: "#94A3B8",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            marginTop: 2,
          }}
        >
          {s.label}
        </span>
      </div>
    ))}
  </div>
);

// ─────────────────────────────────────────────
// Agent-specific detail content
// ─────────────────────────────────────────────

const AGENT_DETAIL_LABELS: Record<AgentType, string> = {
  "call-intel": "View Call Intelligence",
  "deal-breaker": "View Risk Analysis",
  guidelines: "View Guideline Details",
  "smart-docs": "View Document Review",
  bulletin: "View Bulletin Impact",
  marketing: "View Campaign Details",
  "turn-down": "View Turn-Down Analysis",
  aria: "View Aria Details",
  underwriting: "View Operations Detail",
  "lead-assignment": "View Assignment Details",
};

const DetailModal: React.FC<{
  event: AIActivityEvent;
  onClose: () => void;
}> = ({ event, onClose }) => {
  const agentCfg = AGENT_CONFIG[event.agent_type] ?? AGENT_CONFIG.guidelines;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(15, 23, 42, 0.5)",
        backdropFilter: "blur(4px)",
        animation: "fadeSlide 0.2s ease both",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          width: "min(720px, 92vw)",
          maxHeight: "85vh",
          overflowY: "auto",
          background: "#FFFFFF",
          borderRadius: 14,
          boxShadow: "0 25px 60px rgba(0,0,0,0.18)",
          position: "relative",
        }}
      >
        {/* Accent bar top */}
        <div style={{ height: 4, background: agentCfg.accentHex, borderRadius: "14px 14px 0 0" }} />

        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: 16,
            right: 16,
            width: 32,
            height: 32,
            borderRadius: "50%",
            border: "1px solid #E2E8F0",
            background: "#F8FAFC",
            color: "#64748B",
            fontSize: 16,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 2,
          }}
        >
          ✕
        </button>

        {/* Header */}
        <div style={{ padding: "24px 28px 0" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: "50%",
                background: agentCfg.bgColor,
                border: `2px solid ${agentCfg.borderColor}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 18,
                flexShrink: 0,
              }}
            >
              {agentCfg.icon}
            </div>
            <div>
              <div
                style={{
                  fontFamily: "'DM Mono', monospace",
                  fontSize: 10,
                  fontWeight: 500,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: agentCfg.color,
                  marginBottom: 2,
                }}
              >
                {event.agent_label}
              </div>
              <div
                style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontSize: 20,
                  fontWeight: 600,
                  color: "#0F172A",
                  lineHeight: 1.3,
                }}
              >
                {event.action_title}
              </div>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginTop: 12,
              marginBottom: 4,
            }}
          >
            <OutcomePill outcome={event.outcome} label={event.outcome_label} />
            <span
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: 10,
                color: "#94A3B8",
                letterSpacing: "0.04em",
              }}
            >
              {new Date(event.created_at).toLocaleString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "numeric",
                minute: "2-digit",
                hour12: true,
              })}
            </span>
            {event.is_live && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "2px 8px",
                  borderRadius: 10,
                  background: "#ECFDF5",
                  border: "1px solid #A7F3D0",
                  fontSize: 10,
                  fontFamily: "'DM Mono', monospace",
                  color: "#059669",
                }}
              >
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#059669", animation: "pulse 2s infinite" }} />
                LIVE
              </span>
            )}
          </div>
        </div>

        {/* Divider */}
        <div style={{ margin: "16px 28px", borderTop: "1px solid #F1F5F9" }} />

        {/* Body */}
        <div style={{ padding: "0 28px 28px" }}>
          {/* Summary */}
          <div style={{ marginBottom: 20 }}>
            <div
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: 9,
                textTransform: "uppercase",
                letterSpacing: "0.12em",
                color: "#94A3B8",
                marginBottom: 8,
              }}
            >
              Summary
            </div>
            <p
              style={{
                fontSize: 13,
                color: "#334155",
                lineHeight: 1.75,
                margin: 0,
              }}
            >
              {event.summary}
            </p>
          </div>

          {/* Stats — larger in modal */}
          {event.stats && (
            <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
              {event.stats.map((s, i) => (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    background: "#F8FAFC",
                    border: "1px solid #E2E8F0",
                    borderRadius: 10,
                    padding: "14px 16px",
                    textAlign: "center",
                  }}
                >
                  <span
                    style={{
                      display: "block",
                      fontFamily: "'Cormorant Garamond', serif",
                      fontSize: 28,
                      fontWeight: 600,
                      color: agentCfg.accentHex,
                      lineHeight: 1.2,
                    }}
                  >
                    {s.value}
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontFamily: "'DM Mono', monospace",
                      fontSize: 10,
                      color: "#94A3B8",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      marginTop: 4,
                    }}
                  >
                    {s.label}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Detail sections — full width in modal */}
          {event.detail_sections?.map((section, i) => (
            <div key={i} style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontFamily: "'DM Mono', monospace",
                  fontSize: 9,
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                  color: "#94A3B8",
                  marginBottom: 8,
                }}
              >
                {section.label}
              </div>
              <div
                style={{
                  background: "#F8FAFC",
                  border: "1px solid #E2E8F0",
                  borderRadius: 8,
                  padding: "14px 16px",
                  fontFamily: "'DM Mono', monospace",
                  fontSize: 12,
                  color: "#334155",
                  lineHeight: 1.85,
                  whiteSpace: "pre-wrap",
                }}
              >
                {section.content}
              </div>
            </div>
          ))}

          {/* Agent-specific deep-dive sections */}
          {event.agent_type === "call-intel" && (
            <div style={{ marginTop: 8, padding: "16px", background: agentCfg.bgColor, border: `1px solid ${agentCfg.borderColor}`, borderRadius: 10 }}>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em", color: agentCfg.color, marginBottom: 10 }}>
                Call Intelligence Analysis
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Call Type</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A" }}>Inbound — Borrower Initiated</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Recording</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#059669" }}>Available — Click to play</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Compliance Check</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#059669" }}>Passed — No violations detected</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Follow-Up</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#D97706" }}>3 tasks auto-created</div>
                </div>
              </div>
            </div>
          )}

          {event.agent_type === "deal-breaker" && (
            <div style={{ marginTop: 8, padding: "16px", background: agentCfg.bgColor, border: `1px solid ${agentCfg.borderColor}`, borderRadius: 10 }}>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em", color: agentCfg.color, marginBottom: 10 }}>
                Risk Assessment Detail
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Risk Level</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#DC2626" }}>Medium-High — Approaching limit</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Trigger</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A" }}>Income analysis update</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>AUS Status</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#D97706" }}>Recommend re-run before submission</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Mitigations</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#059669" }}>2 options identified</div>
                </div>
              </div>
            </div>
          )}

          {event.agent_type === "guidelines" && (
            <div style={{ marginTop: 8, padding: "16px", background: agentCfg.bgColor, border: `1px solid ${agentCfg.borderColor}`, borderRadius: 10 }}>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em", color: agentCfg.color, marginBottom: 10 }}>
                Guideline Research Detail
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Confidence</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#059669" }}>High — Multiple sources confirmed</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Sources Checked</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A" }}>Fannie, Freddie, lender overlays</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Overlays</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#D97706" }}>1 investor overlay found</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Last Updated</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A" }}>Selling guide current as of Q1 2026</div>
                </div>
              </div>
            </div>
          )}

          {event.agent_type === "smart-docs" && (
            <div style={{ marginTop: 8, padding: "16px", background: agentCfg.bgColor, border: `1px solid ${agentCfg.borderColor}`, borderRadius: 10 }}>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em", color: agentCfg.color, marginBottom: 10 }}>
                Document Review Detail
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Documents Reviewed</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A" }}>3 files analyzed</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Fraud Detection</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#DC2626" }}>1 screenshot detected</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Freshness Check</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#DC2626" }}>1 stale document (67 days)</div>
                </div>
                <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12 }}>
                  <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, color: "#94A3B8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>Borrower Notified</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#059669" }}>Yes — Portal message sent</div>
                </div>
              </div>
            </div>
          )}

          {(event.agent_type === "bulletin" || event.agent_type === "marketing" || event.agent_type === "underwriting" || event.agent_type === "turn-down") && (
            <div style={{ marginTop: 8, padding: "16px", background: agentCfg.bgColor, border: `1px solid ${agentCfg.borderColor}`, borderRadius: 10 }}>
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.12em", color: agentCfg.color, marginBottom: 10 }}>
                {event.agent_label} — Extended Analysis
              </div>
              <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 14 }}>
                <p style={{ fontSize: 12, color: "#334155", lineHeight: 1.75, margin: 0 }}>
                  Full analysis data will populate from live agent activity. This event was processed by the {event.agent_label} agent
                  on {new Date(event.created_at).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}.
                </p>
              </div>
            </div>
          )}

          {/* Metadata (if present) */}
          {event.metadata && Object.keys(event.metadata).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div
                style={{
                  fontFamily: "'DM Mono', monospace",
                  fontSize: 9,
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                  color: "#94A3B8",
                  marginBottom: 8,
                }}
              >
                Raw Metadata
              </div>
              <div
                style={{
                  background: "#F8FAFC",
                  border: "1px solid #E2E8F0",
                  borderRadius: 8,
                  padding: "12px 14px",
                  fontFamily: "'DM Mono', monospace",
                  fontSize: 11,
                  color: "#475569",
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(event.metadata, null, 2)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const ActivityCard: React.FC<{ event: AIActivityEvent; onViewDetails: (event: AIActivityEvent) => void }> = ({ event, onViewDetails }) => {
  const [expanded, setExpanded] = useState(false);
  const agentCfg = AGENT_CONFIG[event.agent_type] ?? AGENT_CONFIG.guidelines;

  return (
    <div
      style={{
        display: "flex",
        gap: 14,
        padding: "10px 0",
        animation: "fadeSlide 0.25s ease both",
      }}
    >
      {/* Agent icon */}
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: "50%",
          background: agentCfg.bgColor,
          border: `1.5px solid ${agentCfg.borderColor}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 15,
          flexShrink: 0,
          position: "relative",
          zIndex: 1,
        }}
      >
        {agentCfg.icon}
      </div>

      {/* Card */}
      <div
        style={{
          flex: 1,
          background: "#FFFFFF",
          border: "1px solid #E2E8F0",
          borderRadius: 10,
          padding: "12px 16px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)",
          position: "relative",
          overflow: "hidden",
          transition: "box-shadow 0.15s, border-color 0.15s",
          cursor: event.detail_sections || event.stats ? "pointer" : "default",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.boxShadow =
            "0 4px 12px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04)";
          (e.currentTarget as HTMLDivElement).style.borderColor = "#CBD5E1";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLDivElement).style.boxShadow =
            "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)";
          (e.currentTarget as HTMLDivElement).style.borderColor = "#E2E8F0";
        }}
        onClick={() => {
          if (event.detail_sections || event.stats) setExpanded((v) => !v);
        }}
      >
        {/* Left accent bar */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 3,
            background: agentCfg.accentHex,
            borderRadius: "10px 0 0 10px",
          }}
        />

        {/* Header row */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 6 }}>
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: 10,
                fontWeight: 500,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: agentCfg.color,
                marginBottom: 3,
              }}
            >
              {event.agent_label}
            </div>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "#0F172A",
                lineHeight: 1.4,
              }}
            >
              {event.action_title}
            </div>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              flexShrink: 0,
            }}
          >
            {event.is_live && (
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: "#059669",
                  display: "inline-block",
                  animation: "pulse 2s infinite",
                }}
              />
            )}
            <span
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: 10,
                color: "#94A3B8",
                letterSpacing: "0.04em",
              }}
            >
              {formatTime(event.created_at)}
            </span>
          </div>
        </div>

        {/* Summary */}
        <p
          style={{
            fontSize: 12,
            color: "#475569",
            lineHeight: 1.65,
            marginBottom: 10,
          }}
        >
          {event.summary}
        </p>

        {/* Footer row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <OutcomePill outcome={event.outcome} label={event.outcome_label} />

          {(event.detail_sections || event.stats) && (
            <span
              style={{
                marginLeft: "auto",
                fontFamily: "'DM Mono', monospace",
                fontSize: 10,
                color: "#94A3B8",
                letterSpacing: "0.06em",
                userSelect: "none",
              }}
            >
              {expanded ? "▾ COLLAPSE" : "▸ DETAILS"}
            </span>
          )}
        </div>

        {/* Expandable detail */}
        {expanded && (
          <div
            style={{
              marginTop: 14,
              paddingTop: 14,
              borderTop: "1px solid #F1F5F9",
            }}
          >
            {event.stats && (
              <StatBlock stats={event.stats} accentColor={agentCfg.accentHex} />
            )}
            {event.detail_sections?.map((section, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div
                  style={{
                    fontFamily: "'DM Mono', monospace",
                    fontSize: 9,
                    textTransform: "uppercase",
                    letterSpacing: "0.12em",
                    color: "#94A3B8",
                    marginBottom: 6,
                  }}
                >
                  {section.label}
                </div>
                <div
                  style={{
                    background: "#F8FAFC",
                    border: "1px solid #E2E8F0",
                    borderRadius: 6,
                    padding: "10px 12px",
                    fontFamily: "'DM Mono', monospace",
                    fontSize: 11,
                    color: "#334155",
                    lineHeight: 1.75,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {section.content}
                </div>
              </div>
            ))}

            {/* View Full Details button */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onViewDetails(event);
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                marginTop: 8,
                padding: "7px 16px",
                borderRadius: 8,
                border: `1px solid ${agentCfg.borderColor}`,
                background: agentCfg.bgColor,
                color: agentCfg.color,
                fontSize: 11,
                fontWeight: 600,
                fontFamily: "'DM Sans', sans-serif",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = agentCfg.accentHex;
                (e.currentTarget as HTMLButtonElement).style.color = "#FFFFFF";
                (e.currentTarget as HTMLButtonElement).style.borderColor = agentCfg.accentHex;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = agentCfg.bgColor;
                (e.currentTarget as HTMLButtonElement).style.color = agentCfg.color;
                (e.currentTarget as HTMLButtonElement).style.borderColor = agentCfg.borderColor;
              }}
            >
              {AGENT_DETAIL_LABELS[event.agent_type] || "View Full Details"}
              <span style={{ fontSize: 12 }}>→</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────

interface AIActivityTabProps {
  loanId: string;
  borrowerName?: string;
  loanNumber?: string;
  loanAmount?: number;
  loanStatus?: string;
  /** Optional: pass events directly (bypasses API fetch) */
  events?: AIActivityEvent[];
  /** Click-to-dial handler — when provided, shows a "Start Call Intelligence" button */
  onClickToDial?: () => void;
}

const AIActivityTab: React.FC<AIActivityTabProps> = ({
  loanId,
  borrowerName = "Borrower",
  loanNumber,
  loanAmount,
  loanStatus = "In Processing",
  events: propEvents,
  onClickToDial,
}) => {
  const [events, setEvents] = useState<AIActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<AgentType | "all">("all");
  const [selectedEvent, setSelectedEvent] = useState<AIActivityEvent | null>(null);

  // Fetch from API or use prop-injected events
  const fetchEvents = useCallback(async () => {
    if (propEvents) {
      setEvents(propEvents);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const res = await fetch(`/api/loans/${loanId}/ai-activity`);
      if (!res.ok) throw new Error("Failed to load AI activity");
      const data: AIActivityEvent[] = await res.json();
      setEvents(data);
    } catch {
      // Fallback to mock data in development
      console.warn("[AIActivityTab] API unavailable — using mock data");
      setEvents(MOCK_EVENTS);
    } finally {
      setLoading(false);
    }
  }, [loanId, propEvents]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const filteredEvents =
    activeFilter === "all"
      ? events
      : events.filter((e) => e.agent_type === activeFilter);

  const dayGroups = groupEventsByDay(filteredEvents);

  // Only show filter chips for agent types present in data
  const presentAgentTypes = Array.from(new Set(events.map((e) => e.agent_type))) as AgentType[];

  const initials = borrowerName
    .split(" ")
    .slice(0, 2)
    .map((n) => n[0])
    .join("");

  return (
    <>
      {/* Inject keyframe animations */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@400;500;600&display=swap');
        @keyframes fadeSlide {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.4; transform: scale(0.85); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

      <div
        style={{
          background: "#FFFFFF",
          fontFamily: "'DM Sans', sans-serif",
          minHeight: 400,
        }}
      >
        {/* Filter bar */}
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            alignItems: "center",
            padding: "0 0 16px 0",
            borderBottom: "1px solid #F1F5F9",
            marginBottom: 20,
          }}
        >
          <span
            style={{
              fontFamily: "'DM Mono', monospace",
              fontSize: 10,
              color: "#94A3B8",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginRight: 4,
            }}
          >
            Filter
          </span>

          {/* All chip */}
          <button
            onClick={() => setActiveFilter("all")}
            style={{
              padding: "5px 12px",
              borderRadius: 20,
              border: activeFilter === "all" ? "1px solid #1D6FCC" : "1px solid #E2E8F0",
              background: activeFilter === "all" ? "#EFF6FF" : "#FFFFFF",
              color: activeFilter === "all" ? "#1D6FCC" : "#64748B",
              fontSize: 11,
              fontWeight: 500,
              fontFamily: "'DM Sans', sans-serif",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            All Agents
          </button>

          {presentAgentTypes.map((agentType) => {
            const label = AGENT_FILTER_LABELS[agentType];
            if (!label) return null;
            const cfg = AGENT_CONFIG[agentType];
            const isActive = activeFilter === agentType;
            return (
              <button
                key={agentType}
                onClick={() => setActiveFilter(agentType)}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "5px 12px",
                  borderRadius: 20,
                  border: isActive ? `1px solid ${cfg.borderColor}` : "1px solid #E2E8F0",
                  background: isActive ? cfg.bgColor : "#FFFFFF",
                  color: isActive ? cfg.color : "#64748B",
                  fontSize: 11,
                  fontWeight: 500,
                  fontFamily: "'DM Sans', sans-serif",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: cfg.accentHex,
                    display: "inline-block",
                    flexShrink: 0,
                  }}
                />
                {label}
              </button>
            );
          })}

          <div style={{ flex: 1 }} />

          {/* Start Call Intelligence button */}
          {onClickToDial && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClickToDial();
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 14px",
                borderRadius: 20,
                border: "1px solid #A7F3D0",
                background: "#059669",
                color: "#FFFFFF",
                fontSize: 11,
                fontWeight: 600,
                fontFamily: "'DM Sans', sans-serif",
                cursor: "pointer",
                transition: "all 0.15s",
                boxShadow: "0 1px 3px rgba(5,150,105,0.3)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "#047857";
                (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 2px 6px rgba(5,150,105,0.4)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "#059669";
                (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 1px 3px rgba(5,150,105,0.3)";
              }}
            >
              <span style={{ fontSize: 13 }}>📞</span>
              Start Call Intelligence
            </button>
          )}

          {/* Refresh button */}
          <button
            onClick={fetchEvents}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "5px 12px",
              borderRadius: 20,
              border: "1px solid #E2E8F0",
              background: "#FFFFFF",
              color: "#64748B",
              fontSize: 11,
              fontFamily: "'DM Mono', monospace",
              letterSpacing: "0.05em",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            ↻ Refresh
          </button>

          <span
            style={{
              fontFamily: "'DM Mono', monospace",
              fontSize: 10,
              color: "#94A3B8",
              letterSpacing: "0.08em",
            }}
          >
            {filteredEvents.length} EVENT{filteredEvents.length !== 1 ? "S" : ""}
          </span>
        </div>

        {/* Loading */}
        {loading && (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#94A3B8" }}>
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: "50%",
                border: "2px solid #E2E8F0",
                borderTopColor: "#1D6FCC",
                animation: "spin 0.7s linear infinite",
                margin: "0 auto 12px",
              }}
            />
            <div
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize: 11,
                letterSpacing: "0.08em",
              }}
            >
              Loading AI activity...
            </div>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div
            style={{
              padding: "20px",
              background: "#FEF2F2",
              border: "1px solid #FECACA",
              borderRadius: 8,
              color: "#DC2626",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && filteredEvents.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 0" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>✦</div>
            <div
              style={{
                fontFamily: "'Cormorant Garamond', serif",
                fontSize: 18,
                color: "#475569",
                marginBottom: 6,
              }}
            >
              No AI activity recorded yet
            </div>
            <div style={{ fontSize: 12, color: "#94A3B8" }}>
              Agent activity will appear here as it occurs
            </div>
          </div>
        )}

        {/* Timeline */}
        {!loading && !error && filteredEvents.length > 0 && (
          <div style={{ position: "relative" }}>
            {/* Vertical line */}
            <div
              style={{
                position: "absolute",
                left: 17,
                top: 0,
                bottom: 0,
                width: 1,
                background:
                  "linear-gradient(to bottom, #CBD5E1 0%, #E2E8F0 60%, transparent 100%)",
              }}
            />

            {dayGroups.map((group, gi) => (
              <div key={gi} style={{ marginBottom: 8 }}>
                {/* Day label */}
                <div
                  style={{
                    fontFamily: "'DM Mono', monospace",
                    fontSize: 10,
                    color: "#94A3B8",
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    paddingLeft: 48,
                    paddingBottom: 8,
                    paddingTop: gi === 0 ? 0 : 16,
                  }}
                >
                  {group.label}
                </div>

                {group.events.map((event) => (
                  <ActivityCard key={event.id} event={event} onViewDetails={setSelectedEvent} />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selectedEvent && (
        <DetailModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      )}
    </>
  );
};

export default AIActivityTab;
export { MOCK_EVENTS };
export type { AIActivityTabProps };
