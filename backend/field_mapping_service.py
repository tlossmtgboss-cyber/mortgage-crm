"""
Automatic Field Mapping Service for Data Import
Intelligently maps Excel columns to CRM fields using fuzzy matching
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import re

logger = logging.getLogger(__name__)


# Field mapping configuration
class FieldMapping:
    def __init__(
        self,
        crm_field: str,
        excel_patterns: List[str],
        data_type: str = 'string',
        required: bool = False,
        transform: Optional[Callable] = None,
        validation: Optional[Callable] = None
    ):
        self.crm_field = crm_field
        self.excel_patterns = excel_patterns
        self.data_type = data_type
        self.required = required
        self.transform = transform
        self.validation = validation


# Phone number transformer
def transform_phone(v):
    if not v:
        return None
    return re.sub(r'\D', '', str(v))


# Email transformer
def transform_email(v):
    if not v:
        return None
    return str(v).lower().strip()


# Number transformer
def transform_number(v):
    if v is None or v == '':
        return None
    try:
        cleaned = re.sub(r'[^0-9.-]', '', str(v))
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


# Integer transformer
def transform_int(v):
    if v is None or v == '':
        return None
    try:
        cleaned = re.sub(r'[^0-9-]', '', str(v))
        return int(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


# Date transformer
def transform_date(v):
    if v is None or v == '':
        return None
    try:
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, (int, float)):
            # Excel serial date
            from datetime import timedelta
            excel_epoch = datetime(1899, 12, 30)
            return (excel_epoch + timedelta(days=v)).isoformat()
        return datetime.fromisoformat(str(v).replace('/', '-')).isoformat()
    except Exception as e:
        logger.warning(f"Error parsing date with fromisoformat: {e}")
        try:
            from dateutil import parser
            return parser.parse(str(v)).isoformat()
        except Exception as e:
            logger.warning(f"Error parsing date with dateutil: {e}")
            return None


# Boolean transformer
def transform_bool(v):
    if v is None or v == '':
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ('yes', 'true', '1', 'y')


# Email validation
def validate_email(v):
    if not v:
        return True
    return bool(re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', str(v)))


# Comprehensive field mappings for mortgage CRM
FIELD_MAPPINGS: List[FieldMapping] = [
    # ===== BORROWER INFORMATION =====
    FieldMapping(
        crm_field='borrower_name',
        excel_patterns=['borrower name', 'borrower full name', 'bor name', 'bor full name',
                       'client name', 'name', 'full name', 'bor 1 name', 'bor 1 full name'],
        data_type='string',
        transform=lambda v: str(v).strip() if v else None,
    ),
    FieldMapping(
        crm_field='borrower_last_name',
        excel_patterns=['last name', 'lastname', 'bor last', 'borrower last', 'bor 1 last name'],
        data_type='string',
        required=True,
        transform=lambda v: str(v).strip() if v else None,
    ),
    FieldMapping(
        crm_field='borrower_first_name',
        excel_patterns=['first name', 'firstname', 'bor first', 'borrower first', 'bor 1 first name'],
        data_type='string',
        required=True,
        transform=lambda v: str(v).strip() if v else None,
    ),
    FieldMapping(
        crm_field='borrower_email',
        excel_patterns=['bor 1 email', 'borrower email', 'email', 'bor email', 'primary email'],
        data_type='email',
        validation=validate_email,
        transform=transform_email,
    ),
    FieldMapping(
        crm_field='borrower_mobile_phone',
        excel_patterns=['bor 1 mobile phone', 'bor 1 mobile', 'borrower mobile phone', 'mobile phone', 'cell phone', 'bor mobile', 'mobile', 'cell'],
        data_type='phone',
        transform=transform_phone,
    ),
    FieldMapping(
        crm_field='borrower_home_phone',
        excel_patterns=['bor 1 home phone', 'bor 1 home', 'borrower home phone', 'home phone', 'bor home'],
        data_type='phone',
        transform=transform_phone,
    ),
    FieldMapping(
        crm_field='borrower_work_phone',
        excel_patterns=['bor 1 work phone', 'bor 1 work', 'borrower work phone', 'work phone', 'bor work'],
        data_type='phone',
        transform=transform_phone,
    ),
    FieldMapping(
        crm_field='co_borrower_email',
        excel_patterns=['bor 2 email', 'co-borrower email', 'coborrower email', 'co borrower email'],
        data_type='email',
        validation=validate_email,
        transform=transform_email,
    ),
    FieldMapping(
        crm_field='borrower_prequalified',
        excel_patterns=['borrower prequalified', 'prequalified', 'pre-qualified'],
        data_type='boolean',
        transform=transform_bool,
    ),

    # ===== PROPERTY INFORMATION =====
    FieldMapping(
        crm_field='property_street',
        excel_patterns=['sub prop street', 'property street', 'address', 'street', 'property address'],
        data_type='string',
        transform=lambda v: str(v).strip() if v else None,
    ),
    FieldMapping(
        crm_field='property_city',
        excel_patterns=['sub prop city', 'property city', 'city'],
        data_type='string',
        transform=lambda v: str(v).strip() if v else None,
    ),
    FieldMapping(
        crm_field='property_state',
        excel_patterns=['sub prop state', 'property state', 'state'],
        data_type='string',
        transform=lambda v: str(v).upper().strip() if v else None,
    ),
    FieldMapping(
        crm_field='property_zip',
        excel_patterns=['sub prop zip', 'property zip', 'zip code', 'zip', 'postal code'],
        data_type='string',
        transform=lambda v: str(v).strip() if v else None,
    ),
    FieldMapping(
        crm_field='property_type',
        excel_patterns=['sub prop property type', 'property type', 'prop type'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='occupancy_type',
        excel_patterns=['occupancy type', 'occupancy'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='appraised_value',
        excel_patterns=['sub prop appraised value', 'appraised value', 'appraisal value'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='purchase_price',
        excel_patterns=['pur price', 'purchase price', 'sale price'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='buy_price_net',
        excel_patterns=['buy price net', 'buy price'],
        data_type='number',
        transform=transform_number,
    ),

    # ===== LOAN INFORMATION =====
    FieldMapping(
        crm_field='file_name',
        excel_patterns=['file name', 'loan number', 'loan #', 'file number', 'loan id'],
        data_type='string',
        required=True,
    ),
    FieldMapping(
        crm_field='loan_status',
        excel_patterns=['loan status', 'status', 'stage'],
        data_type='string',
        required=True,
    ),
    FieldMapping(
        crm_field='loan_purpose',
        excel_patterns=['loan purpose', 'purpose'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='loan_program_code',
        excel_patterns=['loan program code', 'program code'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='loan_program_name',
        excel_patterns=['loan program name', 'program name', 'loan program'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='loan_amount',
        excel_patterns=['loan amount', 'base loan amount', 'amount'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='interest_rate',
        excel_patterns=['int rate', 'interest rate', 'rate', 'note rate'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='ltv',
        excel_patterns=['ltv', 'loan to value'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='cltv',
        excel_patterns=['cltv', 'combined ltv'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='first_ratio',
        excel_patterns=['first ratio', 'dti front', 'front ratio', 'front dti'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='second_ratio',
        excel_patterns=['second ratio', 'dti back', 'back ratio', 'total ratio', 'back dti'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='credit_score',
        excel_patterns=['file credit score', 'credit score', 'fico', 'fico score'],
        data_type='number',
        transform=transform_int,
    ),
    FieldMapping(
        crm_field='cash_to_borrower',
        excel_patterns=['dot cash from to borrower', 'cash to borrower', 'cash from borrower'],
        data_type='number',
        transform=transform_number,
    ),
    FieldMapping(
        crm_field='lender_credit',
        excel_patterns=['lender credit', 'credit'],
        data_type='number',
        transform=transform_number,
    ),

    # ===== TEAM MEMBERS =====
    FieldMapping(
        crm_field='loan_officer_name',
        excel_patterns=['lo full name', 'loan officer', 'lo name', 'loan officer name', 'originator'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='loan_processor_name',
        excel_patterns=['lp full name', 'loan processor', 'processor', 'lp name'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='loan_processor_email',
        excel_patterns=['lp email', 'processor email'],
        data_type='email',
        transform=transform_email,
    ),
    FieldMapping(
        crm_field='loan_processor_phone',
        excel_patterns=['lp work phone', 'processor phone'],
        data_type='phone',
        transform=transform_phone,
    ),
    FieldMapping(
        crm_field='underwriter_name',
        excel_patterns=['uw first and last name', 'underwriter', 'uw name'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='closer_name',
        excel_patterns=['closer first and last name', 'closer', 'closing agent'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='doc_drawer_name',
        excel_patterns=['doc drawer first and last name', 'doc drawer', 'document drawer'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='broker_name',
        excel_patterns=['broker first and last name', 'broker'],
        data_type='string',
    ),

    # ===== AGENTS =====
    FieldMapping(
        crm_field='listing_agent_name',
        excel_patterns=['list agent full name', 'listing agent', 'list agent'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='listing_agent_company',
        excel_patterns=['list agent company', 'listing company'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='listing_agent_phone',
        excel_patterns=['list agent mobile phone', 'list agent mobile', 'listing agent phone'],
        data_type='phone',
        transform=transform_phone,
    ),
    FieldMapping(
        crm_field='listing_agent_email',
        excel_patterns=['list agent email', 'listing agent email'],
        data_type='email',
        transform=transform_email,
    ),
    FieldMapping(
        crm_field='selling_agent_name',
        excel_patterns=['sel agent full name', 'selling agent', 'buyer agent', "buyer's agent"],
        data_type='string',
    ),
    FieldMapping(
        crm_field='selling_agent_company',
        excel_patterns=['sel agent company', 'selling company'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='selling_agent_phone',
        excel_patterns=['sel agent mobile', 'selling agent phone'],
        data_type='phone',
        transform=transform_phone,
    ),
    FieldMapping(
        crm_field='selling_agent_email',
        excel_patterns=['sel agent email', 'selling agent email'],
        data_type='email',
        transform=transform_email,
    ),

    # ===== SETTLEMENT/TITLE =====
    FieldMapping(
        crm_field='settlement_company',
        excel_patterns=['settlement co company', 'title company', 'settlement company'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='settlement_company_phone',
        excel_patterns=['settlement co work phone', 'title phone'],
        data_type='phone',
        transform=transform_phone,
    ),

    # ===== DATES =====
    FieldMapping(
        crm_field='date_created',
        excel_patterns=['date created', 'created date', 'created'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='status_date',
        excel_patterns=['status date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='scheduled_closing_date',
        excel_patterns=['sched closing date', 'scheduled closing', 'closing date', 'est closing date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='lock_expiration_date',
        excel_patterns=['lock expiration date', 'rate lock expiration', 'lock exp'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='le_pending_date',
        excel_patterns=['le pending date', 'le sent'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='le_initial_delivery_date',
        excel_patterns=['disc log entry le initial delivery', 'le delivery date', 'le initial delivery'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='le_received_date',
        excel_patterns=['disc log entry le initial received', 'le received'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='file_received_date',
        excel_patterns=['file received date', 'received date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='uw_received_date',
        excel_patterns=['uw received date', 'underwriting received'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='original_approved_date',
        excel_patterns=['original approved date', 'first approval'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='approved_date',
        excel_patterns=['approved date', 'approval date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='conditions_for_review_date',
        excel_patterns=['conditions for review date', 'conditions sent'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='appraisal_ordered_date',
        excel_patterns=['appraisal ordered', 'appraisal order date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='appraisal_received_date',
        excel_patterns=['appraisal received', 'appraisal received date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='title_ordered_date',
        excel_patterns=['title ordered', 'title order date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='title_received_date',
        excel_patterns=['title received', 'title received date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='clear_to_close_date',
        excel_patterns=['clear to close date', 'ctc date', 'clear to close'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='cd_requested_date',
        excel_patterns=['cd requested', 'cd request date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='cd_initial_delivery_date',
        excel_patterns=['disc log entry cd initial delivery', 'cd delivery date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='cd_received_date',
        excel_patterns=['disc log entry cd initial received', 'cd received'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='intent_to_proceed_date',
        excel_patterns=['intent to proceed date', 'itp date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='le_requested_date',
        excel_patterns=['le requested date', 'le request date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='docs_ordered_date',
        excel_patterns=['docs ordered date', 'documents ordered'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='docs_out_date',
        excel_patterns=['docs out date', 'documents sent'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='docs_back_date',
        excel_patterns=['docs back date', 'documents returned'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='funded_date',
        excel_patterns=['funded date', 'funding date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='suspended_date',
        excel_patterns=['suspended date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='declined_date',
        excel_patterns=['declined date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='withdrawn_date',
        excel_patterns=['withdrawn date'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='credit_ordered_date',
        excel_patterns=['credit ordered', 'credit order date'],
        data_type='date',
        transform=transform_date,
    ),

    # ===== OTHER =====
    FieldMapping(
        crm_field='organization_code',
        excel_patterns=['organization code', 'org code', 'branch'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='loan_with',
        excel_patterns=['loan with', 'lender', 'investor'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='disclosure',
        excel_patterns=['disclosure'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='origination_channel',
        excel_patterns=['origination channel', 'channel'],
        data_type='string',
    ),
    FieldMapping(
        crm_field='referral_source',
        excel_patterns=['referral source', 'lead source', 'source'],
        data_type='string',
    ),

    # ===== ADDITIONAL DATE FIELDS =====
    FieldMapping(
        crm_field='approved_not_accepted_date',
        excel_patterns=['approved not accepted date', 'approved not accepted'],
        data_type='date',
        transform=transform_date,
    ),
    FieldMapping(
        crm_field='canceled_for_incompleteness_date',
        excel_patterns=['canceled for incompleteness date', 'canceled for incompleteness', 'cancelled for incompleteness'],
        data_type='date',
        transform=transform_date,
    ),

    # ===== ADDITIONAL BORROWER FIELDS =====
    FieldMapping(
        crm_field='borrower_email_3',
        excel_patterns=['bor 3 email', 'borrower 3 email', 'third borrower email'],
        data_type='email',
        validation=validate_email,
        transform=transform_email,
    ),
]


def calculate_levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return calculate_levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate similarity between two strings using multiple methods.
    Returns a score between 0.0 and 1.0
    """
    # Normalize strings
    s1 = re.sub(r'[^a-z0-9]', '', str1.lower())
    s2 = re.sub(r'[^a-z0-9]', '', str2.lower())

    # Exact match
    if s1 == s2:
        return 1.0

    # One contains the other - but penalize if lengths are very different
    if s1 in s2 or s2 in s1:
        min_len = min(len(s1), len(s2))
        max_len = max(len(s1), len(s2))
        # Only give high score if the contained string is a significant portion
        length_ratio = min_len / max_len if max_len > 0 else 0
        if length_ratio >= 0.7:
            return 0.95
        elif length_ratio >= 0.5:
            return 0.85
        else:
            # Short substring in long string - use length ratio as base
            return 0.5 * length_ratio + 0.3

    # Levenshtein distance-based similarity
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 0.0

    distance = calculate_levenshtein_distance(s1, s2)
    levenshtein_sim = 1 - (distance / max_len)

    # Token overlap (word-based similarity)
    tokens1 = set(str1.lower().split())
    tokens2 = set(str2.lower().split())
    if tokens1 and tokens2:
        overlap = len(tokens1.intersection(tokens2))
        token_sim = overlap / max(len(tokens1), len(tokens2))
    else:
        token_sim = 0

    # Return the better of the two similarity scores
    return max(levenshtein_sim, token_sim)


