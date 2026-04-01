"""Mortgage Qualification Rules Engine — evaluates borrower eligibility across all major loan programs."""
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


PROGRAM_RULES = {
    "conventional": {
        "min_credit": 620,
        "max_dti": 50,
        "min_down_payment_pct": Decimal("3.0"),
        "pmi_threshold": Decimal("20.0"),
        "max_loan_amount": Decimal("766550"),
        "high_balance_limit": Decimal("1149825"),
        "notes": "PMI required if LTV > 80%",
    },
    "fha": {
        "min_credit": 580,
        "min_credit_10pct": 500,
        "max_dti": 57,
        "min_down_payment_pct": Decimal("3.5"),
        "min_down_payment_10pct": Decimal("10.0"),
        "mip_required": True,
        "max_loan_amount": Decimal("498257"),
        "notes": "MIP for life of loan if LTV > 90%",
    },
    "va": {
        "min_credit": 620,
        "max_dti": 60,
        "min_down_payment_pct": Decimal("0"),
        "requires_eligibility": True,
        "funding_fee": True,
        "notes": "No down payment, no PMI. Requires military service.",
    },
    "usda": {
        "min_credit": 640,
        "max_dti": 41,
        "max_front_end_dti": 29,
        "min_down_payment_pct": Decimal("0"),
        "rural_only": True,
        "income_limits": True,
        "notes": "Rural properties only, income limits apply",
    },
    "jumbo": {
        "min_credit": 700,
        "max_dti": 43,
        "min_down_payment_pct": Decimal("10"),
        "min_reserves_months": 12,
        "notes": "Above conforming limits. Stricter requirements.",
    },
    "non_qm": {
        "min_credit": 600,
        "max_dti": 50,
        "income_types": ["bank_statement", "asset_depletion", "dscr", "1099_only"],
        "notes": "Alternative documentation. Higher rates.",
    },
}

INCOME_TYPES = {
    "w2": {
        "stability": "high",
        "doc_requirements": ["2-year W-2s", "30-day pay stubs", "Most recent tax returns"],
        "min_years": 0,
    },
    "self_employed": {
        "stability": "medium",
        "doc_requirements": ["2-year tax returns with all schedules", "Year-to-date P&L", "12-24 month bank statements"],
        "min_years": 2,
    },
    "1099": {
        "stability": "medium",
        "doc_requirements": ["2-year 1099 forms", "Tax returns"],
        "min_years": 2,
    },
    "retired": {
        "stability": "high",
        "doc_requirements": ["Pension/SS award letter", "Tax returns", "Asset statements"],
        "min_years": 0,
    },
    "rental_income": {
        "stability": "medium",
        "doc_requirements": ["Executed lease agreements", "Tax returns with Schedule E", "Rent roll"],
        "min_years": 1,
    },
    "commission": {
        "stability": "medium",
        "doc_requirements": ["2-year tax returns", "W-2s", "Employer VOE"],
        "min_years": 2,
    },
}

STATE_RULES = {
    "TX": {"home_equity_cooling_days": 12, "max_cash_out_ltv": 80, "notes": "Texas 50(a)(6) rules for cash-out"},
    "NY": {"mansion_tax_threshold": 1000000, "mortgage_recording_tax": True, "notes": "Additional recording taxes"},
    "CA": {"fair_lending_notice": True, "mlds_required": True, "notes": "MLDS and fair lending disclosures required"},
    "FL": {"homestead_exemption": True, "wind_mitigation_discount": True, "notes": "Homestead exemption affects title"},
    "VA_STATE": {"wet_settlement_state": True, "notes": "Wet funding required"},
    "MD": {"wet_settlement_state": True, "notes": "Wet funding state"},
    "NJ": {"high_cost_area": True, "notes": "Higher conforming limits in many counties"},
    "IL": {"responsible_lending_act": True, "notes": "Additional consumer protections"},
    "GA": {"anti_predatory_lending": True, "notes": "Georgia Fair Lending Act"},
    "CO": {"first_time_buyer_programs": True, "notes": "CHFA programs available"},
    "WA": {"consumer_loan_act": True, "notes": "State-specific disclosures"},
    "OR": {"predatory_lending_protections": True, "notes": "Oregon consumer protections"},
    "AZ": {"deed_of_trust_state": True, "non_judicial_foreclosure": True},
    "NV": {"mediation_required_foreclosure": True, "superpriority_lien": True},
    "MA": {"right_to_cure": True, "notes": "150-day right to cure before foreclosure"},
    "CT": {"judicial_foreclosure_only": True},
    "HI": {"conveyance_tax": True, "notes": "State conveyance tax on transfers"},
    "AK": {"no_state_income_tax": True, "rural_programs": True},
    "PA": {"transfer_tax": True, "notes": "1% state + 1% local transfer tax"},
    "OH": {"transfer_tax": True},
    "MI": {"transfer_tax": True},
    "MN": {"deed_tax": True, "mortgage_registration_tax": True},
    "NC": {"recording_tax": True},
    "SC": {"recording_fee": True},
    "TN": {"no_state_income_tax": True},
    "IN": {"transfer_tax": False, "notes": "No state transfer tax"},
    "WI": {"transfer_fee": True},
    "MO": {"no_prepayment_penalty_restriction": True},
    "AL": {"deed_tax": True},
    "LA": {"community_property_state": True, "notes": "Community property affects qualification"},
    "MS": {"deed_of_trust_state": True},
    "KY": {"transfer_tax": True},
    "OK": {"documentary_stamp_tax": True},
    "AR": {"transfer_tax": True},
    "KS": {"mortgage_registration_fee": True},
    "IA": {"transfer_tax": False},
    "NE": {"documentary_stamp_tax": True},
    "UT": {"deed_of_trust_state": True},
    "NM": {"community_property_state": True},
    "WV": {"transfer_tax": True},
    "ID": {"deed_of_trust_state": True},
    "MT": {"no_state_transfer_tax": True},
    "ND": {"no_state_transfer_tax": True},
    "SD": {"no_state_transfer_tax": True},
    "WY": {"no_state_transfer_tax": True},
    "NH": {"transfer_tax": True},
    "VT": {"transfer_tax": True},
    "ME": {"transfer_tax": True},
    "RI": {"transfer_tax": True},
    "DE": {"transfer_tax": True},
    "DC": {"transfer_tax": True, "recordation_tax": True},
}


