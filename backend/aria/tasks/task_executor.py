"""
aria/tasks/task_executor.py
Perennia AI — Aria Task Executor

Maps resolved intents + slots to real actions:
document generation, email/SMS sending, CRM updates, etc.

Each handler is an async function that receives the collected slots
and returns a result dict describing what was done.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from aria.documents.document_generator import DocumentGenerator
from aria.tools.crm_tools import CRMTools
from aria.tools.communication_tools import CommunicationTools
from aria.tools.pipeline_tools import PipelineTools
from aria.tools.knowledge_tools import KnowledgeTools

logger = logging.getLogger(__name__)


class TaskExecutor:
    def __init__(self):
        self.docs   = DocumentGenerator()
        self.crm    = CRMTools()
        self.comms  = CommunicationTools()
        self.pipe   = PipelineTools()
        self.know   = KnowledgeTools()

        self._handlers = {
            "send_preapproval_letter":    self._send_preapproval_letter,
            "send_conditional_approval":  self._send_conditional_approval,
            "send_adverse_action_notice": self._send_adverse_action_notice,
            "generate_loe":               self._generate_loe,
            "send_sms":                   self._send_sms,
            "send_email":                 self._send_email,
            "schedule_call":              self._schedule_call,
            "update_loan_status":         self._update_loan_status,
            "add_loan_note":              self._add_loan_note,
            "create_task":                self._create_task,
            "request_documents":          self._request_documents,
            "loan_status_lookup":         self._loan_status_lookup,
            "mortgage_guideline_question":self._guideline_question,
            "pipeline_report":            self._pipeline_report,
            "run_income_analysis":        self._income_analysis,
        }

    async def execute(
        self, intent: str, slots: Dict[str, Any],
        user_id: str, org_id: str,
    ) -> Dict[str, Any]:
        handler = self._handlers.get(intent)
        if not handler:
            raise ValueError(f"No handler registered for intent: {intent}")

        logger.info(f"Executing intent={intent} user={user_id} slots={list(slots.keys())}")
        return await handler(slots=slots, user_id=user_id, org_id=org_id)

    # ── Document handlers ───────────────────────────────────────────────────

    async def _send_preapproval_letter(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        if not borrower:
            raise ValueError(f"Borrower not found: {slots['borrower_id']}")

        loan = await self.crm.get_active_loan(borrower["id"], org_id)
        lo   = await self.crm.get_user(user_id)

        doc_result = await self.docs.generate_preapproval_letter(
            borrower=borrower, loan=loan, lo=lo,
            approval_amount=float(slots["approval_amount"]),
            property_address=slots.get("property_address"),
            expiry_days=int(slots.get("expiry_days", 30)),
            custom_note=slots.get("custom_note"),
        )

        sent = await self.comms.send_email(
            to_email=slots["recipient_email"],
            to_name=slots.get("recipient_name", ""),
            from_user=lo,
            subject=f"Pre-Approval Letter — {borrower['full_name']}",
            body=self._preapproval_email_body(borrower, slots, lo),
            attachments=[{
                "filename": f"PreApproval_{borrower['last_name']}_{slots['approval_amount']}.pdf",
                "content":  doc_result["pdf_bytes"],
                "content_type": "application/pdf",
            }],
        )

        await self.pipe.add_note(
            loan_id=loan["id"], user_id=user_id,
            note=f"Pre-approval letter sent to {slots['recipient_email']} "
                 f"for ${slots['approval_amount']:,.0f}. "
                 f"Email message ID: {sent['message_id']}",
            note_type="document_sent",
        )

        return {
            "action": "pre_approval_letter_sent",
            "borrower_name": borrower["full_name"],
            "recipient_email": slots["recipient_email"],
            "amount": slots["approval_amount"],
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "message_id": sent["message_id"],
            "loan_id": loan["id"],
            "document_id": doc_result["document_id"],
        }

    def _preapproval_email_body(self, borrower, slots, lo) -> str:
        name = slots.get("recipient_name") or "Agent"
        return (
            f"Hi {name},\n\n"
            f"Please find attached the pre-approval letter for {borrower['full_name']}.\n\n"
            f"They are pre-approved up to ${float(slots['approval_amount']):,.0f}. "
            f"Please don't hesitate to reach out with any questions.\n\n"
            f"Best regards,\n{lo['full_name']}\n{lo.get('nmls_number', '')}"
        )

    async def _send_conditional_approval(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        loan     = await self.crm.get_active_loan(borrower["id"], org_id)
        lo       = await self.crm.get_user(user_id)

        doc_result = await self.docs.generate_conditional_approval(
            borrower=borrower, loan=loan, lo=lo,
            conditions=slots["conditions"], due_date=slots.get("due_date"),
        )

        sent = await self.comms.send_email(
            to_email=slots["recipient_email"], to_name=slots.get("recipient_name", ""),
            from_user=lo,
            subject=f"Conditional Approval — {borrower['full_name']}",
            body=f"Please find attached the conditional approval letter for {borrower['full_name']}.",
            attachments=[{"filename": f"ConditionalApproval_{borrower['last_name']}.pdf",
                          "content": doc_result["pdf_bytes"], "content_type": "application/pdf"}],
        )

        await self.pipe.add_note(loan["id"], user_id,
            f"Conditional approval sent to {slots['recipient_email']}", "document_sent")
        await self.pipe.update_status(loan["id"], "conditional_approval", user_id)

        return {"action": "conditional_approval_sent", "borrower_name": borrower["full_name"],
                "recipient_email": slots["recipient_email"], "sent_at": datetime.now(timezone.utc).isoformat()}

    async def _send_adverse_action_notice(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        lo       = await self.crm.get_user(user_id)

        doc_result = await self.docs.generate_adverse_action_notice(
            borrower=borrower, lo=lo,
            denial_reasons=slots["denial_reasons"],
            credit_score=int(slots["credit_score"]),
        )

        sent = await self.comms.send_email(
            to_email=borrower["email"], to_name=borrower["full_name"],
            from_user=lo,
            subject="Notice of Adverse Action",
            body="Please find attached your Notice of Adverse Action.",
            attachments=[{"filename": "AdverseActionNotice.pdf",
                          "content": doc_result["pdf_bytes"], "content_type": "application/pdf"}],
        )

        return {"action": "adverse_action_sent", "borrower_name": borrower["full_name"],
                "sent_at": datetime.now(timezone.utc).isoformat()}

    async def _generate_loe(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        lo       = await self.crm.get_user(user_id)

        doc_result = await self.docs.generate_loe(
            borrower=borrower, lo=lo,
            topic=slots["loe_topic"], details=slots.get("details", ""),
        )

        return {
            "action": "loe_generated",
            "borrower_name": borrower["full_name"],
            "topic": slots["loe_topic"],
            "document_id": doc_result["document_id"],
            "preview_text": doc_result["preview_text"],
            "note": "LOE saved to loan file. Ready to attach to underwriter submission.",
        }

    # ── Communication handlers ───────────────────────────────────────────────

    async def _send_sms(self, slots, user_id, org_id) -> Dict:
        contact = await self.crm.resolve_contact(slots["recipient"], org_id)
        lo      = await self.crm.get_user(user_id)

        result = await self.comms.send_sms(
            to_phone=contact["phone"], from_user=lo,
            message=slots["message"], org_id=org_id,
        )

        return {"action": "sms_sent", "to": contact["name"],
                "phone": contact["phone"], "sent_at": result["sent_at"]}

    async def _send_email(self, slots, user_id, org_id) -> Dict:
        contact = await self.crm.resolve_contact(slots["recipient"], org_id)
        lo      = await self.crm.get_user(user_id)

        result = await self.comms.send_email(
            to_email=contact["email"], to_name=contact["name"],
            from_user=lo, subject=slots["subject"], body=slots["body"],
        )

        return {"action": "email_sent", "to": contact["name"],
                "email": contact["email"], "sent_at": result["sent_at"]}

    async def _schedule_call(self, slots, user_id, org_id) -> Dict:
        contact = await self.crm.resolve_contact(slots["with_person"], org_id)
        lo      = await self.crm.get_user(user_id)

        result = await self.comms.schedule_call(
            with_contact=contact, lo=lo,
            date=slots["call_date"], time=slots["call_time"],
            duration_minutes=int(slots.get("duration_minutes", 30)),
            topic=slots.get("call_topic", ""),
        )

        return {"action": "call_scheduled", "with": contact["name"],
                "datetime": result["datetime"], "calendar_link": result.get("calendar_link")}

    # ── Pipeline handlers ────────────────────────────────────────────────────

    async def _update_loan_status(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        loan     = await self.crm.get_active_loan(borrower["id"], org_id)
        prev_stage = loan.get("stage")

        await self.pipe.update_status(loan["id"], slots["new_stage"], user_id)
        await self.pipe.add_note(loan["id"], user_id,
            f"Stage updated: {prev_stage} → {slots['new_stage']}", "status_change")

        return {"action": "status_updated", "borrower_name": borrower["full_name"],
                "from_stage": prev_stage, "to_stage": slots["new_stage"]}

    async def _add_loan_note(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        loan     = await self.crm.get_active_loan(borrower["id"], org_id)

        note = await self.pipe.add_note(loan["id"], user_id, slots["note_text"], "manual")

        return {"action": "note_added", "borrower_name": borrower["full_name"],
                "note_id": note["id"], "added_at": note["created_at"]}

    async def _create_task(self, slots, user_id, org_id) -> Dict:
        task = await self.pipe.create_task(
            description=slots["task_description"],
            due_date=slots["due_date"],
            assigned_to=slots.get("assigned_to", user_id),
            borrower_id=slots.get("borrower_id"),
            created_by=user_id, org_id=org_id,
        )

        return {"action": "task_created", "task_id": task["id"],
                "description": slots["task_description"], "due_date": slots["due_date"]}

    async def _request_documents(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        loan     = await self.crm.get_active_loan(borrower["id"], org_id)

        result = await self.pipe.send_document_request(
            loan_id=loan["id"], borrower=borrower,
            doc_list=slots["doc_list"], due_date=slots.get("due_date"),
            note=slots.get("note"), requested_by=user_id,
        )

        return {"action": "document_request_sent", "borrower_name": borrower["full_name"],
                "portal_link": result["portal_link"], "docs_requested": slots["doc_list"]}

    # ── Lookup/analysis handlers ─────────────────────────────────────────────

    async def _loan_status_lookup(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        loan     = await self.crm.get_active_loan(borrower["id"], org_id)
        tasks    = await self.pipe.get_open_tasks(loan["id"])
        docs     = await self.pipe.get_document_status(loan["id"])

        return {
            "borrower_name": borrower["full_name"],
            "loan_amount":   loan.get("loan_amount"),
            "stage":         loan.get("stage"),
            "sla_days_remaining": loan.get("sla_days_remaining"),
            "open_tasks":    len(tasks),
            "missing_docs":  [d["name"] for d in docs if not d["received"]],
            "last_activity": loan.get("last_activity_at"),
        }

    async def _guideline_question(self, slots, user_id, org_id) -> Dict:
        answer = await self.know.answer_guideline_question(slots["question"])
        return {"answer": answer["text"], "sources": answer.get("sources", []),
                "confidence": answer.get("confidence")}

    async def _pipeline_report(self, slots, user_id, org_id) -> Dict:
        report = await self.pipe.generate_report(
            user_id=user_id, org_id=org_id,
            time_period=slots.get("time_period", "this month"),
            filter_by=slots.get("filter_by"),
        )
        return report

    async def _income_analysis(self, slots, user_id, org_id) -> Dict:
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        loan     = await self.crm.get_active_loan(borrower["id"], org_id)
        result   = await self.know.run_income_analysis(loan["id"], org_id)
        return {"borrower_name": borrower["full_name"], **result}
