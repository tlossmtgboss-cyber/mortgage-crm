"""
CI runner for the Perennia AI agent challenge framework.

This is a thin adapter around backend.agents.tools.u_agent_challenge —
it does NOT refactor or duplicate the original framework. It:

  1. Invokes ChallengeRunner.run_all() against the configured API,
  2. Normalizes the summary into a stable JSON schema for CI consumption,
  3. Optionally diffs the run against a baseline and exits non-zero on
     regression (per Wave 2 regression policy).

Regression policy (matches README):
  * Overall score drops > 2 points  -> regression
  * Any compliance pillar drops > 5 -> regression
  * Any NEW critical-severity failure appears -> regression

Usage:
  python3 -m backend.agents.challenge.runner --output json \
      --baseline backend/agents/challenge/baseline.json

If no Anthropic API key / Perennia API password is available, the runner
emits a structured "skipped" report and exits 0 (so the nightly job can
record the skip without failing). PR gating uses the same exit semantics:
a clean skip is treated as non-blocking.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Lazy import of the underlying challenge framework. We import inside main()
# so that --help still works in environments where heavy deps (httpx, the
# anthropic SDK, etc.) are unavailable.
# ---------------------------------------------------------------------------


SCHEMA_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _have_api_credentials() -> bool:
    """Return True iff we have enough credentials to actually run scenarios."""
    return bool(
        os.getenv("ANTHROPIC_API_KEY")
        and os.getenv("PERENNIA_API_PASS")
    )


def _empty_report(reason: str) -> Dict[str, Any]:
    """Build a structurally-valid report when the challenge cannot run."""
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": _utc_now_iso(),
        "status": "skipped",
        "skip_reason": reason,
        "overall_score": None,
        "per_agent_scores": {},
        "per_compliance_pillar": {},
        "failures": [],
        "regressions": [],
    }


# ---------------------------------------------------------------------------
# Normalization: take the rich summary from ChallengeRunner._build_summary()
# and project it into the stable CI schema.
# ---------------------------------------------------------------------------

# The six scoring dimensions used by ScoringEngine. Two of them
# (accuracy + compliance) act as "compliance pillars" for the regression
# policy because they encode the non-negotiable behaviors. The remaining
# four are tracked for visibility.
_COMPLIANCE_PILLARS = (
    "accuracy",
    "compliance",
    "tone",
    "tool_usage",
    "efficiency",
    "adaptability",
)


def _normalize_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Project ChallengeRunner output into the CI-stable schema."""
    agent_summaries = summary.get("agent_summaries", {}) or {}

    # Overall score = mean of per-agent avg_score, weighted by challenge count.
    total_weight = 0
    weighted_sum = 0.0
    per_agent_scores: Dict[str, float] = {}
    pillar_running: Dict[str, List[float]] = {p: [] for p in _COMPLIANCE_PILLARS}

    for agent_id, adata in agent_summaries.items():
        challenges = int(adata.get("challenges", 0) or 0)
        avg = float(adata.get("avg_score", 0.0) or 0.0)
        per_agent_scores[agent_id] = round(avg, 2)
        if challenges > 0:
            weighted_sum += avg * challenges
            total_weight += challenges

        dim_avgs = adata.get("dimension_averages", {}) or {}
        for pillar in _COMPLIANCE_PILLARS:
            if pillar in dim_avgs:
                pillar_running[pillar].append(float(dim_avgs[pillar]))

    overall_score: Optional[float] = (
        round(weighted_sum / total_weight, 2) if total_weight else None
    )

    per_compliance_pillar = {
        p: round(sum(vals) / len(vals), 2) if vals else None
        for p, vals in pillar_running.items()
    }

    # Failures = violations enriched with severity. ScoringEngine flags
    # compliance violations as "critical"; everything else defaults to
    # "warning" unless the violation dict already carries a severity.
    failures: List[Dict[str, Any]] = []
    for v in summary.get("violations", []) or []:
        severity = (v.get("severity") or "").lower()
        if not severity:
            severity = "critical" if v.get("type") == "compliance" else "warning"
        failures.append(
            {
                "agent": v.get("agent"),
                "challenge": v.get("challenge"),
                "type": v.get("type"),
                "severity": severity,
                "detail": v.get("detail") or v.get("message") or "",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": summary.get("timestamp", _utc_now_iso()),
        "status": "ran",
        "skip_reason": None,
        "run_id": summary.get("run_id"),
        "total_challenges": summary.get("total_challenges", 0),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "pass_rate": summary.get("pass_rate", 0.0),
        "overall_score": overall_score,
        "per_agent_scores": per_agent_scores,
        "per_compliance_pillar": per_compliance_pillar,
        "failures": failures,
        "regressions": [],
    }


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------


def _load_baseline(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"[runner] WARN: cannot read baseline {path}: {e}", file=sys.stderr)
        return None


def _failure_key(f: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(f.get("agent")), str(f.get("challenge")), str(f.get("type")))


def _detect_regressions(
    current: Dict[str, Any], baseline: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Apply the Wave 2 regression policy.

    Returns a list of regression records. An empty list means "no regression"
    and the runner should exit 0.
    """
    regressions: List[Dict[str, Any]] = []

    # Skip regression detection if baseline never captured a real score.
    base_overall = baseline.get("overall_score")
    cur_overall = current.get("overall_score")
    if base_overall is None or cur_overall is None:
        return regressions

    # Rule 1: overall score drop > 2 points.
    if base_overall - cur_overall > 2.0:
        regressions.append(
            {
                "rule": "overall_score_drop",
                "threshold": 2.0,
                "baseline": base_overall,
                "current": cur_overall,
                "drop": round(base_overall - cur_overall, 2),
            }
        )

    # Rule 2: any compliance pillar drop > 5 points.
    base_pillars = baseline.get("per_compliance_pillar", {}) or {}
    cur_pillars = current.get("per_compliance_pillar", {}) or {}
    for pillar, base_val in base_pillars.items():
        cur_val = cur_pillars.get(pillar)
        if base_val is None or cur_val is None:
            continue
        if base_val - cur_val > 5.0:
            regressions.append(
                {
                    "rule": "pillar_drop",
                    "pillar": pillar,
                    "threshold": 5.0,
                    "baseline": base_val,
                    "current": cur_val,
                    "drop": round(base_val - cur_val, 2),
                }
            )

    # Rule 3: any NEW critical-severity failure.
    base_critical = {
        _failure_key(f)
        for f in baseline.get("failures", []) or []
        if (f.get("severity") or "").lower() == "critical"
    }
    for f in current.get("failures", []) or []:
        if (f.get("severity") or "").lower() != "critical":
            continue
        if _failure_key(f) not in base_critical:
            regressions.append(
                {
                    "rule": "new_critical_failure",
                    "agent": f.get("agent"),
                    "challenge": f.get("challenge"),
                    "type": f.get("type"),
                    "detail": f.get("detail"),
                }
            )

    return regressions


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


async def _run_challenge_async() -> Dict[str, Any]:
    """Invoke the underlying ChallengeRunner end-to-end."""
    # Lazy import keeps --help cheap and avoids requiring httpx etc.
    from backend.agents.tools.u_agent_challenge import (  # type: ignore
        AgentAPIClient,
        ChallengeRunner,
    )

    runner = ChallengeRunner()
    async with AgentAPIClient() as api:
        summary = await runner.run_all(api)
    return summary


def _emit(report: Dict[str, Any], output: str) -> None:
    if output == "json":
        print(json.dumps(report, indent=2, default=str))
    else:  # "text" / human summary
        status = report.get("status")
        print(f"Challenge run status: {status}")
        print(f"Timestamp:            {report.get('timestamp')}")
        print(f"Overall score:        {report.get('overall_score')}")
        print(f"Total challenges:     {report.get('total_challenges', 0)}")
        print(f"Failed:               {report.get('failed', 0)}")
        if report.get("regressions"):
            print("REGRESSIONS:")
            for r in report["regressions"]:
                print(f"  - {r}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backend.agents.challenge.runner",
        description="Run the Perennia AI agent challenge suite for CI.",
    )
    parser.add_argument(
        "--output",
        choices=("json", "text"),
        default="json",
        help="Output format (default: json).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline JSON; if provided, exit 1 on regression.",
    )
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="Optional path to also write the report JSON to disk.",
    )
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        default=True,
        help="Exit 0 when credentials are missing (default).",
    )
    parser.add_argument(
        "--require-run",
        dest="allow_skip",
        action="store_false",
        help="Exit 2 if credentials are missing and the suite cannot run.",
    )
    args = parser.parse_args(argv)

    # Step 1: produce a report (either real, or a structured skip).
    if not _have_api_credentials():
        report = _empty_report(
            "missing ANTHROPIC_API_KEY or PERENNIA_API_PASS env vars"
        )
    else:
        try:
            summary = asyncio.run(_run_challenge_async())
            report = _normalize_summary(summary)
        except Exception as e:  # pragma: no cover - defensive
            report = _empty_report(f"challenge execution failed: {e}")
            report["traceback"] = traceback.format_exc()

    # Step 2: regression detection vs baseline (if provided).
    exit_code = 0
    if args.baseline is not None:
        baseline = _load_baseline(args.baseline)
        if baseline is None:
            print(
                f"[runner] WARN: baseline {args.baseline} missing/unreadable; "
                "skipping regression check.",
                file=sys.stderr,
            )
        else:
            regressions = _detect_regressions(report, baseline)
            report["regressions"] = regressions
            if regressions:
                exit_code = 1

    # Step 3: handle skip semantics.
    if report.get("status") == "skipped":
        if not args.allow_skip:
            exit_code = 2

    # Step 4: emit.
    _emit(report, args.output)
    if args.write is not None:
        try:
            args.write.parent.mkdir(parents=True, exist_ok=True)
            args.write.write_text(json.dumps(report, indent=2, default=str))
        except OSError as e:
            print(f"[runner] WARN: could not write {args.write}: {e}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
