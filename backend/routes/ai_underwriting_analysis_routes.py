"""
AI Underwriting Analysis Routes

AI-powered loan underwriting analysis endpoints including risk scoring,
guidelines lookup, and underwriting checklists.
"""

import os
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/ai/underwriting", tags=["AI Underwriting Analysis"])
logger = logging.getLogger(__name__)


# =============================================================================
# Dependencies - Import from main at runtime to avoid circular imports
# =============================================================================

def get_current_user_flexible_dep():
    """Get current user flexible - imports from main at runtime"""
    import main
    return main.get_current_user_flexible


def get_models():
    """Get model classes from main at runtime to avoid circular imports"""
    import main
    return {
        "Loan": main.Loan,
        "User": main.User,
    }


async def log_ai_action_to_mission_control(**kwargs):
    """Log AI action to mission control - imports from main at runtime"""
    import main
    return await main.log_ai_action_to_mission_control(**kwargs)


# =============================================================================
# AI UNDERWRITING ENDPOINTS
# =============================================================================

@router.post("/analyze")
async def ai_underwriting_analyze(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    AI-powered loan underwriting analysis
    Analyzes loan application and provides recommendations
    """
    try:
        from openai import OpenAI

        models = get_models()
        Loan = models["Loan"]

        data = await request.json()
        loan_id = data.get("loan_id")

        # Get loan data
        loan_data = None
        if loan_id:
            loan_query = db.query(Loan).filter(Loan.id == loan_id)
            # Defense-in-depth: org_id filter to prevent cross-tenant access
            org_id = getattr(current_user, 'organization_id', None)
            if org_id:
                loan_query = loan_query.filter(Loan.organization_id == org_id)
            loan = loan_query.first()
            if loan:
                loan_data = {
                    "loan_amount": float(loan.loan_amount) if loan.loan_amount else 0,
                    "property_value": float(loan.property_value) if loan.property_value else 0,
                    "loan_type": loan.loan_type,
                    "interest_rate": float(loan.interest_rate) if loan.interest_rate else 0,
                    "term_months": loan.term_months,
                    "borrower_name": loan.borrower_name,
                    "credit_score": loan.credit_score,
                    "dti_ratio": float(loan.dti_ratio) if loan.dti_ratio else 0,
                    "ltv_ratio": float(loan.ltv_ratio) if loan.ltv_ratio else 0,
                    "employment_status": loan.employment_status,
                    "income": float(loan.income) if loan.income else 0,
                    "assets": float(loan.assets) if loan.assets else 0
                }

        # Use provided data or loan data
        analysis_data = data.get("loan_data", loan_data) or {
            "loan_amount": data.get("loan_amount", 0),
            "property_value": data.get("property_value", 0),
            "loan_type": data.get("loan_type", "Conventional"),
            "credit_score": data.get("credit_score", 0),
            "dti_ratio": data.get("dti_ratio", 0),
            "ltv_ratio": data.get("ltv_ratio", 0),
            "income": data.get("income", 0),
            "employment_status": data.get("employment_status", "Unknown")
        }

        # Calculate LTV if not provided
        if not analysis_data.get("ltv_ratio") and analysis_data.get("loan_amount") and analysis_data.get("property_value"):
            analysis_data["ltv_ratio"] = (analysis_data["loan_amount"] / analysis_data["property_value"]) * 100

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # AI Analysis
        analysis_prompt = f"""You are an expert mortgage underwriter. Analyze this loan application and provide a detailed underwriting assessment.

Loan Details:
- Loan Amount: ${analysis_data.get('loan_amount', 0):,.2f}
- Property Value: ${analysis_data.get('property_value', 0):,.2f}
- Loan Type: {analysis_data.get('loan_type', 'Unknown')}
- Credit Score: {analysis_data.get('credit_score', 'Not provided')}
- DTI Ratio: {analysis_data.get('dti_ratio', 'Not provided')}%
- LTV Ratio: {analysis_data.get('ltv_ratio', 'Not provided')}%
- Monthly Income: ${analysis_data.get('income', 0):,.2f}
- Employment: {analysis_data.get('employment_status', 'Unknown')}

Provide your analysis in JSON format:
{{
    "recommendation": "<APPROVE|APPROVE_WITH_CONDITIONS|REFER|DECLINE>",
    "confidence_score": <0-100>,
    "risk_level": "<LOW|MEDIUM|HIGH|VERY_HIGH>",
    "risk_factors": ["list of identified risk factors"],
    "strengths": ["list of positive factors"],
    "conditions": ["list of conditions if approve with conditions"],
    "required_documents": ["list of additional documents needed"],
    "pricing_adjustment": <basis points adjustment suggestion>,
    "summary": "2-3 sentence summary of the analysis",
    "detailed_analysis": {{
        "credit": {{"score": <1-10>, "notes": "..."}},
        "capacity": {{"score": <1-10>, "notes": "..."}},
        "collateral": {{"score": <1-10>, "notes": "..."}},
        "capital": {{"score": <1-10>, "notes": "..."}}
    }},
    "compliance_flags": ["any compliance concerns"],
    "next_steps": ["recommended next steps"]
}}"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert mortgage underwriter with deep knowledge of Fannie Mae, Freddie Mac, FHA, and VA guidelines."},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        analysis = json.loads(response.choices[0].message.content)

        # Log to Mission Control
        await log_ai_action_to_mission_control(
            db=db,
            agent_name="AI Underwriter",
            action_type="underwriting_analysis",
            loan_id=loan_id,
            user_id=current_user.id,
            context={"loan_amount": analysis_data.get("loan_amount"), "recommendation": analysis.get("recommendation")},
            reasoning=analysis.get("summary"),
            autonomy_level="assisted",
            status="completed"
        )

        return {
            "success": True,
            "loan_id": loan_id,
            "input_data": analysis_data,
            "analysis": analysis,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"AI Underwriting error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/guidelines")