class MappingResult:
    def __init__(
        self,
        excel_column: str,
        crm_field: str,
        confidence: float,
        data_type: str,
        transform: Optional[Callable] = None
    ):
        self.excel_column = excel_column
        self.crm_field = crm_field
        self.confidence = confidence
        self.data_type = data_type
        self.transform = transform

    def to_dict(self) -> Dict[str, Any]:
        return {
            'excel_column': self.excel_column,
            'crm_field': self.crm_field,
            'confidence': f"{int(self.confidence * 100)}%",
            'data_type': self.data_type,
        }


def auto_map_fields(excel_columns: List[str], min_confidence: float = 0.7) -> List[MappingResult]:
    """
    Automatically map Excel columns to CRM fields using fuzzy matching.

    Args:
        excel_columns: List of column names from the Excel file
        min_confidence: Minimum confidence threshold (0.0 - 1.0)

    Returns:
        List of MappingResult objects
    """
    mapping_results: List[MappingResult] = []
    used_crm_fields = set()

    for excel_column in excel_columns:
        best_match: Optional[MappingResult] = None
        highest_confidence = min_confidence

        for mapping in FIELD_MAPPINGS:
            # Skip if CRM field already mapped
            if mapping.crm_field in used_crm_fields:
                continue

            # Calculate best similarity score against all patterns
            confidences = [
                calculate_similarity(excel_column, pattern)
                for pattern in mapping.excel_patterns
            ]
            max_confidence = max(confidences) if confidences else 0

            if max_confidence > highest_confidence:
                highest_confidence = max_confidence
                best_match = MappingResult(
                    excel_column=excel_column,
                    crm_field=mapping.crm_field,
                    confidence=max_confidence,
                    data_type=mapping.data_type,
                    transform=mapping.transform,
                )

        if best_match:
            mapping_results.append(best_match)
            used_crm_fields.add(best_match.crm_field)

    return mapping_results


