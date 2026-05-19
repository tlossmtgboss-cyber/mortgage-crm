"""
Global Search Routes

Extracted from inline_legacy_routes.py.
Provides cross-entity search across leads, loans, contacts, partners, and portfolio.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


def register_search_routes(app, get_db, get_current_user_flexible, Lead, Loan, LoanTeamMember, ReferralPartner, MUMClient, filter_leads_by_permissions, **kwargs):
    """Register global search routes."""

    @app.get("/api/v1/search/global")
    async def global_search(
        q: str,
        limit: int = 20,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user_flexible)
    ):
        """
        Global search across leads, loans, contacts, and partners.
        Returns categorized results from all entity types.
        """
        if not q or len(q.strip()) < 2:
            return {"results": [], "total": 0}

        search_term = q.strip().lower()
        results = []

        # Search Leads
        try:
            leads_query = db.query(Lead)
            leads_query = filter_leads_by_permissions(leads_query, current_user, db)
            leads_query = leads_query.filter(
                or_(
                    func.lower(Lead.name).contains(search_term),
                    func.lower(Lead.email).contains(search_term),
                    func.lower(Lead.phone).contains(search_term)
                )
            ).limit(limit)

            for lead in leads_query.all():
                results.append({
                    "id": lead.id,
                    "type": "lead",
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "status": lead.status if hasattr(lead, 'status') else lead.stage.value if lead.stage else None,
                    "url": f"/leads/{lead.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - leads error: {e}")

        # Search Loans (tenant-scoped)
        try:
            loans_query = db.query(Loan)
            # Tenant isolation: scope to user's organization
            org_id = getattr(current_user, 'organization_id', None)
            is_platform_admin = getattr(current_user, 'permission_role', '') == 'admin'
            if org_id and not is_platform_admin:
                loans_query = loans_query.filter(Loan.organization_id == org_id)
            loans_query = loans_query.filter(
                or_(
                    func.lower(Loan.borrower_name).contains(search_term),
                    func.lower(Loan.borrower_email).contains(search_term),
                    func.lower(Loan.loan_number).contains(search_term),
                    func.lower(Loan.property_address).contains(search_term)
                )
            ).limit(limit)

            for loan in loans_query.all():
                results.append({
                    "id": loan.id,
                    "type": "loan",
                    "name": loan.borrower_name,
                    "email": loan.borrower_email,
                    "phone": None,
                    "status": loan.status,
                    "loan_number": loan.loan_number,
                    "property_address": loan.property_address,
                    "url": f"/loans/{loan.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - loans error: {e}")

        # Search Loan Team Members (scoped via loan's org)
        try:
            team_members_query = db.query(LoanTeamMember).join(
                Loan, LoanTeamMember.loan_id == Loan.id
            )
            if org_id and not is_platform_admin:
                team_members_query = team_members_query.filter(Loan.organization_id == org_id)
            team_members_query = team_members_query.filter(
                or_(
                    func.lower(LoanTeamMember.name).contains(search_term),
                    func.lower(LoanTeamMember.email).contains(search_term),
                    func.lower(LoanTeamMember.company).contains(search_term)
                )
            ).limit(limit)

            for member in team_members_query.all():
                results.append({
                    "id": member.id,
                    "type": "contact",
                    "name": member.name,
                    "email": member.email,
                    "phone": member.phone,
                    "company": member.company,
                    "role": member.role,
                    "url": f"/loans/{member.loan_id}"
                })
        except Exception as e:
            logger.warning(f"Global search - team members error: {e}")

        # Search Referral Partners (tenant-scoped)
        try:
            partners_query = db.query(ReferralPartner)
            if org_id and not is_platform_admin:
                partners_query = partners_query.filter(ReferralPartner.organization_id == org_id)
            partners_query = partners_query.filter(
                or_(
                    func.lower(ReferralPartner.name).contains(search_term),
                    func.lower(ReferralPartner.email).contains(search_term),
                    func.lower(ReferralPartner.company).contains(search_term),
                    func.lower(ReferralPartner.contact_name).contains(search_term)
                )
            ).limit(limit)

            for partner in partners_query.all():
                results.append({
                    "id": partner.id,
                    "type": "partner",
                    "name": partner.name or partner.contact_name,
                    "email": partner.email,
                    "phone": partner.phone,
                    "company": partner.company or partner.business_name,
                    "partner_type": partner.type or partner.category,
                    "url": f"/referral-partners/{partner.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - partners error: {e}")

        # Search Portfolio Clients (tenant-scoped)
        try:
            portfolio_query = db.query(MUMClient)
            if org_id and not is_platform_admin:
                portfolio_query = portfolio_query.filter(MUMClient.organization_id == org_id)
            portfolio_query = portfolio_query.filter(
                or_(
                    func.lower(MUMClient.client_name).contains(search_term),
                    func.lower(MUMClient.email).contains(search_term),
                    func.lower(MUMClient.phone).contains(search_term),
                    func.lower(MUMClient.loan_number).contains(search_term)
                )
            ).limit(limit)

            for client in portfolio_query.all():
                results.append({
                    "id": client.id,
                    "type": "portfolio",
                    "name": client.client_name,
                    "email": client.email,
                    "phone": client.phone,
                    "loan_number": client.loan_number,
                    "status": client.status,
                    "url": f"/portfolio/{client.id}"
                })
        except Exception as e:
            logger.warning(f"Global search - portfolio error: {e}")

        # Sort by relevance
        def relevance_score(item):
            name = (item.get("name") or "").lower()
            if name == search_term:
                return 0
            if name.startswith(search_term):
                return 1
            return 2

        results.sort(key=relevance_score)

        return {
            "results": results[:limit],
            "total": len(results),
            "query": q
        }

    logger.info("✅ Global search routes loaded")
