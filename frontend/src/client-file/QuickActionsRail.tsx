import { useState, useMemo, useCallback } from "react";
import { Card } from "./primitives/Card";
import type { ClientFile } from "./types";

interface Props {
  clientFileId: string;
  client: ClientFile;
}

const QUICK_ACTIONS: { key: string; label: string; icon: string; color?: string }[] = [
  { key: "call", label: "Call", icon: "phone" },
  { key: "task", label: "Create Task", icon: "check-square" },
  { key: "appointment", label: "Set Appointment", icon: "calendar" },
  { key: "video", label: "Video Call", icon: "video" },
  { key: "voicemail", label: "Voicemail Drop", icon: "voicemail" },
  { key: "record_video", label: "Record Video", icon: "film" },
  { key: "application", label: "Send Application", icon: "file-text" },
  { key: "portals", label: "Portals", icon: "layout" },
  { key: "escalation", label: "Escalation", icon: "alert-triangle" },
];

function ActionIcon({ icon }: { icon: string }) {
  const paths: Record<string, JSX.Element> = {
    phone: <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.11 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />,
    "check-square": <><polyline points="9 11 12 14 22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>,
    calendar: <><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></>,
    video: <><polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" ry="2" /></>,
    voicemail: <><circle cx="5.5" cy="11.5" r="4.5" /><circle cx="18.5" cy="11.5" r="4.5" /><line x1="5.5" y1="16" x2="18.5" y2="16" /></>,
    film: <><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" /><line x1="7" y1="2" x2="7" y2="22" /><line x1="17" y1="2" x2="17" y2="22" /><line x1="2" y1="12" x2="22" y2="12" /></>,
    "file-text": <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></>,
    layout: <><rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="9" y1="21" x2="9" y2="9" /></>,
    "alert-triangle": <><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
  };
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {paths[icon] || paths.phone}
    </svg>
  );
}

function MiniCalendar() {
  const today = new Date();
  const [month, setMonth] = useState(today.getMonth());
  const [year, setYear] = useState(today.getFullYear());

  const { weeks, monthLabel } = useMemo(() => {
    const first = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0).getDate();
    const startDow = first.getDay();
    const ws: (number | null)[][] = [];
    let week: (number | null)[] = [];
    for (let i = 0; i < startDow; i++) week.push(null);
    for (let d = 1; d <= lastDay; d++) {
      week.push(d);
      if (week.length === 7) { ws.push(week); week = []; }
    }
    if (week.length > 0) {
      while (week.length < 7) week.push(null);
      ws.push(week);
    }
    const label = first.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    return { weeks: ws, monthLabel: label };
  }, [month, year]);

  const prevMonth = useCallback(() => {
    if (month === 0) { setMonth(11); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
  }, [month]);

  const nextMonth = useCallback(() => {
    if (month === 11) { setMonth(0); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
  }, [month]);

  const isToday = (d: number | null) =>
    d !== null && month === today.getMonth() && year === today.getFullYear() && d === today.getDate();

  return (
    <div className="pf-cf-minical">
      <div className="pf-cf-minical__nav">
        <button type="button" onClick={prevMonth} className="pf-cf-minical__arrow">&lt;</button>
        <span className="pf-cf-minical__label">{monthLabel}</span>
        <button type="button" onClick={nextMonth} className="pf-cf-minical__arrow">&gt;</button>
      </div>
      <table className="pf-cf-minical__table">
        <thead>
          <tr>
            {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
              <th key={i}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, wi) => (
            <tr key={wi}>
              {week.map((d, di) => (
                <td key={di} className={isToday(d) ? "pf-cf-minical__today" : ""}>
                  {d ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="pf-cf-minical__footer">
        <div className="pf-cf-minical__footer-label">Today</div>
        <div className="pf-cf-empty">No appointments scheduled</div>
      </div>
    </div>
  );
}

export function QuickActionsRail({ clientFileId, client }: Props) {
  const handleAction = (key: string) => {
    const phone = client.primary_phone;

    switch (key) {
      case "call":
        if (phone) {
          window.open(`msteams://teams.microsoft.com/l/call/0/0?users=4:${phone}`, "_blank");
        }
        break;
      default:
        break;
    }
  };

  return (
    <div className="pf-cf-rail">
      <Card title="quick actions" variant="strong">
        <div className="pf-cf-quick-actions">
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a.key}
              type="button"
              className="pf-cf-quick-action"
              onClick={() => handleAction(a.key)}
            >
              <ActionIcon icon={a.icon} />
              <span>{a.label}</span>
            </button>
          ))}
        </div>
      </Card>
      <MiniCalendar />
    </div>
  );
}
