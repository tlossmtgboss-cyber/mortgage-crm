"""
Approval Chain Service (Smart Docs V2 Enterprise)

Configurable multi-step approval workflows with delegation, timeout
handling, separation-of-duties enforcement, and analytics.

Features:
    - Multi-step sequential approval chains
    - Parallel approval (any of N approvers)
    - Conditional steps (skip based on loan amount, AI confidence, etc.)
    - Auto-approve rules for low-risk items
    - Maker-checker enforcement (cannot approve own work)
    - Out-of-office and permanent delegation with audit trail
    - Configurable timeout with escalation / auto-approve / auto-reject
    - Bulk approval with individual audit entries
    - Conditional approval (approved with conditions attached)
    - Approval dashboard and analytics

Usage:
    from services.smart_docs.enterprise.approval_chain_service import (
        ApprovalChainService,
    )

    svc = ApprovalChainService(db=db, org_id=1)
    request = await svc.submit_for_approval(
        approval_type="INCOME_APPROVAL",
        entity_type="income_calculation",
        entity_id=42,
        loan_id=100,
        user_id=5,
        context={"justification": "Amended tax return received"},
    )

    result = await svc.make_decision(
        request_id=request.id,
        user_id=8,
        decision="APPROVED",
        comments="Verified against amended 1040",
    )
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, and_, or_, case, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# LAZY IMPORTS (avoid circular dependencies at module load time)
# =============================================================================

def _get_models():
    from database.models.approval_chain import (
        ApprovalChainConfig,
        ApprovalRequest,
        ApprovalDecision,
        ApprovalDelegation,
    )
    return ApprovalChainConfig, ApprovalRequest, ApprovalDecision, ApprovalDelegation


# =============================================================================
# CONSTANTS
# =============================================================================

VALID_APPROVAL_TYPES = {
    "INCOME_APPROVAL",
    "DOCUMENT_APPROVAL",
    "EXCEPTION_APPROVAL",
    "FRAUD_CLEARANCE",
    "CONDITION_WAIVER",
    "PACKAGE_APPROVAL",
    "HIGH_VALUE_APPROVAL",
}

VALID_DECISIONS = {"APPROVED", "REJECTED", "RETURNED"}

VALID_STATUSES = {
    "PENDING", "IN_PROGRESS", "APPROVED", "REJECTED", "TIMED_OUT", "CANCELLED",
}

TERMINAL_STATUSES = {"APPROVED", "REJECTED", "TIMED_OUT", "CANCELLED"}

VALID_ENTITY_TYPES = {
    "document", "income_calc", "condition", "exception", "package",
    "income_calculation", "fraud_alert",
}

VALID_TIMEOUT_ACTIONS = {"escalate", "auto_approve", "auto_reject"}

# Role-to-user lookup queries (org-scoped)
ROLE_LOOKUP_QUERIES: Dict[str, str] = {
    "processor": """
        SELECT ltm.user_id
        FROM loan_team_members ltm
        WHERE ltm.loan_id = :loan_id AND ltm.role = 'processor'
        LIMIT 1
    """,
    "underwriter": """
        SELECT ltm.user_id
        FROM loan_team_members ltm
        WHERE ltm.loan_id = :loan_id AND ltm.role = 'underwriter'
        LIMIT 1
    """,
    "manager": """
        SELECT u.reports_to_id AS user_id
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.id = :loan_id AND l.organization_id = :org_id
        LIMIT 1
    """,
    "senior_compliance": """
        SELECT u.id AS user_id
        FROM users u
        WHERE u.organization_id = :org_id AND u.role = 'senior_compliance'
        LIMIT 1
    """,
    "chief_underwriter": """
        SELECT u.id AS user_id
        FROM users u
        WHERE u.organization_id = :org_id AND u.role = 'chief_underwriter'
        LIMIT 1
    """,
    "vp": """
        SELECT u.id AS user_id
        FROM users u
        WHERE u.organization_id = :org_id AND u.role = 'vp_operations'
        LIMIT 1
    """,
    "compliance": """
        SELECT ltm.user_id
        FROM loan_team_members ltm
        WHERE ltm.loan_id = :loan_id AND ltm.role = 'compliance'
        LIMIT 1
    """,
    "loan_officer": """
        SELECT l.loan_officer_id AS user_id
        FROM loans l
        WHERE l.id = :loan_id AND l.organization_id = :org_id
    """,
}

# Built-in chain templates seeded per-org on first use
DEFAULT_CHAIN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "chain_name": "Income Approval - Standard",
        "approval_type": "INCOME_APPROVAL",
        "conditions": None,
        "steps": [
            {"step": 1, "approver_type": "role", "approver": "processor", "required": True},
            {"step": 2, "approver_type": "role", "approver": "underwriter", "required": True},
        ],
        "auto_approve_conditions": {"ai_confidence_above": 0.95, "amount_below": 100000},
        "timeout_hours": 24,
        "timeout_action": "escalate",
    },
    {
        "chain_name": "Document Exception",
        "approval_type": "EXCEPTION_APPROVAL",
        "conditions": None,
        "steps": [
            {"step": 1, "approver_type": "role", "approver": "processor", "required": True},
            {"step": 2, "approver_type": "role", "approver": "manager", "required": True},
        ],
        "auto_approve_conditions": None,
        "timeout_hours": 48,
        "timeout_action": "escalate",
    },
    {
        "chain_name": "Fraud Clearance",
        "approval_type": "FRAUD_CLEARANCE",
        "conditions": None,
        "steps": [
            {"step": 1, "approver_type": "role", "approver": "compliance", "required": True},
            {"step": 2, "approver_type": "role", "approver": "senior_compliance", "required": True},
        ],
        "auto_approve_conditions": None,
        "timeout_hours": 12,
        "timeout_action": "escalate",
    },
    {
        "chain_name": "High-Value Loan Approval (>$1M)",
        "approval_type": "HIGH_VALUE_APPROVAL",
        "conditions": {"min_loan_amount": 1000000},
        "steps": [
            {"step": 1, "approver_type": "role", "approver": "underwriter", "required": True},
            {"step": 2, "approver_type": "role", "approver": "chief_underwriter", "required": True},
            {"step": 3, "approver_type": "role", "approver": "vp", "required": True},
        ],
        "auto_approve_conditions": None,
        "timeout_hours": 48,
        "timeout_action": "escalate",
    },
    {
        "chain_name": "Condition Waiver",
        "approval_type": "CONDITION_WAIVER",
        "conditions": None,
        "steps": [
            {"step": 1, "approver_type": "role", "approver": "underwriter", "required": True},
            {"step": 2, "approver_type": "role", "approver": "chief_underwriter", "required": True},
        ],
        "auto_approve_conditions": None,
        "timeout_hours": 24,
        "timeout_action": "escalate",
    },
]


# =============================================================================
# SERVICE
# =============================================================================

class ApprovalChainService:
    """Async approval chain service with org-level isolation.

    All queries are scoped to ``self.org_id`` to enforce multi-tenant
    boundaries at the service layer.
    """

    def __init__(self, db: Session, org_id: int):
        if not org_id:
            raise ValueError("org_id is required for ApprovalChainService")
        self.db = db
        self.org_id = org_id

    # ------------------------------------------------------------------
    # CHAIN CONFIGURATION
    # ------------------------------------------------------------------

    async def ensure_default_chains(self) -> int:
        """Seed default approval chain templates for this org if none exist.

        Returns the number of chains created (0 if already seeded).
        """
        ApprovalChainConfig, _, _, _ = _get_models()

        existing_count = (
            self.db.query(func.count(ApprovalChainConfig.id))
            .filter(ApprovalChainConfig.organization_id == self.org_id)
            .scalar()
        )
        if existing_count > 0:
            return 0

        created = 0
        for template in DEFAULT_CHAIN_TEMPLATES:
            chain = ApprovalChainConfig(
                organization_id=self.org_id,
                chain_name=template["chain_name"],
                approval_type=template["approval_type"],
                conditions=template.get("conditions"),
                steps=template["steps"],
                auto_approve_conditions=template.get("auto_approve_conditions"),
                timeout_hours=template.get("timeout_hours", 24),
                timeout_action=template.get("timeout_action", "escalate"),
                is_active=True,
            )
            self.db.add(chain)
            created += 1

        self.db.flush()
        logger.info(
            "Seeded %d default approval chains for org %d", created, self.org_id,
        )
        return created

    async def get_chains(
        self,
        approval_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List["ApprovalChainConfig"]:
        """List approval chain configs for this org."""
        ApprovalChainConfig, _, _, _ = _get_models()

        query = self.db.query(ApprovalChainConfig).filter(
            ApprovalChainConfig.organization_id == self.org_id,
        )
        if approval_type:
            query = query.filter(ApprovalChainConfig.approval_type == approval_type)
        if active_only:
            query = query.filter(ApprovalChainConfig.is_active == True)  # noqa: E712

        return query.order_by(ApprovalChainConfig.chain_name).all()

    async def create_chain(
        self,
        chain_name: str,
        approval_type: str,
        steps: List[Dict[str, Any]],
        conditions: Optional[Dict[str, Any]] = None,
        auto_approve_conditions: Optional[Dict[str, Any]] = None,
        timeout_hours: int = 24,
        timeout_action: str = "escalate",
    ) -> "ApprovalChainConfig":
        """Create a new approval chain config."""
        ApprovalChainConfig, _, _, _ = _get_models()

        if approval_type not in VALID_APPROVAL_TYPES:
            raise ValueError(
                f"Invalid approval_type '{approval_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_APPROVAL_TYPES))}"
            )
        if not steps or not isinstance(steps, list):
            raise ValueError("steps must be a non-empty list")
        if timeout_action not in VALID_TIMEOUT_ACTIONS:
            raise ValueError(
                f"Invalid timeout_action '{timeout_action}'. "
                f"Must be one of: {', '.join(sorted(VALID_TIMEOUT_ACTIONS))}"
            )

        self._validate_steps(steps)

        chain = ApprovalChainConfig(
            organization_id=self.org_id,
            chain_name=chain_name,
            approval_type=approval_type,
            conditions=conditions,
            steps=steps,
            auto_approve_conditions=auto_approve_conditions,
            timeout_hours=timeout_hours,
            timeout_action=timeout_action,
            is_active=True,
        )
        self.db.add(chain)
        self.db.flush()

        logger.info(
            "Created approval chain '%s' (type=%s, steps=%d) for org %d",
            chain_name, approval_type, len(steps), self.org_id,
        )
        return chain

    async def update_chain(
        self,
        chain_id: int,
        **updates: Any,
    ) -> "ApprovalChainConfig":
        """Update an existing approval chain config.

        Allowed fields: chain_name, conditions, steps, auto_approve_conditions,
        timeout_hours, timeout_action, is_active.
        """
        ApprovalChainConfig, _, _, _ = _get_models()

        chain = (
            self.db.query(ApprovalChainConfig)
            .filter(
                ApprovalChainConfig.id == chain_id,
                ApprovalChainConfig.organization_id == self.org_id,
            )
            .first()
        )
        if not chain:
            raise ValueError(f"Approval chain {chain_id} not found in org {self.org_id}")

        allowed_fields = {
            "chain_name", "conditions", "steps", "auto_approve_conditions",
            "timeout_hours", "timeout_action", "is_active",
        }
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key == "steps":
                self._validate_steps(value)
            if key == "timeout_action" and value not in VALID_TIMEOUT_ACTIONS:
                raise ValueError(f"Invalid timeout_action '{value}'")
            setattr(chain, key, value)

        chain.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        logger.info("Updated approval chain %d for org %d", chain_id, self.org_id)
        return chain

    # ------------------------------------------------------------------
    # SUBMIT FOR APPROVAL
    # ------------------------------------------------------------------

    async def submit_for_approval(
        self,
        approval_type: str,
        entity_type: str,
        entity_id: int,
        loan_id: int,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> "ApprovalRequest":
        """Submit an entity for approval.

        Finds the matching chain, checks auto-approve conditions, and creates
        an approval request. If auto-approve conditions are met, the request
        is immediately approved.

        Args:
            approval_type: The type of approval (e.g. INCOME_APPROVAL).
            entity_type: The entity being approved (e.g. document, income_calc).
            entity_id: ID of the entity being approved.
            loan_id: Related loan ID.
            user_id: ID of the user submitting the request.
            context: Optional dict of justification/evidence for the approver.

        Returns:
            The created ApprovalRequest (may already be APPROVED if auto-approved).

        Raises:
            ValueError: If no matching chain is found or inputs are invalid.
        """
        ApprovalChainConfig, ApprovalRequest, ApprovalDecision, _ = _get_models()

        if approval_type not in VALID_APPROVAL_TYPES:
            raise ValueError(f"Invalid approval_type '{approval_type}'")

        # Find matching chain
        chain = await self._find_matching_chain(approval_type, loan_id, context)
        if not chain:
            raise ValueError(
                f"No active approval chain found for type '{approval_type}' "
                f"in org {self.org_id}"
            )

        # Check auto-approve conditions
        if await self._check_auto_approve(chain, context):
            request = ApprovalRequest(
                organization_id=self.org_id,
                chain_id=chain.id,
                loan_id=loan_id,
                entity_type=entity_type,
                entity_id=entity_id,
                current_step=0,
                status="APPROVED",
                request_data=context,
                requested_by_user_id=user_id,
                completed_at=datetime.now(timezone.utc),
            )
            self.db.add(request)
            self.db.flush()

            # Record auto-approve decision
            decision = ApprovalDecision(
                approval_request_id=request.id,
                step_number=0,
                approver_user_id=user_id,
                decision="APPROVED",
                comments="Auto-approved: met auto-approve conditions",
            )
            self.db.add(decision)
            self.db.flush()

            logger.info(
                "Auto-approved request for %s:%d on loan %d (chain=%s, org=%d)",
                entity_type, entity_id, loan_id, chain.chain_name, self.org_id,
            )
            return request

        # Determine effective first step (skip conditional steps that don't apply)
        first_step = await self._find_next_applicable_step(chain, 0, loan_id, context)
        if first_step is None:
            # All steps are conditional and none apply -- auto-approve
            request = ApprovalRequest(
                organization_id=self.org_id,
                chain_id=chain.id,
                loan_id=loan_id,
                entity_type=entity_type,
                entity_id=entity_id,
                current_step=0,
                status="APPROVED",
                request_data=context,
                requested_by_user_id=user_id,
                completed_at=datetime.now(timezone.utc),
            )
            self.db.add(request)
            self.db.flush()
            logger.info(
                "All conditional steps skipped -- auto-approved %s:%d (org=%d)",
                entity_type, entity_id, self.org_id,
            )
            return request

        request = ApprovalRequest(
            organization_id=self.org_id,
            chain_id=chain.id,
            loan_id=loan_id,
            entity_type=entity_type,
            entity_id=entity_id,
            current_step=first_step,
            status="PENDING",
            request_data=context,
            requested_by_user_id=user_id,
        )
        self.db.add(request)
        self.db.flush()

        logger.info(
            "Submitted approval request %d for %s:%d on loan %d "
            "(chain=%s, step=%d, org=%d)",
            request.id, entity_type, entity_id, loan_id,
            chain.chain_name, first_step, self.org_id,
        )
        return request

    # ------------------------------------------------------------------
    # MAKE DECISION
    # ------------------------------------------------------------------

    async def make_decision(
        self,
        request_id: int,
        user_id: int,
        decision: str,
        comments: Optional[str] = None,
        conditions_added: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Record an approval decision for the current step of a request.

        Enforces separation of duties:
            - Cannot approve own submission (maker-checker)
            - Cannot approve if you uploaded the entity document

        After recording the decision:
            - APPROVED: advance to next step or complete the request
            - REJECTED: immediately reject the entire request
            - RETURNED: reset to PENDING for re-submission

        Args:
            request_id: The approval request ID.
            user_id: The user making the decision.
            decision: One of APPROVED, REJECTED, RETURNED.
            comments: Optional decision comments.
            conditions_added: Optional conditions attached to a conditional approval.

        Returns:
            Dict with request status, decision details, and next_step info.

        Raises:
            ValueError: On validation failures.
            PermissionError: On separation-of-duties violations.
        """
        _, ApprovalRequest, ApprovalDecision, _ = _get_models()

        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}"
            )

        request = (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == request_id,
                ApprovalRequest.organization_id == self.org_id,
            )
            .first()
        )
        if not request:
            raise ValueError(f"Approval request {request_id} not found in org {self.org_id}")

        if request.status in TERMINAL_STATUSES:
            raise ValueError(
                f"Request {request_id} is already in terminal status '{request.status}'"
            )

        # Resolve effective approver (check delegation)
        effective_user_id = await self._resolve_effective_approver(user_id)

        # Separation of duties checks
        await self._enforce_separation_of_duties(request, effective_user_id)

        # Verify the user is authorized for this step
        chain = await self._get_chain_for_request(request)
        await self._verify_step_authority(
            chain, request.current_step, effective_user_id, request.loan_id,
        )

        # Record the decision
        decision_record = ApprovalDecision(
            approval_request_id=request.id,
            step_number=request.current_step,
            approver_user_id=effective_user_id,
            decision=decision,
            comments=comments,
            conditions_added=conditions_added,
        )
        self.db.add(decision_record)

        now = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "request_id": request.id,
            "decision": decision,
            "step": request.current_step,
            "approver_user_id": effective_user_id,
        }

        if decision == "REJECTED":
            request.status = "REJECTED"
            request.completed_at = now
            request.updated_at = now
            result["request_status"] = "REJECTED"
            result["next_step"] = None
            logger.info(
                "Request %d REJECTED at step %d by user %d (org=%d)",
                request_id, request.current_step, effective_user_id, self.org_id,
            )

        elif decision == "RETURNED":
            request.status = "PENDING"
            request.updated_at = now
            result["request_status"] = "PENDING"
            result["next_step"] = request.current_step
            logger.info(
                "Request %d RETURNED at step %d by user %d (org=%d)",
                request_id, request.current_step, effective_user_id, self.org_id,
            )

        elif decision == "APPROVED":
            context = request.request_data or {}
            next_step = await self._find_next_applicable_step(
                chain, request.current_step, request.loan_id, context,
            )

            if next_step is None:
                # All steps complete
                request.status = "APPROVED"
                request.completed_at = now
                request.updated_at = now
                result["request_status"] = "APPROVED"
                result["next_step"] = None
                logger.info(
                    "Request %d fully APPROVED (final step %d by user %d, org=%d)",
                    request_id, request.current_step, effective_user_id, self.org_id,
                )
            else:
                request.current_step = next_step
                request.status = "IN_PROGRESS"
                request.updated_at = now
                result["request_status"] = "IN_PROGRESS"
                result["next_step"] = next_step
                logger.info(
                    "Request %d step %d approved by user %d, advancing to step %d (org=%d)",
                    request_id, decision_record.step_number, effective_user_id,
                    next_step, self.org_id,
                )

        if conditions_added:
            result["conditions_added"] = conditions_added

        self.db.flush()
        return result

    # ------------------------------------------------------------------
    # BULK APPROVAL
    # ------------------------------------------------------------------

    async def bulk_approve(
        self,
        request_ids: List[int],
        user_id: int,
        comments: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve multiple requests at once. Each gets an individual audit entry.

        Skips requests that fail validation (wrong org, terminal status,
        separation-of-duties violation) and continues with the rest.

        Returns:
            Dict with approved_count, skipped (list of {id, reason}), and errors.
        """
        approved = []
        skipped = []

        for req_id in request_ids:
            try:
                result = await self.make_decision(
                    request_id=req_id,
                    user_id=user_id,
                    decision="APPROVED",
                    comments=comments or "Bulk approval",
                )
                approved.append({"request_id": req_id, "result": result})
            except (ValueError, PermissionError) as e:
                skipped.append({"request_id": req_id, "reason": str(e)})
                logger.warning(
                    "Bulk approve skipped request %d: %s (org=%d)",
                    req_id, e, self.org_id,
                )

        logger.info(
            "Bulk approval: %d approved, %d skipped (org=%d, user=%d)",
            len(approved), len(skipped), self.org_id, user_id,
        )
        return {
            "approved_count": len(approved),
            "skipped_count": len(skipped),
            "approved": approved,
            "skipped": skipped,
        }

    # ------------------------------------------------------------------
    # QUERY: PENDING APPROVALS
    # ------------------------------------------------------------------

    async def get_pending_approvals(
        self,
        user_id: int,
        approval_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get approval requests pending action by this user.

        Checks role assignments and delegation rules to determine which
        requests the user can act on.
        """
        _, ApprovalRequest, _, _ = _get_models()
        ApprovalChainConfig, _, _, _ = _get_models()

        # Get all non-terminal requests for this org
        query = (
            self.db.query(ApprovalRequest, ApprovalChainConfig)
            .join(
                ApprovalChainConfig,
                ApprovalChainConfig.id == ApprovalRequest.chain_id,
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.status.in_(["PENDING", "IN_PROGRESS"]),
            )
        )

        if approval_type:
            query = query.filter(ApprovalChainConfig.approval_type == approval_type)

        query = query.order_by(ApprovalRequest.created_at.asc()).limit(limit)
        rows = query.all()

        # Resolve which requests this user can approve (check step authority)
        effective_user_id = await self._resolve_effective_approver(user_id)
        delegated_from = await self._get_delegated_from_users(user_id)
        check_user_ids = {effective_user_id, user_id} | delegated_from

        pending = []
        for request, chain in rows:
            step_config = self._get_step_config(chain, request.current_step)
            if not step_config:
                continue

            # Check if user is authorized for this step
            authorized = False
            for check_uid in check_user_ids:
                if await self._is_user_authorized_for_step(
                    step_config, check_uid, request.loan_id,
                ):
                    authorized = True
                    break

            if not authorized:
                continue

            # Check separation of duties
            try:
                await self._enforce_separation_of_duties(request, effective_user_id)
            except PermissionError:
                continue

            pending.append({
                "request_id": request.id,
                "chain_name": chain.chain_name,
                "approval_type": chain.approval_type,
                "entity_type": request.entity_type,
                "entity_id": request.entity_id,
                "loan_id": request.loan_id,
                "current_step": request.current_step,
                "total_steps": len(chain.steps or []),
                "status": request.status,
                "request_data": request.request_data,
                "requested_by_user_id": request.requested_by_user_id,
                "created_at": request.created_at.isoformat() if request.created_at else None,
                "age_hours": self._hours_since(request.created_at),
                "timeout_hours": chain.timeout_hours,
            })

        return pending

    async def get_team_pending_approvals(
        self,
        manager_user_id: int,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Get all pending approvals for users who report to this manager.

        Useful for manager dashboards showing team queue depth.
        """
        _, ApprovalRequest, _, _ = _get_models()
        ApprovalChainConfig, _, _, _ = _get_models()

        # Find direct reports
        team_ids_result = self.db.execute(
            text("""
                SELECT id FROM users
                WHERE reports_to_id = :manager_id
                AND organization_id = :org_id
            """),
            {"manager_id": manager_user_id, "org_id": self.org_id},
        )
        team_user_ids = {row[0] for row in team_ids_result}
        team_user_ids.add(manager_user_id)

        rows = (
            self.db.query(ApprovalRequest, ApprovalChainConfig)
            .join(
                ApprovalChainConfig,
                ApprovalChainConfig.id == ApprovalRequest.chain_id,
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.status.in_(["PENDING", "IN_PROGRESS"]),
            )
            .order_by(ApprovalRequest.created_at.asc())
            .limit(limit)
            .all()
        )

        results = []
        for request, chain in rows:
            step_config = self._get_step_config(chain, request.current_step)
            if not step_config:
                continue

            for uid in team_user_ids:
                if await self._is_user_authorized_for_step(
                    step_config, uid, request.loan_id,
                ):
                    results.append({
                        "request_id": request.id,
                        "chain_name": chain.chain_name,
                        "approval_type": chain.approval_type,
                        "entity_type": request.entity_type,
                        "entity_id": request.entity_id,
                        "loan_id": request.loan_id,
                        "current_step": request.current_step,
                        "status": request.status,
                        "created_at": request.created_at.isoformat() if request.created_at else None,
                        "age_hours": self._hours_since(request.created_at),
                    })
                    break

        return results

    # ------------------------------------------------------------------
    # CHECK STATUS
    # ------------------------------------------------------------------

    async def check_approval_status(
        self,
        request_id: int,
    ) -> Dict[str, Any]:
        """Get full status of an approval request including decision history."""
        _, ApprovalRequest, ApprovalDecision, _ = _get_models()
        ApprovalChainConfig, _, _, _ = _get_models()

        request = (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == request_id,
                ApprovalRequest.organization_id == self.org_id,
            )
            .first()
        )
        if not request:
            raise ValueError(f"Approval request {request_id} not found in org {self.org_id}")

        chain = (
            self.db.query(ApprovalChainConfig)
            .filter(ApprovalChainConfig.id == request.chain_id)
            .first()
        )

        decisions = (
            self.db.query(ApprovalDecision)
            .filter(ApprovalDecision.approval_request_id == request_id)
            .order_by(ApprovalDecision.decided_at.asc())
            .all()
        )

        total_steps = len(chain.steps or []) if chain else 0

        return {
            "request_id": request.id,
            "chain_name": chain.chain_name if chain else None,
            "approval_type": chain.approval_type if chain else None,
            "entity_type": request.entity_type,
            "entity_id": request.entity_id,
            "loan_id": request.loan_id,
            "status": request.status,
            "current_step": request.current_step,
            "total_steps": total_steps,
            "requested_by_user_id": request.requested_by_user_id,
            "created_at": request.created_at.isoformat() if request.created_at else None,
            "completed_at": request.completed_at.isoformat() if request.completed_at else None,
            "age_hours": self._hours_since(request.created_at),
            "decisions": [
                {
                    "step": d.step_number,
                    "approver_user_id": d.approver_user_id,
                    "decision": d.decision,
                    "comments": d.comments,
                    "conditions_added": d.conditions_added,
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                }
                for d in decisions
            ],
            "request_data": request.request_data,
        }

    # ------------------------------------------------------------------
    # DELEGATION
    # ------------------------------------------------------------------

    async def delegate_approvals(
        self,
        from_user_id: int,
        to_user_id: int,
        approval_types: Optional[List[str]] = None,
        until_date: Optional[datetime] = None,
        reason: Optional[str] = None,
        created_by_user_id: Optional[int] = None,
    ) -> "ApprovalDelegation":
        """Create an approval delegation from one user to another.

        Args:
            from_user_id: The user delegating their approval authority.
            to_user_id: The user receiving delegated authority.
            approval_types: List of approval types to delegate (null = all).
            until_date: Expiration datetime (null = permanent).
            reason: Reason for delegation.
            created_by_user_id: Who created this delegation (for audit).

        Returns:
            The created ApprovalDelegation.

        Raises:
            ValueError: If delegating to yourself or invalid inputs.
        """
        _, _, _, ApprovalDelegation = _get_models()

        if from_user_id == to_user_id:
            raise ValueError("Cannot delegate approvals to yourself")

        if approval_types:
            invalid = set(approval_types) - VALID_APPROVAL_TYPES
            if invalid:
                raise ValueError(f"Invalid approval types: {', '.join(invalid)}")

        delegation_type = "permanent" if until_date is None else "out_of_office"
        starts_at = datetime.now(timezone.utc)

        delegation = ApprovalDelegation(
            organization_id=self.org_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            delegation_type=delegation_type,
            approval_types=approval_types,
            starts_at=starts_at,
            ends_at=until_date,
            reason=reason,
            is_active=True,
            created_by_user_id=created_by_user_id or from_user_id,
        )
        self.db.add(delegation)
        self.db.flush()

        logger.info(
            "Created %s delegation: user %d -> user %d (types=%s, until=%s, org=%d)",
            delegation_type, from_user_id, to_user_id,
            approval_types or "all", until_date, self.org_id,
        )
        return delegation

    async def revoke_delegation(
        self,
        delegation_id: int,
    ) -> None:
        """Revoke an active delegation."""
        _, _, _, ApprovalDelegation = _get_models()

        delegation = (
            self.db.query(ApprovalDelegation)
            .filter(
                ApprovalDelegation.id == delegation_id,
                ApprovalDelegation.organization_id == self.org_id,
            )
            .first()
        )
        if not delegation:
            raise ValueError(f"Delegation {delegation_id} not found in org {self.org_id}")

        delegation.is_active = False
        delegation.ends_at = datetime.now(timezone.utc)
        self.db.flush()

        logger.info("Revoked delegation %d (org=%d)", delegation_id, self.org_id)

    async def get_active_delegations(
        self,
        user_id: Optional[int] = None,
    ) -> List["ApprovalDelegation"]:
        """Get active delegations, optionally filtered by from_user_id."""
        _, _, _, ApprovalDelegation = _get_models()

        now = datetime.now(timezone.utc)
        query = (
            self.db.query(ApprovalDelegation)
            .filter(
                ApprovalDelegation.organization_id == self.org_id,
                ApprovalDelegation.is_active == True,  # noqa: E712
                or_(
                    ApprovalDelegation.ends_at.is_(None),
                    ApprovalDelegation.ends_at > now,
                ),
            )
        )
        if user_id is not None:
            query = query.filter(
                or_(
                    ApprovalDelegation.from_user_id == user_id,
                    ApprovalDelegation.to_user_id == user_id,
                ),
            )
        return query.order_by(ApprovalDelegation.created_at.desc()).all()

    # ------------------------------------------------------------------
    # TIMEOUT HANDLING
    # ------------------------------------------------------------------

    async def process_timeouts(self) -> Dict[str, Any]:
        """Check for timed-out approval requests and apply timeout actions.

        Should be called periodically (e.g. every 15 minutes by scheduler).

        Returns:
            Dict with counts of escalated, auto-approved, and auto-rejected requests.
        """
        ApprovalChainConfig, ApprovalRequest, ApprovalDecision, _ = _get_models()

        now = datetime.now(timezone.utc)

        # Find non-terminal requests past their timeout
        rows = (
            self.db.query(ApprovalRequest, ApprovalChainConfig)
            .join(
                ApprovalChainConfig,
                ApprovalChainConfig.id == ApprovalRequest.chain_id,
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.status.in_(["PENDING", "IN_PROGRESS"]),
            )
            .all()
        )

        escalated = 0
        auto_approved = 0
        auto_rejected = 0

        for request, chain in rows:
            timeout_hours = chain.timeout_hours or 24

            # Check per-step timeout override
            step_config = self._get_step_config(chain, request.current_step)
            if step_config and step_config.get("timeout_hours"):
                timeout_hours = step_config["timeout_hours"]

            timeout_at = (request.updated_at or request.created_at) + timedelta(
                hours=timeout_hours,
            )
            if now < timeout_at:
                continue

            timeout_action = chain.timeout_action or "escalate"

            if timeout_action == "auto_approve":
                request.status = "APPROVED"
                request.completed_at = now
                request.updated_at = now
                decision = ApprovalDecision(
                    approval_request_id=request.id,
                    step_number=request.current_step,
                    approver_user_id=request.requested_by_user_id,
                    decision="APPROVED",
                    comments=f"Auto-approved after {timeout_hours}h timeout",
                )
                self.db.add(decision)
                auto_approved += 1

            elif timeout_action == "auto_reject":
                request.status = "TIMED_OUT"
                request.completed_at = now
                request.updated_at = now
                decision = ApprovalDecision(
                    approval_request_id=request.id,
                    step_number=request.current_step,
                    approver_user_id=request.requested_by_user_id,
                    decision="REJECTED",
                    comments=f"Auto-rejected after {timeout_hours}h timeout",
                )
                self.db.add(decision)
                auto_rejected += 1

            else:
                # Escalate: advance to next step or mark as timed out
                context = request.request_data or {}
                next_step = await self._find_next_applicable_step(
                    chain, request.current_step, request.loan_id, context,
                )
                if next_step is not None:
                    decision = ApprovalDecision(
                        approval_request_id=request.id,
                        step_number=request.current_step,
                        approver_user_id=request.requested_by_user_id,
                        decision="APPROVED",
                        comments=f"Escalated after {timeout_hours}h timeout -- auto-advanced to step {next_step}",
                    )
                    self.db.add(decision)
                    request.current_step = next_step
                    request.status = "IN_PROGRESS"
                    request.updated_at = now
                else:
                    request.status = "TIMED_OUT"
                    request.completed_at = now
                    request.updated_at = now
                escalated += 1

        self.db.flush()

        result = {
            "processed_at": now.isoformat(),
            "escalated": escalated,
            "auto_approved": auto_approved,
            "auto_rejected": auto_rejected,
            "total_processed": escalated + auto_approved + auto_rejected,
        }

        if result["total_processed"] > 0:
            logger.info(
                "Timeout processing for org %d: %d escalated, %d auto-approved, "
                "%d auto-rejected",
                self.org_id, escalated, auto_approved, auto_rejected,
            )

        return result

    # ------------------------------------------------------------------
    # CANCEL
    # ------------------------------------------------------------------

    async def cancel_request(
        self,
        request_id: int,
        user_id: int,
        reason: Optional[str] = None,
    ) -> None:
        """Cancel an in-flight approval request."""
        _, ApprovalRequest, ApprovalDecision, _ = _get_models()

        request = (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == request_id,
                ApprovalRequest.organization_id == self.org_id,
            )
            .first()
        )
        if not request:
            raise ValueError(f"Approval request {request_id} not found in org {self.org_id}")

        if request.status in TERMINAL_STATUSES:
            raise ValueError(f"Request {request_id} is already in terminal status '{request.status}'")

        now = datetime.now(timezone.utc)
        request.status = "CANCELLED"
        request.completed_at = now
        request.updated_at = now

        decision = ApprovalDecision(
            approval_request_id=request.id,
            step_number=request.current_step,
            approver_user_id=user_id,
            decision="REJECTED",
            comments=f"Cancelled: {reason}" if reason else "Cancelled by user",
        )
        self.db.add(decision)
        self.db.flush()

        logger.info(
            "Cancelled approval request %d by user %d (org=%d)",
            request_id, user_id, self.org_id,
        )

    # ------------------------------------------------------------------
    # ANALYTICS
    # ------------------------------------------------------------------

    async def get_approval_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get approval analytics for this organization.

        Returns:
            Dict with average times, rejection rates, bottlenecks, and trends.
        """
        ApprovalChainConfig, ApprovalRequest, ApprovalDecision, _ = _get_models()

        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=90)
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        # Overall stats
        overall = (
            self.db.query(
                func.count(ApprovalRequest.id).label("total"),
                func.count(
                    case(
                        (ApprovalRequest.status == "APPROVED", 1),
                    )
                ).label("approved"),
                func.count(
                    case(
                        (ApprovalRequest.status == "REJECTED", 1),
                    )
                ).label("rejected"),
                func.count(
                    case(
                        (ApprovalRequest.status == "TIMED_OUT", 1),
                    )
                ).label("timed_out"),
                func.count(
                    case(
                        (ApprovalRequest.status.in_(["PENDING", "IN_PROGRESS"]), 1),
                    )
                ).label("open"),
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.created_at >= start_date,
                ApprovalRequest.created_at <= end_date,
            )
            .first()
        )

        total = overall.total or 0
        approved = overall.approved or 0
        rejected = overall.rejected or 0

        # Average approval time (for completed requests)
        avg_time = (
            self.db.query(
                func.avg(
                    func.extract(
                        "epoch",
                        ApprovalRequest.completed_at - ApprovalRequest.created_at,
                    ) / 3600
                ).label("avg_hours"),
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.status == "APPROVED",
                ApprovalRequest.completed_at.isnot(None),
                ApprovalRequest.created_at >= start_date,
                ApprovalRequest.created_at <= end_date,
            )
            .first()
        )

        # Average time by approval type
        by_type = (
            self.db.query(
                ApprovalChainConfig.approval_type,
                func.count(ApprovalRequest.id).label("count"),
                func.count(
                    case(
                        (ApprovalRequest.status == "APPROVED", 1),
                    )
                ).label("approved_count"),
                func.count(
                    case(
                        (ApprovalRequest.status == "REJECTED", 1),
                    )
                ).label("rejected_count"),
                func.avg(
                    case(
                        (
                            and_(
                                ApprovalRequest.completed_at.isnot(None),
                                ApprovalRequest.status == "APPROVED",
                            ),
                            func.extract(
                                "epoch",
                                ApprovalRequest.completed_at - ApprovalRequest.created_at,
                            ) / 3600,
                        ),
                    )
                ).label("avg_hours"),
            )
            .join(
                ApprovalChainConfig,
                ApprovalChainConfig.id == ApprovalRequest.chain_id,
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.created_at >= start_date,
                ApprovalRequest.created_at <= end_date,
            )
            .group_by(ApprovalChainConfig.approval_type)
            .all()
        )

        # Rejection reasons (top comments from rejected decisions)
        rejection_comments = (
            self.db.query(
                ApprovalDecision.comments,
                func.count(ApprovalDecision.id).label("count"),
            )
            .join(
                ApprovalRequest,
                ApprovalRequest.id == ApprovalDecision.approval_request_id,
            )
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalDecision.decision == "REJECTED",
                ApprovalDecision.comments.isnot(None),
                ApprovalDecision.decided_at >= start_date,
                ApprovalDecision.decided_at <= end_date,
            )
            .group_by(ApprovalDecision.comments)
            .order_by(func.count(ApprovalDecision.id).desc())
            .limit(10)
            .all()
        )

        # Queue depth and aging (current open requests)
        open_requests = (
            self.db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.organization_id == self.org_id,
                ApprovalRequest.status.in_(["PENDING", "IN_PROGRESS"]),
            )
            .all()
        )

        now = datetime.now(timezone.utc)
        aging_buckets = {"0-4h": 0, "4-24h": 0, "24-48h": 0, "48h+": 0}
        for req in open_requests:
            age_hours = self._hours_since(req.created_at)
            if age_hours < 4:
                aging_buckets["0-4h"] += 1
            elif age_hours < 24:
                aging_buckets["4-24h"] += 1
            elif age_hours < 48:
                aging_buckets["24-48h"] += 1
            else:
                aging_buckets["48h+"] += 1

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_requests": total,
                "approved": approved,
                "rejected": rejected,
                "timed_out": overall.timed_out or 0,
                "open": overall.open or 0,
                "approval_rate": round((approved / total) * 100, 1) if total > 0 else 0,
                "rejection_rate": round((rejected / total) * 100, 1) if total > 0 else 0,
                "avg_approval_hours": round(float(avg_time.avg_hours or 0), 1),
            },
            "by_type": [
                {
                    "approval_type": row.approval_type,
                    "count": row.count,
                    "approved": row.approved_count,
                    "rejected": row.rejected_count,
                    "rejection_rate": round(
                        (row.rejected_count / row.count) * 100, 1,
                    ) if row.count > 0 else 0,
                    "avg_approval_hours": round(float(row.avg_hours or 0), 1),
                }
                for row in by_type
            ],
            "top_rejection_reasons": [
                {"reason": row.comments, "count": row.count}
                for row in rejection_comments
            ],
            "queue": {
                "depth": len(open_requests),
                "aging": aging_buckets,
            },
        }

    async def get_approval_dashboard(
        self,
        user_id: int,
    ) -> Dict[str, Any]:
        """Get approval dashboard data for a specific user.

        Combines pending approvals, recent decisions, and queue stats.
        """
        _, ApprovalRequest, ApprovalDecision, _ = _get_models()

        pending = await self.get_pending_approvals(user_id)

        # Recent decisions by this user
        recent_decisions = (
            self.db.query(ApprovalDecision)
            .filter(ApprovalDecision.approver_user_id == user_id)
            .order_by(ApprovalDecision.decided_at.desc())
            .limit(20)
            .all()
        )

        # Active delegations involving this user
        delegations = await self.get_active_delegations(user_id)

        return {
            "pending_count": len(pending),
            "pending": pending[:20],  # First 20 for dashboard
            "recent_decisions": [
                {
                    "request_id": d.approval_request_id,
                    "step": d.step_number,
                    "decision": d.decision,
                    "comments": d.comments,
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                }
                for d in recent_decisions
            ],
            "active_delegations": [
                {
                    "id": d.id,
                    "from_user_id": d.from_user_id,
                    "to_user_id": d.to_user_id,
                    "delegation_type": d.delegation_type,
                    "approval_types": d.approval_types,
                    "ends_at": d.ends_at.isoformat() if d.ends_at else None,
                    "reason": d.reason,
                }
                for d in delegations
            ],
        }

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    async def _find_matching_chain(
        self,
        approval_type: str,
        loan_id: int,
        context: Optional[Dict[str, Any]],
    ) -> Optional["ApprovalChainConfig"]:
        """Find the best matching chain for the given type and context.

        Chains with conditions are checked first (more specific match).
        Falls back to chains without conditions.
        """
        ApprovalChainConfig, _, _, _ = _get_models()

        chains = (
            self.db.query(ApprovalChainConfig)
            .filter(
                ApprovalChainConfig.organization_id == self.org_id,
                ApprovalChainConfig.approval_type == approval_type,
                ApprovalChainConfig.is_active == True,  # noqa: E712
            )
            .all()
        )

        if not chains:
            return None

        # Separate conditional and unconditional chains
        conditional = [c for c in chains if c.conditions]
        unconditional = [c for c in chains if not c.conditions]

        # Check conditional chains first
        for chain in conditional:
            if self._conditions_match(chain.conditions, loan_id, context):
                return chain

        # Fall back to first unconditional chain
        return unconditional[0] if unconditional else (conditional[0] if conditional else None)

    def _conditions_match(
        self,
        conditions: Dict[str, Any],
        loan_id: int,
        context: Optional[Dict[str, Any]],
    ) -> bool:
        """Check if a chain's conditions match the current loan/context."""
        if not conditions:
            return True

        ctx = context or {}

        # Check min_loan_amount
        min_amount = conditions.get("min_loan_amount")
        if min_amount is not None:
            loan_amount = ctx.get("loan_amount")
            if loan_amount is None:
                # Try to look up the loan amount
                result = self.db.execute(
                    text("SELECT amount FROM loans WHERE id = :lid AND organization_id = :oid"),
                    {"lid": loan_id, "oid": self.org_id},
                ).first()
                loan_amount = float(result[0]) if result and result[0] else 0
            if loan_amount < min_amount:
                return False

        # Check max_loan_amount
        max_amount = conditions.get("max_loan_amount")
        if max_amount is not None:
            loan_amount = ctx.get("loan_amount")
            if loan_amount is None:
                result = self.db.execute(
                    text("SELECT amount FROM loans WHERE id = :lid AND organization_id = :oid"),
                    {"lid": loan_id, "oid": self.org_id},
                ).first()
                loan_amount = float(result[0]) if result and result[0] else 0
            if loan_amount > max_amount:
                return False

        # Check doc_types
        required_doc_types = conditions.get("doc_types")
        if required_doc_types:
            entity_doc_type = ctx.get("doc_type")
            if entity_doc_type and entity_doc_type not in required_doc_types:
                return False

        # Check loan_types
        required_loan_types = conditions.get("loan_types")
        if required_loan_types:
            loan_type = ctx.get("loan_type")
            if loan_type is None:
                result = self.db.execute(
                    text("SELECT loan_type FROM loans WHERE id = :lid AND organization_id = :oid"),
                    {"lid": loan_id, "oid": self.org_id},
                ).first()
                loan_type = result[0] if result else None
            if loan_type and loan_type not in required_loan_types:
                return False

        return True

    async def _check_auto_approve(
        self,
        chain: "ApprovalChainConfig",
        context: Optional[Dict[str, Any]],
    ) -> bool:
        """Check if auto-approve conditions are met."""
        conditions = chain.auto_approve_conditions
        if not conditions:
            return False

        ctx = context or {}

        # All specified conditions must be met
        confidence_threshold = conditions.get("ai_confidence_above")
        if confidence_threshold is not None:
            ai_confidence = ctx.get("ai_confidence")
            if ai_confidence is None or ai_confidence <= confidence_threshold:
                return False

        amount_threshold = conditions.get("amount_below")
        if amount_threshold is not None:
            amount = ctx.get("amount") or ctx.get("loan_amount")
            if amount is None or amount >= amount_threshold:
                return False

        allowed_doc_types = conditions.get("doc_types")
        if allowed_doc_types:
            doc_type = ctx.get("doc_type")
            if doc_type and doc_type not in allowed_doc_types:
                return False

        return True

    async def _find_next_applicable_step(
        self,
        chain: "ApprovalChainConfig",
        current_step: int,
        loan_id: int,
        context: Optional[Dict[str, Any]],
    ) -> Optional[int]:
        """Find the next step that applies (skipping conditional steps that don't match).

        Returns None if all remaining steps are skipped or there are no more steps.
        """
        steps = chain.steps or []

        for step_def in steps:
            step_num = step_def.get("step", 0)
            if step_num <= current_step:
                continue

            # Check step-level conditions
            step_condition = step_def.get("condition")
            if step_condition and not self._conditions_match(step_condition, loan_id, context):
                continue

            # Check if the step is required
            if not step_def.get("required", True):
                # Optional step -- check if auto-approve conditions skip it
                if await self._check_auto_approve(chain, context):
                    continue

            return step_num

        return None

    def _get_step_config(
        self,
        chain: "ApprovalChainConfig",
        step_number: int,
    ) -> Optional[Dict[str, Any]]:
        """Get the configuration for a specific step in the chain."""
        steps = chain.steps or []
        for step in steps:
            if step.get("step") == step_number:
                return step
        return None

    async def _verify_step_authority(
        self,
        chain: "ApprovalChainConfig",
        step_number: int,
        user_id: int,
        loan_id: int,
    ) -> None:
        """Verify a user is authorized to act on a specific step.

        Raises PermissionError if the user is not authorized.
        """
        step_config = self._get_step_config(chain, step_number)
        if not step_config:
            raise ValueError(f"Step {step_number} not found in chain {chain.id}")

        if await self._is_user_authorized_for_step(step_config, user_id, loan_id):
            return

        # Check parallel approvers
        parallel = step_config.get("parallel_approvers", [])
        if parallel:
            for alt_approver in parallel:
                alt_config = {
                    "approver_type": alt_approver.get("approver_type", "role"),
                    "approver": alt_approver.get("approver"),
                }
                if await self._is_user_authorized_for_step(alt_config, user_id, loan_id):
                    return

        raise PermissionError(
            f"User {user_id} is not authorized for step {step_number} "
            f"of chain '{chain.chain_name}'"
        )

    async def _is_user_authorized_for_step(
        self,
        step_config: Dict[str, Any],
        user_id: int,
        loan_id: int,
    ) -> bool:
        """Check if a user is authorized for a specific step config."""
        approver_type = step_config.get("approver_type", "role")
        approver_value = step_config.get("approver")

        if approver_type == "user":
            # Direct user match
            try:
                return int(approver_value) == user_id
            except (TypeError, ValueError):
                return False

        elif approver_type == "role":
            # Role-based lookup
            query_template = ROLE_LOOKUP_QUERIES.get(approver_value)
            if not query_template:
                logger.warning(
                    "Unknown role '%s' in approval chain step", approver_value,
                )
                return False

            try:
                result = self.db.execute(
                    text(query_template),
                    {"loan_id": loan_id, "org_id": self.org_id},
                ).first()
                if result and result[0] == user_id:
                    return True
            except Exception as e:
                logger.warning(
                    "Role lookup failed for role '%s': %s", approver_value, e,
                )

        return False

    async def _enforce_separation_of_duties(
        self,
        request: "ApprovalRequest",
        approver_user_id: int,
    ) -> None:
        """Enforce separation-of-duties constraints.

        Raises PermissionError if:
            - The approver is the same user who submitted the request (maker-checker)
            - The approver uploaded the entity document being approved
            - High-value items require two different approvers
        """
        # Maker-checker: cannot approve own submission
        if request.requested_by_user_id == approver_user_id:
            raise PermissionError(
                f"Separation of duties violation: user {approver_user_id} cannot approve "
                f"their own submission (request {request.id})"
            )

        # Cannot approve if you uploaded the document
        if request.entity_type in ("document", "income_calc", "income_calculation"):
            uploader_id = self._get_entity_uploader(
                request.entity_type, request.entity_id,
            )
            if uploader_id is not None and uploader_id == approver_user_id:
                raise PermissionError(
                    f"Separation of duties violation: user {approver_user_id} uploaded "
                    f"the {request.entity_type} being approved (entity {request.entity_id})"
                )

        # Two-person rule for high-value items: check if this user already
        # approved a previous step on the same request
        chain = await self._get_chain_for_request(request)
        if chain and chain.approval_type == "HIGH_VALUE_APPROVAL":
            _, _, ApprovalDecision, _ = _get_models()
            prior_approval = (
                self.db.query(ApprovalDecision)
                .filter(
                    ApprovalDecision.approval_request_id == request.id,
                    ApprovalDecision.approver_user_id == approver_user_id,
                    ApprovalDecision.decision == "APPROVED",
                )
                .first()
            )
            if prior_approval:
                raise PermissionError(
                    f"Two-person rule violation: user {approver_user_id} already approved "
                    f"step {prior_approval.step_number} of high-value request {request.id}"
                )

    def _get_entity_uploader(
        self,
        entity_type: str,
        entity_id: int,
    ) -> Optional[int]:
        """Look up who uploaded/created the entity."""
        try:
            if entity_type == "document":
                result = self.db.execute(
                    text("SELECT uploaded_by_user_id FROM documents WHERE id = :eid"),
                    {"eid": entity_id},
                ).first()
                return result[0] if result else None

            elif entity_type in ("income_calc", "income_calculation"):
                result = self.db.execute(
                    text("SELECT calculated_by_user_id FROM income_calculations WHERE id = :eid"),
                    {"eid": entity_id},
                ).first()
                return result[0] if result else None

        except Exception as e:
            logger.warning("Failed to lookup uploader for %s:%d: %s", entity_type, entity_id, e)

        return None

    async def _resolve_effective_approver(
        self,
        user_id: int,
    ) -> int:
        """Resolve the effective approver, accounting for delegation.

        If user_id is the delegate (to_user_id), they act under their own ID.
        This method returns user_id unchanged -- delegation is checked in
        get_pending_approvals and _get_delegated_from_users.
        """
        # The delegate acts under their own user_id for audit purposes.
        # Delegation just expands which requests they can see/act on.
        return user_id

    async def _get_delegated_from_users(
        self,
        to_user_id: int,
    ) -> set:
        """Get the set of user IDs that have delegated their authority to this user."""
        _, _, _, ApprovalDelegation = _get_models()

        now = datetime.now(timezone.utc)
        delegations = (
            self.db.query(ApprovalDelegation.from_user_id)
            .filter(
                ApprovalDelegation.organization_id == self.org_id,
                ApprovalDelegation.to_user_id == to_user_id,
                ApprovalDelegation.is_active == True,  # noqa: E712
                ApprovalDelegation.starts_at <= now,
                or_(
                    ApprovalDelegation.ends_at.is_(None),
                    ApprovalDelegation.ends_at > now,
                ),
            )
            .all()
        )
        return {d[0] for d in delegations}

    async def _get_chain_for_request(
        self,
        request: "ApprovalRequest",
    ) -> Optional["ApprovalChainConfig"]:
        """Load the chain config for a request."""
        ApprovalChainConfig, _, _, _ = _get_models()
        return (
            self.db.query(ApprovalChainConfig)
            .filter(ApprovalChainConfig.id == request.chain_id)
            .first()
        )

    def _validate_steps(self, steps: List[Dict[str, Any]]) -> None:
        """Validate step definitions."""
        if not steps:
            raise ValueError("steps must be a non-empty list")

        seen_numbers = set()
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Each step must be a dict")
            step_num = step.get("step")
            if step_num is None or not isinstance(step_num, int) or step_num < 1:
                raise ValueError(f"Each step must have a positive integer 'step' field, got {step_num}")
            if step_num in seen_numbers:
                raise ValueError(f"Duplicate step number: {step_num}")
            seen_numbers.add(step_num)

            approver_type = step.get("approver_type")
            if approver_type not in ("role", "user"):
                raise ValueError(
                    f"Step {step_num}: approver_type must be 'role' or 'user', got '{approver_type}'"
                )

            approver = step.get("approver")
            if approver is None:
                raise ValueError(f"Step {step_num}: 'approver' is required")

            if approver_type == "role" and approver not in ROLE_LOOKUP_QUERIES:
                logger.warning(
                    "Step %d references unknown role '%s' -- lookups will fail",
                    step_num, approver,
                )

    @staticmethod
    def _hours_since(dt: Optional[datetime]) -> float:
        """Calculate hours elapsed since a datetime."""
        if dt is None:
            return 0.0
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        return round(delta.total_seconds() / 3600, 1)
