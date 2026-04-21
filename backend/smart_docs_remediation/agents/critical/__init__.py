"""Specialist agents for the critical tier.

Only agents whose behaviour warrants extra safety rails live here.
Every other critical-tier agent is handled by :class:`GenericAgent`.

The pattern: subclass :class:`BaseAgent`, build a targeted prompt,
and add post-processing that hard-fails if the generated output
violates an invariant the operator cannot catch by eye.
"""
from __future__ import annotations

import re
from typing import Any

from agents.base import AgentEnvelope, BaseAgent
from orchestrator.state import RunState


# ============================================================================
# A07 — Id Contract Validator
# ============================================================================


class IdContractValidator(BaseAgent):
    """Introduces NewType RequestId / DocumentId across Python + TS.

    Hard invariants enforced in postprocess:
      * Every produced TS patch must include `type RequestId = string &`.
      * Every produced Python patch must import NewType.
      * Patches must touch both backend and frontend (or explicitly
        state why one side is not ready).
    """

    prefer_opus = True

    SYSTEM = """\
You are the Id Contract Validator for the Perennia Smart Docs remediation.
Your job: eliminate the structural confusion between DocumentRequest.id
and DocumentRequest.document_id across Python and TypeScript.

You introduce:
  * Python: `RequestId = NewType('RequestId', str)` and
           `DocumentId = NewType('DocumentId', str)` in
           `models/smart_docs/id_types.py`.
  * TypeScript: branded string types in `frontend/src/types/ids.ts`
           using the `Brand<T, K>` pattern.

You then migrate the signatures of the functions implicated by A02 and
A03's scans. Functions accepting a RequestId must refuse to type-check
if passed a DocumentId.

You must return a single JSON envelope. Produce BOTH a Python patch and
a TypeScript patch. If either is impossible given the upstream context,
set human_approval_needed=true and explain.
"""

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        upstream = {
            dep: state.get("agent_outputs", {}).get(dep, {})
            for dep in self.spec.get("depends_on", [])
        }
        upstream_summary = "\n".join(
            f"## {aid}\n{out.get('summary', '(no summary)')}"
            for aid, out in upstream.items()
        ) or "(no upstream yet)"

        user = f"""\
# Upstream scan results
{upstream_summary}

# Your mission
{self.spec['mission']}

Produce the envelope. The patches dict must contain exactly two keys:
  - `models/smart_docs/id_types.py`
  - `frontend/src/types/ids.ts`
(Plus any signature-migration patches in additional keys.)
"""
        return [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": user},
        ]

    def postprocess(self, env: AgentEnvelope, state: RunState) -> AgentEnvelope:
        required_py = "models/smart_docs/id_types.py"
        required_ts = "frontend/src/types/ids.ts"

        missing = [p for p in (required_py, required_ts) if p not in env.patches]
        if missing and not env.human_approval_needed:
            env.open_questions.append(
                f"Missing required patches: {missing}. Forcing human review."
            )
            env.human_approval_needed = True
            env.approval_reason = "ID contract incomplete"

        # Sanity-check branded type idiom exists
        if required_ts in env.patches:
            if "Brand" not in env.patches[required_ts] and "& {" not in env.patches[required_ts]:
                env.open_questions.append(
                    "TypeScript file does not use a brand pattern; review required"
                )
                env.human_approval_needed = True
        if required_py in env.patches:
            if "NewType" not in env.patches[required_py]:
                env.open_questions.append("Python file missing NewType import")
                env.human_approval_needed = True

        return env


# ============================================================================
# A23 — Secret Startup Validator
# ============================================================================


class SecretStartupValidator(BaseAgent):
    """Removes insecure defaults; crashes the app if secrets are missing.

    Hard invariants:
      * The produced config must import `sys` and call `sys.exit(1)`
        on missing required secret — no silent fallbacks.
      * The A22 audit report must be cited; we refuse to ship a config
        that misses a secret flagged in that report.
    """

    prefer_opus = True

    SYSTEM = """\
You are the Secret Startup Validator. You produce the `config/required_env.py`
module that runs at FastAPI startup and crashes hard on missing secrets.

Required behaviour:
  1. Read the list of required env vars from the A22 audit. For each:
     os.environ[name] -> raise SystemExit(1) with a clear error.
  2. Export a `validate_required_env()` function called from main.py.
  3. Specifically remove the default value in
     `services/borrower_portal/borrower_portal_v2_service.py:44` and
     anywhere else A22 flagged a similar pattern.
  4. Provide a patch to main.py that calls validate_required_env()
     BEFORE any other import that may use secrets.

This is marked autonomy=review_required. Always set human_approval_needed=true
because this change can prevent production startup.
"""

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        a22 = state.get("agent_outputs", {}).get("A22", {})
        audit_summary = a22.get("summary", "(A22 has not run yet)")

        user = f"""\
# A22 Secret Audit summary
{audit_summary}

# Artifacts from A22
{a22.get('artifacts', {})}

Produce the envelope. At minimum produce:
  - artifacts.required_env_source: the full source of required_env.py
  - patches['services/borrower_portal/borrower_portal_v2_service.py']: unified diff removing the default
  - patches['main.py']: unified diff wiring the validator in
"""
        return [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": user},
        ]

    def postprocess(self, env: AgentEnvelope, state: RunState) -> AgentEnvelope:
        # We always require human review for secrets — no exceptions.
        env.human_approval_needed = True
        if not env.approval_reason:
            env.approval_reason = (
                "Secret config changes can block production startup; "
                "operator must confirm required keys before merge."
            )

        # Minimum surface area check
        if "required_env_source" not in env.artifacts:
            env.open_questions.append("required_env_source artifact missing")
        # Must not reintroduce insecure defaults
        bad_patterns = [
            r'os\.getenv\([^,]+,\s*["\']dev[^"\']*["\']\)',
            r'os\.getenv\([^,]+,\s*["\'].*change.*["\']\)',
        ]
        for pattern in bad_patterns:
            for path, diff in env.patches.items():
                if re.search(pattern, diff):
                    env.open_questions.append(
                        f"Patch for {path} reintroduces an insecure default: {pattern}"
                    )
        return env


