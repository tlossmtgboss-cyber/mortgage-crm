"""
Perennia AI - Duplicate Detection Tools
Tools for identifying and managing duplicate leads in the CRM.
"""

from typing import Optional

from .base import (
    mortgage_tool, ToolResult,
    execute_query, execute_single,
    format_date,
)


@mortgage_tool(
    name="find_duplicate_contacts",
    description="Search for potential duplicate leads by email, phone, or name. Returns matches with a confidence score indicating how likely they are duplicates.",
    agent_roles=["data_quality_manager", "ops_manager", "lead_nurturer"],
    risk_level="low",
    examples=[
        "Find duplicates for this email address",
        "Check if this lead already exists",
        "Search for duplicate contacts",
        "Is there already a lead with this phone number?",
    ],
)
def find_duplicate_contacts(
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
) -> ToolResult:
    """Search for potential duplicate leads.

    Args:
        email: Email address to match against (exact, case-insensitive)
        phone: Phone number to match against (normalized)
        name: Full name to match against (case-insensitive)
    """
    try:
        if not email and not phone and not name:
            return ToolResult.error(
                "At least one search field (email, phone, or name) is required"
            )

        # Build search conditions and weights
        conditions = []
        params = {}

        if email:
            conditions.append(
                "(LOWER(l.email) = LOWER(:email))"
            )
            params["email"] = email

        if phone:
            # Normalize phone: strip non-digits for comparison
            clean_phone = "".join(c for c in phone if c.isdigit())
            if len(clean_phone) >= 10:
                # Match last 10 digits to handle +1 prefix variations
                phone_suffix = clean_phone[-10:]
                conditions.append(
                    "(REPLACE(REPLACE(REPLACE(REPLACE(l.phone, '-', ''), ' ', ''), '(', ''), ')', '') LIKE :phone_pattern)"
                )
                params["phone_pattern"] = f"%{phone_suffix}"

        if name:
            # Split name for first/last matching
            name_parts = name.strip().split()
            if len(name_parts) >= 2:
                conditions.append(
                    "(LOWER(l.first_name) = LOWER(:first_name) AND LOWER(l.last_name) = LOWER(:last_name))"
                )
                params["first_name"] = name_parts[0]
                params["last_name"] = " ".join(name_parts[1:])
            else:
                # Single name -- search both first and last
                conditions.append(
                    "(LOWER(l.first_name) = LOWER(:name_single) OR LOWER(l.last_name) = LOWER(:name_single))"
                )
                params["name_single"] = name_parts[0]

        if not conditions:
            return ToolResult.no_data("No valid search criteria after normalization")

        where_clause = " OR ".join(conditions)

        query = f"""
            SELECT
                l.id,
                l.first_name,
                l.last_name,
                l.name,
                l.email,
                l.phone,
                l.stage,
                l.source,
                l.owner_id,
                l.created_at,
                l.updated_at,
                l.ai_score
            FROM leads l
            WHERE ({where_clause})
            ORDER BY l.created_at DESC
            LIMIT 50
        """

        matches = execute_query(query, params)

        if not matches:
            return ToolResult.no_data("No matching leads found")

        # Score each match
        scored_matches = []
        for match in matches:
            confidence = 0
            match_reasons = []

            # Email match (strongest signal)
            if email and match.get("email") and match["email"].lower() == email.lower():
                confidence += 100
                match_reasons.append("exact_email")

            # Phone match
            if phone:
                clean_phone = "".join(c for c in phone if c.isdigit())
                match_phone = "".join(c for c in (match.get("phone") or "") if c.isdigit())
                if clean_phone and match_phone and clean_phone[-10:] == match_phone[-10:]:
                    confidence += 80
                    match_reasons.append("phone_match")

            # Name match
            if name:
                name_parts = name.strip().split()
                first = name_parts[0].lower() if name_parts else ""
                last = " ".join(name_parts[1:]).lower() if len(name_parts) > 1 else ""

                match_first = (match.get("first_name") or "").lower()
                match_last = (match.get("last_name") or "").lower()

                if first and last and match_first == first and match_last == last:
                    confidence += 60
                    match_reasons.append("full_name_match")
                elif last and match_last == last:
                    confidence += 30
                    match_reasons.append("last_name_match")
                elif first and match_first == first:
                    confidence += 20
                    match_reasons.append("first_name_match")

            # Cap at 100
            confidence = min(confidence, 100)

            scored_matches.append({
                "lead_id": match["id"],
                "name": match.get("name") or f"{match.get('first_name', '')} {match.get('last_name', '')}".strip(),
                "email": match.get("email"),
                "phone": match.get("phone"),
                "stage": match.get("stage"),
                "source": match.get("source"),
                "ai_score": match.get("ai_score"),
                "created_at": format_date(match.get("created_at")),
                "confidence": confidence,
                "match_reasons": match_reasons,
            })

        # Sort by confidence descending
        scored_matches.sort(key=lambda x: x["confidence"], reverse=True)

        high_confidence = [m for m in scored_matches if m["confidence"] >= 80]
        medium_confidence = [m for m in scored_matches if 40 <= m["confidence"] < 80]

        return ToolResult.success({
            "search_criteria": {
                "email": email,
                "phone": phone,
                "name": name,
            },
            "total_matches": len(scored_matches),
            "high_confidence_count": len(high_confidence),
            "medium_confidence_count": len(medium_confidence),
            "matches": scored_matches,
            "summary": (
                f"Found {len(scored_matches)} potential matches "
                f"({len(high_confidence)} high confidence, "
                f"{len(medium_confidence)} medium confidence)"
            ),
        })

    except Exception as e:
        return ToolResult.error(f"Failed to find duplicate contacts: {str(e)}")


