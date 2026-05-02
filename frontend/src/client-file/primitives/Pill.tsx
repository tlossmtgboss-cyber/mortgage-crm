import type { ReactNode } from "react";

type PillVariant = "default" | "accent" | "success" | "warning" | "danger" | "agent";

interface PillProps {
  variant?: PillVariant;
  active?: boolean;
  onClick?: () => void;
  className?: string;
  children: ReactNode;
}

export function Pill({
  variant = "default",
  active = false,
  onClick,
  className = "",
  children,
}: PillProps) {
  const cls = [
    "pf-cf-pill",
    variant !== "default" && `pf-cf-pill--${variant}`,
    onClick && "pf-cf-pill--clickable",
    active && "pf-cf-pill--active",
    className,
  ].filter(Boolean).join(" ");

  if (onClick) {
    return (
      <button type="button" className={cls} onClick={onClick}>
        {children}
      </button>
    );
  }
  return <span className={cls}>{children}</span>;
}
