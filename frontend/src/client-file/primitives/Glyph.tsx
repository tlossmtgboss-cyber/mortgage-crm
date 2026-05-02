import type { ActivityEventKind } from "../types";

type GlyphVariant = "default" | "accent" | "agent" | "success" | "warning" | "danger";

interface GlyphProps {
  kind?: ActivityEventKind;
  glyph?: string;
  variant?: GlyphVariant;
}

// Map event kinds → display glyph + color variant.
// Using simple unicode glyphs for visual consistency without emoji bloat.
function mapKind(kind: ActivityEventKind): { glyph: string; variant: GlyphVariant } {
  if (kind.startsWith("message_received")) return { glyph: "→", variant: "default" };
  if (kind.startsWith("message_sent_voice_agent")) return { glyph: "←", variant: "agent" };
  if (kind.startsWith("message_sent")) return { glyph: "←", variant: "default" };
  if (kind === "note_added") return { glyph: "•", variant: "default" };
  if (kind.startsWith("call_")) return { glyph: "☎", variant: "default" };
  if (kind === "milestone_reached") return { glyph: "◆", variant: "success" };
  if (kind === "milestone_at_risk" || kind === "milestone_predicted_slip")
    return { glyph: "◆", variant: "warning" };
  if (kind === "document_uploaded" || kind === "document_approved")
    return { glyph: "▤", variant: "success" };
  if (kind === "document_rejected") return { glyph: "▤", variant: "danger" };
  if (kind === "document_stale_reopened" || kind === "document_requested")
    return { glyph: "▤", variant: "warning" };
  if (kind.startsWith("task_") || kind === "appointment_booked")
    return { glyph: "✓", variant: "default" };
  if (kind.startsWith("action_plan_")) return { glyph: "▶", variant: "default" };
  if (kind.startsWith("insight_")) return { glyph: "✦", variant: "agent" };
  if (kind === "lifecycle_stage_changed") return { glyph: "⇄", variant: "default" };
  if (kind === "tag_added" || kind === "tag_removed") return { glyph: "#", variant: "default" };
  if (kind === "collaborator_added" || kind === "collaborator_removed")
    return { glyph: "@", variant: "default" };
  if (kind.startsWith("cadence_")) return { glyph: "◇", variant: "agent" };
  if (kind === "property_viewed" || kind === "portal_logged_in")
    return { glyph: "◉", variant: "default" };
  if (kind === "email_opened" || kind === "email_link_clicked")
    return { glyph: "◉", variant: "default" };
  return { glyph: "•", variant: "default" };
}

export function Glyph({ kind, glyph, variant }: GlyphProps) {
  let resolvedGlyph = glyph;
  let resolvedVariant: GlyphVariant = variant ?? "default";

  if (kind && !glyph) {
    const m = mapKind(kind);
    resolvedGlyph = m.glyph;
    if (!variant) resolvedVariant = m.variant;
  }

  const cls = [
    "pf-cf-glyph",
    resolvedVariant !== "default" && `pf-cf-glyph--${resolvedVariant}`,
  ].filter(Boolean).join(" ");

  return <span className={cls} aria-hidden="true">{resolvedGlyph ?? "•"}</span>;
}