@mortgage_tool(
    name="get_duplicate_candidates",
    description="Get system-identified groups of leads that share the same email address, indicating likely duplicates that need review and possible merging.",
    agent_roles=["data_quality_manager", "ops_manager"],
    risk_level="low",
    examples=[
        "Show me duplicate leads",
        "Find all duplicate groups",
        "Which leads are duplicated?",
        "Get data quality issues",
    ],
)
def get_duplicate_candidates(
    limit: int = 20,
) -> ToolResult:
    """Get groups of leads that share duplicate email addresses.

    Args:
        limit: Maximum number of duplicate groups to return (default 20)
    """
    try:
        # Find emails that appear on more than one lead
        dup_emails_query = """
            SELECT
                LOWER(l.email) as email_lower,
                COUNT(*) as duplicate_count
            FROM leads l
            WHERE l.email IS NOT NULL
                AND l.email != ''
                AND l.deleted_at IS NULL
            GROUP BY LOWER(l.email)
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT :limit
        """
        dup_emails = execute_query(dup_emails_query, {"limit": limit})

        if not dup_emails:
            return ToolResult.success({
                "duplicate_groups": [],
                "total_groups": 0,
                "total_duplicate_leads": 0,
                "summary": "No duplicate leads found. Data quality looks good.",
            })

        # For each duplicate email, get the lead details
        duplicate_groups = []
        total_duplicate_leads = 0

        for dup in dup_emails:
            email = dup["email_lower"]
            leads_query = """
                SELECT
                    l.id,
                    l.first_name,
                    l.last_name,
                    l.name,
                    l.email,
                    l.phone,
                    l.stage,
                    l.source,
                    l.owner_id,
                    l.ai_score,
                    l.created_at,
                    l.updated_at,
                    l.last_contact
                FROM leads l
                WHERE LOWER(l.email) = :email
                    AND l.deleted_at IS NULL
                ORDER BY l.created_at ASC
            """
            group_leads = execute_query(leads_query, {"email": email})

            if len(group_leads) < 2:
                continue

            total_duplicate_leads += len(group_leads)

            # Identify the "primary" lead (oldest, or highest AI score)
            primary = group_leads[0]  # Oldest by created_at
            for lead in group_leads:
                if (lead.get("ai_score") or 0) > (primary.get("ai_score") or 0):
                    primary = lead

            formatted_leads = []
            for lead in group_leads:
                formatted_leads.append({
                    "lead_id": lead["id"],
                    "name": lead.get("name") or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
                    "email": lead.get("email"),
                    "phone": lead.get("phone"),
                    "stage": lead.get("stage"),
                    "source": lead.get("source"),
                    "ai_score": lead.get("ai_score"),
                    "created_at": format_date(lead.get("created_at")),
                    "last_contact": format_date(lead.get("last_contact")),
                    "is_suggested_primary": lead["id"] == primary["id"],
                })

            duplicate_groups.append({
                "email": email,
                "count": len(group_leads),
                "suggested_primary_id": primary["id"],
                "leads": formatted_leads,
            })

        return ToolResult.success({
            "duplicate_groups": duplicate_groups,
            "total_groups": len(duplicate_groups),
            "total_duplicate_leads": total_duplicate_leads,
            "summary": (
                f"Found {len(duplicate_groups)} duplicate groups "
                f"affecting {total_duplicate_leads} leads. "
                f"Review and merge to improve data quality."
            ),
        })

    except Exception as e:
        return ToolResult.error(f"Failed to get duplicate candidates: {str(e)}")
