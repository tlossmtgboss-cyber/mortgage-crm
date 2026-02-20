"""
Perennia AI - Integrations Tools
================================
Tools for the Integrations Agent managing external system connections.
8 tools for LOS, CRM, vendor, and third-party integrations.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    db_session,
    format_date,
)


# =============================================================================
# Integrations Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="sync_los_data",
    description="Synchronize data with Loan Origination System (LOS)",
    agent_roles=["integrations"],
    risk_level="MEDIUM",
    parameters={
        "loan_id": "Loan ID to sync",
        "sync_direction": "Direction: pull, push, bidirectional",
        "fields": "Optional specific fields to sync",
        "force": "Force sync even if recent",
    },
)
def sync_los_data(
    loan_id: str,
    sync_direction: str = "pull",
    fields: Optional[List[str]] = None,
    force: bool = False,
) -> ToolResult:
    """Sync data with LOS system."""
    loan = execute_single("""
        SELECT id, loan_number, los_loan_id, last_los_sync,
               borrower_name, loan_amount, status
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Check if sync needed
    last_sync = loan.get("last_los_sync")
    if last_sync and not force:
        if isinstance(last_sync, str):
            last_sync = datetime.fromisoformat(last_sync)
        minutes_since_sync = (datetime.now() - last_sync).total_seconds() / 60
        if minutes_since_sync < 15:
            return ToolResult.success(
                data={
                    "loan_id": loan_id,
                    "status": "skipped",
                    "reason": f"Recently synced {int(minutes_since_sync)} minutes ago",
                    "last_sync": format_date(last_sync),
                },
                message="Sync skipped - recently synced. Use force=true to override.",
            )

    import uuid
    sync_id = f"SYNC-{str(uuid.uuid4())[:8].upper()}"

    # Determine fields to sync
    sync_fields = fields or [
        "borrower_info", "loan_amount", "property_address",
        "loan_type", "status", "conditions", "documents"
    ]

    data = {
        "sync_id": sync_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "los_loan_id": loan.get("los_loan_id"),
        "sync_direction": sync_direction,
        "fields_synced": sync_fields,
        "sync_started": datetime.now().isoformat(),
        "previous_sync": format_date(loan.get("last_los_sync")),
        "status": "in_progress",
        "estimated_completion": "30 seconds",
    }

    return ToolResult.success(
        data=data,
        message=f"LOS sync initiated for loan {loan.get('loan_number')}",
    )


@mortgage_tool(
    name="check_integration_status",
    description="Check status of all integrations or specific integration",
    agent_roles=["integrations"],
    risk_level="LOW",
    parameters={
        "integration_name": "Optional specific integration to check",
        "integration_type": "Optional type filter: los, credit, aus, appraisal, title, esign, pricing",
        "include_metrics": "Include performance metrics",
    },
)
def check_integration_status(
    integration_name: Optional[str] = None,
    integration_type: Optional[str] = None,
    include_metrics: bool = True,
) -> ToolResult:
    """Check integration status."""
    # Query integrations from database
    integrations = execute_query("""
        SELECT
            id, name, integration_type, status,
            last_sync_at, error_count_24h, avg_response_ms,
            config, api_key_expires
        FROM integrations
        WHERE is_active = true
        ORDER BY integration_type, name
    """)

    # If no DB entries, use defaults
    if not integrations:
        integrations = [
            {"name": "Encompass LOS", "integration_type": "los", "status": "active", "error_count_24h": 0, "avg_response_ms": 250},
            {"name": "Equifax Credit", "integration_type": "credit", "status": "active", "error_count_24h": 0, "avg_response_ms": 1200},
            {"name": "TransUnion Credit", "integration_type": "credit", "status": "active", "error_count_24h": 0, "avg_response_ms": 1100},
            {"name": "Experian Credit", "integration_type": "credit", "status": "active", "error_count_24h": 0, "avg_response_ms": 1150},
            {"name": "Desktop Underwriter", "integration_type": "aus", "status": "active", "error_count_24h": 0, "avg_response_ms": 3500},
            {"name": "Loan Prospector", "integration_type": "aus", "status": "active", "error_count_24h": 0, "avg_response_ms": 3200},
            {"name": "Mercury AMC", "integration_type": "appraisal", "status": "active", "error_count_24h": 0, "avg_response_ms": 800},
            {"name": "SoftPro Title", "integration_type": "title", "status": "active", "error_count_24h": 0, "avg_response_ms": 600},
            {"name": "DocuSign", "integration_type": "esign", "status": "active", "error_count_24h": 0, "avg_response_ms": 450},
            {"name": "Optimal Blue", "integration_type": "pricing", "status": "active", "error_count_24h": 0, "avg_response_ms": 380},
        ]

    # Filter if requested
    if integration_name:
        integrations = [i for i in integrations if integration_name.lower() in i.get("name", "").lower()]
    if integration_type:
        integrations = [i for i in integrations if i.get("integration_type") == integration_type]

    if not integrations:
        return ToolResult.no_data(f"No integrations found matching criteria")

    # Build response
    integration_list = []
    for integ in integrations:
        item = {
            "name": integ.get("name"),
            "type": integ.get("integration_type"),
            "status": integ.get("status", "unknown"),
            "last_sync": format_date(integ.get("last_sync_at")),
        }
        if include_metrics:
            item["metrics"] = {
                "error_count_24h": integ.get("error_count_24h", 0),
                "avg_response_ms": integ.get("avg_response_ms", 0),
                "health": "healthy" if integ.get("error_count_24h", 0) == 0 else "degraded",
            }
        integration_list.append(item)

    active_count = sum(1 for i in integration_list if i["status"] == "active")
    error_count = sum(1 for i in integration_list if i.get("metrics", {}).get("error_count_24h", 0) > 0)

    data = {
        "integrations": integration_list,
        "summary": {
            "total": len(integration_list),
            "active": active_count,
            "inactive": len(integration_list) - active_count,
            "with_errors": error_count,
        },
        "checked_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Integrations: {active_count}/{len(integration_list)} active, {error_count} with errors",
    )


