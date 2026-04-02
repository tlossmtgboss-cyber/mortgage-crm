"""
URLA Payload Builder
Transforms intake session data into URLA-compliant payload
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from .models import Session, Party, PartyType


class URLABuilder:
    """Builds URLA-compliant payload from session data"""

    def __init__(self, questions: Dict[str, Any], value_sets: Dict[str, Any] = None):
        self.questions = questions
        self.value_sets = value_sets or {}

        # Build mapping from question_id to URLA path
        self.urla_mapping = {}
        for qid, q_def in questions.items():
            if q_def.get("urla_payload_path"):
                self.urla_mapping[qid] = q_def["urla_payload_path"]

    def build(self, session: Session) -> Dict[str, Any]:
        """Build complete URLA payload from session"""
        payload = {
            "version": "3.4",
            "generatedAt": datetime.now(timezone.utc).isoformat() + "Z",
            "applicationId": session.session_id,
            "loanId": session.loan_id,
            "borrowers": [],
            "loan": {},
            "property": {},
            "declarations": [],
            "assets": [],
            "liabilities": [],
            "realEstateOwned": [],
        }

        # Build borrower sections for each party
        for party in session.parties:
            borrower = self._build_borrower(session, party)
            if borrower:
                payload["borrowers"].append(borrower)

        # Build loan section
        payload["loan"] = self._build_loan_section(session)

        # Build property section
        payload["property"] = self._build_property_section(session)

        # Build declarations
        payload["declarations"] = self._build_declarations(session)

        # Build assets
        payload["assets"] = self._build_assets(session)

        # Build liabilities
        payload["liabilities"] = self._build_liabilities(session)

        # Clean up empty sections
        payload = self._clean_payload(payload)

        return payload

    def _build_borrower(self, session: Session, party: Party) -> Dict[str, Any]:
        """Build borrower section for a party"""
        borrower = {
            "partyId": party.party_id,
            "partyType": party.party_type,
            "personal": {},
            "contact": {},
            "employment": [],
            "income": {},
        }

        # Personal information
        name = session.get_answer("Q_ID_0200", party.party_id) or session.get_answer("Q_ID_0200")
        if name:
            if isinstance(name, dict):
                borrower["personal"]["firstName"] = name.get("first", "")
                borrower["personal"]["middleName"] = name.get("middle", "")
                borrower["personal"]["lastName"] = name.get("last", "")
                borrower["personal"]["suffix"] = name.get("suffix", "")
            else:
                borrower["personal"]["firstName"] = name

        dob = session.get_answer("Q_ID_0201", party.party_id) or session.get_answer("Q_ID_0201")
        if dob:
            borrower["personal"]["dateOfBirth"] = dob

        ssn = session.get_answer("Q_ID_0203", party.party_id) or session.get_answer("Q_ID_0203")
        if ssn:
            borrower["personal"]["ssnLast4"] = ssn

        citizenship = session.get_answer("Q_ID_0205", party.party_id) or session.get_answer("Q_ID_0205")
        if citizenship:
            borrower["personal"]["citizenshipStatus"] = citizenship

        # Contact information
        email = session.get_answer("Q_ID_0204", party.party_id) or session.get_answer("Q_ID_0204")
        if email:
            borrower["contact"]["email"] = email

        phone = session.get_answer("Q_ID_0207", party.party_id) or session.get_answer("Q_ID_0207")
        if phone:
            borrower["contact"]["phone"] = phone

        # Current address
        address = session.get_answer("Q_ADDR_0100", party.party_id) or session.get_answer("Q_ADDR_0100")
        if address:
            borrower["contact"]["currentAddress"] = self._format_address(address)

        # Employment
        emp_status = session.get_answer("Q_INC_0300", party.party_id) or session.get_answer("Q_INC_0300")
        if emp_status:
            employment = {
                "employmentStatus": emp_status,
            }

            employer = session.get_answer("Q_INC_0301", party.party_id) or session.get_answer("Q_INC_0301")
            if employer:
                if isinstance(employer, dict):
                    employment["employerName"] = employer.get("name", "")
                    employment["employerAddress"] = employer.get("address")
                else:
                    employment["employerName"] = employer

            job_title = session.get_answer("Q_INC_0302", party.party_id) or session.get_answer("Q_INC_0302")
            if job_title:
                employment["jobTitle"] = job_title

            years = session.get_answer("Q_INC_0312", party.party_id) or session.get_answer("Q_INC_0312")
            if years:
                employment["yearsInPosition"] = years

            borrower["employment"].append(employment)

        # Income
        monthly_income = session.get_answer("Q_INC_0303", party.party_id) or session.get_answer("Q_INC_0303")
        if monthly_income:
            borrower["income"]["monthlyGrossIncome"] = monthly_income

        return borrower

    def _build_loan_section(self, session: Session) -> Dict[str, Any]:
        """Build loan section"""
        loan = {}

        purpose = session.get_answer("Q_PURP_0010")
        if purpose:
            loan["loanPurpose"] = purpose

        loan_amount = session.get_answer("Q_PURP_0012")
        if loan_amount:
            loan["loanAmount"] = loan_amount

        property_value = session.get_answer("Q_PURP_0011")
        if property_value:
            loan["propertyValue"] = property_value

        down_payment = session.get_answer("Q_PURP_0013")
        if down_payment:
            loan["downPaymentAmount"] = down_payment

        # Refinance specific
        if purpose == "Refinance":
            current_balance = session.get_answer("Q_PURP_0020")
            if current_balance:
                loan["currentLoanBalance"] = current_balance

            cash_out = session.get_answer("Q_PURP_0022")
            if cash_out:
                loan["cashOutAmount"] = cash_out

        return loan

    def _build_property_section(self, session: Session) -> Dict[str, Any]:
        """Build property section"""
        prop = {}

        address = session.get_answer("Q_PROP_0100")
        if address:
            prop["address"] = self._format_address(address)

        prop_type = session.get_answer("Q_PROP_0101")
        if prop_type:
            prop["propertyType"] = prop_type

        occupancy = session.get_answer("Q_PROP_0110")
        if occupancy:
            prop["occupancyType"] = occupancy

        units = session.get_answer("Q_PROP_0102")
        if units:
            prop["numberOfUnits"] = units

        # Expected rent for investment
        rent = session.get_answer("Q_RENT_0118")
        if rent:
            prop["expectedRentalIncome"] = rent

        return prop

    def _build_declarations(self, session: Session) -> List[Dict[str, Any]]:
        """Build declarations section"""
        declarations = []

        # Map of declaration question IDs
        declaration_questions = [
            ("Q_DEC_0600", "outstandingJudgments"),
            ("Q_DEC_0601", "declaredBankrupt"),
            ("Q_DEC_0602", "propertyForeclosed"),
            ("Q_DEC_0603", "lawsuitParty"),
            ("Q_DEC_0604", "loanForeclosed"),
            ("Q_DEC_0605", "delinquentFederalDebt"),
            ("Q_DEC_0606", "alimonyObligation"),
            ("Q_DEC_0607", "borrowedDownPayment"),
            ("Q_DEC_0608", "coMakerEndorser"),
            ("Q_DEC_0609", "primaryResidence"),
            ("Q_DEC_0610", "ownershipInterest"),
        ]

        for qid, decl_type in declaration_questions:
            answer = session.get_answer(qid)
            if answer is not None:
                declarations.append({
                    "declarationType": decl_type,
                    "response": answer,
                })

        return declarations

    def _build_assets(self, session: Session) -> List[Dict[str, Any]]:
        """Build assets section"""
        assets = []

        asset_questions = [
            ("Q_AST_0401", "checking"),
            ("Q_AST_0402", "savings"),
            ("Q_AST_0403", "retirement"),
            ("Q_AST_0404", "investment"),
            ("Q_AST_0405", "other"),
        ]

        for qid, asset_type in asset_questions:
            answer = session.get_answer(qid)
            if answer and answer > 0:
                assets.append({
                    "assetType": asset_type,
                    "value": answer,
                })

        return assets

    def _build_liabilities(self, session: Session) -> List[Dict[str, Any]]:
        """Build liabilities section"""
        liabilities = []

        # Housing expense
        housing = session.get_answer("Q_LIA_0500")
        if housing:
            liabilities.append({
                "liabilityType": "housingExpense",
                "monthlyPayment": housing,
            })

        # Other debts
        debts = session.get_answer("Q_LIA_0501")
        if debts:
            liabilities.append({
                "liabilityType": "otherDebts",
                "monthlyPayment": debts,
            })

        return liabilities

    def _format_address(self, address: Any) -> Dict[str, str]:
        """Format address into URLA structure"""
        if isinstance(address, dict):
            return {
                "streetAddress": address.get("street", ""),
                "city": address.get("city", ""),
                "state": address.get("state", ""),
                "zipCode": address.get("zip", ""),
                "country": address.get("country", "US"),
            }
        elif isinstance(address, str):
            # Try to parse string address
            return {
                "streetAddress": address,
                "city": "",
                "state": "",
                "zipCode": "",
                "country": "US",
            }
        return {}

    def _clean_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Remove empty sections from payload"""
        cleaned = {}
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            if isinstance(value, dict) and len(value) == 0:
                continue
            cleaned[key] = value
        return cleaned

    def validate_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate URLA payload and return issues"""
        issues = []
        warnings = []

        # Check required sections
        if not payload.get("borrowers"):
            issues.append({
                "path": "borrowers",
                "message": "At least one borrower is required",
            })

        for i, borrower in enumerate(payload.get("borrowers", [])):
            # Check required borrower fields
            personal = borrower.get("personal", {})
            if not personal.get("firstName"):
                issues.append({
                    "path": f"borrowers[{i}].personal.firstName",
                    "message": "First name is required",
                })
            if not personal.get("lastName"):
                issues.append({
                    "path": f"borrowers[{i}].personal.lastName",
                    "message": "Last name is required",
                })

        # Check loan section
        loan = payload.get("loan", {})
        if not loan.get("loanPurpose"):
            issues.append({
                "path": "loan.loanPurpose",
                "message": "Loan purpose is required",
            })

        # Check property section
        prop = payload.get("property", {})
        if not prop.get("address"):
            warnings.append({
                "path": "property.address",
                "message": "Property address is incomplete",
            })

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }


def create_urla_builder(
    questions: Dict[str, Any],
    value_sets: Dict[str, Any] = None,
) -> URLABuilder:
    """Factory function to create URLA builder"""
    return URLABuilder(questions, value_sets)
