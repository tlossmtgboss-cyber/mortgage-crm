import type { ReactNode } from "react";

interface CardProps {
  title?: string;
  action?: { label: string; onClick: () => void };
  variant?: "default" | "strong" | "accent";
  children: ReactNode;
}

export function Card({ title, action, variant = "default", children }: CardProps) {
  const cls = [
    "pf-cf-card",
    variant === "strong" && "pf-cf-card--strong",
    variant === "accent" && "pf-cf-card--accent",
  ].filter(Boolean).join(" ");

  return (
    <div className={cls}>
      {(title || action) && (
        <div className="pf-cf-card__header">
          {title && <h3 className="pf-cf-card__title">{title}</h3>}
          {action && (
            <button
              type="button"
              className="pf-cf-card__action"
              onClick={action.onClick}
            >
              {action.label}
            </button>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
