"""
Calculator Agent

AI agent for automatically identifying mortgage calculation opportunities
from call transcripts and generating completed calculator results.

Includes:
- Financial data extraction from conversations
- Automatic calculator selection based on context
- Full calculation execution with all 8 calculator types
- Confidence scoring based on data completeness
"""

import logging
from typing import Dict, List, Any, Optional
import json

from .base_agent import BaseCallAgent, AgentResult
from ...calculator_service import calculator_service, LoanType

logger = logging.getLogger(__name__)


class CalculatorAgent(BaseCallAgent):
    """
    Calculator Agent for mortgage calculations from call transcripts.

    Capabilities:
    - Extract financial parameters from call conversations
    - Identify which calculators are relevant to the discussion
    - Execute calculations with extracted data
    - Generate calculator_result artifacts for review

    Supported Calculators:
    - Monthly P&I (principal & interest payment)
    - Full PITI (with taxes, insurance, PMI)
    - PMI/MIP Calculator (conventional, FHA, VA, USDA)
    - DTI Calculator (debt-to-income ratios)
    - LTV Calculator (loan-to-value)
    - Affordability Calculator (max purchase price)
    - Closing Costs Estimator
    - Amortization Schedule
    """

    @property
    def agent_type(self) -> str:
        return "calculator"

    @property
    def system_prompt(self) -> str:
        return """You are a Mortgage Calculator Assistant that analyzes call transcripts to extract financial data and determine which calculators would be helpful.

## YOUR TASK:
Extract all financial data mentioned in the call that can be used for mortgage calculations. Look for:

### Loan Parameters:
- Purchase price / Property value
- Loan amount / Amount financed
- Down payment (amount or percentage)
- Interest rates discussed (current quotes, market rates)
- Loan term (15, 20, 30 years)
- Loan type (Conventional, FHA, VA, USDA)

### Borrower Financial Data:
- Monthly/annual income (gross)
- Credit score (if mentioned)
- Monthly debt payments (car loans, credit cards, student loans, etc.)
- Current rent/housing payment

### Property Data:
- Property value / Purchase price
- Property taxes (annual or monthly)
- Homeowner's insurance estimate
- HOA fees
- Property state (for tax/cost estimates)
- Property type (primary, investment, second home)

### Special Factors:
- First-time homebuyer status
- VA eligibility (first use or subsequent)
- VA exemption status (disability)
- Self-employed status

## CALCULATOR TYPES TO CONSIDER:

1. **monthly_pi**: Basic P&I payment
   - Requires: loan_amount, interest_rate, term_years

2. **piti**: Full housing payment breakdown
   - Requires: loan_amount, interest_rate, term_years, property_value
   - Optional: annual_taxes, annual_insurance, hoa_monthly, credit_score

3. **pmi**: Mortgage insurance calculation
   - Requires: loan_amount, home_value
   - Optional: credit_score, loan_type, is_first_va_use

4. **dti**: Debt-to-income ratios
   - Requires: monthly_income, monthly_debts, proposed_housing_payment

5. **ltv**: Loan-to-value ratio
   - Requires: loan_amount, property_value

6. **affordability**: Maximum purchase price
   - Requires: annual_income, monthly_debts, down_payment, interest_rate

7. **closing_costs**: Estimated closing costs
   - Requires: loan_amount, property_value
   - Optional: state, loan_type

8. **amortization**: Payment schedule
   - Requires: loan_amount, interest_rate, term_years

## OUTPUT FORMAT:

Respond with a JSON object containing all extracted data and recommended calculations:

```json
{
    "extracted_data": {
        "loan_amount": null,
        "property_value": null,
        "down_payment": null,
        "down_payment_percent": null,
        "interest_rate": null,
        "term_years": 30,
        "loan_type": "conventional",
        "monthly_income": null,
        "annual_income": null,
        "monthly_debts": null,
        "credit_score": null,
        "annual_taxes": null,
        "annual_insurance": null,
        "hoa_monthly": 0,
        "state": null,
        "is_first_va_use": true,
        "is_va_exempt": false
    },
    "calculations_to_run": [
        {
            "calculator_type": "piti",
            "reason": "Customer asked about monthly payment",
            "evidence": "Exact quote from transcript",
            "priority": "high"
        }
    ],
    "missing_data": [
        "credit_score - needed for accurate PMI calculation"
    ],
    "assumptions": [
        "Assumed 30-year term since not specified"
    ]
}
```

## EXTRACTION RULES:

1. **Be Precise**: Use exact values stated - don't round or estimate
2. **Note Units**: Be careful with monthly vs annual figures, percentages vs decimals
3. **Quote Evidence**: Include exact phrases where data was mentioned
4. **Calculate Derived Values**: If they say "10% down on a $400,000 home", calculate down_payment = $40,000
5. **Default to Common Values**: If term not mentioned, default to 30 years
6. **Flag Missing Data**: List what data would improve accuracy

## CONFIDENCE SCORING:

Assign confidence based on data completeness:
- **0.95+**: All required inputs explicitly stated
- **0.85-0.94**: Most inputs stated, minor assumptions made
- **0.70-0.84**: Key inputs stated but significant assumptions needed
- **0.50-0.69**: Limited data, calculations are estimates only"""

    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        transcript = context.get('transcript', '')
        transcript = self._truncate_transcript(transcript, max_words=5000)

        participants = self._format_participants(context.get('participants', []))
        loan_context = self._format_loan_context(context.get('loan'))

        # Include existing loan data for context
        existing_data = ""
        loan = context.get('loan', {})
        if loan:
            existing_data = f"""
## EXISTING LOAN FILE DATA (use as defaults/context)
- Loan Amount: ${loan.get('loan_amount', 0):,.2f}
- Property Value: ${loan.get('appraisal_value', 0):,.2f}
- Interest Rate: {loan.get('rate', 'N/A')}%
- Loan Type: {loan.get('loan_type', 'conventional')}
- Credit Score: {loan.get('credit_score', 'N/A')}
- Property State: {loan.get('property_state', 'N/A')}

Use these values as defaults when calculating, but prefer values explicitly mentioned in the call."""

        prompt = f"""Analyze this mortgage call transcript and extract all financial data for calculations.

## Call Participants
{participants}
{existing_data}

## Call Transcript
{transcript}

---

## YOUR TASK:

1. **Extract all financial numbers** mentioned (prices, rates, payments, income, debts)
2. **Identify which calculators** would be most helpful based on the conversation
3. **Note any missing data** that would improve calculation accuracy
4. **List assumptions** you need to make for calculations

Think step-by-step through the conversation and identify:
- What specific question(s) did the borrower ask?
- What financial scenario was discussed?
- Which calculation would best answer their question?

Respond with the JSON format specified in your instructions.

IMPORTANT: Only extract data explicitly stated. Flag when you make assumptions."""

        return prompt

    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Calculator agent response and execute calculations."""
        artifacts = []

        # Try to extract JSON
        parsed = self._extract_json_from_response(response_text)

        if not parsed:
            logger.warning("Calculator agent: Could not parse JSON response")
            return artifacts

        extracted_data = parsed.get('extracted_data', {})
        calculations_to_run = parsed.get('calculations_to_run', [])
        assumptions = parsed.get('assumptions', [])
        missing_data = parsed.get('missing_data', [])

        # Merge with loan context for defaults
        loan = context.get('loan', {})
        merged_data = self._merge_with_loan_context(extracted_data, loan)

        # Execute each requested calculation
        for calc_request in calculations_to_run:
            calc_type = calc_request.get('calculator_type', '')
            evidence = calc_request.get('evidence', '')
            reason = calc_request.get('reason', '')
            priority = calc_request.get('priority', 'medium')

            try:
                result = self._execute_calculation(calc_type, merged_data, context)

                if result and 'error' not in result:
                    # Determine confidence based on data quality
                    confidence = self._calculate_confidence(
                        calc_type, merged_data, missing_data, assumptions
                    )

                    artifact = {
                        'type': 'calculator_result',
                        'title': self._generate_title(calc_type, result),
                        'content': self._generate_content(calc_type, result, reason),
                        'structured_data': {
                            'calculator_type': calc_type,
                            'inputs': result.get('inputs', {}),
                            'outputs': self._extract_outputs(calc_type, result),
                            'assumptions': assumptions,
                            'missing_data': missing_data,
                        },
                        'evidence': evidence,
                        'confidence': confidence,
                        'priority': priority,
                        'source_agent': 'calculator',
                    }
                    artifacts.append(artifact)

            except Exception as e:
                logger.error(f"Calculator agent: Error running {calc_type}: {e}")

        # If no specific calculations requested but we have data, suggest calculations
        if not calculations_to_run and self._has_sufficient_data(merged_data):
            suggested = self._suggest_calculations(merged_data)
            for calc_type in suggested:
                try:
                    result = self._execute_calculation(calc_type, merged_data, context)
                    if result and 'error' not in result:
                        confidence = self._calculate_confidence(
                            calc_type, merged_data, missing_data, assumptions
                        )
                        artifact = {
                            'type': 'calculator_result',
                            'title': self._generate_title(calc_type, result),
                            'content': self._generate_content(calc_type, result, "Based on financial data discussed"),
                            'structured_data': {
                                'calculator_type': calc_type,
                                'inputs': result.get('inputs', {}),
                                'outputs': self._extract_outputs(calc_type, result),
                                'suggested': True,
                            },
                            'confidence': confidence,
                            'priority': 'low',
                            'source_agent': 'calculator',
                        }
                        artifacts.append(artifact)
                except Exception as e:
                    logger.error(f"Calculator agent: Error suggesting {calc_type}: {e}")

        return artifacts

    def _merge_with_loan_context(self, extracted: Dict, loan: Dict) -> Dict:
        """Merge extracted data with loan context, preferring extracted values."""
        merged = {
            'loan_amount': extracted.get('loan_amount') or loan.get('loan_amount'),
            'property_value': extracted.get('property_value') or loan.get('appraisal_value'),
            'interest_rate': extracted.get('interest_rate') or loan.get('rate'),
            'term_years': extracted.get('term_years') or 30,
            'loan_type': extracted.get('loan_type') or loan.get('loan_type', 'conventional'),
            'credit_score': extracted.get('credit_score') or loan.get('credit_score') or 720,
            'down_payment': extracted.get('down_payment'),
            'down_payment_percent': extracted.get('down_payment_percent'),
            'monthly_income': extracted.get('monthly_income'),
            'annual_income': extracted.get('annual_income'),
            'monthly_debts': extracted.get('monthly_debts') or 0,
            'annual_taxes': extracted.get('annual_taxes'),
            'annual_insurance': extracted.get('annual_insurance'),
            'hoa_monthly': extracted.get('hoa_monthly') or 0,
            'state': extracted.get('state') or loan.get('property_state', 'CA'),
            'is_first_va_use': extracted.get('is_first_va_use', True),
            'is_va_exempt': extracted.get('is_va_exempt', False),
        }

        # Calculate derived values
        if merged['property_value'] and merged['down_payment_percent'] and not merged['down_payment']:
            merged['down_payment'] = merged['property_value'] * (merged['down_payment_percent'] / 100)

        if merged['property_value'] and merged['down_payment'] and not merged['loan_amount']:
            merged['loan_amount'] = merged['property_value'] - merged['down_payment']

        if merged['annual_income'] and not merged['monthly_income']:
            merged['monthly_income'] = merged['annual_income'] / 12

        return merged

    def _execute_calculation(self, calc_type: str, data: Dict, context: Dict) -> Optional[Dict]:
        """Execute a specific calculator with the given data."""
        try:
            if calc_type == 'monthly_pi':
                if not data.get('loan_amount') or not data.get('interest_rate'):
                    return None
                return calculator_service.calculate_monthly_pi(
                    loan_amount=data['loan_amount'],
                    interest_rate=data['interest_rate'],
                    term_years=data.get('term_years', 30),
                )

            elif calc_type == 'piti':
                if not data.get('loan_amount') or not data.get('interest_rate') or not data.get('property_value'):
                    return None
                return calculator_service.calculate_piti(
                    loan_amount=data['loan_amount'],
                    interest_rate=data['interest_rate'],
                    term_years=data.get('term_years', 30),
                    property_value=data['property_value'],
                    annual_taxes=data.get('annual_taxes'),
                    annual_insurance=data.get('annual_insurance'),
                    hoa_monthly=data.get('hoa_monthly', 0),
                    credit_score=data.get('credit_score', 720),
                    loan_type=data.get('loan_type', 'conventional'),
                )

            elif calc_type == 'pmi':
                if not data.get('loan_amount') or not data.get('property_value'):
                    return None
                return calculator_service.calculate_pmi(
                    loan_amount=data['loan_amount'],
                    home_value=data['property_value'],
                    credit_score=data.get('credit_score', 720),
                    loan_type=data.get('loan_type', 'conventional'),
                    term_years=data.get('term_years', 30),
                    is_first_va_use=data.get('is_first_va_use', True),
                    is_va_exempt=data.get('is_va_exempt', False),
                )

            elif calc_type == 'dti':
                monthly_income = data.get('monthly_income')
                if not monthly_income and data.get('annual_income'):
                    monthly_income = data['annual_income'] / 12
                if not monthly_income:
                    return None

                # Need a housing payment - try to calculate
                if data.get('loan_amount') and data.get('interest_rate') and data.get('property_value'):
                    piti = calculator_service.calculate_piti(
                        loan_amount=data['loan_amount'],
                        interest_rate=data['interest_rate'],
                        term_years=data.get('term_years', 30),
                        property_value=data['property_value'],
                    )
                    housing_payment = piti['total_piti']
                else:
                    return None

                return calculator_service.calculate_dti(
                    monthly_income=monthly_income,
                    monthly_debts=data.get('monthly_debts', 0),
                    proposed_housing_payment=housing_payment,
                )

            elif calc_type == 'ltv':
                if not data.get('loan_amount') or not data.get('property_value'):
                    return None
                return calculator_service.calculate_ltv(
                    loan_amount=data['loan_amount'],
                    property_value=data['property_value'],
                )

            elif calc_type == 'affordability':
                annual_income = data.get('annual_income')
                if not annual_income and data.get('monthly_income'):
                    annual_income = data['monthly_income'] * 12
                if not annual_income or not data.get('interest_rate'):
                    return None

                return calculator_service.calculate_affordability(
                    annual_income=annual_income,
                    monthly_debts=data.get('monthly_debts', 0),
                    down_payment=data.get('down_payment', 0),
                    interest_rate=data['interest_rate'],
                )

            elif calc_type == 'closing_costs':
                if not data.get('loan_amount') or not data.get('property_value'):
                    return None
                return calculator_service.estimate_closing_costs(
                    loan_amount=data['loan_amount'],
                    property_value=data['property_value'],
                    state=data.get('state', 'CA'),
                    loan_type=data.get('loan_type', 'conventional'),
                )

            elif calc_type == 'amortization':
                if not data.get('loan_amount') or not data.get('interest_rate'):
                    return None
                schedule = calculator_service.generate_amortization(
                    loan_amount=data['loan_amount'],
                    interest_rate=data['interest_rate'],
                    term_years=data.get('term_years', 30),
                    num_payments=12,  # First 12 payments
                )
                return {
                    'schedule': schedule,
                    'inputs': {
                        'loan_amount': data['loan_amount'],
                        'interest_rate': data['interest_rate'],
                        'term_years': data.get('term_years', 30),
                    },
                }

            return None

        except Exception as e:
            logger.error(f"Calculation error for {calc_type}: {e}")
            return None

    def _calculate_confidence(
        self,
        calc_type: str,
        data: Dict,
        missing_data: List[str],
        assumptions: List[str],
    ) -> float:
        """Calculate confidence score based on data quality."""
        base_confidence = 0.95

        # Reduce for missing critical data
        critical_fields = {
            'monthly_pi': ['loan_amount', 'interest_rate'],
            'piti': ['loan_amount', 'interest_rate', 'property_value'],
            'pmi': ['loan_amount', 'property_value', 'credit_score'],
            'dti': ['monthly_income', 'loan_amount'],
            'ltv': ['loan_amount', 'property_value'],
            'affordability': ['annual_income', 'interest_rate'],
            'closing_costs': ['loan_amount', 'property_value'],
            'amortization': ['loan_amount', 'interest_rate'],
        }

        required = critical_fields.get(calc_type, [])
        for field in required:
            if not data.get(field):
                base_confidence -= 0.15

        # Reduce for assumptions
        base_confidence -= len(assumptions) * 0.03

        # Reduce for missing data notes
        base_confidence -= len(missing_data) * 0.02

        return max(min(base_confidence, 0.98), 0.50)

    def _generate_title(self, calc_type: str, result: Dict) -> str:
        """Generate a human-readable title for the calculation result."""
        titles = {
            'monthly_pi': f"Monthly P&I Payment: ${result.get('monthly_payment', 0):,.2f}",
            'piti': f"Total Monthly Payment: ${result.get('total_piti', 0):,.2f}",
            'pmi': f"Mortgage Insurance: ${result.get('monthly_premium', 0):,.2f}/mo",
            'dti': f"DTI Ratio: {result.get('back_end_dti', 0):.1f}%",
            'ltv': f"LTV: {result.get('ltv', 0):.1f}%",
            'affordability': f"Max Purchase Price: ${result.get('max_purchase_price', 0):,.0f}",
            'closing_costs': f"Estimated Closing Costs: ${result.get('total_closing_costs', 0):,.0f}",
            'amortization': "Amortization Schedule (First 12 Months)",
        }
        return titles.get(calc_type, f"{calc_type.replace('_', ' ').title()} Calculation")

    def _generate_content(self, calc_type: str, result: Dict, reason: str) -> str:
        """Generate descriptive content for the calculation result."""
        lines = [reason, ""]

        if calc_type == 'monthly_pi':
            lines.extend([
                f"Loan Amount: ${result['inputs']['loan_amount']:,.2f}",
                f"Interest Rate: {result['inputs']['interest_rate']}%",
                f"Term: {result['inputs']['term_years']} years",
                f"",
                f"Monthly P&I: ${result['monthly_payment']:,.2f}",
                f"Total Interest: ${result['total_interest']:,.2f}",
            ])

        elif calc_type == 'piti':
            lines.extend([
                f"Principal & Interest: ${result['principal_interest']:,.2f}",
                f"Property Tax: ${result['property_tax_monthly']:,.2f}",
                f"Insurance: ${result['insurance_monthly']:,.2f}",
                f"PMI/MIP: ${result['pmi_monthly']:,.2f}",
                f"HOA: ${result['hoa_monthly']:,.2f}",
                f"",
                f"Total PITI: ${result['total_piti']:,.2f}",
                f"LTV: {result['ltv']:.1f}%",
            ])

        elif calc_type == 'pmi':
            if result.get('required'):
                lines.extend([
                    f"Type: {result.get('type', 'PMI')}",
                    f"Monthly Premium: ${result['monthly_premium']:,.2f}",
                    f"Annual Rate: {result.get('annual_rate', 0):.2f}%",
                    f"LTV: {result['ltv']:.1f}%",
                ])
                if result.get('upfront_premium', 0) > 0:
                    lines.append(f"Upfront Premium: ${result['upfront_premium']:,.2f}")
            else:
                lines.append("No mortgage insurance required (LTV ≤ 80%)")

        elif calc_type == 'dti':
            lines.extend([
                f"Front-End DTI (Housing): {result['front_end_dti']:.1f}%",
                f"Back-End DTI (Total): {result['back_end_dti']:.1f}%",
                f"",
                f"Status: {'Qualifies' if result['qualifies'] else 'Does Not Qualify'} (43% max)",
            ])

        elif calc_type == 'ltv':
            lines.extend([
                f"Loan Amount: ${result['inputs']['loan_amount']:,.2f}",
                f"Property Value: ${result['inputs']['property_value']:,.2f}",
                f"Down Payment: ${result['down_payment']:,.2f} ({result['down_payment_percent']:.1f}%)",
                f"",
                f"LTV: {result['ltv']:.1f}% ({result['tier']} tier)",
                f"PMI Required: {'Yes' if result['pmi_required'] else 'No'}",
            ])

        elif calc_type == 'affordability':
            lines.extend([
                f"Based on ${result['inputs']['annual_income']:,.0f} annual income",
                f"",
                f"Max Purchase Price: ${result['max_purchase_price']:,.0f}",
                f"Max Loan Amount: ${result['max_loan_amount']:,.0f}",
                f"Down Payment: ${result['down_payment']:,.0f}",
                f"Estimated Payment: ${result['estimated_monthly_payment']:,.2f}",
            ])

        elif calc_type == 'closing_costs':
            lines.extend([
                f"Lender Fees: ${result['lender_fees']['total']:,.2f}",
                f"Third Party Fees: ${result['third_party_fees']['total']:,.2f}",
                f"Prepaids: ${result['prepaids']['total']:,.2f}",
                f"Escrows: ${result['escrows']['total']:,.2f}",
                f"",
                f"Total Closing Costs: ${result['total_closing_costs']:,.2f}",
            ])

        elif calc_type == 'amortization':
            schedule = result.get('schedule', [])
            if schedule:
                lines.append("First 12 Months:")
                for pmt in schedule[:6]:  # Show first 6
                    lines.append(
                        f"  #{pmt['payment_number']}: ${pmt['payment']:,.2f} "
                        f"(P: ${pmt['principal']:,.2f}, I: ${pmt['interest']:,.2f})"
                    )

        return "\n".join(lines)

    def _extract_outputs(self, calc_type: str, result: Dict) -> Dict:
        """Extract key output values from calculation result."""
        if calc_type == 'monthly_pi':
            return {
                'monthly_payment': result.get('monthly_payment'),
                'total_interest': result.get('total_interest'),
            }
        elif calc_type == 'piti':
            return {
                'principal_interest': result.get('principal_interest'),
                'property_tax_monthly': result.get('property_tax_monthly'),
                'insurance_monthly': result.get('insurance_monthly'),
                'pmi_monthly': result.get('pmi_monthly'),
                'hoa_monthly': result.get('hoa_monthly'),
                'total_piti': result.get('total_piti'),
                'ltv': result.get('ltv'),
            }
        elif calc_type == 'pmi':
            return {
                'required': result.get('required'),
                'monthly_premium': result.get('monthly_premium'),
                'upfront_premium': result.get('upfront_premium'),
                'type': result.get('type'),
            }
        elif calc_type == 'dti':
            return {
                'front_end_dti': result.get('front_end_dti'),
                'back_end_dti': result.get('back_end_dti'),
                'qualifies': result.get('qualifies'),
            }
        elif calc_type == 'ltv':
            return {
                'ltv': result.get('ltv'),
                'down_payment_percent': result.get('down_payment_percent'),
                'pmi_required': result.get('pmi_required'),
            }
        elif calc_type == 'affordability':
            return {
                'max_purchase_price': result.get('max_purchase_price'),
                'max_loan_amount': result.get('max_loan_amount'),
                'estimated_monthly_payment': result.get('estimated_monthly_payment'),
            }
        elif calc_type == 'closing_costs':
            return {
                'total_closing_costs': result.get('total_closing_costs'),
                'lender_fees': result.get('lender_fees', {}).get('total'),
                'third_party_fees': result.get('third_party_fees', {}).get('total'),
            }
        elif calc_type == 'amortization':
            return {
                'first_payment': result.get('schedule', [{}])[0] if result.get('schedule') else None,
            }
        return result

    def _has_sufficient_data(self, data: Dict) -> bool:
        """Check if we have enough data for at least one calculation."""
        return bool(
            (data.get('loan_amount') and data.get('interest_rate')) or
            (data.get('property_value') and data.get('loan_amount')) or
            (data.get('annual_income') or data.get('monthly_income'))
        )

    def _suggest_calculations(self, data: Dict) -> List[str]:
        """Suggest relevant calculations based on available data."""
        suggested = []

        # Always suggest these if we have the data
        if data.get('loan_amount') and data.get('interest_rate'):
            suggested.append('monthly_pi')

        if data.get('loan_amount') and data.get('interest_rate') and data.get('property_value'):
            suggested.append('piti')

        if data.get('loan_amount') and data.get('property_value'):
            suggested.append('ltv')
            if data.get('property_value') > data.get('loan_amount', 0) * 1.25:  # LTV < 80%
                pass  # No PMI needed
            else:
                suggested.append('pmi')

        return suggested[:3]  # Limit suggestions

    def _truncate_transcript(self, transcript: str, max_words: int = 5000) -> str:
        """Truncate transcript while preserving financial discussion context."""
        if not transcript:
            return ""

        words = transcript.split()
        if len(words) <= max_words:
            return transcript

        # For calculator, we want the parts with numbers and financial discussion
        # Keep first 20% for context and last 80% for details
        first_portion = int(max_words * 0.2)
        last_portion = max_words - first_portion

        first_words = words[:first_portion]
        last_words = words[-last_portion:]

        return ' '.join(first_words) + '\n\n[... transcript truncated ...]\n\n' + ' '.join(last_words)
