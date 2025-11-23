import { GroundingSnapshot, RetrievedContext } from "../orchestrator/types";

export function buildGroundingSnapshot(ctx: RetrievedContext): GroundingSnapshot {
  const snapshot: GroundingSnapshot = {
    participantSummary: {
      borrowerName: ctx.lead?.borrowerName ?? ctx.loan?.borrowerName,
      coBorrowerName: ctx.lead?.coBorrowerName ?? ctx.loan?.coBorrowerName,
      agents: compactArray([
        ctx.lead?.buyerAgentName,
        ctx.lead?.listingAgentName,
        ctx.loan?.agentName
      ]),
      emails: unique(compactArray([
        ctx.lead?.email,
        ctx.loan?.email,
        ...(ctx.lead?.additionalEmails ?? [])
      ])),
      phones: unique(compactArray([
        ctx.lead?.phone,
        ctx.loan?.phone,
        ...(ctx.lead?.additionalPhones ?? [])
      ]))
    },
    loanSnapshot: ctx.loan
      ? {
          loanId: ctx.loan.loanId ?? ctx.loan.id,
          product: ctx.loan.product,
          purpose: ctx.loan.purpose,
          occupancy: ctx.loan.occupancy,
          rate: safeNumber(ctx.loan.rate),
          lockStatus: ctx.loan.lockStatus,
          loanAmount: safeNumber(ctx.loan.loanAmount),
          purchasePrice: safeNumber(ctx.loan.purchasePrice),
          ltv: safeNumber(ctx.loan.ltv),
          stage: ctx.loan.stage,
          importantDates: {
            appDate: ctx.loan.appDate,
            lockDate: ctx.loan.lockDate,
            closingDate: ctx.loan.closingDate
          },
          keyConditions: (ctx.loan.conditions ?? [])
            .slice(0, 10)
            .map((c: any) => (typeof c === "string" ? c : c.description ?? "")) as string[]
        }
      : undefined,
    timeline: buildTimeline(ctx),
    openTasks: buildOpenTasks(ctx),
    kbSummary: (ctx.kbArticles ?? [])
      .slice(0, 5)
      .map((a: any) => a.summary ?? a.title ?? "")
      .filter(Boolean),
    rawIds: {
      leadId: ctx.lead?.id,
      loanId: ctx.loan?.id ?? ctx.loan?.loanId
    }
  };

  return snapshot;
}

function buildTimeline(ctx: RetrievedContext) {
  const items: GroundingSnapshot["timeline"] = [];

  (ctx.notes ?? []).slice(-10).forEach((note: any) => {
    items.push({
      type: "NOTE",
      date: note.date ?? note.createdAt ?? "",
      summary: truncate(note.text ?? note.body ?? "", 300)
    });
  });

  (ctx.emails ?? []).slice(-10).forEach((email: any) => {
    items.push({
      type: "EMAIL",
      date: email.date ?? email.sentAt ?? "",
      summary: truncate(email.subject + " — " + (email.snippet ?? ""), 300)
    });
  });

  (ctx.sms ?? []).slice(-10).forEach((sms: any) => {
    items.push({
      type: "SMS",
      date: sms.date ?? sms.sentAt ?? "",
      summary: truncate(sms.body ?? "", 300)
    });
  });

  items.sort((a, b) => {
    const da = a.date ? Date.parse(a.date) : NaN;
    const db = b.date ? Date.parse(b.date) : NaN;

    if (isNaN(da) && isNaN(db)) return 0;
    if (isNaN(da)) return 1;
    if (isNaN(db)) return -1;
    return db - da;
  });

  return items;
}

function buildOpenTasks(ctx: RetrievedContext) {
  const tasks: GroundingSnapshot["openTasks"] = [];

  if ((ctx.pipeline as any)?.openTasks) {
    (ctx.pipeline as any).openTasks.forEach((t: any) => {
      tasks.push({
        taskId: t.id,
        title: t.title ?? "",
        dueDate: t.dueDate,
        status: t.status ?? "OPEN"
      });
    });
  }

  return tasks.slice(0, 20);
}

export function groundingSummaryBullets(snapshot: GroundingSnapshot): string {
  const parts: string[] = [];

  if (snapshot.participantSummary.borrowerName) {
    parts.push(`- Borrower: ${snapshot.participantSummary.borrowerName}`);
  }
  if (snapshot.loanSnapshot) {
    parts.push(
      `- Loan: ${snapshot.loanSnapshot.loanId ?? "N/A"} | ` +
      `${snapshot.loanSnapshot.product ?? "product N/A"} | ` +
      `Stage: ${snapshot.loanSnapshot.stage ?? "unknown"} | ` +
      `Rate: ${snapshot.loanSnapshot.rate ?? "N/A"} | ` +
      `Lock: ${snapshot.loanSnapshot.lockStatus ?? "N/A"}`
    );
  }
  if (snapshot.timeline.length > 0) {
    const last = snapshot.timeline[0];
    parts.push(
      `- Last activity: ${last.type} on ${last.date}: ${truncate(last.summary, 120)}`
    );
  }
  if (snapshot.openTasks.length > 0) {
    parts.push(
      `- Open tasks: ${snapshot.openTasks.length} (top: ${snapshot.openTasks[0].title})`
    );
  }

  return parts.join("\n");
}

// Helpers
function compactArray<T>(arr: (T | undefined | null)[]): T[] {
  return arr.filter((x): x is T => x !== undefined && x !== null);
}

function unique<T>(arr: T[]): T[] {
  return Array.from(new Set(arr));
}

function safeNumber(val: any): number | null {
  const n = Number(val);
  return isNaN(n) ? null : n;
}

function truncate(text = "", max = 100): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 3) + "...";
}
