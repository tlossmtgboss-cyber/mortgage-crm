interface AvatarProps {
  initials: string;
  size?: "sm" | "md" | "lg";
  online?: boolean;
}

export function Avatar({ initials, size = "md", online }: AvatarProps) {
  const cls = [
    "pf-cf-avatar",
    size === "sm" && "pf-cf-avatar--sm",
    size === "lg" && "pf-cf-avatar--lg",
  ].filter(Boolean).join(" ");

  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <span className={cls}>{initials.slice(0, 2).toUpperCase()}</span>
      {online && (
        <span
          aria-label="online"
          style={{
            position: "absolute",
            bottom: 0,
            right: 0,
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--pf-cf-success)",
            border: "1.5px solid var(--pf-cf-bg-deep)",
          }}
        />
      )}
    </span>
  );
}

export function deriveInitials(displayName: string): string {
  const parts = displayName.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2);
  return (parts[0][0] + parts[parts.length - 1][0]);
}