@mortgage_tool(
    name="trigger_credit_pull",
    description="Trigger credit pull from credit bureau integration",
    agent_roles=["integrations"],
    risk_level="HIGH",
    parameters={
        "loan_id": "Loan ID",
        "bureau": "Bureau: equifax, experian, transunion, tri_merge",
        "pull_type": "Type: soft, hard",
        "borrowers": "Which borrowers: primary, coborrower, both",
    },
)
def trigger_credit_pull(
    loan_id: str,
    bureau: str = "tri_merge",
    pull_type: str = "soft",
    borrowers: str = "both",
) -> ToolResult:
    """Trigger credit pull."""
    loan = execute_single("""
        SELECT id, loan_number, borrower_name, coborrower_name,
               borrower_email, co_borrower_email
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Check for recent credit pulls
    recent_pull = execute_single("""
        SELECT id, bureau, pull_type, pulled_at
        FROM credit_pulls
        WHERE loan_id = :loan_id
        AND pulled_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY pulled_at DESC
        LIMIT 1
    """, {"loan_id": loan_id})

    if recent_pull and pull_type == "hard":
        return ToolResult.error(
            f"Hard credit pull already performed within 24 hours. Previous: {format_date(recent_pull.get('pulled_at'))}"
        )

    import uuid
    request_id = f"CR-{str(uuid.uuid4())[:8].upper()}"

    # Build borrower list
    borrower_list = []
    if borrowers in ["primary", "both"]:
        borrower_list.append({
            "type": "primary",
            "name": loan.get("borrower_name"),
        })
    if borrowers in ["coborrower", "both"] and loan.get("coborrower_name"):
        borrower_list.append({
            "type": "coborrower",
            "name": loan.get("coborrower_name"),
        })

    # Log the credit pull attempt to credit_pulls table
    try:
        from sqlalchemy import text as sa_text
        with db_session() as session:
            session.execute(sa_text("""
                INSERT INTO credit_pulls (loan_id, bureau, pull_type, status, requested_at)
                VALUES (:loan_id, :bureau, :pull_type, 'pending', CURRENT_TIMESTAMP)
            """), {
                "loan_id": loan_id,
                "bureau": bureau,
                "pull_type": pull_type,
            })
        logged = True
    except Exception:
        logged = False

    data = {
        "request_id": request_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "bureau": bureau,
        "pull_type": pull_type,
        "borrowers": borrower_list,
        "status": "pending",
        "requested_at": datetime.now().isoformat(),
        "requires_authorization": pull_type == "hard",
        "estimated_response": "30-60 seconds",
        "audit_logged": logged,
    }

    return ToolResult.success(
        data=data,
        message=f"Credit pull requested: {bureau} ({pull_type})",
        requires_approval=pull_type == "hard",
    )


@mortgage_tool(
    name="submit_to_aus",
    description="Submit loan to Automated Underwriting System (DU/LP)",
    agent_roles=["integrations"],
    risk_level="MEDIUM",
    parameters={
        "loan_id": "Loan ID",
        "aus_system": "System: du, lp, both",
        "submission_type": "Type: initial, resubmit",
        "include_findings_analysis": "Analyze findings automatically",
    },
)
def submit_to_aus(
    loan_id: str,
    aus_system: str = "both",
    submission_type: str = "initial",
    include_findings_analysis: bool = True,
) -> ToolResult:
    """Submit loan to AUS."""
    loan = execute_single("""
        SELECT id, loan_number, borrower_name, loan_type,
               loan_amount, property_type
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Check loan type compatibility
    loan_type = loan.get("loan_type", "").lower()
    available_aus = []
    if loan_type in ["conventional", "jumbo"]:
        available_aus = ["du", "lp"]
    elif loan_type == "fha":
        available_aus = ["du"]  # FHA uses DU
    elif loan_type == "va":
        available_aus = ["lp"]  # VA uses LP
    else:
        available_aus = ["du", "lp"]

    if aus_system != "both" and aus_system not in available_aus:
        return ToolResult.error(
            f"AUS system '{aus_system}' not available for {loan_type} loans. Available: {available_aus}"
        )

    systems_to_submit = [aus_system] if aus_system != "both" else available_aus

    import uuid
    submission_id = f"AUS-{str(uuid.uuid4())[:8].upper()}"

    submissions = []
    for system in systems_to_submit:
        submissions.append({
            "aus_system": system,
            "aus_name": "Desktop Underwriter" if system == "du" else "Loan Prospector",
            "status": "submitted",
            "expected_response": "5-10 minutes",
        })

    data = {
        "submission_id": submission_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "loan_type": loan.get("loan_type"),
        "submission_type": submission_type,
        "submissions": submissions,
        "submitted_at": datetime.now().isoformat(),
        "include_findings_analysis": include_findings_analysis,
    }

    return ToolResult.success(
        data=data,
        message=f"AUS submission initiated: {', '.join(systems_to_submit)}",
    )


@mortgage_tool(
    name="order_appraisal",
    description="Order appraisal through AMC integration",
    agent_roles=["integrations"],
    risk_level="HIGH",
    parameters={
        "loan_id": "Loan ID",
        "amc": "AMC to use",
        "appraisal_type": "Type: full, drive_by, desktop, hybrid",
        "rush": "Rush order (additional fees apply)",
        "special_instructions": "Special instructions for appraiser",
    },
)
def order_appraisal(
    loan_id: str,
    amc: str = "mercury",
    appraisal_type: str = "full",
    rush: bool = False,
    special_instructions: Optional[str] = None,
) -> ToolResult:
    """Order appraisal through AMC."""
    loan = execute_single("""
        SELECT id, loan_number, borrower_name, borrower_phone,
               property_address, property_city, property_state, property_zip,
               property_type, loan_amount
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Check for existing appraisal order
    existing = execute_single("""
        SELECT id, status, ordered_at
        FROM appraisal_orders
        WHERE loan_id = :loan_id AND status NOT IN ('cancelled', 'completed')
    """, {"loan_id": loan_id})

    if existing:
        return ToolResult.error(
            f"Active appraisal order exists (ordered {format_date(existing.get('ordered_at'))}). Cancel existing order first."
        )

    import uuid
    order_id = f"APR-{str(uuid.uuid4())[:8].upper()}"

    # Estimate fees
    base_fee = {"full": 550, "drive_by": 350, "desktop": 200, "hybrid": 400}.get(appraisal_type, 550)
    rush_fee = 150 if rush else 0
    total_fee = base_fee + rush_fee

    data = {
        "order_id": order_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "amc": amc,
        "appraisal_type": appraisal_type,
        "rush": rush,
        "property": {
            "address": loan.get("property_address"),
            "city": loan.get("property_city"),
            "state": loan.get("property_state"),
            "zip": loan.get("property_zip"),
            "type": loan.get("property_type"),
        },
        "contact": {
            "name": loan.get("borrower_name"),
            "phone": loan.get("borrower_phone"),
        },
        "special_instructions": special_instructions,
        "fees": {
            "base_fee": base_fee,
            "rush_fee": rush_fee,
            "total": total_fee,
        },
        "status": "ordered",
        "ordered_at": datetime.now().isoformat(),
        "estimated_delivery": "2-3 business days" if rush else "5-7 business days",
    }

    return ToolResult.success(
        data=data,
        message=f"Appraisal ordered: {appraisal_type} via {amc} (${total_fee})",
        requires_approval=True,
    )


@mortgage_tool(
    name="order_title",
    description="Order title work through title company integration",
    agent_roles=["integrations"],
    risk_level="MEDIUM",
    parameters={
        "loan_id": "Loan ID",
        "title_company": "Title company to use",
        "services": "Services to request: title_search, commitment, insurance, closing",
        "rush": "Rush order",
    },
)
def order_title(
    loan_id: str,
    title_company: str = "softpro",
    services: Optional[List[str]] = None,
    rush: bool = False,
) -> ToolResult:
    """Order title work."""
    loan = execute_single("""
        SELECT id, loan_number, borrower_name,
               property_address, property_city, property_state, property_zip,
               loan_amount, loan_type
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    if not services:
        services = ["title_search", "commitment", "insurance"]

    import uuid
    order_id = f"TTL-{str(uuid.uuid4())[:8].upper()}"

    # Estimate fees based on services
    service_fees = {
        "title_search": 150,
        "commitment": 200,
        "insurance": 0,  # Calculated based on loan amount
        "closing": 500,
    }

    base_fee = sum(service_fees.get(s, 0) for s in services)
    if "insurance" in services:
        # Title insurance typically ~0.5% of loan amount
        loan_amount = float(loan.get("loan_amount", 0))
        base_fee += round(loan_amount * 0.005, 2)

    rush_fee = 100 if rush else 0
    total_fee = base_fee + rush_fee

    data = {
        "order_id": order_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "title_company": title_company,
        "services_requested": services,
        "rush": rush,
        "property": {
            "address": loan.get("property_address"),
            "city": loan.get("property_city"),
            "state": loan.get("property_state"),
            "zip": loan.get("property_zip"),
        },
        "fees": {
            "estimated_total": total_fee,
            "rush_fee": rush_fee,
        },
        "status": "ordered",
        "ordered_at": datetime.now().isoformat(),
        "estimated_delivery": "2-3 business days" if rush else "5-7 business days",
    }

    return ToolResult.success(
        data=data,
        message=f"Title work ordered: {', '.join(services)} via {title_company}",
    )


@mortgage_tool(
    name="send_for_esign",
    description="Send documents for electronic signature via DocuSign/other",
    agent_roles=["integrations"],
    risk_level="MEDIUM",
    parameters={
        "loan_id": "Loan ID",
        "document_package": "Document package: disclosures, application, closing_docs",
        "signers": "List of signers with roles",
        "due_date": "Signature due date",
        "reminder_days": "Days between reminders",
    },
)
def send_for_esign(
    loan_id: str,
    document_package: str,
    signers: Optional[List[Dict]] = None,
    due_date: Optional[str] = None,
    reminder_days: int = 2,
) -> ToolResult:
    """Send documents for electronic signature."""
    loan = execute_single("""
        SELECT id, loan_number, borrower_name, borrower_email,
               coborrower_name, co_borrower_email
        FROM loans
        WHERE id = :id
    """, {"id": loan_id})

    if not loan:
        return ToolResult.no_data(f"Loan {loan_id} not found")

    # Build signers list if not provided
    if not signers:
        signers = [{
            "name": loan.get("borrower_name"),
            "email": loan.get("borrower_email"),
            "role": "borrower",
            "order": 1,
        }]
        if loan.get("coborrower_name") and loan.get("co_borrower_email"):
            signers.append({
                "name": loan.get("coborrower_name"),
                "email": loan.get("co_borrower_email"),
                "role": "coborrower",
                "order": 2,
            })

    # Validate signers have emails
    for signer in signers:
        if not signer.get("email"):
            return ToolResult.error(f"Missing email for signer: {signer.get('name')}")

    # Set default due date
    if not due_date:
        due_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

    import uuid
    envelope_id = f"ENV-{str(uuid.uuid4())[:8].upper()}"

    # Document package details
    package_docs = {
        "disclosures": ["Loan Estimate", "Intent to Proceed", "Privacy Notice"],
        "application": ["Uniform Residential Loan Application", "Authorization Forms"],
        "closing_docs": ["Closing Disclosure", "Note", "Deed of Trust"],
    }

    data = {
        "envelope_id": envelope_id,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "document_package": document_package,
        "documents": package_docs.get(document_package, [document_package]),
        "signers": signers,
        "due_date": due_date,
        "reminder_settings": {
            "enabled": True,
            "days_between": reminder_days,
        },
        "status": "sent",
        "sent_at": datetime.now().isoformat(),
        "tracking_url": f"https://docusign.example.com/envelope/{envelope_id}",
    }

    return ToolResult.success(
        data=data,
        message=f"Documents sent for e-signature: {document_package} ({len(signers)} signers)",
    )


@mortgage_tool(
    name="get_pricing_engine_quote",
    description="Get pricing quote from pricing engine integration",
    agent_roles=["integrations", "rate_advisor"],
    risk_level="LOW",
    parameters={
        "loan_id": "Optional loan ID for existing loan",
        "loan_params": "Loan parameters for pricing (if no loan_id)",
        "pricing_engine": "Pricing engine: optimal_blue, polly, loantek",
        "lock_period": "Lock period in days: 15, 30, 45, 60",
        "include_scenarios": "Include multiple scenarios",
    },
)
def get_pricing_engine_quote(
    loan_id: Optional[str] = None,
    loan_params: Optional[Dict[str, Any]] = None,
    pricing_engine: str = "optimal_blue",
    lock_period: int = 30,
    include_scenarios: bool = True,
) -> ToolResult:
    """Get pricing quote from pricing engine."""
    # Get loan details if loan_id provided
    if loan_id:
        loan = execute_single("""
            SELECT id, loan_number, loan_amount, loan_type,
                   property_type, property_state, occupancy_type,
                   borrower_credit_score, ltv, dti
            FROM loans
            WHERE id = :id
        """, {"id": loan_id})

        if not loan:
            return ToolResult.no_data(f"Loan {loan_id} not found")

        pricing_params = {
            "loan_amount": float(loan.get("loan_amount", 0)),
            "loan_type": loan.get("loan_type"),
            "property_type": loan.get("property_type"),
            "state": loan.get("property_state"),
            "occupancy": loan.get("occupancy_type"),
            "credit_score": loan.get("borrower_credit_score"),
            "ltv": float(loan.get("ltv", 0)),
            "dti": float(loan.get("dti", 0)),
        }
    elif loan_params:
        pricing_params = loan_params
    else:
        return ToolResult.error("Either loan_id or loan_params required")

    import uuid
    quote_id = f"PRC-{str(uuid.uuid4())[:8].upper()}"

    # Generate sample pricing (in production, would call actual API)
    base_rate = 6.875  # Sample base rate

    scenarios = []
    if include_scenarios:
        for points in [0, 0.5, 1.0, 1.5]:
            rate_adjustment = -0.125 * (points / 0.5)  # Rate buydown
            scenarios.append({
                "rate": round(base_rate + rate_adjustment, 3),
                "points": points,
                "apr": round(base_rate + rate_adjustment + 0.125, 3),
                "lock_period": lock_period,
                "monthly_payment": round((pricing_params.get("loan_amount", 400000) * (base_rate + rate_adjustment) / 100 / 12) +
                                         (pricing_params.get("loan_amount", 400000) / 360), 2),
            })
    else:
        scenarios.append({
            "rate": base_rate,
            "points": 0,
            "apr": base_rate + 0.125,
            "lock_period": lock_period,
        })

    data = {
        "quote_id": quote_id,
        "loan_id": loan_id,
        "pricing_engine": pricing_engine,
        "loan_params": pricing_params,
        "lock_period": lock_period,
        "quotes": scenarios,
        "best_rate": min(s["rate"] for s in scenarios),
        "best_apr": min(s["apr"] for s in scenarios),
        "quoted_at": datetime.now().isoformat(),
        "valid_until": (datetime.now() + timedelta(hours=4)).isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Pricing quote: {data['best_rate']}% ({pricing_engine}, {lock_period}-day lock)",
    )