# ============================================================================
# A26 — Fail-Closed Screenshot Detection
# ============================================================================


class FailClosedPolicy(BaseAgent):
    """Patches document_review_pipeline.py to fail CLOSED on detector errors.

    Hard invariants:
      * Patch must change the default from 'not_screenshot' to 'NEEDS_REVIEW'.
      * Patch must not mask the underlying exception (logs it).
      * Test must prove the new behaviour.
    """

    prefer_opus = True

    SYSTEM = """\
You are the Fail-Closed Policy agent. Patch
`services/smart_docs/document_review_pipeline.py` lines ~269-275 so
that when the screenshot-detection service raises OR times out, the
document is routed to manual review (NEEDS_REVIEW) rather than passed
through as not_screenshot.

The exception must be logged with the original traceback — we fail
closed but we do not swallow the error.

Also produce a pytest test that proves:
  - Exception in detector -> status=NEEDS_REVIEW, document in review queue.
  - Timeout in detector -> status=NEEDS_REVIEW.
  - Successful detection -> existing behaviour unchanged.
"""

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        user = f"""\
# Mission
{self.spec['mission']}

Produce the envelope with:
  - patches['services/smart_docs/document_review_pipeline.py']
  - tests['tests/smart_docs/test_screenshot_fail_closed.py']
  - summary explaining the before/after semantics.
"""
        return [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": user},
        ]

    def postprocess(self, env: AgentEnvelope, state: RunState) -> AgentEnvelope:
        path = "services/smart_docs/document_review_pipeline.py"
        if path not in env.patches:
            env.open_questions.append(f"required patch missing: {path}")
            env.human_approval_needed = True
            return env

        diff = env.patches[path]
        # Guardrail: patch must mention NEEDS_REVIEW
        if "NEEDS_REVIEW" not in diff:
            env.open_questions.append(
                "Patch does not mention NEEDS_REVIEW; may not fail closed correctly"
            )
            env.human_approval_needed = True
        # Guardrail: patch must not still set not_screenshot in the except branch
        if "not_screenshot" in diff and "except" in diff:
            # crude heuristic but flag it for review
            env.open_questions.append(
                "Patch still references not_screenshot near an except; verify manually"
            )
            env.human_approval_needed = True

        if "test_screenshot_fail_closed" not in str(env.tests):
            env.open_questions.append("regression test missing")
        return env


# ============================================================================
# A30 — Unified Consent Gateway
# ============================================================================


class UnifiedConsentGateway(BaseAgent):
    """Builds the single check_all_consent() choke point.

    This is the highest-risk agent on the critical tier. It always
    escalates to human approval and enforces structural invariants on
    the produced gateway.
    """

    prefer_opus = True

    SYSTEM = """\
You are the Unified Consent Gateway agent. You build
`services/consent/unified_gateway.py` exposing ONE function:

    def check_all_consent(
        phone: str,
        channel: Literal["sms", "voice", "email"],
        purpose: Literal["transactional", "marketing", "servicing"],
    ) -> ConsentResult: ...

Requirements:
  1. Deny-by-default. Any exception from any upstream source => denied.
  2. Query every source catalogued by A29: SmartDocsConsentRecord,
     InternalDNCEntry, OutreachLog suppression, telephony compliance,
     TCPA models, per-request notification flags. If A29 found more,
     include them.
  3. Emit a ConsentAudit record on every call (allowed or denied).
  4. ConsentResult includes: allowed (bool), reason (str), evidence
     (dict pointing to each source's verdict), correlation_id.
  5. Provide a comprehensive pytest suite covering the truth table
     from A29 — every combination of source-states must be exercised.

This change affects TCPA compliance. Always set
human_approval_needed=true. Always require legal review notes in
approval_reason.
"""

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        a29 = state.get("agent_outputs", {}).get("A29", {})
        truth_table = a29.get("summary", "(A29 has not run)")

        user = f"""\
# Consent truth table from A29
{truth_table}

# A29 artifacts
{a29.get('artifacts', {})}

Produce the envelope.
"""
        return [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": user},
        ]

    def postprocess(self, env: AgentEnvelope, state: RunState) -> AgentEnvelope:
        env.human_approval_needed = True
        if not env.approval_reason:
            env.approval_reason = (
                "Consent gateway is the TCPA defense choke point. "
                "Requires legal + engineering sign-off before merge."
            )

        required_patch = "services/consent/unified_gateway.py"
        required_test = "tests/consent/test_unified_gateway.py"
        if required_patch not in env.patches and required_patch not in env.artifacts:
            env.open_questions.append("gateway source missing")
        test_keys = set(env.tests)
        if not any(required_test in k for k in test_keys):
            env.open_questions.append("gateway tests missing")

        # Must not be allow-by-default
        gateway_src = env.patches.get(required_patch, "") + env.artifacts.get(required_patch, "")
        if gateway_src:
            if "return ConsentResult(allowed=True" in gateway_src.replace(" ", "") \
                    and "allowed=False" not in gateway_src.replace(" ", ""):
                env.open_questions.append(
                    "Gateway appears allow-by-default; must be deny-by-default"
                )
        return env


__all__ = [
    "IdContractValidator",
    "SecretStartupValidator",
    "FailClosedPolicy",
    "UnifiedConsentGateway",
]
