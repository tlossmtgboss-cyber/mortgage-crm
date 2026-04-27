"""
Tests for the MISMO 3.4 XML serializer.
"""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from agents.urla.models import (
    URLAApplication,
    Borrower,
    Address,
    ResidenceHistory,
    Section1a_PersonalInformation,
    Section1b_CurrentEmployment,
    Section1d_PreviousEmployment,
    Section1e_OtherIncome,
    OtherIncomeSource,
    Section2_AssetsAndLiabilities,
    Asset,
    Liability,
    OtherLiability,
    Section3_RealEstate,
    PropertyOwned,
    REOMortgage,
    Section4_LoanAndProperty,
    Section4a_LoanAndProperty,
    Section4b_OtherNewMortgages,
    Section4d_GiftsOrGrants,
    Gift,
    Section5_Declarations,
    Section5a_DeclarationsPropertyMoney,
    Section5b_DeclarationsFinances,
    Section6_Acknowledgments,
    Section7_MilitaryService,
    Section8_Demographics,
    Section9_LoanOriginator,
)
from agents.urla.bytepro_adapter import LoanOfficer
from agents.urla.mismo_serializer import serialize_to_mismo34, serialize_to_mismo34_bytes


def _parse_strip_ns(xml_str: str) -> ET.Element:
    """Parse XML and strip namespace prefixes so find(".//TAG") works without ns maps."""
    clean = re.sub(r'\sxmlns(?::\w+)?="[^"]*"', "", xml_str)
    return ET.fromstring(clean)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_address():
    return Address(street="123 Main St", city="Springfield", state="IL", zip_code="62704")


@pytest.fixture
def sample_loan_officer():
    return LoanOfficer(
        name="Timothy Loss",
        nmlsr_id="987654",
        email="tloss@cmghomeloans.com",
        phone="+18431234567",
        organization_name="The Tim Loss Team",
        organization_nmlsr_id="112233",
    )


@pytest.fixture
def minimal_app(sample_address):
    """Minimal valid application with just enough data to serialize."""
    return URLAApplication(
        loan_id="LOAN-001",
        tenant_id="t-1",
        caller_phone="+18435551212",
        borrowers=[
            Borrower(
                borrower_id="borrower_1",
                is_primary=True,
                section_1a=Section1a_PersonalInformation(
                    first_name="Alice",
                    last_name="Johnson",
                    ssn="123-45-6789",
                    date_of_birth=date(1985, 6, 12),
                    citizenship="US_CITIZEN",
                    marital_status="MARRIED",
                    cell_phone="+18435551212",
                    email="alice@example.com",
                    current_address=ResidenceHistory(
                        address=Address(
                            street="456 Oak Ave",
                            city="Charleston",
                            state="SC",
                            zip_code="29401",
                        ),
                        years_at_address=3,
                        months_at_address=6,
                        housing_expense_monthly=Decimal("1800"),
                        own_or_rent="RENT",
                    ),
                ),
                section_1b=Section1b_CurrentEmployment(
                    employer_name="Acme Corp",
                    position_title="Engineer",
                    start_date=date(2020, 3, 15),
                    base_monthly=Decimal("8500"),
                ),
                section_5=Section5_Declarations(
                    section_5a=Section5a_DeclarationsPropertyMoney(
                        will_occupy_as_primary_residence=True,
                        had_ownership_interest_last_3_years=False,
                    ),
                    section_5b=Section5b_DeclarationsFinances(
                        outstanding_judgments=False,
                        declared_bankruptcy_last_7_years=False,
                    ),
                ),
                section_7=Section7_MilitaryService(served_in_military=False),
                section_8=Section8_Demographics(
                    ethnicity=["NOT_HISPANIC_OR_LATINO"],
                    race=["WHITE"],
                    sex="FEMALE",
                ),
            ),
        ],
        section_2=Section2_AssetsAndLiabilities(
            assets=[
                Asset(
                    asset_type="CHECKING_ACCOUNT",
                    financial_institution="Wells Fargo",
                    account_number_last_4="4567",
                    cash_or_market_value=Decimal("50000"),
                ),
            ],
            liabilities=[
                Liability(
                    liability_type="REVOLVING",
                    creditor_name="Chase Visa",
                    account_number_last_4="1111",
                    unpaid_balance=Decimal("5000"),
                    monthly_payment=Decimal("150"),
                ),
            ],
        ),
        section_4=Section4_LoanAndProperty(
            section_4a=Section4a_LoanAndProperty(
                loan_amount=Decimal("280000"),
                loan_purpose="PURCHASE",
                subject_property_address=sample_address,
                number_of_units=1,
                property_value=Decimal("350000"),
                occupancy="PRIMARY_RESIDENCE",
            ),
        ),
        section_6=Section6_Acknowledgments(verbal_consent_given=True),
        section_9=Section9_LoanOriginator(
            loan_originator_name="Timothy Loss",
            loan_originator_nmlsr_id="987654",
        ),
    )


