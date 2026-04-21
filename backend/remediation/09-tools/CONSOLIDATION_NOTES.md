# Tool Consolidation Framework

**Not in scope for this PR.** This document is the playbook for a future PR
once the telemetry from the router (stage 09) has 30+ days of data.

## When to Deprecate a Tool

A tool is a candidate for deprecation when any of:

- **Zero invocations in 30 days across all customers.** Dead code in prod.
- **<5 invocations in 30 days AND a more general tool exists that covers the case.** Low-value specialization.
- **100% of invocations happen alongside another tool in the same turn.** The pair should probably be one composite tool.
- **Error rate >20% AND low usage.** Broken and nobody noticed — rip it out.

## When NOT to Deprecate

- **High error rate on an important tool.** Fix the tool, don't delete it.
- **Infrequent but critical path.** "Used twice a month by underwriters to override AUS" is not a candidate for deletion even if the number is small.
- **Compliance-required paths.** Credit report pulls, adverse action notices, etc., may have low volume but are legally required to exist.

## Process

1. Query `agent_tool_invocations` table for the 30-day window.
2. Generate the candidate list with `scripts/tool_usage_report.py --days=30 --candidates`.
3. Manually review each candidate. Write a justification for deletion OR keep.
4. Mark deprecated in registry: `deprecated=True, deprecation_replacement="<other_tool>"`.
5. Monitor for 30 days. If no customer complaints and continued zero usage, delete.

## Goal

Target state: 255 tools today → ~180 in six months, without breaking workflows.
Consolidation is a continuous process, not a one-time rewrite.
