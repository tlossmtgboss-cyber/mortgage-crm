"""
Calculator Share Service

Manages shareable links for calculator results and other call artifacts.
Allows loan officers to generate secure, expiring links for sharing
calculator results with borrowers during video calls.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class CalculatorShareService:
    """
    Service for managing shareable artifact links.

    Features:
    - Generate unique share tokens
    - Set expiration times
    - Track view counts
    - Deactivate links
    """

    def __init__(self, db: Session):
        self.db = db

    def create_share_link(
        self,
        artifact_id: str,
        user_id: int,
        expires_in_days: int = 7,
        title_override: Optional[str] = None,
        description_override: Optional[str] = None,
        organization_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a shareable link for an artifact.

        Args:
            artifact_id: UUID of the call artifact to share
            user_id: ID of user creating the share link
            expires_in_days: Days until link expires (default 7)
            title_override: Optional custom title for shared view
            description_override: Optional custom description
            organization_id: Tenant org ID for isolation (returns 404 if artifact belongs to different org)

        Returns:
            Dict with share_token, share_url, and expiration info
        """
        # Verify artifact exists and belongs to the user's organization
        artifact_query = """
            SELECT id, artifact_type, content, session_id
            FROM call_artifacts
            WHERE id = :artifact_id
        """
        artifact_params = {"artifact_id": artifact_id}

        if organization_id:
            artifact_query += " AND organization_id = :org_id"
            artifact_params["org_id"] = organization_id

        artifact = self.db.execute(
            text(artifact_query),
            artifact_params
        ).fetchone()

        if not artifact:
            raise ValueError(f"Artifact {artifact_id} not found")

        # Generate secure token
        share_token = secrets.token_urlsafe(32)

        # Calculate expiration
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        # Insert share record
        self.db.execute(
            text("""
                INSERT INTO artifact_shares (
                    artifact_id, share_token, created_by, created_at,
                    expires_at, is_active, title_override, description_override
                ) VALUES (
                    :artifact_id, :share_token, :created_by, :created_at,
                    :expires_at, true, :title_override, :description_override
                )
            """),
            {
                "artifact_id": artifact_id,
                "share_token": share_token,
                "created_by": user_id,
                "created_at": datetime.now(timezone.utc),
                "expires_at": expires_at,
                "title_override": title_override,
                "description_override": description_override,
            }
        )
        self.db.commit()

        return {
            "share_token": share_token,
            "artifact_id": artifact_id,
            "expires_at": expires_at.isoformat(),
            "expires_in_days": expires_in_days,
            "share_url": f"/shared/calculator/{share_token}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_shared_artifact(
        self,
        share_token: str,
        viewer_ip: Optional[str] = None,
        viewer_user_agent: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a shared artifact by its token.

        Args:
            share_token: The unique share token
            viewer_ip: Optional IP address for tracking
            viewer_user_agent: Optional user agent for tracking

        Returns:
            Artifact data if found and valid, None otherwise
        """
        # Get share record
        share = self.db.execute(
            text("""
                SELECT
                    s.id, s.artifact_id, s.expires_at, s.is_active,
                    s.title_override, s.description_override, s.view_count
                FROM artifact_shares s
                WHERE s.share_token = :share_token
            """),
            {"share_token": share_token}
        ).fetchone()

        if not share:
            logger.warning(f"Share token not found: {share_token[:8]}...")
            return None

        # Check if active
        if not share.is_active:
            logger.info(f"Share link deactivated: {share_token[:8]}...")
            return None

        # Check expiration
        if share.expires_at and share.expires_at < datetime.now(timezone.utc):
            logger.info(f"Share link expired: {share_token[:8]}...")
            return None

        # Get artifact
        artifact = self.db.execute(
            text("""
                SELECT
                    a.id, a.artifact_type, a.content, a.confidence_score,
                    a.created_at, a.session_id,
                    cs.loan_id, cs.lead_id, cs.contact_id
                FROM call_artifacts a
                LEFT JOIN call_sessions cs ON cs.id = a.session_id
                WHERE a.id = :artifact_id
            """),
            {"artifact_id": str(share.artifact_id)}
        ).fetchone()

        if not artifact:
            logger.error(f"Artifact not found for share: {share_token[:8]}...")
            return None

        # Update view count and tracking
        self.db.execute(
            text("""
                UPDATE artifact_shares
                SET
                    view_count = view_count + 1,
                    last_viewed_at = :now,
                    last_viewer_ip = :viewer_ip,
                    last_viewer_user_agent = :viewer_user_agent
                WHERE share_token = :share_token
            """),
            {
                "share_token": share_token,
                "now": datetime.now(timezone.utc),
                "viewer_ip": viewer_ip,
                "viewer_user_agent": viewer_user_agent[:500] if viewer_user_agent else None,
            }
        )
        self.db.commit()

        # Parse content
        import json
        content = artifact.content
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass

        return {
            "artifact_id": str(artifact.id),
            "artifact_type": artifact.artifact_type,
            "content": content,
            "confidence_score": artifact.confidence_score,
            "title": share.title_override,
            "description": share.description_override,
            "view_count": share.view_count + 1,
            "loan_id": artifact.loan_id,
        }

    def deactivate_share(self, share_token: str, user_id: int, organization_id: Optional[int] = None) -> bool:
        """
        Deactivate a share link.

        Args:
            share_token: The token to deactivate
            user_id: User requesting deactivation (must be creator)
            organization_id: Tenant org ID for isolation

        Returns:
            True if deactivated, False if not found or unauthorized
        """
        # Build query with org isolation via the parent artifact
        query = """
            UPDATE artifact_shares
            SET is_active = false
            WHERE share_token = :share_token
                AND (created_by = :user_id OR :user_id IN (
                    SELECT id FROM users WHERE role IN ('admin', 'super_admin')
                ))
        """
        params = {"share_token": share_token, "user_id": user_id}

        if organization_id:
            query += """
                AND artifact_id IN (
                    SELECT id FROM call_artifacts WHERE organization_id = :org_id
                )
            """
            params["org_id"] = organization_id

        result = self.db.execute(text(query), params)
        self.db.commit()

        return result.rowcount > 0

    def get_shares_for_artifact(self, artifact_id: str, organization_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all share links for an artifact.

        Args:
            artifact_id: The artifact UUID
            organization_id: Tenant org ID for isolation (returns empty if artifact belongs to different org)

        Returns:
            List of share link records
        """
        # Verify artifact belongs to the caller's organization
        if organization_id:
            artifact_check = self.db.execute(
                text("SELECT id FROM call_artifacts WHERE id = :artifact_id AND organization_id = :org_id"),
                {"artifact_id": artifact_id, "org_id": organization_id}
            ).fetchone()
            if not artifact_check:
                return []

        shares = self.db.execute(
            text("""
                SELECT
                    id, share_token, created_by, created_at,
                    expires_at, view_count, last_viewed_at, is_active
                FROM artifact_shares
                WHERE artifact_id = :artifact_id
                ORDER BY created_at DESC
            """),
            {"artifact_id": artifact_id}
        ).fetchall()

        return [
            {
                "id": s.id,
                "share_token": s.share_token,
                "created_by": s.created_by,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "view_count": s.view_count,
                "last_viewed_at": s.last_viewed_at.isoformat() if s.last_viewed_at else None,
                "is_active": s.is_active,
                "is_expired": s.expires_at and s.expires_at < datetime.now(timezone.utc),
            }
            for s in shares
        ]

    def get_user_shares(
        self,
        user_id: int,
        include_expired: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get all share links created by a user.

        Args:
            user_id: The user ID
            include_expired: Whether to include expired links
            limit: Max results to return

        Returns:
            List of share records with artifact info
        """
        query = """
            SELECT
                s.id, s.share_token, s.artifact_id, s.created_at,
                s.expires_at, s.view_count, s.is_active,
                a.artifact_type, a.content
            FROM artifact_shares s
            JOIN call_artifacts a ON a.id = s.artifact_id
            WHERE s.created_by = :user_id
        """

        if not include_expired:
            query += " AND (s.expires_at IS NULL OR s.expires_at > :now)"

        query += " ORDER BY s.created_at DESC LIMIT :limit"

        params = {
            "user_id": user_id,
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        shares = self.db.execute(text(query), params).fetchall()

        import json
        results = []
        for s in shares:
            content = s.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass

            results.append({
                "id": s.id,
                "share_token": s.share_token,
                "artifact_id": str(s.artifact_id),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "view_count": s.view_count,
                "is_active": s.is_active,
                "artifact_type": s.artifact_type,
                "content_preview": self._get_content_preview(s.artifact_type, content),
            })

        return results

    def _get_content_preview(self, artifact_type: str, content: Any) -> str:
        """Generate a preview string for artifact content."""
        if not content:
            return ""

        if isinstance(content, dict):
            if artifact_type == "calculator_result":
                calc_type = content.get("calculator_type", "unknown")
                outputs = content.get("outputs", {})

                if calc_type == "piti":
                    total = outputs.get("total_payment", 0)
                    return f"PITI: ${total:,.2f}/mo"
                elif calc_type == "dti":
                    front = outputs.get("front_end_ratio", 0)
                    back = outputs.get("back_end_ratio", 0)
                    return f"DTI: {front:.1f}% / {back:.1f}%"
                elif calc_type == "ltv":
                    ltv = outputs.get("ltv", 0)
                    return f"LTV: {ltv:.1f}%"
                elif calc_type == "affordability":
                    max_price = outputs.get("max_purchase_price", 0)
                    return f"Max Price: ${max_price:,.0f}"
                elif calc_type == "closing_costs":
                    total = outputs.get("total_estimated", 0)
                    return f"Closing Costs: ${total:,.0f}"
                else:
                    return f"Calculator: {calc_type}"

            return str(content)[:100]

        return str(content)[:100]

    def cleanup_expired_shares(self, days_past_expiry: int = 30) -> int:
        """
        Clean up old expired share records.

        Args:
            days_past_expiry: Delete records expired more than this many days ago

        Returns:
            Number of records deleted
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_past_expiry)

        result = self.db.execute(
            text("""
                DELETE FROM artifact_shares
                WHERE expires_at < :cutoff
            """),
            {"cutoff": cutoff}
        )
        self.db.commit()

        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired share records")

        return deleted


def generate_embed_html(artifact: Dict[str, Any], base_url: str = "") -> str:
    """
    Generate embeddable HTML for a calculator result.

    This can be used in iframes for portal integration or
    email embedding.

    Args:
        artifact: The artifact data dict
        base_url: Base URL for assets

    Returns:
        HTML string for embedding
    """
    content = artifact.get("content", {})
    artifact_type = artifact.get("artifact_type", "")

    if artifact_type != "calculator_result":
        return f"<div>Unsupported artifact type: {artifact_type}</div>"

    calc_type = content.get("calculator_type", "unknown")
    outputs = content.get("outputs", {})
    inputs = content.get("inputs", {})

    # Build HTML based on calculator type
    if calc_type == "piti":
        html = _generate_piti_html(outputs, inputs)
    elif calc_type == "dti":
        html = _generate_dti_html(outputs, inputs)
    elif calc_type == "ltv":
        html = _generate_ltv_html(outputs, inputs)
    elif calc_type == "affordability":
        html = _generate_affordability_html(outputs, inputs)
    elif calc_type == "closing_costs":
        html = _generate_closing_costs_html(outputs, inputs)
    elif calc_type == "amortization":
        html = _generate_amortization_html(outputs, inputs)
    else:
        html = f"<div>Calculator type: {calc_type}</div>"

    # Wrap in styled container
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Calculator Result</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
            }}
            .calculator-card {{
                background: white;
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                max-width: 500px;
                margin: 0 auto;
            }}
            .calculator-title {{
                font-size: 18px;
                font-weight: 600;
                color: #1a365d;
                margin-bottom: 16px;
            }}
            .calculator-result {{
                font-size: 32px;
                font-weight: 700;
                color: #2563eb;
                margin-bottom: 16px;
            }}
            .result-row {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #e5e7eb;
            }}
            .result-label {{
                color: #6b7280;
            }}
            .result-value {{
                font-weight: 500;
                color: #111827;
            }}
            .gauge-container {{
                width: 100%;
                height: 20px;
                background: #e5e7eb;
                border-radius: 10px;
                overflow: hidden;
                margin: 12px 0;
            }}
            .gauge-fill {{
                height: 100%;
                border-radius: 10px;
                transition: width 0.3s ease;
            }}
            .inputs-section {{
                margin-top: 20px;
                padding-top: 16px;
                border-top: 1px solid #e5e7eb;
            }}
            .inputs-title {{
                font-size: 14px;
                font-weight: 600;
                color: #6b7280;
                margin-bottom: 12px;
            }}
        </style>
    </head>
    <body>
        {html}
    </body>
    </html>
    """


def _generate_piti_html(outputs: Dict, inputs: Dict) -> str:
    """Generate HTML for PITI calculator."""
    total = outputs.get("total_payment", 0)
    pi = outputs.get("principal_interest", 0)
    taxes = outputs.get("property_taxes", 0)
    insurance = outputs.get("homeowners_insurance", 0)
    pmi = outputs.get("mortgage_insurance", 0)
    hoa = outputs.get("hoa", 0)

    return f"""
    <div class="calculator-card">
        <div class="calculator-title">Monthly Payment (PITI)</div>
        <div class="calculator-result">${total:,.2f}</div>
        <div class="result-row">
            <span class="result-label">Principal & Interest</span>
            <span class="result-value">${pi:,.2f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Property Taxes</span>
            <span class="result-value">${taxes:,.2f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Home Insurance</span>
            <span class="result-value">${insurance:,.2f}</span>
        </div>
        {f'<div class="result-row"><span class="result-label">Mortgage Insurance</span><span class="result-value">${pmi:,.2f}</span></div>' if pmi > 0 else ''}
        {f'<div class="result-row"><span class="result-label">HOA</span><span class="result-value">${hoa:,.2f}</span></div>' if hoa > 0 else ''}
    </div>
    """


def _generate_dti_html(outputs: Dict, inputs: Dict) -> str:
    """Generate HTML for DTI calculator."""
    front = outputs.get("front_end_ratio", 0)
    back = outputs.get("back_end_ratio", 0)
    max_back = 43  # Standard QM threshold

    back_color = "#22c55e" if back <= 36 else "#eab308" if back <= 43 else "#ef4444"

    return f"""
    <div class="calculator-card">
        <div class="calculator-title">Debt-to-Income Ratio</div>
        <div class="result-row">
            <span class="result-label">Front-End (Housing)</span>
            <span class="result-value">{front:.1f}%</span>
        </div>
        <div class="gauge-container">
            <div class="gauge-fill" style="width: {min(front, 100)}%; background: #3b82f6;"></div>
        </div>
        <div class="result-row">
            <span class="result-label">Back-End (Total)</span>
            <span class="result-value" style="color: {back_color}">{back:.1f}%</span>
        </div>
        <div class="gauge-container">
            <div class="gauge-fill" style="width: {min(back / max_back * 100, 100)}%; background: {back_color};"></div>
        </div>
        <div style="font-size: 12px; color: #6b7280; text-align: center; margin-top: 8px;">
            QM threshold: 43%
        </div>
    </div>
    """


def _generate_ltv_html(outputs: Dict, inputs: Dict) -> str:
    """Generate HTML for LTV calculator."""
    ltv = outputs.get("ltv", 0)
    cltv = outputs.get("cltv", 0)
    requires_pmi = outputs.get("requires_pmi", False)

    ltv_color = "#22c55e" if ltv <= 80 else "#eab308" if ltv <= 95 else "#ef4444"

    return f"""
    <div class="calculator-card">
        <div class="calculator-title">Loan-to-Value Ratio</div>
        <div class="calculator-result" style="color: {ltv_color}">{ltv:.1f}%</div>
        <div class="gauge-container">
            <div class="gauge-fill" style="width: {min(ltv, 100)}%; background: {ltv_color};"></div>
        </div>
        <div style="position: relative; height: 4px; margin-top: -8px;">
            <div style="position: absolute; left: 80%; width: 2px; height: 12px; background: #374151; top: -4px;"></div>
            <div style="position: absolute; left: 80%; transform: translateX(-50%); font-size: 10px; color: #6b7280; top: 12px;">80%</div>
        </div>
        <div style="margin-top: 24px;">
            {'<div style="color: #ef4444; font-size: 14px;">⚠️ PMI Required</div>' if requires_pmi else '<div style="color: #22c55e; font-size: 14px;">✓ No PMI Required</div>'}
        </div>
    </div>
    """


def _generate_affordability_html(outputs: Dict, inputs: Dict) -> str:
    """Generate HTML for affordability calculator."""
    max_price = outputs.get("max_purchase_price", 0)
    max_payment = outputs.get("max_monthly_payment", 0)
    max_loan = outputs.get("max_loan_amount", 0)

    return f"""
    <div class="calculator-card">
        <div class="calculator-title">Affordability Analysis</div>
        <div class="calculator-result">${max_price:,.0f}</div>
        <div style="font-size: 14px; color: #6b7280; margin-bottom: 16px;">Maximum Purchase Price</div>
        <div class="result-row">
            <span class="result-label">Max Monthly Payment</span>
            <span class="result-value">${max_payment:,.0f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Max Loan Amount</span>
            <span class="result-value">${max_loan:,.0f}</span>
        </div>
    </div>
    """


def _generate_closing_costs_html(outputs: Dict, inputs: Dict) -> str:
    """Generate HTML for closing costs calculator."""
    total = outputs.get("total_estimated", 0)
    lender = outputs.get("lender_fees", 0)
    third_party = outputs.get("third_party_fees", 0)
    prepaids = outputs.get("prepaids", 0)
    escrow = outputs.get("escrow_reserves", 0)

    return f"""
    <div class="calculator-card">
        <div class="calculator-title">Estimated Closing Costs</div>
        <div class="calculator-result">${total:,.0f}</div>
        <div class="result-row">
            <span class="result-label">Lender Fees</span>
            <span class="result-value">${lender:,.0f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Third Party Fees</span>
            <span class="result-value">${third_party:,.0f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Prepaids</span>
            <span class="result-value">${prepaids:,.0f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Escrow Reserves</span>
            <span class="result-value">${escrow:,.0f}</span>
        </div>
    </div>
    """


def _generate_amortization_html(outputs: Dict, inputs: Dict) -> str:
    """Generate HTML for amortization calculator."""
    schedule = outputs.get("schedule", [])[:6]  # First 6 months
    total_interest = outputs.get("total_interest", 0)
    total_cost = outputs.get("total_cost", 0)

    rows = ""
    for payment in schedule:
        rows += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{payment.get('month', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${payment.get('principal', 0):,.2f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${payment.get('interest', 0):,.2f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${payment.get('balance', 0):,.0f}</td>
        </tr>
        """

    return f"""
    <div class="calculator-card">
        <div class="calculator-title">Amortization Schedule</div>
        <div class="result-row">
            <span class="result-label">Total Interest</span>
            <span class="result-value">${total_interest:,.0f}</span>
        </div>
        <div class="result-row">
            <span class="result-label">Total Cost</span>
            <span class="result-value">${total_cost:,.0f}</span>
        </div>
        <table style="width: 100%; margin-top: 16px; border-collapse: collapse; font-size: 14px;">
            <thead>
                <tr style="background: #f9fafb;">
                    <th style="padding: 8px; text-align: left;">Month</th>
                    <th style="padding: 8px; text-align: left;">Principal</th>
                    <th style="padding: 8px; text-align: left;">Interest</th>
                    <th style="padding: 8px; text-align: left;">Balance</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    """