@pytest.fixture
def full_app(sample_address):
    """Full application with all sections populated."""
    return URLAApplication(
        loan_id="LOAN-FULL-001",
        tenant_id="t-1",
        caller_phone="+18435551212",
        application_received_at=datetime(2026, 4, 26, 14, 0, 0, tzinfo=timezone.utc),
        borrowers=[
            Borrower(
                borrower_id="borrower_1",
                is_primary=True,
                section_1a=Section1a_PersonalInformation(
                    first_name="Alice",
                    middle_name="Marie",
                    last_name="Johnson",
                    suffix="Jr",
                    alternate_names=["A.M. Johnson", "Alice M. Smith"],
                    ssn="123-45-6789",
                    date_of_birth=date(1985, 6, 12),
                    citizenship="US_CITIZEN",
                    marital_status="MARRIED",
                    dependents_count=2,
                    dependents_ages=[5, 8],
                    home_phone="+18435550001",
                    cell_phone="+18435551212",
                    work_phone="+18435550002",
                    email="alice@example.com",
                    current_address=ResidenceHistory(
                        address=Address(
                            street="456 Oak Ave", unit="Apt 3B",
                            city="Charleston", state="SC", zip_code="29401",
                        ),
                        years_at_address=3, months_at_address=6,
                        housing_expense_monthly=Decimal("1800"), own_or_rent="RENT",
                    ),
                    prior_addresses=[
                        ResidenceHistory(
                            address=Address(
                                street="100 Pine St", city="Columbia",
                                state="SC", zip_code="29201",
                            ),
                            years_at_address=2, months_at_address=0,
                            own_or_rent="OWN",
                        ),
                    ],
                ),
                section_1b=Section1b_CurrentEmployment(
                    employer_name="Acme Corp",
                    employer_address=Address(
                        street="789 Business Blvd", city="Charleston",
                        state="SC", zip_code="29403",
                    ),
                    position_title="Senior Engineer",
                    start_date=date(2020, 3, 15),
                    years_in_profession=10,
                    base_monthly=Decimal("8500"),
                    overtime_monthly=Decimal("500"),
                    bonus_monthly=Decimal("1000"),
                    employed_by_family_or_party_to_transaction=False,
                ),
                section_1d=Section1d_PreviousEmployment(
                    employer_name="OldCo Inc",
                    position_title="Junior Engineer",
                    start_date=date(2017, 1, 1),
                    end_date=date(2020, 2, 28),
                ),
                section_1e=Section1e_OtherIncome(
                    sources=[
                        OtherIncomeSource(
                            source_type="RENTAL_INCOME",
                            monthly_amount=Decimal("1200"),
                        ),
                    ],
                ),
                section_5=Section5_Declarations(
                    section_5a=Section5a_DeclarationsPropertyMoney(
                        will_occupy_as_primary_residence=True,
                        had_ownership_interest_last_3_years=True,
                        property_type_last_3_years="PRIMARY",
                        how_held_title_last_3_years="JOINT_WITH_SPOUSE",
                        family_business_relationship_with_seller=False,
                        borrowing_money_for_transaction=False,
                        applying_for_other_mortgage_before_closing=False,
                        applying_for_new_credit_before_closing=False,
                        property_subject_to_lien=False,
                    ),
                    section_5b=Section5b_DeclarationsFinances(
                        co_signer_on_undisclosed_debt=False,
                        outstanding_judgments=False,
                        currently_delinquent_on_federal_debt=False,
                        party_to_lawsuit=False,
                        conveyed_title_in_lieu_of_foreclosure_last_7_years=False,
                        short_sale_or_pre_foreclosure_last_7_years=False,
                        foreclosed_last_7_years=False,
                        declared_bankruptcy_last_7_years=True,
                        bankruptcy_types=["CHAPTER_7"],
                    ),
                ),
                section_7=Section7_MilitaryService(
                    served_in_military=True,
                    currently_active_duty=False,
                    retired_discharged_separated=True,
                ),
                section_8=Section8_Demographics(
                    demographics_notice_read_at=datetime(2026, 4, 26, 14, 30, tzinfo=timezone.utc),
                    ethnicity=["NOT_HISPANIC_OR_LATINO"],
                    race=["WHITE"],
                    sex="FEMALE",
                    was_demographic_info_provided_by_borrower=True,
                    was_collected_via_visual_observation_or_surname=False,
                ),
            ),
            # Co-borrower
            Borrower(
                borrower_id="borrower_2",
                is_primary=False,
                section_1a=Section1a_PersonalInformation(
                    first_name="Bob",
                    last_name="Johnson",
                    ssn="987-65-4321",
                    date_of_birth=date(1983, 11, 20),
                    citizenship="US_CITIZEN",
                    marital_status="MARRIED",
                    email="bob@example.com",
                    current_address=ResidenceHistory(
                        address=Address(
                            street="456 Oak Ave", unit="Apt 3B",
                            city="Charleston", state="SC", zip_code="29401",
                        ),
                        years_at_address=3, months_at_address=6,
                        own_or_rent="RENT",
                    ),
                ),
                section_1b=Section1b_CurrentEmployment(
                    employer_name="Beta LLC",
                    position_title="Manager",
                    start_date=date(2018, 7, 1),
                    base_monthly=Decimal("7000"),
                ),
                section_5=Section5_Declarations(
                    section_5a=Section5a_DeclarationsPropertyMoney(
                        will_occupy_as_primary_residence=True,
                        had_ownership_interest_last_3_years=True,
                        property_type_last_3_years="PRIMARY",
                        how_held_title_last_3_years="JOINT_WITH_SPOUSE",
                    ),
                    section_5b=Section5b_DeclarationsFinances(
                        outstanding_judgments=False,
                        declared_bankruptcy_last_7_years=False,
                    ),
                ),
                section_7=Section7_MilitaryService(served_in_military=False),
                section_8=Section8_Demographics(
                    ethnicity=["NOT_HISPANIC_OR_LATINO"],
                    race=["WHITE"],
                    sex="MALE",
                ),
            ),
        ],
        section_2=Section2_AssetsAndLiabilities(
            assets=[
                Asset(
                    asset_type="CHECKING_ACCOUNT",
                    financial_institution="Wells Fargo",
                    account_number_last_4="4567",
                    cash_or_market_value=Decimal("50000"),
                ),
                Asset(
                    asset_type="RETIREMENT",
                    financial_institution="Fidelity",
                    account_number_last_4="2345",
                    cash_or_market_value=Decimal("150000"),
                ),
            ],
            liabilities=[
                Liability(
                    liability_type="REVOLVING",
                    creditor_name="Chase Visa",
                    account_number_last_4="1111",
                    unpaid_balance=Decimal("5000"),
                    monthly_payment=Decimal("150"),
                    months_remaining=36,
                ),
                Liability(
                    liability_type="INSTALLMENT",
                    creditor_name="Toyota Financial",
                    account_number_last_4="2222",
                    unpaid_balance=Decimal("18000"),
                    monthly_payment=Decimal("450"),
                    to_be_paid_off_at_closing=True,
                ),
            ],
            other_liabilities=[
                OtherLiability(
                    liability_type="CHILD_SUPPORT",
                    monthly_payment=Decimal("500"),
                    description="Court-ordered",
                ),
            ],
        ),
        section_3=Section3_RealEstate(
            properties=[
                PropertyOwned(
                    address=Address(
                        street="100 Rental Rd", city="N Charleston",
                        state="SC", zip_code="29405",
                    ),
                    property_value=Decimal("275000"),
                    status="RETAINED",
                    intended_occupancy="INVESTMENT",
                    monthly_insurance_taxes_assoc_dues=Decimal("350"),
                    monthly_rental_income=Decimal("1800"),
                    net_monthly_rental_income=Decimal("1200"),
                    mortgages=[
                        REOMortgage(
                            creditor_name="BofA",
                            account_number_last_4="9999",
                            monthly_payment=Decimal("1100"),
                            unpaid_balance=Decimal("180000"),
                        ),
                    ],
                ),
            ],
        ),
        section_4=Section4_LoanAndProperty(
            section_4a=Section4a_LoanAndProperty(
                loan_amount=Decimal("280000"),
                loan_purpose="PURCHASE",
                subject_property_address=sample_address,
                number_of_units=1,
                property_value=Decimal("350000"),
                occupancy="PRIMARY_RESIDENCE",
                mixed_use_property=False,
            ),
            section_4b=Section4b_OtherNewMortgages(
                does_not_apply=False,
                creditor_name="Second Lender",
                lien_type="SUBORDINATE",
                monthly_payment=Decimal("300"),
                loan_amount=Decimal("40000"),
            ),
            section_4d=Section4d_GiftsOrGrants(
                does_not_apply=False,
                gifts=[
                    Gift(
                        asset_type="CASH_GIFT",
                        deposited=True,
                        source="RELATIVE",
                        cash_or_market_value=Decimal("20000"),
                    ),
                ],
            ),
        ),
        section_6=Section6_Acknowledgments(
            verbal_consent_given=True,
            verbal_consent_timestamp=datetime(2026, 4, 26, 15, 0, 0, tzinfo=timezone.utc),
        ),
        section_9=Section9_LoanOriginator(
            loan_originator_name="Timothy Loss",
            loan_originator_nmlsr_id="987654",
            loan_originator_email="tloss@cmghomeloans.com",
            loan_originator_phone="+18431234567",
            loan_originator_organization_name="The Tim Loss Team",
            loan_originator_organization_nmlsr_id="112233",
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestMISMOSerializer:
    """Core serialization tests."""

    def test_produces_well_formed_xml(self, minimal_app):
        xml_str = serialize_to_mismo34(minimal_app)
        # Should not raise
        root = _parse_strip_ns(xml_str)
        assert root.tag == "MESSAGE"

    def test_xml_declaration_present(self, minimal_app):
        xml_str = serialize_to_mismo34(minimal_app)
        assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_mismo_version(self, minimal_app):
        xml_str = serialize_to_mismo34(minimal_app)
        root = _parse_strip_ns(xml_str)
        assert root.get("MISMOVersionID") == "3.4.032420210307"

    def test_about_versions(self, minimal_app):
        xml_str = serialize_to_mismo34(minimal_app)
        root = _parse_strip_ns(xml_str)
        version_name = root.find(".//ABOUT_VERSION/DataVersionName")
        assert version_name is not None
        assert version_name.text == "Uniform Residential Loan Application"

    def test_deal_structure(self, minimal_app):
        xml_str = serialize_to_mismo34(minimal_app)
        root = _parse_strip_ns(xml_str)
        assert root.find(".//DEAL_SETS/DEAL_SET/DEALS/DEAL") is not None

    def test_namespace_declarations(self, minimal_app):
        xml_str = serialize_to_mismo34(minimal_app)
        assert 'xmlns="http://www.mismo.org/residential/2009/schemas"' in xml_str
        assert 'xmlns:ULAD="http://www.datamodelextension.org/Schema/ULAD"' in xml_str
        assert 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' in xml_str
        # Verify it parses as valid XML even with namespaces
        ET.fromstring(xml_str)

    def test_bytes_output(self, minimal_app):
        result = serialize_to_mismo34_bytes(minimal_app)
        assert isinstance(result, bytes)
        assert result.startswith(b'<?xml version="1.0"')


class TestBorrowerParty:
    """Test borrower PARTY generation."""

    def test_borrower_name(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        name = root.find(".//PARTY/INDIVIDUAL/NAME")
        assert name is not None
        assert name.find("FirstName").text == "Alice"
        assert name.find("LastName").text == "Johnson"

    def test_borrower_ssn(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        ssn = root.find(".//BORROWER_DETAIL/BorrowerSSN")
        assert ssn is not None
        assert ssn.text == "123-45-6789"

    def test_borrower_dob(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        dob = root.find(".//BORROWER_DETAIL/BorrowerBirthDate")
        assert dob is not None
        assert dob.text == "1985-06-12"

    def test_citizenship(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        cit = root.find(".//BORROWER_DETAIL/CitizenshipResidencyType")
        assert cit is not None
        assert cit.text == "USCitizen"

    def test_marital_status(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        ms = root.find(".//BORROWER_DETAIL/MaritalStatusType")
        assert ms is not None
        assert ms.text == "Married"

    def test_contact_email(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        email = root.find(".//CONTACT_POINT_EMAIL/ContactPointEmailValue")
        assert email is not None
        assert email.text == "alice@example.com"

    def test_contact_phone(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        phone = root.find(".//CONTACT_POINT_TELEPHONE/ContactPointTelephoneValue")
        assert phone is not None
        assert phone.text == "+18435551212"

    def test_role_type_is_borrower(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        role_type = root.find(".//PARTY/ROLES/ROLE/ROLE_DETAIL/PartyRoleType")
        assert role_type is not None
        assert role_type.text == "Borrower"

    def test_military_indicator(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        mil = root.find(".//BORROWER_DETAIL/SelfDeclaredMilitaryServiceIndicator")
        assert mil is not None
        assert mil.text == "false"


class TestFullApplication:
    """Test with fully populated application."""

    def test_two_borrower_parties(self, full_app, sample_loan_officer):
        root = _parse_strip_ns(serialize_to_mismo34(full_app, sample_loan_officer))
        parties = root.findall(".//PARTY")
        # 2 borrowers + 1 LO
        assert len(parties) == 3

    def test_co_borrower_ssn(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        ssns = root.findall(".//BORROWER_DETAIL/BorrowerSSN")
        ssn_texts = [s.text for s in ssns]
        assert "123-45-6789" in ssn_texts
        assert "987-65-4321" in ssn_texts

    def test_alternate_names(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        aliases = root.findall(".//ALIASES/ALIAS/NAME/FullName")
        alias_texts = [a.text for a in aliases]
        assert "A.M. Johnson" in alias_texts

    def test_prior_address(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        res_types = root.findall(".//RESIDENCE_DETAIL/BorrowerResidencyType")
        type_texts = [r.text for r in res_types]
        assert "Current" in type_texts
        assert "Prior" in type_texts

    def test_previous_employer(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        statuses = root.findall(".//EMPLOYER_DETAIL/EmploymentStatusType")
        status_texts = [s.text for s in statuses]
        assert "Previous" in status_texts

    def test_military_retired(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        mil_statuses = root.findall(".//BORROWER_DETAIL/MilitaryStatusType")
        assert any(s.text == "RetiredDischarged" for s in mil_statuses)

    def test_bankruptcy_type(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        bk = root.find(".//DECLARATION_DETAIL/BankruptcyChapterType")
        assert bk is not None
        assert bk.text == "Chapter7"

    def test_dependents(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        dep_count = root.find(".//BORROWER_DETAIL/DependentCount")
        assert dep_count is not None
        assert dep_count.text == "2"
        dep_ages = root.find(".//BORROWER_DETAIL/DependentAgesDescription")
        assert dep_ages is not None
        assert "5" in dep_ages.text and "8" in dep_ages.text


class TestAssets:
    """Test ASSETS section."""

    def test_asset_type_mapping(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        asset_type = root.find(".//ASSET_DETAIL/AssetType")
        assert asset_type is not None
        assert asset_type.text == "CheckingAccount"

    def test_asset_value(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        val = root.find(".//ASSET_DETAIL/AssetCashOrMarketValueAmount")
        assert val is not None
        assert val.text == "50000"

    def test_asset_institution(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        name = root.find(".//ASSET_HOLDER/NAME/FullName")
        assert name is not None
        assert name.text == "Wells Fargo"

    def test_multiple_assets(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        assets = root.findall(".//ASSET")
        assert len(assets) == 2


class TestLiabilities:
    """Test LIABILITIES section."""

    def test_liability_type_mapping(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        liab_type = root.find(".//LIABILITY_DETAIL/LiabilityType")
        assert liab_type is not None
        assert liab_type.text == "Revolving"

    def test_liability_creditor(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        name = root.find(".//LIABILITY_HOLDER/NAME/FullName")
        assert name is not None
        assert name.text == "Chase Visa"

    def test_payoff_indicator(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        payoffs = root.findall(".//LIABILITY_DETAIL/LiabilityPayoffStatusIndicator")
        assert any(p.text == "true" for p in payoffs)

    def test_other_liabilities(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        liab_types = root.findall(".//LIABILITY_DETAIL/LiabilityType")
        type_texts = [t.text for t in liab_types]
        assert "ChildSupport" in type_texts


class TestCollaterals:
    """Test COLLATERALS (subject property)."""

    def test_subject_property_address(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        addr = root.find(".//SUBJECT_PROPERTY/ADDRESS/AddressLineText")
        assert addr is not None
        assert addr.text == "123 Main St"

    def test_property_value(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        val = root.find(".//PROPERTY_DETAIL/PropertyEstimatedValueAmount")
        assert val is not None
        assert val.text == "350000"

    def test_property_usage(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        usage = root.find(".//PROPERTY_DETAIL/PropertyUsageType")
        assert usage is not None
        assert usage.text == "PrimaryResidence"


class TestLoans:
    """Test LOANS section."""

    def test_loan_purpose(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        purpose = root.find(".//LOAN_DETAIL/LoanPurposeType")
        assert purpose is not None
        assert purpose.text == "Purchase"

    def test_base_loan_amount(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        amount = root.find(".//TERMS_OF_LOAN/BaseLoanAmount")
        assert amount is not None
        assert amount.text == "280000"

    def test_housing_expense(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        exp = root.find(".//HOUSING_EXPENSE/HousingExpensePaymentAmount")
        assert exp is not None
        assert exp.text == "1800"

    def test_housing_expense_type_rent(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        exp_type = root.find(".//HOUSING_EXPENSE/HousingExpenseType")
        assert exp_type is not None
        assert exp_type.text == "Rent"


class TestIncome:
    """Test CURRENT_INCOME section."""

    def test_base_income(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        income_type = root.find(".//CURRENT_INCOME_ITEM_DETAIL/IncomeType")
        assert income_type is not None
        assert income_type.text == "Base"

    def test_income_amount(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        amount = root.find(".//CURRENT_INCOME_ITEM_DETAIL/CurrentIncomeMonthlyTotalAmount")
        assert amount is not None
        assert amount.text == "8500"

    def test_multiple_income_types(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        types = root.findall(".//CURRENT_INCOME_ITEM_DETAIL/IncomeType")
        type_texts = [t.text for t in types]
        assert "Base" in type_texts
        assert "Overtime" in type_texts
        assert "Bonus" in type_texts
        assert "RentalIncome" in type_texts


class TestDeclarations:
    """Test DECLARATION section."""

    def test_intent_to_occupy(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        intent = root.find(".//DECLARATION_DETAIL/IntentToOccupyType")
        assert intent is not None
        assert intent.text == "Yes"

    def test_homeowner_past_3_years(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        ho = root.find(".//DECLARATION_DETAIL/HomeownerPastThreeYearsType")
        assert ho is not None
        assert ho.text == "No"

    def test_outstanding_judgments(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        oj = root.find(".//DECLARATION_DETAIL/OutstandingJudgmentsIndicator")
        assert oj is not None
        assert oj.text == "false"

    def test_prior_property_usage_and_title(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        usage = root.find(".//DECLARATION_DETAIL/PriorPropertyUsageType")
        assert usage is not None
        assert usage.text == "PrimaryResidence"
        title = root.find(".//DECLARATION_DETAIL/PriorPropertyTitleType")
        assert title is not None
        assert title.text == "JointlyWithSpouse"


class TestGifts:
    """Test gifts and grants."""

    def test_gift_amount(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        amt = root.find(".//GIFT/GiftOrGrantAmount")
        assert amt is not None
        assert amt.text == "20000"

    def test_gift_type(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        gift_type = root.find(".//GIFT/GiftOrGrantType")
        assert gift_type is not None
        assert gift_type.text == "CashGift"

    def test_gift_source(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        source = root.find(".//GIFT/GiftOrGrantSourceType")
        assert source is not None
        assert source.text == "Relative"

    def test_gift_deposited(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        dep = root.find(".//GIFT/FundsDepositedIndicator")
        assert dep is not None
        assert dep.text == "true"


class TestRealEstateOwned:
    """Test Section 3 REO."""

    def test_reo_property_value(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        val = root.find(".//OWNED_PROPERTY_DETAIL/OwnedPropertyMarketValueAmount")
        assert val is not None
        assert val.text == "275000"

    def test_reo_status(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        status = root.find(".//OWNED_PROPERTY_DETAIL/OwnedPropertyDispositionStatusType")
        assert status is not None
        assert status.text == "Retained"

    def test_reo_mortgage(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        balance = root.find(".//OWNED_PROPERTY_MORTGAGE/OwnedPropertyMortgageUnpaidBalanceAmount")
        assert balance is not None
        assert balance.text == "180000"


class TestGovernmentMonitoring:
    """Test HMDA / Section 8."""

    def test_ethnicity(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        eth = root.find(".//GOVERNMENT_MONITORING_DETAIL_EXTENSION/HMDAEthnicityType")
        assert eth is not None
        assert eth.text == "NotHispanicOrLatino"

    def test_race(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        race = root.find(".//GOVERNMENT_MONITORING_DETAIL_EXTENSION/HMDARaceType")
        assert race is not None
        assert race.text == "White"

    def test_sex(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        sex = root.find(".//GOVERNMENT_MONITORING_DETAIL_EXTENSION/HMDAGenderType")
        assert sex is not None
        assert sex.text == "Female"


class TestLoanOriginator:
    """Test LO PARTY generation."""

    def test_lo_from_section9(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        nmlsr = root.find(".//LOAN_ORIGINATOR_DETAIL/NMLSIdentifier")
        assert nmlsr is not None
        assert nmlsr.text == "987654"

    def test_lo_role_type(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        roles = root.findall(".//ROLE_DETAIL/PartyRoleType")
        role_texts = [r.text for r in roles]
        assert "NotePayTo" in role_texts

    def test_lo_from_param(self, minimal_app, sample_loan_officer):
        # Clear section 9 to test LoanOfficer param fallback
        minimal_app.section_9 = None
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app, sample_loan_officer))
        nmlsr = root.find(".//LOAN_ORIGINATOR_DETAIL/NMLSIdentifier")
        assert nmlsr is not None
        assert nmlsr.text == "987654"

    def test_lo_taxpayer_identifier(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        tax_type = root.find(".//TAXPAYER_IDENTIFIER/TaxpayerIdentifierType")
        assert tax_type is not None
        assert tax_type.text == "NMLSIdentifier"


class TestOtherNewMortgage:
    """Test Section 4b additional loans."""

    def test_additional_loan_present(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        addl_amt = root.find(".//ADDITIONAL_LOAN/AdditionalLoanAmount")
        assert addl_amt is not None
        assert addl_amt.text == "40000"


class TestRelationships:
    """Test RELATIONSHIPS linking parties to loans."""

    def test_relationships_present(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        rels = root.findall(".//RELATIONSHIP")
        assert len(rels) >= 1


class TestEmptySections:
    """Test graceful handling of missing/empty sections."""

    def test_no_section2(self):
        app = URLAApplication(
            loan_id="LOAN-EMPTY",
            tenant_id="t-1",
            caller_phone="+18435551212",
            borrowers=[
                Borrower(
                    borrower_id="borrower_1",
                    is_primary=True,
                    section_1a=Section1a_PersonalInformation(
                        first_name="Jane",
                        last_name="Doe",
                    ),
                ),
            ],
        )
        xml_str = serialize_to_mismo34(app)
        root = _parse_strip_ns(xml_str)
        # Should still produce valid XML
        assert root.find(".//DEAL") is not None
        # No ASSETS element
        assert root.find(".//ASSETS") is None

    def test_no_section4(self):
        app = URLAApplication(
            loan_id="LOAN-EMPTY2",
            tenant_id="t-1",
            caller_phone="+18435551212",
            borrowers=[
                Borrower(borrower_id="borrower_1", is_primary=True),
            ],
        )
        xml_str = serialize_to_mismo34(app)
        root = _parse_strip_ns(xml_str)
        assert root.find(".//COLLATERALS") is None

    def test_no_loan_officer(self):
        app = URLAApplication(
            loan_id="LOAN-NO-LO",
            tenant_id="t-1",
            caller_phone="+18435551212",
            borrowers=[
                Borrower(borrower_id="borrower_1", is_primary=True),
            ],
        )
        xml_str = serialize_to_mismo34(app)
        root = _parse_strip_ns(xml_str)
        # Only 1 party (borrower), no LO party
        parties = root.findall(".//PARTY")
        assert len(parties) == 1


class TestResidences:
    """Test RESIDENCES serialization."""

    def test_residence_duration(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        months = root.find(".//RESIDENCE_DETAIL/BorrowerResidencyDurationMonthsCount")
        assert months is not None
        # 3 years + 6 months = 42
        assert months.text == "42"

    def test_residence_type(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        res_type = root.find(".//RESIDENCE_DETAIL/BorrowerResidencyType")
        assert res_type is not None
        assert res_type.text == "Current"

    def test_residence_basis_rent(self, minimal_app):
        root = _parse_strip_ns(serialize_to_mismo34(minimal_app))
        basis = root.find(".//RESIDENCE_DETAIL/BorrowerResidencyBasisType")
        assert basis is not None
        assert basis.text == "Rent"

    def test_address_with_unit(self, full_app):
        root = _parse_strip_ns(serialize_to_mismo34(full_app))
        addresses = root.findall(".//RESIDENCE/ADDRESS/AddressLineText")
        address_texts = [a.text for a in addresses]
        assert any("Apt 3B" in addr for addr in address_texts)
