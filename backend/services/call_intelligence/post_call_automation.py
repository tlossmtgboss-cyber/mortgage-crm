"""
Post-Call Automation Service (Domain 4)

Runs after every call ends. Handles:
1. Transcript attachment to loan file (FileCommunication record)
2. AI summary generation (< 150 words via Claude)
3. Action item extraction -> Task queue
4. Follow-up SMS draft for LO approval
5. Compliance score computation from call monitoring results
6. Sentiment summary from call timeline

Usage:
    from services.call_intelligence.post_call_automation import PostCallAutomationService

    service = PostCallAutomationService(db_session)
    results = await service.process_call_end(
        call_id="call_abc123",
        loan_id=42,
        org_id=1,
        transcript="LO: Hi, I'm calling about your loan...",
        call_metadata={"lo_user_id": 5, "borrower_name": "Jane Doe", ...},
    )
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .pii_utils import redact_transcript_for_llm

logger = logging.getLogger(__name__)

# Claude model for post-call tasks (fast model is sufficient for summaries)
POST_CALL_MODEL = os.getenv("POST_CALL_MODEL", "claude-haiku-4-5-20251001")
MAX_SUMMARY_TOKENS = 512
MAX_ACTION_ITEMS_TOKENS = 1024
MAX_SMS_TOKENS = 256

# Compliance scoring weights
COMPLIANCE_WEIGHTS = {
    "trid_disclosure": 0.25,
    "fair_lending": 0.20,
    "consent_obtained": 0.15,
    "rate_lock_accuracy": 0.15,
    "identity_verified": 0.10,
    "fee_transparency": 0.10,
    "do_not_call_respected": 0.05,
}


class PostCallAutomationService:
    """Runs after every call ends. Handles transcript, summary, tasks, follow-up."""

    SUMMARY_MAX_WORDS = 150

    def __init__(self, db: Session):
        self.db = db
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        """Lazy-init Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                if not self.anthropic_key:
                    raise ValueError("ANTHROPIC_API_KEY not set")
                self._client = anthropic.AsyncAnthropic(api_key=self.anthropic_key)
            except ImportError:
                raise ImportError("anthropic package required: pip install anthropic")
        return self._client

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_call_end(
        self,
        call_id: str,
        loan_id: int,
        org_id: int,
        transcript: str,
        call_metadata: dict,
    ) -> dict:
        """
        Main entry point. Runs all post-call steps sequentially.

        Args:
            call_id: External call identifier (e.g. Vapi/Telnyx call SID).
            loan_id: Loan file ID in the CRM.
            org_id: Organization ID (tenant isolation).
            transcript: Full call transcript text.
            call_metadata: Dict with keys like:
                - lo_user_id: int
                - borrower_name: str
                - borrower_phone: str
                - call_duration_seconds: int
                - call_direction: str  ("inbound" | "outbound")
                - compliance_results: dict  (from ComplianceMonitorCallAgent)
                - sentiment_timeline: list  (from SentimentAnalysisAgent)
                - call_outcome: str
                - lead_id: int (optional)

        Returns:
            Dict with results from each step, keyed by step name.
        """
        logger.info(
            "post_call_automation: starting for call_id=%s loan_id=%s org_id=%s",
            call_id, loan_id, org_id,
        )
        results: Dict[str, Any] = {}

        results["transcript_attached"] = await self._attach_transcript(
            call_id, loan_id, org_id, transcript, call_metadata
        )
        results["summary"] = await self._generate_summary(transcript, call_metadata)
        results["action_items"] = await self._extract_action_items(
            transcript, call_metadata, loan_id, org_id
        )
        results["followup_sms"] = await self._draft_followup_sms(
            transcript, call_metadata, loan_id, org_id
        )
        results["compliance_score"] = await self._compute_compliance_score(
            call_metadata, call_id, loan_id, org_id
        )
        results["sentiment_summary"] = await self._summarize_sentiment(
            call_metadata, call_id, loan_id, org_id
        )

        logger.info(
            "post_call_automation: completed for call_id=%s — transcript=%s summary_len=%d "
            "action_items=%d compliance=%.2f",
            call_id,
            results["transcript_attached"],
            len(results.get("summary") or ""),
            len(results.get("action_items") or []),
            results.get("compliance_score") or 0.0,
        )
        return results

    # ------------------------------------------------------------------
    # 1. Transcript attachment
    # ------------------------------------------------------------------

    async def _attach_transcript(
        self,
        call_id: str,
        loan_id: int,
        org_id: int,
        transcript: str,
        call_metadata: dict,
    ) -> bool:
        """
        Attach the full transcript to the loan file as a FileCommunication record.

        Creates a 'call' channel entry in file_communications with the raw
        transcript in the body and call metadata in the metadata JSON column.
        """
        try:
            lo_user_id = call_metadata.get("lo_user_id")
            borrower_name = call_metadata.get("borrower_name", "Borrower")
            direction = call_metadata.get("call_direction", "outbound")
            duration = call_metadata.get("call_duration_seconds", 0)

            # Build a concise subject line
            subject = f"Call transcript — {borrower_name} ({duration}s)"

            now = datetime.now(timezone.utc)

            self.db.execute(
                text("""
                    INSERT INTO file_communications
                        (organization_id, file_id, direction, channel, body, subject,
                         from_party, to_party, sender_user_id, source_id, source_table,
                         metadata, created_at)
                    VALUES
                        (:org_id, :file_id, :direction, 'call', :body, :subject,
                         :from_party, :to_party, :sender_user_id, :source_id, 'call_logs',
                         :metadata, :created_at)
                """),
                {
                    "org_id": org_id,
                    "file_id": loan_id,
                    "direction": direction,
                    "body": transcript,
                    "subject": subject,
                    "from_party": f"LO:{lo_user_id}" if direction == "outbound" else borrower_name,
                    "to_party": borrower_name if direction == "outbound" else f"LO:{lo_user_id}",
                    "sender_user_id": lo_user_id,
                    "source_id": call_id,
                    "metadata": json.dumps({
                        "call_id": call_id,
                        "duration_seconds": duration,
                        "call_direction": direction,
                        "borrower_name": borrower_name,
                        "automated_by": "post_call_automation",
                    }),
                    "created_at": now,
                },
            )
            self.db.commit()
            logger.info(
                "post_call: transcript attached to loan %s (call %s)", loan_id, call_id
            )
            return True

        except Exception as e:
            logger.exception(
                "post_call: failed to attach transcript for call %s: %s", call_id, e
            )
            self.db.rollback()
            return False

    # ------------------------------------------------------------------
    # 2. AI summary generation
    # ------------------------------------------------------------------

    async def _generate_summary(self, transcript: str, metadata: dict) -> str:
        """
        Generate a < 150 word call summary using Claude.

        The transcript is PII-redacted before being sent to the LLM.
        Returns the summary string, or an error placeholder on failure.
        """
        try:
            if not transcript or not transcript.strip():
                return ""

            redacted_transcript, _stats = redact_transcript_for_llm(transcript)

            borrower_name = metadata.get("borrower_name", "the borrower")
            call_outcome = metadata.get("call_outcome", "unknown")
            duration = metadata.get("call_duration_seconds", 0)

            client = self._get_client()
            response = await client.messages.create(
                model=POST_CALL_MODEL,
                max_tokens=MAX_SUMMARY_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Summarize this mortgage call in under {self.SUMMARY_MAX_WORDS} words. "
                            f"Borrower: {borrower_name}. Duration: {duration}s. "
                            f"Outcome: {call_outcome}.\n\n"
                            f"Focus on: key topics discussed, decisions made, "
                            f"commitments from both parties, and next steps.\n\n"
                            f"Transcript:\n{redacted_transcript}"
                        ),
                    }
                ],
                system=(
                    "You are a mortgage industry call analyst. Write concise, factual "
                    "summaries. Never include SSNs, full account numbers, or PII. "
                    "Use bullet points only if the call covers 3+ distinct topics."
                ),
            )

            summary = response.content[0].text.strip()

            # Enforce word limit — truncate if the model went over
            words = summary.split()
            if len(words) > self.SUMMARY_MAX_WORDS:
                summary = " ".join(words[: self.SUMMARY_MAX_WORDS]) + "..."

            logger.info("post_call: summary generated (%d words)", len(summary.split()))
            return summary

        except Exception as e:
            logger.exception("post_call: summary generation failed: %s", e)
            return f"[Summary generation failed: {type(e).__name__}]"

    # ------------------------------------------------------------------
    # 3. Action items extraction -> Task queue
    # ------------------------------------------------------------------

    async def _extract_action_items(
        self,
        transcript: str,
        metadata: dict,
        loan_id: int,
        org_id: int,
    ) -> list:
        """
        Parse transcript for action items and create tasks in the task queue.

        Uses Claude to extract structured action items, then inserts each as a
        Task record assigned to the LO.
        """
        try:
            if not transcript or not transcript.strip():
                return []

            redacted_transcript, _stats = redact_transcript_for_llm(transcript)
            borrower_name = metadata.get("borrower_name", "Borrower")
            lo_user_id = metadata.get("lo_user_id")
            lead_id = metadata.get("lead_id")

            client = self._get_client()
            response = await client.messages.create(
                model=POST_CALL_MODEL,
                max_tokens=MAX_ACTION_ITEMS_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Extract action items from this mortgage call transcript. "
                            "Return a JSON array where each item has:\n"
                            '  - "title": short task title (< 80 chars)\n'
                            '  - "description": what needs to be done\n'
                            '  - "owner": "lo" or "borrower"\n'
                            '  - "priority": "low", "medium", or "high"\n'
                            '  - "due_days": days from now the task should be due (1-30)\n\n'
                            f"Borrower: {borrower_name}\n\n"
                            f"Transcript:\n{redacted_transcript}\n\n"
                            "Return ONLY the JSON array, no markdown fences."
                        ),
                    }
                ],
                system=(
                    "You are a mortgage task extraction specialist. Identify concrete, "
                    "actionable items from calls — document requests, rate locks, "
                    "follow-ups, disclosures, appraisal orders, etc. Only include items "
                    "that were explicitly discussed or committed to. Return valid JSON."
                ),
            )

            raw_text = response.content[0].text.strip()
            # Strip markdown fences if the model included them anyway
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            items = json.loads(raw_text)
            if not isinstance(items, list):
                items = [items]

            now = datetime.now(timezone.utc)
            created_tasks: List[Dict[str, Any]] = []

            for item in items:
                title = str(item.get("title", "Follow-up task"))[:200]
                description = str(item.get("description", ""))
                priority = item.get("priority", "medium")
                if priority not in ("low", "medium", "high"):
                    priority = "medium"
                due_days = min(max(int(item.get("due_days", 3)), 1), 30)
                owner = item.get("owner", "lo")
                due_date = now + timedelta(days=due_days)

                # Only create CRM tasks for LO-owned items
                if owner == "lo" and lo_user_id:
                    try:
                        result = self.db.execute(
                            text("""
                                INSERT INTO tasks
                                    (organization_id, title, description, status, priority,
                                     due_date, owner_id, loan_id, lead_id, related_contact_name,
                                     related_type, created_at, updated_at)
                                VALUES
                                    (:org_id, :title, :description, 'pending', :priority,
                                     :due_date, :owner_id, :loan_id, :lead_id, :contact_name,
                                     'post_call', :now, :now)
                                RETURNING id
                            """),
                            {
                                "org_id": org_id,
                                "title": title,
                                "description": description,
                                "priority": priority,
                                "due_date": due_date,
                                "owner_id": lo_user_id,
                                "loan_id": loan_id,
                                "lead_id": lead_id,
                                "contact_name": borrower_name,
                                "now": now,
                            },
                        )
                        task_id = result.scalar()
                        self.db.commit()
                    except Exception as e:
                        logger.exception("post_call: failed to insert task '%s': %s", title, e)
                        self.db.rollback()
                        task_id = None
                else:
                    task_id = None

                created_tasks.append({
                    "task_id": task_id,
                    "title": title,
                    "owner": owner,
                    "priority": priority,
                    "due_days": due_days,
                    "description": description,
                })

            logger.info(
                "post_call: extracted %d action items (%d tasks created)",
                len(created_tasks),
                sum(1 for t in created_tasks if t.get("task_id")),
            )
            return created_tasks

        except json.JSONDecodeError as e:
            logger.exception("post_call: action item JSON parse failed: %s", e)
            return []
        except Exception as e:
            logger.exception("post_call: action item extraction failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # 4. Follow-up SMS draft
    # ------------------------------------------------------------------

    async def _draft_followup_sms(
        self,
        transcript: str,
        metadata: dict,
        loan_id: int,
        org_id: int,
    ) -> dict:
        """
        Draft a follow-up SMS for LO approval.

        The SMS is stored as a FileCommunication with ai_draft_status='pending'
        so the LO can review and send it from the UI.
        """
        try:
            if not transcript or not transcript.strip():
                return {"drafted": False, "reason": "empty_transcript"}

            redacted_transcript, _stats = redact_transcript_for_llm(transcript)
            borrower_name = metadata.get("borrower_name", "Borrower")
            lo_user_id = metadata.get("lo_user_id")
            call_outcome = metadata.get("call_outcome", "unknown")

            client = self._get_client()
            response = await client.messages.create(
                model=POST_CALL_MODEL,
                max_tokens=MAX_SMS_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Draft a short follow-up SMS (under 160 characters) from a loan officer "
                            f"to {borrower_name} after a mortgage call. "
                            f"Call outcome: {call_outcome}.\n\n"
                            "The SMS should:\n"
                            "- Be warm and professional\n"
                            "- Reference something specific from the call\n"
                            "- Include a clear next step\n"
                            "- NOT include any PII, account numbers, or rates\n\n"
                            f"Transcript excerpt (last portion):\n"
                            f"{redacted_transcript[-2000:]}\n\n"
                            "Return ONLY the SMS text, nothing else."
                        ),
                    }
                ],
                system=(
                    "You are a mortgage communication specialist. Write brief, "
                    "personable SMS messages. Keep under 160 characters. Never include "
                    "rates, SSN, or financial details in SMS."
                ),
            )

            sms_text = response.content[0].text.strip().strip('"').strip("'")

            # Enforce SMS length limit
            if len(sms_text) > 320:
                sms_text = sms_text[:317] + "..."

            # Store as a draft FileCommunication for LO approval
            now = datetime.now(timezone.utc)
            try:
                self.db.execute(
                    text("""
                        INSERT INTO file_communications
                            (organization_id, file_id, direction, channel, body,
                             from_party, to_party, sender_user_id,
                             ai_draft_response, ai_draft_status,
                             metadata, created_at)
                        VALUES
                            (:org_id, :file_id, 'outbound', 'sms', :body,
                             :from_party, :to_party, :sender_user_id,
                             :ai_draft, 'pending',
                             :metadata, :created_at)
                    """),
                    {
                        "org_id": org_id,
                        "file_id": loan_id,
                        "body": sms_text,
                        "from_party": f"LO:{lo_user_id}",
                        "to_party": borrower_name,
                        "sender_user_id": lo_user_id,
                        "ai_draft": sms_text,
                        "metadata": json.dumps({
                            "type": "post_call_followup",
                            "call_outcome": call_outcome,
                            "automated_by": "post_call_automation",
                        }),
                        "created_at": now,
                    },
                )
                self.db.commit()
            except Exception as e:
                logger.exception("post_call: failed to store SMS draft: %s", e)
                self.db.rollback()

            logger.info(
                "post_call: SMS draft created for loan %s (%d chars)", loan_id, len(sms_text)
            )
            return {
                "drafted": True,
                "sms_text": sms_text,
                "char_count": len(sms_text),
                "status": "pending_lo_approval",
            }

        except Exception as e:
            logger.exception("post_call: SMS draft generation failed: %s", e)
            return {"drafted": False, "reason": str(e)}

    # ------------------------------------------------------------------
    # 5. Compliance score
    # ------------------------------------------------------------------

    async def _compute_compliance_score(
        self,
        metadata: dict,
        call_id: str,
        loan_id: int,
        org_id: int,
    ) -> float:
        """
        Compute a weighted compliance score from call monitoring results.

        Expects metadata["compliance_results"] to contain per-category scores
        from the compliance monitoring agent. Each category is weighted per
        COMPLIANCE_WEIGHTS. Missing categories score 0.

        Returns a score between 0.0 and 1.0.
        """
        try:
            compliance_results = metadata.get("compliance_results", {})
            if not compliance_results:
                logger.info(
                    "post_call: no compliance_results in metadata for call %s, "
                    "defaulting to 0.0",
                    call_id,
                )
                return 0.0

            total_weight = 0.0
            weighted_score = 0.0

            for category, weight in COMPLIANCE_WEIGHTS.items():
                category_data = compliance_results.get(category, {})
                # Accept either a dict with "score" key or a bare float
                if isinstance(category_data, dict):
                    score = float(category_data.get("score", 0.0))
                elif isinstance(category_data, (int, float)):
                    score = float(category_data)
                else:
                    score = 0.0

                # Clamp to [0, 1]
                score = max(0.0, min(1.0, score))
                weighted_score += score * weight
                total_weight += weight

            final_score = weighted_score / total_weight if total_weight > 0 else 0.0
            final_score = round(final_score, 4)

            # Persist the score in call_logs metadata if the call_log row exists
            try:
                self.db.execute(
                    text("""
                        UPDATE call_logs
                        SET ai_note_summary = COALESCE(ai_note_summary, '') ||
                            :compliance_note
                        WHERE call_sid = :call_id
                          AND organization_id = :org_id
                    """),
                    {
                        "compliance_note": f"\n[Compliance Score: {final_score:.2%}]",
                        "call_id": call_id,
                        "org_id": org_id,
                    },
                )
                self.db.commit()
            except Exception as e:
                logger.exception(
                    "post_call: failed to persist compliance score for call %s: %s",
                    call_id, e,
                )
                self.db.rollback()

            logger.info(
                "post_call: compliance score for call %s = %.4f", call_id, final_score
            )
            return final_score

        except Exception as e:
            logger.exception("post_call: compliance score computation failed: %s", e)
            return 0.0

    # ------------------------------------------------------------------
    # 6. Sentiment summary
    # ------------------------------------------------------------------

    async def _summarize_sentiment(
        self,
        metadata: dict,
        call_id: str,
        loan_id: int,
        org_id: int,
    ) -> dict:
        """
        Summarize overall call sentiment from the SentimentAnalysisAgent timeline.

        Expects metadata["sentiment_timeline"] as a list of dicts, each with:
            - timestamp: seconds into the call
            - sentiment: "positive" | "neutral" | "hesitant" | "negative"
            - text_snippet: what was said (optional)

        Returns a dict with overall sentiment, trajectory, and flags.
        """
        try:
            timeline = metadata.get("sentiment_timeline", [])
            if not timeline:
                logger.info(
                    "post_call: no sentiment_timeline for call %s, returning neutral",
                    call_id,
                )
                return {
                    "overall": "neutral",
                    "trajectory": "stable",
                    "negative_moments": 0,
                    "positive_moments": 0,
                    "risk_flag": False,
                }

            # Sentiment value mapping for aggregation
            sentiment_values = {
                "positive": 1.0,
                "neutral": 0.5,
                "hesitant": 0.25,
                "negative": 0.0,
            }

            scores = []
            negative_count = 0
            positive_count = 0

            for entry in timeline:
                sentiment = str(entry.get("sentiment", "neutral")).lower()
                value = sentiment_values.get(sentiment, 0.5)
                scores.append(value)
                if sentiment == "negative":
                    negative_count += 1
                elif sentiment == "positive":
                    positive_count += 1

            # Overall sentiment
            avg_score = sum(scores) / len(scores) if scores else 0.5
            if avg_score >= 0.75:
                overall = "positive"
            elif avg_score >= 0.45:
                overall = "neutral"
            elif avg_score >= 0.2:
                overall = "hesitant"
            else:
                overall = "negative"

            # Trajectory: compare first half vs second half
            midpoint = len(scores) // 2 if len(scores) > 1 else 1
            first_half_avg = sum(scores[:midpoint]) / midpoint if midpoint > 0 else 0.5
            second_half_avg = (
                sum(scores[midpoint:]) / len(scores[midpoint:])
                if len(scores[midpoint:]) > 0
                else 0.5
            )
            diff = second_half_avg - first_half_avg
            if diff > 0.15:
                trajectory = "improving"
            elif diff < -0.15:
                trajectory = "declining"
            else:
                trajectory = "stable"

            # Risk flag: call ended negative or had 3+ negative moments
            last_sentiment = str(timeline[-1].get("sentiment", "neutral")).lower()
            risk_flag = last_sentiment == "negative" or negative_count >= 3

            result = {
                "overall": overall,
                "trajectory": trajectory,
                "avg_score": round(avg_score, 3),
                "negative_moments": negative_count,
                "positive_moments": positive_count,
                "total_checkpoints": len(scores),
                "risk_flag": risk_flag,
            }

            # Persist sentiment summary to call_logs
            try:
                self.db.execute(
                    text("""
                        UPDATE call_logs
                        SET ai_note_summary = COALESCE(ai_note_summary, '') ||
                            :sentiment_note
                        WHERE call_sid = :call_id
                          AND organization_id = :org_id
                    """),
                    {
                        "sentiment_note": (
                            f"\n[Sentiment: {overall} | Trajectory: {trajectory} | "
                            f"Risk: {'YES' if risk_flag else 'no'}]"
                        ),
                        "call_id": call_id,
                        "org_id": org_id,
                    },
                )
                self.db.commit()
            except Exception as e:
                logger.exception(
                    "post_call: failed to persist sentiment for call %s: %s",
                    call_id, e,
                )
                self.db.rollback()

            logger.info(
                "post_call: sentiment for call %s — overall=%s trajectory=%s risk=%s",
                call_id, overall, trajectory, risk_flag,
            )
            return result

        except Exception as e:
            logger.exception("post_call: sentiment summarization failed: %s", e)
            return {
                "overall": "unknown",
                "trajectory": "unknown",
                "negative_moments": 0,
                "positive_moments": 0,
                "risk_flag": False,
                "error": str(e),
            }