async def get_underwriting_guidelines(
    loan_type: str = "Conventional",
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get underwriting guidelines for a specific loan type
    """
    guidelines = {
        "Conventional": {
            "loan_type": "Conventional",
            "min_credit_score": 620,
            "max_dti": 45,
            "max_ltv": 97,
            "min_down_payment": 3,
            "pmi_required_above_ltv": 80,
            "reserves_required": "2-6 months",
            "income_documentation": ["W-2s", "Pay stubs", "Tax returns"],
            "property_types": ["SFR", "Condo", "2-4 Unit", "PUD"],
            "notes": "Fannie Mae/Freddie Mac guidelines apply"
        },
        "FHA": {
            "loan_type": "FHA",
            "min_credit_score": 580,
            "max_dti": 43,
            "max_ltv": 96.5,
            "min_down_payment": 3.5,
            "mip_required": True,
            "reserves_required": "1-2 months",
            "income_documentation": ["W-2s", "Pay stubs", "Tax returns"],
            "property_types": ["SFR", "Condo", "2-4 Unit"],
            "notes": "FHA mortgage insurance required for life of loan if LTV > 90%"
        },
        "VA": {
            "loan_type": "VA",
            "min_credit_score": 620,
            "max_dti": 41,
            "max_ltv": 100,
            "min_down_payment": 0,
            "funding_fee_required": True,
            "reserves_required": "None typically",
            "income_documentation": ["W-2s", "Pay stubs", "DD-214", "COE"],
            "property_types": ["SFR", "Condo", "2-4 Unit"],
            "notes": "Must be eligible veteran or active duty service member"
        },
        "USDA": {
            "loan_type": "USDA",
            "min_credit_score": 640,
            "max_dti": 41,
            "max_ltv": 100,
            "min_down_payment": 0,
            "guarantee_fee_required": True,
            "reserves_required": "None typically",
            "income_documentation": ["W-2s", "Pay stubs", "Tax returns"],
            "property_types": ["SFR"],
            "notes": "Property must be in eligible rural area, income limits apply"
        },
        "Jumbo": {
            "loan_type": "Jumbo",
            "min_credit_score": 700,
            "max_dti": 43,
            "max_ltv": 80,
            "min_down_payment": 20,
            "reserves_required": "6-12 months",
            "income_documentation": ["W-2s", "Pay stubs", "Tax returns", "Asset statements"],
            "property_types": ["SFR", "Condo", "2-4 Unit"],
            "notes": "Loan amount exceeds conforming limits, stricter requirements"
        }
    }

    guideline = guidelines.get(loan_type, guidelines["Conventional"])

    return {
        "loan_type": loan_type,
        "guidelines": guideline,
        "conforming_limit_2026": 832750,
        "high_cost_limit_2026": 1249125
    }


@router.post("/risk-score")
async def calculate_risk_score(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Calculate automated risk score for a loan
    """
    try:
        data = await request.json()

        credit_score = data.get("credit_score", 0)
        dti_ratio = data.get("dti_ratio", 0)
        ltv_ratio = data.get("ltv_ratio", 0)
        employment_months = data.get("employment_months", 0)
        reserves_months = data.get("reserves_months", 0)

        # Credit Score Component (0-30 points)
        if credit_score >= 760:
            credit_points = 30
        elif credit_score >= 720:
            credit_points = 25
        elif credit_score >= 680:
            credit_points = 20
        elif credit_score >= 640:
            credit_points = 15
        elif credit_score >= 620:
            credit_points = 10
        else:
            credit_points = 5

        # DTI Component (0-25 points)
        if dti_ratio <= 28:
            dti_points = 25
        elif dti_ratio <= 36:
            dti_points = 20
        elif dti_ratio <= 43:
            dti_points = 15
        elif dti_ratio <= 50:
            dti_points = 10
        else:
            dti_points = 5

        # LTV Component (0-25 points)
        if ltv_ratio <= 60:
            ltv_points = 25
        elif ltv_ratio <= 75:
            ltv_points = 20
        elif ltv_ratio <= 80:
            ltv_points = 15
        elif ltv_ratio <= 90:
            ltv_points = 10
        else:
            ltv_points = 5

        # Employment Stability (0-10 points)
        if employment_months >= 24:
            employment_points = 10
        elif employment_months >= 12:
            employment_points = 7
        elif employment_months >= 6:
            employment_points = 4
        else:
            employment_points = 2

        # Reserves (0-10 points)
        if reserves_months >= 6:
            reserves_points = 10
        elif reserves_months >= 3:
            reserves_points = 7
        elif reserves_months >= 2:
            reserves_points = 4
        else:
            reserves_points = 2

        total_score = credit_points + dti_points + ltv_points + employment_points + reserves_points

        # Determine risk level
        if total_score >= 80:
            risk_level = "LOW"
            recommendation = "APPROVE"
        elif total_score >= 60:
            risk_level = "MEDIUM"
            recommendation = "APPROVE_WITH_CONDITIONS"
        elif total_score >= 40:
            risk_level = "HIGH"
            recommendation = "REFER"
        else:
            risk_level = "VERY_HIGH"
            recommendation = "DECLINE"

        return {
            "total_score": total_score,
            "max_score": 100,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "components": {
                "credit": {"score": credit_points, "max": 30},
                "dti": {"score": dti_points, "max": 25},
                "ltv": {"score": ltv_points, "max": 25},
                "employment": {"score": employment_points, "max": 10},
                "reserves": {"score": reserves_points, "max": 10}
            },
            "input_data": {
                "credit_score": credit_score,
                "dti_ratio": dti_ratio,
                "ltv_ratio": ltv_ratio,
                "employment_months": employment_months,
                "reserves_months": reserves_months
            }
        }

    except Exception as e:
        logger.error(f"Risk score calculation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/checklist/{loan_type}")
async def get_underwriting_checklist(
    loan_type: str,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """
    Get underwriting checklist for a loan type
    """
    base_checklist = [
        {"category": "Identity", "items": [
            "Government-issued ID",
            "Social Security card or verification"
        ]},
        {"category": "Income", "items": [
            "Most recent 30 days pay stubs",
            "W-2s for past 2 years",
            "Federal tax returns for past 2 years",
            "Verification of Employment (VOE)"
        ]},
        {"category": "Assets", "items": [
            "Bank statements (2 months)",
            "Investment account statements",
            "Gift letter (if applicable)",
            "Source of down payment documentation"
        ]},
        {"category": "Credit", "items": [
            "Credit report review",
            "Letter of explanation for derogatory items",
            "Bankruptcy discharge papers (if applicable)"
        ]},
        {"category": "Property", "items": [
            "Purchase contract",
            "Appraisal",
            "Title commitment",
            "Homeowners insurance quote",
            "HOA documents (if applicable)"
        ]}
    ]

    # Add loan-type specific items
    if loan_type == "FHA":
        base_checklist.append({
            "category": "FHA Specific",
            "items": [
                "FHA case number assignment",
                "CAIVRS check",
                "FHA appraisal requirements met",
                "Mortgage insurance premium calculation"
            ]
        })
    elif loan_type == "VA":
        base_checklist.append({
            "category": "VA Specific",
            "items": [
                "Certificate of Eligibility (COE)",
                "DD-214 (if veteran)",
                "VA appraisal (Notice of Value)",
                "VA funding fee calculation"
            ]
        })
    elif loan_type == "USDA":
        base_checklist.append({
            "category": "USDA Specific",
            "items": [
                "Property eligibility verification",
                "Income eligibility verification",
                "USDA guarantee fee calculation"
            ]
        })

    return {
        "loan_type": loan_type,
        "checklist": base_checklist,
        "total_items": sum(len(cat["items"]) for cat in base_checklist)
    }