@dataclass
class ProgramEligibility:
    program: str
    eligible: bool
    reasons: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    min_down_payment_pct: Optional[Decimal] = None
    max_dti: Optional[int] = None
    notes: str = ""


@dataclass
class QualificationResult:
    score: int  # 0-100
    grade: str  # A, B, C, D, F
    eligible_programs: List[ProgramEligibility] = field(default_factory=list)
    best_fit: Optional[str] = None
    flags: List[str] = field(default_factory=list)
    required_documents: List[str] = field(default_factory=list)
    state_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "grade": self.grade,
            "eligible_programs": [
                {"program": p.program, "eligible": p.eligible, "reasons": p.reasons,
                 "conditions": p.conditions, "notes": p.notes}
                for p in self.eligible_programs
            ],
            "best_fit": self.best_fit,
            "flags": self.flags,
            "required_documents": self.required_documents,
            "state_notes": self.state_notes,
        }


def evaluate_qualification(
    credit_score: int = 0,
    dti: Optional[float] = None,
    ltv: Optional[float] = None,
    loan_amount: Optional[Decimal] = None,
    income_type: str = "w2",
    property_type: str = "single_family",
    property_state: str = "",
    is_veteran: bool = False,
    is_rural: bool = False,
    is_first_time_buyer: bool = False,
    years_employed: Optional[int] = None,
) -> QualificationResult:
    """Evaluate borrower qualification across all programs."""
    programs = get_eligible_programs(
        credit_score=credit_score, dti=dti, ltv=ltv,
        loan_amount=loan_amount, income_type=income_type,
        property_type=property_type, is_veteran=is_veteran, is_rural=is_rural,
    )

    score = calculate_qualification_score(
        credit_score=credit_score, dti=dti, ltv=ltv,
        income_type=income_type, years_employed=years_employed,
    )

    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D" if score >= 35 else "F"

    eligible = [p for p in programs if p.eligible]
    best_fit = eligible[0].program if eligible else None

    flags = []
    if credit_score < 620:
        flags.append(f"Credit score {credit_score} limits program options")
    if dti and dti > 45:
        flags.append(f"DTI {dti}% is elevated — may limit options")
    if ltv and ltv > 95:
        flags.append(f"LTV {ltv}% is high — limited programs available")

    docs = get_required_documents(income_type, best_fit or "conventional")
    state_notes = []
    if property_state:
        state_info = STATE_RULES.get(property_state.upper(), {})
        if state_info.get("notes"):
            state_notes.append(state_info["notes"])

    return QualificationResult(
        score=score,
        grade=grade,
        eligible_programs=programs,
        best_fit=best_fit,
        flags=flags,
        required_documents=docs,
        state_notes=state_notes,
    )


