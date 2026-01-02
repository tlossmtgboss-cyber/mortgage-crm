"""
Contract Portal Automation Service
Perennia AI - Mortgage CRM

Automatically creates and manages portals when a contract is received:
1. Client Portal (PURL Workspace) - for borrower access
2. Buyer's Agent Portal - for the buyer's realtor
3. Listing Agent Portal - for the seller's agent

If realtor information is missing, creates AI tasks to gather the info.
When realtors are added, automatically deploys invitations and portal access.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import secrets

logger = logging.getLogger(__name__)


class ContractPortalAutomationService:
    """
    Service to automate portal creation when contracts are received.

    Workflow:
    1. Contract received (document upload or manual trigger)
    2. Check if realtors are assigned to the loan
    3. If yes: Create portals and send invitations
    4. If no: Create AI task to enter realtor info
    5. When realtor info added: Trigger portal creation
    """

    def __init__(self, db: Session, notification_service=None):
        self.db = db
        self.notification_service = notification_service

    def process_contract_received(
        self,
        loan_id: int,
        triggered_by: str = "document_upload"
    ) -> Dict[str, Any]:
        """
        Main entry point when a contract is received.

        Args:
            loan_id: The loan ID that received the contract
            triggered_by: How this was triggered (document_upload, manual, status_change)

        Returns:
            Dict with results of portal creation attempts
        """
        logger.info(f"Processing contract received for loan {loan_id}, triggered by {triggered_by}")

        results = {
            "loan_id": loan_id,
            "triggered_by": triggered_by,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_portal": None,
            "buyers_agent_portal": None,
            "listing_agent_portal": None,
            "tasks_created": [],
            "invitations_sent": [],
            "errors": []
        }

        try:
            # Get loan and lead info
            loan_info = self._get_loan_info(loan_id)
            if not loan_info:
                results["errors"].append(f"Loan {loan_id} not found")
                return results

            # Update contract received date if not set
            self._update_contract_received_date(loan_id)

            # 1. Create/verify Client Portal (PURL Workspace)
            client_result = self._ensure_client_portal(loan_info)
            results["client_portal"] = client_result

            # 2. Handle Buyer's Agent Portal
            buyers_agent_result = self._handle_buyers_agent_portal(loan_info)
            results["buyers_agent_portal"] = buyers_agent_result
            if buyers_agent_result.get("task_created"):
                results["tasks_created"].append(buyers_agent_result["task_created"])
            if buyers_agent_result.get("invitation_sent"):
                results["invitations_sent"].append(buyers_agent_result["invitation_sent"])

            # 3. Handle Listing Agent Portal
            listing_agent_result = self._handle_listing_agent_portal(loan_info)
            results["listing_agent_portal"] = listing_agent_result
            if listing_agent_result.get("task_created"):
                results["tasks_created"].append(listing_agent_result["task_created"])
            if listing_agent_result.get("invitation_sent"):
                results["invitations_sent"].append(listing_agent_result["invitation_sent"])

            # Queue event for processing
            self._queue_contract_received_event(loan_id, results)

            logger.info(f"Contract portal automation completed for loan {loan_id}: "
                       f"{len(results['invitations_sent'])} invitations, "
                       f"{len(results['tasks_created'])} tasks")

        except Exception as e:
            logger.error(f"Error processing contract for loan {loan_id}: {e}")
            results["errors"].append(str(e))

        return results

    def _get_loan_info(self, loan_id: int) -> Optional[Dict]:
        """Get loan and associated information."""
        result = self.db.execute(text("""
            SELECT
                l.id as loan_id,
                l.amount,
                l.stage,
                l.property_address,
                l.property_city,
                l.property_state,
                l.property_zip,
                l.contract_received_date,
                l.target_close_date,
                l.owner_id,
                l.borrower_name,
                l.borrower_email,
                l.borrower_phone,
                l.referral_partner_id,
                l.loan_number,
                u.full_name as lo_name,
                u.email as lo_email,
                u.organization_id
            FROM loans l
            LEFT JOIN users u ON u.id = l.owner_id
            WHERE l.id = :loan_id
        """), {"loan_id": loan_id}).fetchone()

        if not result:
            return None

        return dict(result._mapping)

    def _update_contract_received_date(self, loan_id: int):
        """Set contract_received_date if not already set."""
        self.db.execute(text("""
            UPDATE loans
            SET contract_received_date = COALESCE(contract_received_date, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :loan_id
        """), {"loan_id": loan_id})
        self.db.commit()

    def _ensure_client_portal(self, loan_info: Dict) -> Dict[str, Any]:
        """Create or verify client portal (PURL workspace) exists."""
        result = {
            "status": "unknown",
            "workspace_id": None,
            "workspace_slug": None,
            "portal_url": None
        }

        loan_id = loan_info["loan_id"]

        # Check if workspace already exists
        existing = self.db.execute(text("""
            SELECT id, slug, status
            FROM purl_workspaces
            WHERE loan_id = :loan_id
            LIMIT 1
        """), {"loan_id": loan_id}).fetchone()

        if existing:
            result["status"] = "exists"
            result["workspace_id"] = existing[0]
            result["workspace_slug"] = existing[1]
            result["portal_url"] = f"/portal/{existing[1]}"
            return result

        # Create new workspace
        try:
            borrower_name = loan_info.get("borrower_name", "Client")
            # Generate slug from borrower name
            slug_base = borrower_name.lower().replace(" ", "-").replace(".", "")
            slug = f"{slug_base}-{secrets.token_hex(4)}"

            self.db.execute(text("""
                INSERT INTO purl_workspaces (
                    loan_id, slug, status,
                    organization_id, created_at, updated_at
                ) VALUES (
                    :loan_id, :slug, 'active_loan',
                    :org_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "loan_id": loan_id,
                "slug": slug,
                "org_id": loan_info.get("organization_id", 1)
            })
            self.db.commit()

            # Get the created workspace ID
            new_ws = self.db.execute(text("""
                SELECT id FROM purl_workspaces WHERE slug = :slug
            """), {"slug": slug}).fetchone()

            result["status"] = "created"
            result["workspace_id"] = new_ws[0] if new_ws else None
            result["workspace_slug"] = slug
            result["portal_url"] = f"/portal/{slug}"

            # Send welcome email to borrower
            if loan_info.get("borrower_email") and self.notification_service:
                self._send_client_portal_invitation(loan_info, slug)

        except Exception as e:
            logger.error(f"Failed to create client portal for loan {loan_id}: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _handle_buyers_agent_portal(self, loan_info: Dict) -> Dict[str, Any]:
        """Handle buyer's agent portal - create if info exists, or create task if missing."""
        result = {
            "status": "unknown",
            "partner_id": None,
            "portal_url": None,
            "task_created": None,
            "invitation_sent": None
        }

        loan_id = loan_info["loan_id"]

        # Check if referral partner (buyer's agent) is assigned
        partner_id = loan_info.get("referral_partner_id")

        if partner_id:
            # Partner exists - get their info and send invitation
            partner = self.db.execute(text("""
                SELECT id, name, email, phone, company
                FROM referral_partners
                WHERE id = :partner_id
            """), {"partner_id": partner_id}).fetchone()

            if partner:
                result["status"] = "ready"
                result["partner_id"] = partner[0]
                result["portal_url"] = f"/partner-portal/{partner[0]}/loan/{loan_id}"

                # Send invitation if they have email
                if partner[2]:  # email
                    invitation = self._send_realtor_invitation(
                        loan_info=loan_info,
                        realtor_name=partner[1],
                        realtor_email=partner[2],
                        realtor_type="buyers_agent",
                        partner_id=partner[0]
                    )
                    if invitation:
                        result["invitation_sent"] = invitation
            else:
                result["status"] = "partner_not_found"
        else:
            # No partner assigned - check loan_team_members for buyer's realtor
            team_realtor = self.db.execute(text("""
                SELECT id, name, email, phone, referral_partner_id
                FROM loan_team_members
                WHERE loan_id = :loan_id
                AND role ILIKE '%realtor%' OR role ILIKE '%buyer%agent%'
                LIMIT 1
            """), {"loan_id": loan_id}).fetchone()

            if team_realtor and team_realtor[2]:  # Has email
                result["status"] = "team_member_found"
                # Create referral partner from team member if needed
                if not team_realtor[4]:  # No partner_id linked
                    partner_id = self._create_referral_partner_from_team_member(team_realtor, loan_id)
                    if partner_id:
                        result["partner_id"] = partner_id
                        result["portal_url"] = f"/partner-portal/{partner_id}/loan/{loan_id}"
                        # Send invitation
                        invitation = self._send_realtor_invitation(
                            loan_info=loan_info,
                            realtor_name=team_realtor[1],
                            realtor_email=team_realtor[2],
                            realtor_type="buyers_agent",
                            partner_id=partner_id
                        )
                        if invitation:
                            result["invitation_sent"] = invitation
            else:
                # No buyer's agent info - create task
                result["status"] = "missing_info"
                task = self._create_realtor_task(
                    loan_info=loan_info,
                    realtor_type="buyers_agent",
                    task_title="Enter Buyer's Agent Information",
                    task_description="A contract has been received but no buyer's agent is assigned. "
                                   "Please enter the buyer's agent information to enable their portal access."
                )
                if task:
                    result["task_created"] = task

        return result

    def _handle_listing_agent_portal(self, loan_info: Dict) -> Dict[str, Any]:
        """Handle listing agent portal - create transaction if info exists, or create task if missing."""
        result = {
            "status": "unknown",
            "transaction_id": None,
            "portal_url": None,
            "task_created": None,
            "invitation_sent": None
        }

        loan_id = loan_info["loan_id"]

        # Check if listing transaction already exists
        existing_tx = self.db.execute(text("""
            SELECT id, status FROM listing_transactions
            WHERE loan_id = :loan_id
            LIMIT 1
        """), {"loan_id": loan_id}).fetchone()

        if existing_tx:
            result["status"] = "exists"
            result["transaction_id"] = existing_tx[0]
            result["portal_url"] = f"/listing-portal/transaction/{existing_tx[0]}"
            return result

        # Check loan_team_members for listing agent
        listing_agent = self.db.execute(text("""
            SELECT id, name, email, phone, company
            FROM loan_team_members
            WHERE loan_id = :loan_id
            AND (role ILIKE '%listing%' OR role ILIKE '%seller%agent%')
            LIMIT 1
        """), {"loan_id": loan_id}).fetchone()

        if listing_agent and listing_agent[2]:  # Has email
            # Create listing transaction
            try:
                self.db.execute(text("""
                    INSERT INTO listing_transactions (
                        loan_id, property_address, property_city, property_state, property_zip,
                        purchase_price, contract_date, status, created_at, updated_at
                    ) VALUES (
                        :loan_id, :address, :city, :state, :zip,
                        :price, CURRENT_DATE, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """), {
                    "loan_id": loan_id,
                    "address": loan_info.get("property_address"),
                    "city": loan_info.get("property_city"),
                    "state": loan_info.get("property_state"),
                    "zip": loan_info.get("property_zip"),
                    "price": loan_info.get("amount")
                })
                self.db.commit()

                # Get transaction ID
                tx = self.db.execute(text("""
                    SELECT id FROM listing_transactions WHERE loan_id = :loan_id ORDER BY id DESC LIMIT 1
                """), {"loan_id": loan_id}).fetchone()

                if tx:
                    result["status"] = "created"
                    result["transaction_id"] = tx[0]
                    result["portal_url"] = f"/listing-portal/transaction/{tx[0]}"

                    # Add listing agent as party
                    self.db.execute(text("""
                        INSERT INTO listing_transaction_parties (
                            transaction_id, name, email, phone, company, role, created_at
                        ) VALUES (
                            :tx_id, :name, :email, :phone, :company, 'listing_agent', CURRENT_TIMESTAMP
                        )
                    """), {
                        "tx_id": tx[0],
                        "name": listing_agent[1],
                        "email": listing_agent[2],
                        "phone": listing_agent[3],
                        "company": listing_agent[4]
                    })
                    self.db.commit()

                    # Send invitation
                    invitation = self._send_realtor_invitation(
                        loan_info=loan_info,
                        realtor_name=listing_agent[1],
                        realtor_email=listing_agent[2],
                        realtor_type="listing_agent",
                        transaction_id=tx[0]
                    )
                    if invitation:
                        result["invitation_sent"] = invitation

            except Exception as e:
                logger.error(f"Failed to create listing transaction for loan {loan_id}: {e}")
                result["status"] = "error"
                result["error"] = str(e)
        else:
            # No listing agent info - create task
            result["status"] = "missing_info"
            task = self._create_realtor_task(
                loan_info=loan_info,
                realtor_type="listing_agent",
                task_title="Enter Listing Agent Information",
                task_description="A contract has been received but no listing agent is assigned. "
                               "Please enter the listing agent information to enable their portal access."
            )
            if task:
                result["task_created"] = task

        return result

    def _create_referral_partner_from_team_member(
        self,
        team_member: tuple,
        loan_id: int
    ) -> Optional[int]:
        """Create a referral partner record from a loan team member."""
        try:
            self.db.execute(text("""
                INSERT INTO referral_partners (
                    name, email, phone, category, company, status,
                    owner_id, created_at, updated_at
                )
                SELECT
                    :name, :email, :phone, 'realtor', :company, 'active',
                    l.owner_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM loans l WHERE l.id = :loan_id
            """), {
                "name": team_member[1],
                "email": team_member[2],
                "phone": team_member[3],
                "company": None,  # Team member tuple doesn't have company at index 4
                "loan_id": loan_id
            })
            self.db.commit()

            # Get the new partner ID
            partner = self.db.execute(text("""
                SELECT id FROM referral_partners WHERE email = :email ORDER BY id DESC LIMIT 1
            """), {"email": team_member[2]}).fetchone()

            if partner:
                # Link to team member
                self.db.execute(text("""
                    UPDATE loan_team_members SET referral_partner_id = :partner_id WHERE id = :tm_id
                """), {"partner_id": partner[0], "tm_id": team_member[0]})

                # Also update the loan's referral_partner_id
                self.db.execute(text("""
                    UPDATE loans SET referral_partner_id = :partner_id, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :loan_id AND referral_partner_id IS NULL
                """), {"partner_id": partner[0], "loan_id": loan_id})
                self.db.commit()

                return partner[0]

        except Exception as e:
            logger.error(f"Failed to create referral partner from team member: {e}")
            self.db.rollback()

        return None

    def _create_realtor_task(
        self,
        loan_info: Dict,
        realtor_type: str,
        task_title: str,
        task_description: str
    ) -> Optional[Dict]:
        """Create an AI task to enter missing realtor information."""
        try:
            loan_id = loan_info["loan_id"]
            owner_id = loan_info.get("owner_id")

            self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, status, priority,
                    due_date, owner_id, loan_id,
                    created_at, updated_at
                ) VALUES (
                    :title, :description, 'pending', 'high',
                    :due_date, :owner_id, :loan_id,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "title": task_title,
                "description": task_description,
                "due_date": datetime.now(timezone.utc) + timedelta(days=1),
                "owner_id": owner_id,
                "loan_id": loan_id
            })
            self.db.commit()

            # Get task ID by title pattern (task_type column may not exist in production)
            task = self.db.execute(text("""
                SELECT id FROM tasks WHERE loan_id = :loan_id AND title = :title
                ORDER BY id DESC LIMIT 1
            """), {"loan_id": loan_id, "title": task_title}).fetchone()

            return {
                "task_id": task[0] if task else None,
                "title": task_title,
                "realtor_type": realtor_type,
                "assigned_to": owner_id
            }

        except Exception as e:
            logger.error(f"Failed to create realtor task: {e}")
            self.db.rollback()

        return None

    def _send_realtor_invitation(
        self,
        loan_info: Dict,
        realtor_name: str,
        realtor_email: str,
        realtor_type: str,
        partner_id: Optional[int] = None,
        transaction_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Send portal invitation email to realtor."""
        if not self.notification_service:
            logger.warning("Notification service not available, skipping invitation email")
            return None

        try:
            # Generate magic link token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            # Store invitation
            if realtor_type == "listing_agent" and transaction_id:
                self.db.execute(text("""
                    INSERT INTO listing_transaction_invites (
                        transaction_id, email, token, expires_at, created_at
                    ) VALUES (
                        :tx_id, :email, :token, :expires_at, CURRENT_TIMESTAMP
                    )
                """), {
                    "tx_id": transaction_id,
                    "email": realtor_email,
                    "token": token,
                    "expires_at": expires_at
                })
                portal_url = f"/listing-portal/accept-invite?token={token}"
            else:
                # For buyer's agent, store in realtor_magic_links or similar
                self.db.execute(text("""
                    INSERT INTO realtor_magic_links (
                        realtor_id, token, expires_at, created_at
                    )
                    SELECT rpu.id, :token, :expires_at, CURRENT_TIMESTAMP
                    FROM realtor_portal_users rpu
                    WHERE rpu.email = :email
                    LIMIT 1
                """), {
                    "email": realtor_email,
                    "token": token,
                    "expires_at": expires_at
                })
                loan_id = loan_info.get("loan_id")
                portal_url = f"/partner-portal/{partner_id}/loan/{loan_id}?token={token}"

            self.db.commit()

            # Send email
            borrower_name = loan_info.get("borrower_name", "your client")
            property_address = loan_info.get("property_address", "the property")
            lo_name = loan_info.get("lo_name", "The Loan Officer")

            portal_type = "Buyer's Agent" if realtor_type == "buyers_agent" else "Listing Agent"

            subject = f"Portal Access: {borrower_name} - {property_address}"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>You've Been Invited to the {portal_type} Portal</h2>
                <p>Hi {realtor_name},</p>
                <p>{lo_name} has invited you to access the {portal_type} Portal for:</p>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <strong>Borrower:</strong> {borrower_name}<br>
                    <strong>Property:</strong> {property_address}
                </div>
                <p>Through this portal, you can:</p>
                <ul>
                    <li>Track loan status in real-time</li>
                    <li>View and download documents</li>
                    <li>Communicate securely with the loan team</li>
                    <li>Generate pre-approval letters</li>
                </ul>
                <p style="margin: 30px 0;">
                    <a href="{portal_url}" style="background: #3b82f6; color: white; padding: 12px 24px;
                       text-decoration: none; border-radius: 6px; display: inline-block;">
                        Access Your Portal
                    </a>
                </p>
                <p style="color: #666; font-size: 12px;">
                    This link expires in 30 days. If you have any questions, please contact {lo_name}.
                </p>
            </body>
            </html>
            """

            self.notification_service.send_email(
                to_email=realtor_email,
                subject=subject,
                html_content=html_body,
                from_name=lo_name
            )

            return {
                "email": realtor_email,
                "name": realtor_name,
                "type": realtor_type,
                "portal_url": portal_url,
                "sent_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to send realtor invitation: {e}")
            self.db.rollback()

        return None

    def _send_client_portal_invitation(self, loan_info: Dict, workspace_slug: str):
        """Send welcome email to borrower for client portal."""
        if not self.notification_service:
            return

        try:
            borrower_email = loan_info.get("borrower_email")
            borrower_name = loan_info.get("borrower_name", "Valued Client")
            lo_name = loan_info.get("lo_name", "Your Loan Officer")
            property_address = loan_info.get("property_address", "your new home")

            subject = f"Your Loan Portal is Ready - {property_address}"
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Congratulations on Your Contract!</h2>
                <p>Hi {borrower_name},</p>
                <p>Great news! Your purchase contract has been received and your personal loan portal is now ready.</p>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <strong>Property:</strong> {property_address}
                </div>
                <p>Through your portal, you can:</p>
                <ul>
                    <li>Upload required documents securely</li>
                    <li>Track your loan progress in real-time</li>
                    <li>Complete your application digitally</li>
                    <li>Message your loan team anytime</li>
                    <li>View important deadlines and milestones</li>
                </ul>
                <p style="margin: 30px 0;">
                    <a href="/portal/{workspace_slug}" style="background: #10b981; color: white; padding: 12px 24px;
                       text-decoration: none; border-radius: 6px; display: inline-block;">
                        Access Your Portal
                    </a>
                </p>
                <p>If you have any questions, I'm here to help!</p>
                <p>Best regards,<br>{lo_name}</p>
            </body>
            </html>
            """

            self.notification_service.send_email(
                to_email=borrower_email,
                subject=subject,
                html_content=html_body,
                from_name=lo_name
            )

        except Exception as e:
            logger.error(f"Failed to send client portal invitation: {e}")

    def _queue_contract_received_event(self, loan_id: int, results: Dict):
        """Queue a contract_received event for async processing."""
        try:
            # Get workspace ID if created
            workspace_id = None
            if results.get("client_portal", {}).get("workspace_id"):
                workspace_id = results["client_portal"]["workspace_id"]

            self.db.execute(text("""
                INSERT INTO purl_events_outbox (
                    organization_id, workspace_id, event_key, payload,
                    status, created_at
                ) VALUES (
                    1, :workspace_id, 'contract_received', :payload,
                    'pending', CURRENT_TIMESTAMP
                )
            """), {
                "workspace_id": workspace_id,
                "payload": str(results)  # JSON serialize in production
            })
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to queue contract_received event: {e}")

    def on_realtor_added(
        self,
        loan_id: int,
        realtor_type: str,  # 'buyers_agent' or 'listing_agent'
        realtor_info: Dict
    ) -> Dict[str, Any]:
        """
        Called when a realtor is added to a loan after contract received.
        Deploys the portal and sends invitation.

        Args:
            loan_id: The loan ID
            realtor_type: 'buyers_agent' or 'listing_agent'
            realtor_info: Dict with name, email, phone, company, partner_id

        Returns:
            Dict with portal creation results
        """
        logger.info(f"Realtor added to loan {loan_id}: {realtor_type}")

        loan_info = self._get_loan_info(loan_id)
        if not loan_info:
            return {"error": f"Loan {loan_id} not found"}

        result = {
            "loan_id": loan_id,
            "realtor_type": realtor_type,
            "portal_created": False,
            "invitation_sent": None,
            "task_completed": False
        }

        if realtor_type == "buyers_agent":
            # Create/link referral partner if needed
            partner_id = realtor_info.get("partner_id")
            if not partner_id and realtor_info.get("email"):
                # Check if partner exists
                existing = self.db.execute(text("""
                    SELECT id FROM referral_partners WHERE email = :email LIMIT 1
                """), {"email": realtor_info["email"]}).fetchone()

                if existing:
                    partner_id = existing[0]
                else:
                    # Create new partner
                    self.db.execute(text("""
                        INSERT INTO referral_partners (
                            name, email, phone, company, category, status,
                            owner_id, created_at, updated_at
                        ) VALUES (
                            :name, :email, :phone, :company, 'realtor', 'active',
                            :owner_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """), {
                        "name": realtor_info.get("name"),
                        "email": realtor_info.get("email"),
                        "phone": realtor_info.get("phone"),
                        "company": realtor_info.get("company"),
                        "owner_id": loan_info.get("owner_id")
                    })
                    self.db.commit()

                    new_partner = self.db.execute(text("""
                        SELECT id FROM referral_partners WHERE email = :email ORDER BY id DESC LIMIT 1
                    """), {"email": realtor_info["email"]}).fetchone()
                    partner_id = new_partner[0] if new_partner else None

            if partner_id:
                # Update loan's referral_partner_id
                self.db.execute(text("""
                    UPDATE loans SET referral_partner_id = :partner_id, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :loan_id
                """), {"partner_id": partner_id, "loan_id": loan_id})
                self.db.commit()

                result["portal_created"] = True
                result["portal_url"] = f"/partner-portal/{partner_id}/loan/{loan_id}"

                # Send invitation
                invitation = self._send_realtor_invitation(
                    loan_info=loan_info,
                    realtor_name=realtor_info.get("name", "Realtor"),
                    realtor_email=realtor_info.get("email"),
                    realtor_type="buyers_agent",
                    partner_id=partner_id
                )
                if invitation:
                    result["invitation_sent"] = invitation

        elif realtor_type == "listing_agent":
            # Create listing transaction if not exists
            existing_tx = self.db.execute(text("""
                SELECT id FROM listing_transactions WHERE loan_id = :loan_id LIMIT 1
            """), {"loan_id": loan_id}).fetchone()

            if not existing_tx:
                self.db.execute(text("""
                    INSERT INTO listing_transactions (
                        loan_id, property_address, property_city, property_state, property_zip,
                        purchase_price, contract_date, status, created_at, updated_at
                    ) VALUES (
                        :loan_id, :address, :city, :state, :zip,
                        :price, CURRENT_DATE, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """), {
                    "loan_id": loan_id,
                    "address": loan_info.get("property_address"),
                    "city": loan_info.get("property_city"),
                    "state": loan_info.get("property_state"),
                    "zip": loan_info.get("property_zip"),
                    "price": loan_info.get("amount")
                })
                self.db.commit()

            tx = self.db.execute(text("""
                SELECT id FROM listing_transactions WHERE loan_id = :loan_id ORDER BY id DESC LIMIT 1
            """), {"loan_id": loan_id}).fetchone()

            if tx:
                # Add listing agent as party
                self.db.execute(text("""
                    INSERT INTO listing_transaction_parties (
                        transaction_id, name, email, phone, company, role, created_at
                    ) VALUES (
                        :tx_id, :name, :email, :phone, :company, 'listing_agent', CURRENT_TIMESTAMP
                    )
                """), {
                    "tx_id": tx[0],
                    "name": realtor_info.get("name"),
                    "email": realtor_info.get("email"),
                    "phone": realtor_info.get("phone"),
                    "company": realtor_info.get("company")
                })
                self.db.commit()

                result["portal_created"] = True
                result["portal_url"] = f"/listing-portal/transaction/{tx[0]}"

                # Send invitation
                invitation = self._send_realtor_invitation(
                    loan_info=loan_info,
                    realtor_name=realtor_info.get("name", "Listing Agent"),
                    realtor_email=realtor_info.get("email"),
                    realtor_type="listing_agent",
                    transaction_id=tx[0]
                )
                if invitation:
                    result["invitation_sent"] = invitation

        # Complete any pending tasks for this realtor type
        self.db.execute(text("""
            UPDATE tasks SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE loan_id = :loan_id AND task_type = :task_type AND status = 'pending'
        """), {"loan_id": loan_id, "task_type": f"enter_{realtor_type}_info"})
        self.db.commit()
        result["task_completed"] = True

        return result
