"""
Lead Management Service

Creates and updates leads from extracted call data.
Integrates with the CRM to manage lead lifecycle.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class LeadStatus(str, Enum):
    """Lead status in the CRM."""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    NURTURING = "nurturing"
    APPLICATION_STARTED = "application_started"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(str, Enum):
    """Lead source channels."""
    INBOUND_CALL = "inbound_call"
    OUTBOUND_CALL = "outbound_call"
    WEB_FORM = "web_form"
    REFERRAL = "referral"
    MARKETING = "marketing"
    OTHER = "other"


class LeadPriority(str, Enum):
    """Lead priority levels."""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class LeadResult:
    """Result of lead creation/update operation."""
    success: bool
    lead_id: Optional[str] = None
    action: str = ""  # created, updated, merged
    changes_made: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "lead_id": self.lead_id,
            "action": self.action,
            "changes_made": self.changes_made,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class LeadData:
    """Lead data structure."""
    # Identity
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    # Status
    status: LeadStatus = LeadStatus.NEW
    source: LeadSource = LeadSource.INBOUND_CALL
    priority: LeadPriority = LeadPriority.WARM

    # Loan interest
    loan_purpose: Optional[str] = None
    property_type: Optional[str] = None
    estimated_amount: Optional[float] = None
    estimated_credit_score: Optional[int] = None
    target_timeline: Optional[str] = None

    # Assignment
    assigned_to: Optional[str] = None
    organization_id: Optional[int] = None

    # Metadata
    lead_score: int = 50
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "status": self.status.value,
            "source": self.source.value,
            "priority": self.priority.value,
            "loan_purpose": self.loan_purpose,
            "property_type": self.property_type,
            "estimated_amount": self.estimated_amount,
            "estimated_credit_score": self.estimated_credit_score,
            "target_timeline": self.target_timeline,
            "assigned_to": self.assigned_to,
            "organization_id": self.organization_id,
            "lead_score": self.lead_score,
            "tags": self.tags,
            "notes": self.notes,
        }


class LeadManagementService:
    """
    Manages lead creation and updates from call intelligence data.

    Usage:
        service = LeadManagementService(db_session)
        result = await service.create_or_update_lead(extracted_data, call_id)

        if result.success:
            print(f"Lead {result.lead_id} {result.action}")
    """

    def __init__(self, db_session=None):
        """
        Initialize lead management service.

        Args:
            db_session: Database session for persistence (optional for testing)
        """
        self.db_session = db_session
        # In-memory storage for testing when no DB session
        self._leads: Dict[str, LeadData] = {}

    async def create_or_update_lead(
        self,
        extracted_data: Dict[str, Any],
        call_id: str,
        loan_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        assigned_to: Optional[str] = None,
    ) -> LeadResult:
        """
        Create or update a lead from extracted call data.

        Args:
            extracted_data: Data extracted from the call
            call_id: Unique call identifier
            loan_id: Associated loan ID if exists
            organization_id: Organization ID
            assigned_to: User ID to assign lead to

        Returns:
            LeadResult with operation details
        """
        result = LeadResult(success=False)

        try:
            # Extract lead data from call extractions
            lead_data = self._extract_lead_data(extracted_data)
            lead_data.organization_id = organization_id
            lead_data.assigned_to = assigned_to

            # Calculate lead score
            lead_data.lead_score = self._calculate_lead_score(extracted_data)

            # Determine priority based on extracted intent
            lead_data.priority = self._determine_priority(extracted_data)

            # Check for existing lead by phone or email
            existing_lead = await self._find_existing_lead(lead_data)

            if existing_lead:
                # Update existing lead
                result = await self._update_lead(existing_lead, lead_data, call_id)
            else:
                # Create new lead
                result = await self._create_lead(lead_data, call_id)

            # Add call reference to notes
            if result.success:
                result.changes_made.append(f"Linked to call {call_id}")

            logger.info(
                f"Lead {result.action}: {result.lead_id} "
                f"from call {call_id}, score: {lead_data.lead_score}"
            )

        except Exception as e:
            logger.exception(f"Failed to create/update lead from call {call_id}: {e}")
            result.errors.append(str(e))

        return result

    def _extract_lead_data(self, extracted_data: Dict[str, Any]) -> LeadData:
        """Extract lead information from call data."""
        lead = LeadData()

        # Identity fields
        identity = extracted_data.get("identity", {})
        lead.first_name = self._get_value(identity, "first_name")
        lead.last_name = self._get_value(identity, "last_name")
        lead.email = self._get_value(identity, "email")
        lead.phone = self._get_value(identity, "phone")

        # Property/loan interest
        property_info = extracted_data.get("property", {})
        lead.property_type = self._get_value(property_info, "property_type")
        lead.estimated_amount = self._get_numeric_value(property_info, "purchase_price")

        # Intent
        intent = extracted_data.get("intent", {})
        lead.loan_purpose = self._get_value(intent, "loan_purpose")
        lead.target_timeline = self._get_value(intent, "target_timeline")

        # Financial
        financial = extracted_data.get("financial", {})
        identity_credit = self._get_numeric_value(identity, "estimated_credit_score")
        if identity_credit:
            lead.estimated_credit_score = int(identity_credit)

        # Add relevant tags
        tags = []
        if self._get_value(intent, "has_preapproval"):
            tags.append("pre-approved")
        if self._get_value(intent, "has_realtor"):
            tags.append("has-realtor")
        if self._get_value(intent, "urgency") == "high":
            tags.append("urgent")
        if self._get_value(property_info, "current_housing_status") == "renting":
            tags.append("first-time-buyer-potential")

        lead.tags = tags

        return lead

    def _get_value(self, data: Dict, field: str) -> Optional[str]:
        """Get string value from extraction dict."""
        if not data:
            return None

        value = data.get(field)
        if isinstance(value, dict):
            # ExtractedValue format
            return value.get("value")
        return value

    def _get_numeric_value(self, data: Dict, field: str) -> Optional[float]:
        """Get numeric value from extraction dict."""
        value = self._get_value(data, field)
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _calculate_lead_score(self, extracted_data: Dict[str, Any]) -> int:
        """Calculate lead score from 0-100 based on extracted data."""
        score = 50  # Base score

        intent = extracted_data.get("intent", {})
        financial = extracted_data.get("financial", {})
        property_info = extracted_data.get("property", {})
        identity = extracted_data.get("identity", {})

        # Intent signals (+30 max)
        if self._get_value(intent, "has_preapproval"):
            score += 15
        if self._get_value(intent, "has_realtor"):
            score += 10
        if self._get_value(intent, "has_property_identified"):
            score += 10
        if self._get_value(intent, "urgency") == "high":
            score += 10
        elif self._get_value(intent, "urgency") == "medium":
            score += 5

        # Financial readiness (+20 max)
        credit_score = self._get_numeric_value(identity, "estimated_credit_score")
        if credit_score:
            if credit_score >= 740:
                score += 10
            elif credit_score >= 680:
                score += 5

        down_payment = self._get_numeric_value(property_info, "down_payment")
        purchase_price = self._get_numeric_value(property_info, "purchase_price")
        if down_payment and purchase_price and purchase_price > 0:
            down_pct = down_payment / purchase_price
            if down_pct >= 0.20:
                score += 10
            elif down_pct >= 0.10:
                score += 5

        # Data completeness (+10 max)
        complete_fields = 0
        if self._get_value(identity, "first_name"):
            complete_fields += 1
        if self._get_value(identity, "email") or self._get_value(identity, "phone"):
            complete_fields += 1
        if self._get_value(property_info, "purchase_price"):
            complete_fields += 1
        if self._get_value(intent, "loan_purpose"):
            complete_fields += 1

        score += min(complete_fields * 2.5, 10)

        # Cap at 100
        return min(int(score), 100)

    def _determine_priority(self, extracted_data: Dict[str, Any]) -> LeadPriority:
        """Determine lead priority based on extracted signals."""
        intent = extracted_data.get("intent", {})

        # Hot: immediate need indicators
        urgency = self._get_value(intent, "urgency")
        timeline = self._get_value(intent, "target_timeline")

        if urgency == "high" or (timeline and "30 day" in str(timeline).lower()):
            return LeadPriority.HOT

        if self._get_value(intent, "has_property_identified"):
            return LeadPriority.HOT

        if self._get_value(intent, "has_preapproval"):
            return LeadPriority.WARM

        if urgency == "low" or (timeline and "year" in str(timeline).lower()):
            return LeadPriority.COLD

        return LeadPriority.WARM

    async def _find_existing_lead(self, lead_data: LeadData) -> Optional[str]:
        """Find existing lead by phone or email within the same organization."""
        if self.db_session:
            # Need at least one identifier to search
            if not lead_data.email and not lead_data.phone:
                return None

            try:
                # Build conditions based on available identifiers
                conditions = []
                params: Dict[str, Any] = {"org_id": lead_data.organization_id}

                if lead_data.email:
                    conditions.append("email = :email")
                    params["email"] = lead_data.email
                if lead_data.phone:
                    conditions.append("phone = :phone")
                    params["phone"] = lead_data.phone

                where_clause = " OR ".join(conditions)

                result = self.db_session.execute(
                    text(f"""
                        SELECT id FROM leads
                        WHERE organization_id = :org_id
                          AND ({where_clause})
                        LIMIT 1
                    """),
                    params,
                )
                row = result.fetchone()
                if row:
                    return str(row[0])
            except Exception as e:
                logger.exception("Failed to query existing lead: %s", e)
                return None
        else:
            # In-memory lookup for testing
            for lead_id, existing in self._leads.items():
                if lead_data.email and existing.email == lead_data.email:
                    return lead_id
                if lead_data.phone and existing.phone == lead_data.phone:
                    return lead_id

        return None

    async def _create_lead(self, lead_data: LeadData, call_id: str) -> LeadResult:
        """Create a new lead."""
        result = LeadResult(success=True, action="created")

        # Set source and status
        lead_data.source = LeadSource.INBOUND_CALL
        lead_data.status = LeadStatus.NEW

        if self.db_session:
            try:
                now = datetime.now(timezone.utc)
                # Build the full name (Lead.name is NOT NULL)
                full_name = " ".join(
                    part for part in [lead_data.first_name, lead_data.last_name] if part
                ) or "Unknown"

                db_result = self.db_session.execute(
                    text("""
                        INSERT INTO leads
                            (organization_id, name, first_name, last_name,
                             email, phone, source, stage, ai_score,
                             loan_purpose, property_type, credit_score,
                             owner_id, notes, lead_received_date,
                             last_modified_by_ai, created_at, updated_at)
                        VALUES
                            (:organization_id, :name, :first_name, :last_name,
                             :email, :phone, :source, :stage, :ai_score,
                             :loan_purpose, :property_type, :credit_score,
                             :owner_id, :notes, :lead_received_date,
                             true, :created_at, :updated_at)
                        RETURNING id
                    """),
                    {
                        "organization_id": lead_data.organization_id,
                        "name": full_name,
                        "first_name": lead_data.first_name,
                        "last_name": lead_data.last_name,
                        "email": lead_data.email,
                        "phone": lead_data.phone,
                        "source": "call_intelligence",
                        "stage": "New",
                        "ai_score": lead_data.lead_score,
                        "loan_purpose": lead_data.loan_purpose,
                        "property_type": lead_data.property_type,
                        "credit_score": lead_data.estimated_credit_score,
                        "owner_id": int(lead_data.assigned_to) if lead_data.assigned_to else None,
                        "notes": f"Created from call {call_id}. Priority: {lead_data.priority.value}.",
                        "lead_received_date": now,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                lead_id = str(db_result.scalar())
                self.db_session.commit()
                result.lead_id = lead_id

                logger.info(
                    "Created lead %s in DB for org %s from call %s",
                    lead_id, lead_data.organization_id, call_id,
                )
            except Exception as e:
                logger.exception("Failed to insert lead from call %s: %s", call_id, e)
                self.db_session.rollback()
                result.success = False
                result.errors.append(f"DB insert failed: {e}")
                return result
        else:
            # In-memory storage for testing
            lead_id = str(uuid.uuid4())[:8].upper()
            result.lead_id = lead_id
            self._leads[lead_id] = lead_data

        result.changes_made = [
            f"Created new lead: {lead_data.first_name} {lead_data.last_name}",
            f"Score: {lead_data.lead_score}",
            f"Priority: {lead_data.priority.value}",
        ]

        if lead_data.tags:
            result.changes_made.append(f"Tags: {', '.join(lead_data.tags)}")

        return result

    async def _update_lead(
        self,
        lead_id: str,
        new_data: LeadData,
        call_id: str,
    ) -> LeadResult:
        """Update existing lead with new data from a call."""
        result = LeadResult(success=True, action="updated", lead_id=lead_id)

        if self.db_session:
            try:
                now = datetime.now(timezone.utc)

                # Build dynamic SET clause from non-null extracted fields.
                # Maps: LeadData field -> (leads column name, value)
                field_mapping = {
                    "first_name": ("first_name", new_data.first_name),
                    "last_name": ("last_name", new_data.last_name),
                    "email": ("email", new_data.email),
                    "phone": ("phone", new_data.phone),
                    "loan_purpose": ("loan_purpose", new_data.loan_purpose),
                    "property_type": ("property_type", new_data.property_type),
                    "credit_score": ("credit_score", new_data.estimated_credit_score),
                }

                set_clauses = []
                params: Dict[str, Any] = {
                    "lead_id": int(lead_id),
                    "org_id": new_data.organization_id,
                    "now": now,
                }
                changes = []

                for field_name, (col_name, value) in field_mapping.items():
                    if value is not None:
                        set_clauses.append(f"{col_name} = :{col_name}")
                        params[col_name] = value
                        changes.append(f"Updated {col_name}")

                # Update ai_score only if the new score is higher (use GREATEST)
                if new_data.lead_score:
                    set_clauses.append("ai_score = GREATEST(COALESCE(ai_score, 0), :ai_score)")
                    params["ai_score"] = new_data.lead_score

                # Update name if we have name parts
                if new_data.first_name or new_data.last_name:
                    # Rebuild full name: prefer new parts, keep existing via COALESCE
                    if new_data.first_name and new_data.last_name:
                        set_clauses.append("name = :full_name")
                        params["full_name"] = f"{new_data.first_name} {new_data.last_name}"
                    elif new_data.first_name:
                        set_clauses.append("name = :full_name")
                        params["full_name"] = new_data.first_name
                    elif new_data.last_name:
                        set_clauses.append("name = :full_name")
                        params["full_name"] = new_data.last_name

                # Append call reference to notes
                set_clauses.append(
                    "notes = COALESCE(notes, '') || :note_append"
                )
                params["note_append"] = f"\n[{now.isoformat()}] Updated from call {call_id}."

                # Always mark as AI-modified and update timestamp
                set_clauses.append("last_modified_by_ai = true")
                set_clauses.append("updated_at = :now")

                if not set_clauses:
                    result.changes_made = ["No changes needed"]
                    return result

                set_sql = ", ".join(set_clauses)
                self.db_session.execute(
                    text(f"""
                        UPDATE leads
                        SET {set_sql}
                        WHERE id = :lead_id AND organization_id = :org_id
                    """),
                    params,
                )
                self.db_session.commit()

                result.changes_made = changes if changes else ["Metadata updated"]
                logger.info(
                    "Updated lead %s from call %s: %s",
                    lead_id, call_id, ", ".join(changes) if changes else "metadata only",
                )
            except Exception as e:
                logger.exception("Failed to update lead %s from call %s: %s", lead_id, call_id, e)
                self.db_session.rollback()
                result.success = False
                result.errors.append(f"DB update failed: {e}")
        else:
            # In-memory update for testing
            existing = self._leads.get(lead_id)
            if existing:
                # Merge data, preferring new non-null values
                changes = []

                if new_data.first_name and new_data.first_name != existing.first_name:
                    changes.append(f"first_name: {existing.first_name} -> {new_data.first_name}")
                    existing.first_name = new_data.first_name

                if new_data.last_name and new_data.last_name != existing.last_name:
                    changes.append(f"last_name: {existing.last_name} -> {new_data.last_name}")
                    existing.last_name = new_data.last_name

                if new_data.email and new_data.email != existing.email:
                    changes.append(f"email: {existing.email} -> {new_data.email}")
                    existing.email = new_data.email

                if new_data.phone and new_data.phone != existing.phone:
                    changes.append(f"phone: {existing.phone} -> {new_data.phone}")
                    existing.phone = new_data.phone

                if new_data.estimated_amount and new_data.estimated_amount != existing.estimated_amount:
                    changes.append(f"estimated_amount: {existing.estimated_amount} -> {new_data.estimated_amount}")
                    existing.estimated_amount = new_data.estimated_amount

                if new_data.estimated_credit_score and new_data.estimated_credit_score != existing.estimated_credit_score:
                    changes.append(f"credit_score: {existing.estimated_credit_score} -> {new_data.estimated_credit_score}")
                    existing.estimated_credit_score = new_data.estimated_credit_score

                # Update score if new is higher
                if new_data.lead_score > existing.lead_score:
                    changes.append(f"score: {existing.lead_score} -> {new_data.lead_score}")
                    existing.lead_score = new_data.lead_score

                # Merge tags
                new_tags = set(new_data.tags) - set(existing.tags)
                if new_tags:
                    existing.tags.extend(new_tags)
                    changes.append(f"added tags: {', '.join(new_tags)}")

                result.changes_made = changes if changes else ["No changes needed"]

        return result

    async def get_lead(self, lead_id: str) -> Optional[LeadData]:
        """Get lead by ID."""
        if self.db_session:
            try:
                result = self.db_session.execute(
                    text("""
                        SELECT first_name, last_name, email, phone, source,
                               stage, ai_score, loan_purpose, property_type,
                               credit_score, owner_id, notes, organization_id
                        FROM leads
                        WHERE id = :lead_id
                    """),
                    {"lead_id": int(lead_id)},
                )
                row = result.fetchone()
                if row:
                    lead = LeadData(
                        first_name=row[0],
                        last_name=row[1],
                        email=row[2],
                        phone=row[3],
                        source=LeadSource.INBOUND_CALL,
                        status=LeadStatus.NEW if row[5] == "New" else LeadStatus.CONTACTED,
                        lead_score=row[6] or 50,
                        loan_purpose=row[7],
                        property_type=row[8],
                        estimated_credit_score=row[9],
                        assigned_to=str(row[10]) if row[10] else None,
                        organization_id=row[12],
                        notes=row[11] or "",
                    )
                    return lead
            except Exception as e:
                logger.exception("Failed to fetch lead %s: %s", lead_id, e)
            return None
        else:
            return self._leads.get(lead_id)

    async def update_lead_status(
        self,
        lead_id: str,
        new_status: LeadStatus,
        notes: Optional[str] = None,
    ) -> LeadResult:
        """Update lead status."""
        result = LeadResult(success=False, lead_id=lead_id)

        if self.db_session:
            try:
                now = datetime.now(timezone.utc)

                # Map LeadStatus to CRM stage values
                status_to_stage = {
                    LeadStatus.NEW: "New",
                    LeadStatus.CONTACTED: "Contacted",
                    LeadStatus.QUALIFIED: "Pre-Qualified",
                    LeadStatus.NURTURING: "Nurture",
                    LeadStatus.APPLICATION_STARTED: "Application",
                    LeadStatus.CONVERTED: "Converted",
                    LeadStatus.LOST: "Dead",
                }
                new_stage = status_to_stage.get(new_status, "New")

                note_append = ""
                if notes:
                    note_append = f"\n[{now.isoformat()}] {notes}"

                self.db_session.execute(
                    text("""
                        UPDATE leads
                        SET stage = :stage,
                            stage_changed_at = :now,
                            notes = COALESCE(notes, '') || :note_append,
                            last_modified_by_ai = true,
                            updated_at = :now
                        WHERE id = :lead_id
                    """),
                    {
                        "stage": new_stage,
                        "now": now,
                        "note_append": note_append,
                        "lead_id": int(lead_id),
                    },
                )
                self.db_session.commit()

                result.success = True
                result.action = "status_updated"
                result.changes_made = [f"Stage -> {new_stage}"]
                logger.info("Lead %s stage updated to %s", lead_id, new_stage)
            except Exception as e:
                logger.exception("Failed to update lead %s status: %s", lead_id, e)
                self.db_session.rollback()
                result.errors.append(f"DB update failed: {e}")
        else:
            lead = self._leads.get(lead_id)
            if lead:
                old_status = lead.status
                lead.status = new_status
                if notes:
                    lead.notes = f"{lead.notes}\n{datetime.now(timezone.utc).isoformat()}: {notes}"

                result.success = True
                result.action = "status_updated"
                result.changes_made = [f"Status: {old_status.value} -> {new_status.value}"]
            else:
                result.errors.append(f"Lead {lead_id} not found")

        return result


# =============================================================================
# Factory
# =============================================================================

def create_lead_service(db_session=None) -> LeadManagementService:
    """Create lead management service instance."""
    return LeadManagementService(db_session)