def get_eligible_programs(
    credit_score: int = 0,
    dti: Optional[float] = None,
    ltv: Optional[float] = None,
    loan_amount: Optional[Decimal] = None,
    income_type: str = "w2",
    property_type: str = "single_family",
    is_veteran: bool = False,
    is_rural: bool = False,
) -> List[ProgramEligibility]:
    """Check which programs the borrower qualifies for."""
    results = []

    for program_name, rules in PROGRAM_RULES.items():
        reasons = []
        conditions = []
        eligible = True

        # Credit check
        min_credit = rules.get("min_credit", 0)
        if credit_score < min_credit:
            eligible = False
            reasons.append(f"Credit {credit_score} below minimum {min_credit}")

        # DTI check
        max_dti = rules.get("max_dti")
        if max_dti and dti and dti > max_dti:
            eligible = False
            reasons.append(f"DTI {dti}% exceeds maximum {max_dti}%")

        # Loan amount check
        max_amount = rules.get("max_loan_amount")
        if max_amount and loan_amount and loan_amount > max_amount:
            if program_name == "conventional":
                high_bal = rules.get("high_balance_limit", Decimal("0"))
                if loan_amount <= high_bal:
                    conditions.append("High-balance conforming — higher rates may apply")
                else:
                    eligible = False
                    reasons.append(f"Loan ${loan_amount:,.0f} exceeds conforming limit ${max_amount:,.0f}")
            else:
                eligible = False
                reasons.append(f"Loan amount exceeds {program_name.upper()} limit")

        # Program-specific checks
        if program_name == "va" and not is_veteran:
            eligible = False
            reasons.append("VA requires military service eligibility")
        if program_name == "usda" and not is_rural:
            eligible = False
            reasons.append("USDA requires rural property location")

        # FHA special: 500-579 requires 10% down
        if program_name == "fha" and 500 <= credit_score < 580:
            conditions.append("Credit below 580 requires 10% down payment (instead of 3.5%)")

        results.append(ProgramEligibility(
            program=program_name,
            eligible=eligible,
            reasons=reasons,
            conditions=conditions,
            min_down_payment_pct=rules.get("min_down_payment_pct"),
            max_dti=rules.get("max_dti"),
            notes=rules.get("notes", ""),
        ))

    # Sort: eligible first, then by preference
    program_order = ["conventional", "fha", "va", "usda", "jumbo", "non_qm"]
    results.sort(key=lambda p: (not p.eligible, program_order.index(p.program) if p.program in program_order else 99))
    return results


def calculate_qualification_score(
    credit_score: int = 0,
    dti: Optional[float] = None,
    ltv: Optional[float] = None,
    income_type: str = "w2",
    years_employed: Optional[int] = None,
) -> int:
    """0-100 qualification strength score."""
    score = 0

    # Credit (40 points max)
    if credit_score >= 760:
        score += 40
    elif credit_score >= 720:
        score += 35
    elif credit_score >= 680:
        score += 28
    elif credit_score >= 640:
        score += 20
    elif credit_score >= 600:
        score += 12
    elif credit_score >= 500:
        score += 5

    # DTI (25 points max)
    if dti is not None:
        if dti <= 28:
            score += 25
        elif dti <= 36:
            score += 20
        elif dti <= 43:
            score += 15
        elif dti <= 50:
            score += 8
        else:
            score += 2

    # LTV (20 points max)
    if ltv is not None:
        if ltv <= 60:
            score += 20
        elif ltv <= 75:
            score += 17
        elif ltv <= 80:
            score += 14
        elif ltv <= 90:
            score += 10
        elif ltv <= 95:
            score += 6
        else:
            score += 2

    # Income stability (15 points max)
    income_info = INCOME_TYPES.get(income_type, {})
    stability = income_info.get("stability", "medium")
    if stability == "high":
        score += 12
    elif stability == "medium":
        score += 8
    else:
        score += 4

    if years_employed is not None and years_employed >= 2:
        score += 3

    return min(100, score)


def get_required_documents(income_type: str, loan_program: str) -> List[str]:
    """Return document checklist based on income type and program."""
    docs = []

    # Base docs for all
    docs.extend(["Government-issued photo ID", "Social Security card or ITIN"])

    # Income-specific docs
    income_info = INCOME_TYPES.get(income_type, INCOME_TYPES["w2"])
    docs.extend(income_info.get("doc_requirements", []))

    # Asset docs for all
    docs.extend(["2 months bank statements (all pages)", "Investment/retirement account statements"])

    # Program-specific
    if loan_program == "va":
        docs.append("Certificate of Eligibility (COE)")
        docs.append("DD-214 (if separated)")
    elif loan_program == "fha":
        docs.append("Gift letter (if using gift funds)")
    elif loan_program == "usda":
        docs.append("Proof of rural property eligibility")
        docs.append("Household income documentation (all adults)")

    # Property docs
    docs.extend(["Purchase contract (if purchase)", "Homeowners insurance quote"])

    return docs