def transform_data(
    excel_data: List[Dict[str, Any]],
    mappings: List[MappingResult]
) -> Dict[str, Any]:
    """
    Transform Excel data using the field mappings.

    Returns:
        Dict with 'success', 'data', 'errors', 'warnings', 'stats'
    """
    transformed_data = []
    errors = []
    warnings = []
    successful_rows = 0
    failed_rows = 0

    mapping_dict = {m.excel_column: m for m in mappings}

    for row_idx, row in enumerate(excel_data):
        transformed_row = {
            'import_metadata': {
                'imported_at': datetime.now().isoformat(),
                'row_number': row_idx + 2,
                'source': 'excel_auto_import',
            }
        }
        row_has_error = False

        for excel_col, mapping in mapping_dict.items():
            excel_value = row.get(excel_col)

            # Skip null/empty values
            if excel_value is None or excel_value == '' or (isinstance(excel_value, float) and excel_value != excel_value):
                continue

            try:
                # Apply transformation if defined
                transformed_value = mapping.transform(excel_value) if mapping.transform else excel_value

                # Find field config for validation
                field_config = next(
                    (f for f in FIELD_MAPPINGS if f.crm_field == mapping.crm_field),
                    None
                )

                # Validate required fields
                if field_config and field_config.required and not transformed_value:
                    errors.append(f"Row {row_idx + 2}: Required field '{mapping.crm_field}' is empty")
                    row_has_error = True
                    continue

                # Apply validation
                if field_config and field_config.validation and transformed_value:
                    if not field_config.validation(transformed_value):
                        warnings.append(f"Row {row_idx + 2}: Invalid value for '{mapping.crm_field}': {transformed_value}")
                        continue

                transformed_row[mapping.crm_field] = transformed_value

            except Exception as e:
                errors.append(f"Row {row_idx + 2}: Error transforming '{excel_col}' -> '{mapping.crm_field}': {str(e)}")
                row_has_error = True

        if row_has_error:
            failed_rows += 1
        else:
            successful_rows += 1
            transformed_data.append(transformed_row)

    avg_confidence = sum(m.confidence for m in mappings) / len(mappings) if mappings else 0

    return {
        'success': failed_rows == 0,
        'data': transformed_data,
        'errors': errors if errors else None,
        'warnings': warnings if warnings else None,
        'stats': {
            'total_rows': len(excel_data),
            'successful_rows': successful_rows,
            'failed_rows': failed_rows,
            'fields_matched': len(mappings),
            'confidence_average': round(avg_confidence * 100),
        },
        'mappings': [m.to_dict() for m in mappings],
    }


def get_field_mapping_by_crm_field(crm_field: str) -> Optional[FieldMapping]:
    """Get field mapping configuration by CRM field name"""
    return next((f for f in FIELD_MAPPINGS if f.crm_field == crm_field), None)
