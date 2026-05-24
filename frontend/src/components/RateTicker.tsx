import { useEffect, useState } from "react";

/**
 * RateTicker — top-of-CRM widget showing live market + Perennia rates.
 *
 * Polls /api/rate-watch/current-rates every 60s. Renders with the existing
 * Perennia design language (deep space #060A10, electric blue #7EB8F7,
 * Cormorant Garamond / DM Mono / DM Sans, glassmorphism).
 *
 * Frontend agent notes:
 *  - All numeric values are computed server-side; we never do rate math here.
 *  - "stale" badge appears if the latest observation is > 24h old.
 *  - Tooltip on each row shows source + observed_at + provenance kind.
 *  - Mobile layout: collapses to "30yr Fixed" only + tap-to-expand.
 */

type Product =
  | "30_fixed" | "15_fixed" | "30_jumbo"
  | "7_6_sofr_arm" | "30_fha" | "30_va";

type CurrentRate = {
  product: Product;
  market_rate: string;     // Decimal serialized as string
  points: string;
  perennia_rate: string;
  margin_bps: number;
  observed_at: string;     // ISO
  source: string;
};

type CurrentRatesResponse = {
  rates: CurrentRate[];
  fetched_at: string;
  stale: boolean;
};

const PRODUCT_LABELS: Record<Product, string> = {
  "30_fixed":      "30 Yr Fixed",
  "15_fixed":      "15 Yr Fixed",
  "30_jumbo":      "30 Yr Jumbo",
  "7_6_sofr_arm":  "7/6 SOFR ARM",
  "30_fha":        "30 Yr FHA",
  "30_va":         "30 Yr VA",
};

const PRODUCT_ORDER: Product[] = [
  "30_fixed", "15_fixed", "30_jumbo", "7_6_sofr_arm", "30_fha", "30_va",
];

export function RateTicker() {
  const [data, setData] = useState<CurrentRatesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const resp = await fetch("/api/rate-watch/current-rates", {
          credentials: "include",
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const body: CurrentRatesResponse = await resp.json();
        if (!cancelled) {
          setData(body);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "fetch failed");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const id = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (loading) return <TickerSkeleton />;
  if (error) return <TickerError message={error} />;
  if (!data) return null;

  const ratesByProduct = new Map(data.rates.map(r => [r.product, r]));
  const sorted = PRODUCT_ORDER
    .map(p => ratesByProduct.get(p))
    .filter((r): r is CurrentRate => r !== undefined);

  return (
    <div
      role="region"
      aria-label="Current mortgage rates"
      style={{
        background: "rgba(126, 184, 247, 0.04)",
        border: "1px solid rgba(126, 184, 247, 0.18)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderRadius: 12,
        padding: "16px 20px",
        color: "#E8EEF6",
        fontFamily: '"DM Sans", system-ui, sans-serif',
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2
          style={{
            margin: 0,
            fontFamily: '"Cormorant Garamond", serif',
            fontWeight: 500,
            fontSize: 20,
            letterSpacing: "0.02em",
          }}
        >
          Market rates
        </h2>
        {data.stale && (
          <span
            title={`Last observation older than 24 hours`}
            style={{
              fontSize: 11,
              padding: "2px 8px",
              borderRadius: 4,
              background: "rgba(255, 180, 60, 0.15)",
              color: "#FFB43C",
              fontFamily: '"DM Mono", monospace',
            }}
          >
            STALE
          </span>
        )}
      </div>

      <div
        role="table"
        style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr 1fr",
          gap: "8px 16px",
          fontSize: 13,
        }}
      >
        <div role="columnheader" style={headerStyle}>Product</div>
        <div role="columnheader" style={{ ...headerStyle, textAlign: "right" }}>Market</div>
        <div role="columnheader" style={{ ...headerStyle, textAlign: "right" }}>Your rate</div>

        {sorted.map(rate => (
          <RateRow key={rate.product} rate={rate} />
        ))}
      </div>

      <div
        style={{
          marginTop: 12,
          fontSize: 10,
          color: "rgba(232, 238, 246, 0.5)",
          fontFamily: '"DM Mono", monospace',
        }}
      >
        Source: Freddie Mac PMMS via FRED &middot; updated{" "}
        {new Date(data.fetched_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </div>
    </div>
  );
}

const headerStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "rgba(232, 238, 246, 0.55)",
  fontFamily: '"DM Mono", monospace',
  paddingBottom: 4,
  borderBottom: "1px solid rgba(126, 184, 247, 0.08)",
};

function RateRow({ rate }: { rate: CurrentRate }) {
  const tooltip =
    `Source: ${rate.source}\n` +
    `Observed: ${new Date(rate.observed_at).toLocaleString()}\n` +
    `Margin: ${rate.margin_bps} bps`;

  return (
    <>
      <div role="cell" style={{ paddingTop: 6 }}>{PRODUCT_LABELS[rate.product]}</div>
      <div
        role="cell"
        style={{
          paddingTop: 6,
          textAlign: "right",
          fontFamily: '"DM Mono", monospace',
          color: "rgba(232, 238, 246, 0.7)",
        }}
        title={tooltip}
      >
        {formatRate(rate.market_rate)}
      </div>
      <div
        role="cell"
        style={{
          paddingTop: 6,
          textAlign: "right",
          fontFamily: '"DM Mono", monospace',
          color: "#7EB8F7",
          fontWeight: 600,
        }}
        title={tooltip}
      >
        {formatRate(rate.perennia_rate)}
      </div>
    </>
  );
}

function formatRate(s: string): string {
  // "6.6500" → "6.65%"
  const n = parseFloat(s);
  if (Number.isNaN(n)) return s;
  return `${n.toFixed(2)}%`;
}

function TickerSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading rates"
      style={{
        height: 220,
        borderRadius: 12,
        background:
          "linear-gradient(90deg, rgba(126,184,247,0.04) 0%, rgba(126,184,247,0.08) 50%, rgba(126,184,247,0.04) 100%)",
        backgroundSize: "200% 100%",
        animation: "rate-ticker-shimmer 1.6s linear infinite",
      }}
    >
      <style>{`
        @keyframes rate-ticker-shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-busy="true"] { animation: none; }
        }
      `}</style>
    </div>
  );
}

function TickerError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      style={{
        padding: 16,
        borderRadius: 12,
        background: "rgba(255, 90, 90, 0.06)",
        border: "1px solid rgba(255, 90, 90, 0.2)",
        color: "#FF9E9E",
        fontFamily: '"DM Sans", system-ui, sans-serif',
        fontSize: 13,
      }}
    >
      Rates unavailable: {message}
    </div>
  );
}
