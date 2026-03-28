"""
Seed script for 50-state + DC mortgage disclosure requirements.

Covers all 51 jurisdictions. Top 20 states by mortgage volume have full
multi-category entries; remaining 31 have licensing, key disclosure, and
recording consent as a minimum baseline.

Usage:
    python seed_state_disclosures.py
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_DISCLOSURES: List[Dict[str, Any]] = [
    # =========================================================================
    # CALIFORNIA
    # =========================================================================
    {"state_code": "CA", "state_name": "California", "category": "licensing",
     "requirement": "DRE or DFPI (formerly DBO) license required. NMLS registration mandatory for all MLOs.",
     "regulatory_reference": "Cal. Fin. Code § 50000; Cal. Bus. & Prof. Code § 10166"},
    {"state_code": "CA", "state_name": "California", "category": "disclosure",
     "requirement": "Mortgage Loan Disclosure Statement (MLDS) required within 3 business days of application.",
     "regulatory_reference": "Cal. Bus. & Prof. Code § 10240"},
    {"state_code": "CA", "state_name": "California", "category": "disclosure",
     "requirement": "Agency disclosure required prior to accepting deposit or executing purchase agreement.",
     "regulatory_reference": "Cal. Civ. Code § 2079.16"},
    {"state_code": "CA", "state_name": "California", "category": "disclosure",
     "requirement": "Transfer Disclosure Statement (TDS) required in residential sales of 1–4 units.",
     "regulatory_reference": "Cal. Civ. Code § 1102"},
    {"state_code": "CA", "state_name": "California", "category": "fee_limit",
     "requirement": "Origination fees limited to 3% on loans > $30,000. Total points and fees capped at 5%.",
     "regulatory_reference": "Cal. Fin. Code § 50204"},
    {"state_code": "CA", "state_name": "California", "category": "fee_limit",
     "requirement": "APR threshold for high-cost loans: 6.5% above APOR for first lien; 8.5% for subordinate.",
     "regulatory_reference": "Cal. Fin. Code § 4970"},
    {"state_code": "CA", "state_name": "California", "category": "prepayment",
     "requirement": "No prepayment penalties allowed on primary residence loans. Restriction applies to refinances and purchase loans.",
     "regulatory_reference": "Cal. Civ. Code § 2954.9"},
    {"state_code": "CA", "state_name": "California", "category": "cooling_off",
     "requirement": "3-day right of rescission on refinances of primary residence (federal) plus California-specific HELOC rescission.",
     "regulatory_reference": "15 U.S.C. § 1635; Cal. Civ. Code § 1689.5"},
    {"state_code": "CA", "state_name": "California", "category": "special_rule",
     "requirement": "Foreclosure consultant regulations impose strict disclosure and contract requirements when assisting distressed homeowners.",
     "regulatory_reference": "Cal. Civ. Code § 2945"},
    {"state_code": "CA", "state_name": "California", "category": "special_rule",
     "requirement": "One-action rule: lender may pursue only one remedy (foreclosure or deficiency judgment) against defaulting borrower.",
     "regulatory_reference": "Cal. Code Civ. Proc. § 726"},
    {"state_code": "CA", "state_name": "California", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Cal. Penal Code § 632"},

    # =========================================================================
    # TEXAS
    # =========================================================================
    {"state_code": "TX", "state_name": "Texas", "category": "licensing",
     "requirement": "SML (Savings & Mortgage Lending) license required. NMLS registration mandatory.",
     "regulatory_reference": "Tex. Fin. Code § 156.201"},
    {"state_code": "TX", "state_name": "Texas", "category": "disclosure",
     "requirement": "Texas Section 50(a)(6) Home Equity Disclosure required at application for cash-out refinances.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)"},
    {"state_code": "TX", "state_name": "Texas", "category": "disclosure",
     "requirement": "12-Day Letter must be provided at least 12 days before closing for home equity loans.",
     "regulatory_reference": "7 Tex. Admin. Code § 153.14"},
    {"state_code": "TX", "state_name": "Texas", "category": "fee_limit",
     "requirement": "Total fees on home equity loans capped at 3% of loan amount. Excludes bona fide third-party charges.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(E)"},
    {"state_code": "TX", "state_name": "Texas", "category": "prepayment",
     "requirement": "No prepayment penalties on home equity loans secured by homestead. Conventional loans: state law silent, contractual terms govern.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(G)"},
    {"state_code": "TX", "state_name": "Texas", "category": "cooling_off",
     "requirement": "12-day waiting period from date of application or 12-day disclosure (whichever is later) before home equity loan can close.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(M)(ii)"},
    {"state_code": "TX", "state_name": "Texas", "category": "cooling_off",
     "requirement": "3-business-day right of rescission after closing on home equity loans.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(Q)(viii)"},
    {"state_code": "TX", "state_name": "Texas", "category": "special_rule",
     "requirement": "Maximum LTV of 80% for cash-out refinances on homestead property.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(B)"},
    {"state_code": "TX", "state_name": "Texas", "category": "special_rule",
     "requirement": "Once-a-year rule: a homestead property may have only one home equity loan per 12-month period.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(M)(iii)"},
    {"state_code": "TX", "state_name": "Texas", "category": "special_rule",
     "requirement": "Home equity loans must close at the office of the lender, a title company, or an attorney's office.",
     "regulatory_reference": "Tex. Const. art. XVI § 50(a)(6)(N)"},
    {"state_code": "TX", "state_name": "Texas", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls (Texas is a one-party consent state).",
     "regulatory_reference": "Tex. Penal Code § 16.02"},

    # =========================================================================
    # FLORIDA
    # =========================================================================
    {"state_code": "FL", "state_name": "Florida", "category": "licensing",
     "requirement": "OFR (Office of Financial Regulation) Mortgage Loan Originator license required. NMLS registration mandatory.",
     "regulatory_reference": "Fla. Stat. § 494.00312"},
    {"state_code": "FL", "state_name": "Florida", "category": "disclosure",
     "requirement": "Radon gas disclosure required in all residential sales and leases.",
     "regulatory_reference": "Fla. Stat. § 404.056(5)"},
    {"state_code": "FL", "state_name": "Florida", "category": "disclosure",
     "requirement": "Seller's real property disclosure form required for residential sales of 1–4 units.",
     "regulatory_reference": "Fla. Stat. § 689.261"},
    {"state_code": "FL", "state_name": "Florida", "category": "disclosure",
     "requirement": "Energy efficiency rating disclosure required for new construction.",
     "regulatory_reference": "Fla. Stat. § 553.996"},
    {"state_code": "FL", "state_name": "Florida", "category": "fee_limit",
     "requirement": "High-cost loan threshold: APR exceeds APOR by 6.5% (first lien) or 8.5% (subordinate). Additional restrictions apply.",
     "regulatory_reference": "Fla. Stat. § 494.0079"},
    {"state_code": "FL", "state_name": "Florida", "category": "special_rule",
     "requirement": "Documentary stamp tax: $0.35 per $100 of consideration on deed; $0.35 per $100 on mortgage note (Miami-Dade: $0.60 on deed).",
     "regulatory_reference": "Fla. Stat. §§ 201.02, 201.08"},
    {"state_code": "FL", "state_name": "Florida", "category": "special_rule",
     "requirement": "Florida homestead exemption provides strong anti-deficiency protection; forced sale of homestead is narrowly restricted.",
     "regulatory_reference": "Fla. Const. art. X § 4"},
    {"state_code": "FL", "state_name": "Florida", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Fla. Stat. § 934.03"},

    # =========================================================================
    # NEW YORK
    # =========================================================================
    {"state_code": "NY", "state_name": "New York", "category": "licensing",
     "requirement": "NYDFS Mortgage Loan Originator license required. NMLS registration mandatory.",
     "regulatory_reference": "N.Y. Banking Law § 590-b"},
    {"state_code": "NY", "state_name": "New York", "category": "disclosure",
     "requirement": "Subprime/High-Cost Loan Disclosure (NYCRR) required 3 business days before closing.",
     "regulatory_reference": "3 N.Y.C.R.R. Part 41"},
    {"state_code": "NY", "state_name": "New York", "category": "disclosure",
     "requirement": "Mortgage Recording Tax Disclosure required at application. Tax: 1.05% on mortgages ≤ $500K; 1.3% on mortgages > $500K in NYC.",
     "regulatory_reference": "N.Y. Tax Law § 253"},
    {"state_code": "NY", "state_name": "New York", "category": "disclosure",
     "requirement": "Predatory lending disclosure required for high-cost loans (SONYMA definition applies).",
     "regulatory_reference": "N.Y. Banking Law § 6-l"},
    {"state_code": "NY", "state_name": "New York", "category": "fee_limit",
     "requirement": "Points and fees cap: 5% on high-cost loans. Origination fee limits apply under Banking Law § 6-l.",
     "regulatory_reference": "N.Y. Banking Law § 6-l(2)(d)"},
    {"state_code": "NY", "state_name": "New York", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost loans. Conventional loans: 3-year limitation on prepayment penalty terms.",
     "regulatory_reference": "N.Y. Banking Law § 6-l(2)(c)"},
    {"state_code": "NY", "state_name": "New York", "category": "cooling_off",
     "requirement": "3-business-day waiting period after receipt of high-cost loan disclosure before closing.",
     "regulatory_reference": "N.Y. Banking Law § 6-l(2)(b)"},
    {"state_code": "NY", "state_name": "New York", "category": "special_rule",
     "requirement": "Mansion tax: 1% surcharge on residential purchases ≥ $1M; progressive rate up to 3.9% over $25M.",
     "regulatory_reference": "N.Y. Tax Law § 1402-a"},
    {"state_code": "NY", "state_name": "New York", "category": "special_rule",
     "requirement": "CEMA (Consolidation, Extension and Modification Agreement) allows borrowers to avoid mortgage recording tax on refinances.",
     "regulatory_reference": "N.Y. Real Prop. Law § 275"},
    {"state_code": "NY", "state_name": "New York", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls (New York is a one-party consent state).",
     "regulatory_reference": "N.Y. Penal Law § 250.00"},

    # =========================================================================
    # PENNSYLVANIA
    # =========================================================================
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "licensing",
     "requirement": "Pennsylvania Department of Banking license required under the Mortgage Licensing Act. NMLS registration mandatory.",
     "regulatory_reference": "63 P.S. § 456.1 et seq."},
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "disclosure",
     "requirement": "Homeowner's Emergency Mortgage Assistance Program (HEMAP) disclosure required at loan origination.",
     "regulatory_reference": "35 P.S. § 1680.401 et seq."},
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "disclosure",
     "requirement": "Seller Property Disclosure Statement required for residential sales; covers structure, mechanical systems, environmental hazards.",
     "regulatory_reference": "68 Pa. Stat. § 1023"},
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "fee_limit",
     "requirement": "High-cost home loan: APR threshold 8% above TBMR for first liens. Points and fees > 4% triggers high-cost designation.",
     "regulatory_reference": "41 P.S. § 101 (Loan Interest and Protection Law)"},
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost home loans.",
     "regulatory_reference": "41 P.S. § 101"},
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "special_rule",
     "requirement": "Act 91 Notice: lenders must send prescribed notice before initiating foreclosure, giving borrower access to HEMAP counseling.",
     "regulatory_reference": "35 P.S. § 1680.403c"},
    {"state_code": "PA", "state_name": "Pennsylvania", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "18 Pa. Cons. Stat. § 5703"},

    # =========================================================================
    # ILLINOIS
    # =========================================================================
    {"state_code": "IL", "state_name": "Illinois", "category": "licensing",
     "requirement": "IDFPR Residential Mortgage License required. NMLS registration mandatory.",
     "regulatory_reference": "205 ILCS 635/"},
    {"state_code": "IL", "state_name": "Illinois", "category": "disclosure",
     "requirement": "Residential Real Property Disclosure Act report required before sale of residential property.",
     "regulatory_reference": "765 ILCS 77/"},
    {"state_code": "IL", "state_name": "Illinois", "category": "disclosure",
     "requirement": "Illinois Predatory Lending Database Program applies in Cook County and select collar counties; counseling certificate required.",
     "regulatory_reference": "765 ILCS 77/70"},
    {"state_code": "IL", "state_name": "Illinois", "category": "fee_limit",
     "requirement": "High-risk home loan: points and fees cap at 5%. Anti-predatory lending rules impose additional restrictions in covered counties.",
     "regulatory_reference": "815 ILCS 137/"},
    {"state_code": "IL", "state_name": "Illinois", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-risk home loans.",
     "regulatory_reference": "815 ILCS 137/35"},
    {"state_code": "IL", "state_name": "Illinois", "category": "special_rule",
     "requirement": "Attorneys are required to close real estate transactions in Illinois; title companies alone cannot close.",
     "regulatory_reference": "Common practice / Illinois Supreme Court Rule 1.2"},
    {"state_code": "IL", "state_name": "Illinois", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "720 ILCS 5/14-2"},

    # =========================================================================
    # OHIO
    # =========================================================================
    {"state_code": "OH", "state_name": "Ohio", "category": "licensing",
     "requirement": "Ohio Division of Financial Institutions Mortgage Loan Originator license required. NMLS mandatory.",
     "regulatory_reference": "Ohio Rev. Code § 1322.01 et seq."},
    {"state_code": "OH", "state_name": "Ohio", "category": "disclosure",
     "requirement": "Ohio Residential Property Disclosure Form required in sales of residential property (1–4 units).",
     "regulatory_reference": "Ohio Rev. Code § 5302.30"},
    {"state_code": "OH", "state_name": "Ohio", "category": "fee_limit",
     "requirement": "Consumer Sales Practices Act applies; unconscionable terms or excessive fees may be challenged.",
     "regulatory_reference": "Ohio Rev. Code § 1345.02"},
    {"state_code": "OH", "state_name": "Ohio", "category": "prepayment",
     "requirement": "No specific state prepayment penalty prohibition; contractual terms govern. Federal CFPB rules apply.",
     "regulatory_reference": "Ohio Rev. Code Title XIII"},
    {"state_code": "OH", "state_name": "Ohio", "category": "special_rule",
     "requirement": "Ohio Anti-Predatory Lending law (OAML) imposes restrictions on high-cost loans originated in the state.",
     "regulatory_reference": "Ohio Rev. Code § 1349.25"},
    {"state_code": "OH", "state_name": "Ohio", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Ohio Rev. Code § 2933.52"},

    # =========================================================================
    # GEORGIA
    # =========================================================================
    {"state_code": "GA", "state_name": "Georgia", "category": "licensing",
     "requirement": "Georgia Department of Banking and Finance license required. NMLS registration mandatory.",
     "regulatory_reference": "O.C.G.A. § 7-1-1000 et seq."},
    {"state_code": "GA", "state_name": "Georgia", "category": "disclosure",
     "requirement": "Georgia Fair Lending Act Disclosure required for home loans. Notice of transfer of servicing required within 15 days.",
     "regulatory_reference": "O.C.G.A. § 7-6A-1 et seq."},
    {"state_code": "GA", "state_name": "Georgia", "category": "disclosure",
     "requirement": "Seller's Property Disclosure Statement: required by convention in residential sales; statutory requirement for some transfers.",
     "regulatory_reference": "O.C.G.A. § 44-1-16"},
    {"state_code": "GA", "state_name": "Georgia", "category": "fee_limit",
     "requirement": "High-cost home loan: points and fees > 5% of loan amount (or $800, whichever is greater) triggers GFLA restrictions.",
     "regulatory_reference": "O.C.G.A. § 7-6A-2"},
    {"state_code": "GA", "state_name": "Georgia", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost home loans under the Georgia Fair Lending Act.",
     "regulatory_reference": "O.C.G.A. § 7-6A-6"},
    {"state_code": "GA", "state_name": "Georgia", "category": "special_rule",
     "requirement": "Georgia is a non-judicial foreclosure state; Power of Sale clauses are commonly used. 30-day notice required before foreclosure sale.",
     "regulatory_reference": "O.C.G.A. § 44-14-162.2"},
    {"state_code": "GA", "state_name": "Georgia", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "O.C.G.A. § 16-11-62"},

    # =========================================================================
    # NORTH CAROLINA
    # =========================================================================
    {"state_code": "NC", "state_name": "North Carolina", "category": "licensing",
     "requirement": "NC Commissioner of Banks Mortgage Loan Originator license required. NMLS registration mandatory.",
     "regulatory_reference": "N.C. Gen. Stat. § 53-244.010 et seq."},
    {"state_code": "NC", "state_name": "North Carolina", "category": "disclosure",
     "requirement": "NC Residential Property Disclosure Statement required in residential real estate sales.",
     "regulatory_reference": "N.C. Gen. Stat. § 47E-4"},
    {"state_code": "NC", "state_name": "North Carolina", "category": "fee_limit",
     "requirement": "High-cost home loan: points and fees > 5% of loan or $1,000 (whichever is greater). APR threshold 8% above T-bond rate.",
     "regulatory_reference": "N.C. Gen. Stat. § 24-1.1E"},
    {"state_code": "NC", "state_name": "North Carolina", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost home loans. Conventional loans: not restricted beyond federal rules.",
     "regulatory_reference": "N.C. Gen. Stat. § 24-1.1E(d)"},
    {"state_code": "NC", "state_name": "North Carolina", "category": "cooling_off",
     "requirement": "3-business-day waiting period after receipt of high-cost loan disclosures before consummation.",
     "regulatory_reference": "N.C. Gen. Stat. § 24-1.1E(c)"},
    {"state_code": "NC", "state_name": "North Carolina", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "N.C. Gen. Stat. § 15A-287"},

    # =========================================================================
    # MICHIGAN
    # =========================================================================
    {"state_code": "MI", "state_name": "Michigan", "category": "licensing",
     "requirement": "DIFS (Department of Insurance and Financial Services) license required under MRMLA. NMLS mandatory.",
     "regulatory_reference": "M.C.L. § 493.131 et seq."},
    {"state_code": "MI", "state_name": "Michigan", "category": "disclosure",
     "requirement": "Seller Disclosure Act: written disclosure statement required for residential sales of 1–4 units.",
     "regulatory_reference": "M.C.L. § 565.951 et seq."},
    {"state_code": "MI", "state_name": "Michigan", "category": "fee_limit",
     "requirement": "High-cost mortgage: APR exceeds APOR by 6.5% (first lien). Points and fees > 5%. Additional MI-specific restrictions apply.",
     "regulatory_reference": "M.C.L. § 445.1631 et seq."},
    {"state_code": "MI", "state_name": "Michigan", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost mortgages. Otherwise governed by contractual terms.",
     "regulatory_reference": "M.C.L. § 445.1638"},
    {"state_code": "MI", "state_name": "Michigan", "category": "special_rule",
     "requirement": "Michigan is a judicial foreclosure state by default but non-judicial (advertisement-based) foreclosure is available with power-of-sale clause.",
     "regulatory_reference": "M.C.L. § 600.3101; M.C.L. § 600.3201"},
    {"state_code": "MI", "state_name": "Michigan", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "M.C.L. § 750.539c"},

    # =========================================================================
    # NEW JERSEY
    # =========================================================================
    {"state_code": "NJ", "state_name": "New Jersey", "category": "licensing",
     "requirement": "NJ Department of Banking and Insurance license required. NMLS registration mandatory.",
     "regulatory_reference": "N.J. Stat. Ann. § 17:11C-51 et seq."},
    {"state_code": "NJ", "state_name": "New Jersey", "category": "disclosure",
     "requirement": "NJ Seller Property Condition Disclosure Statement required for residential sales.",
     "regulatory_reference": "N.J. Stat. Ann. § 46:3C-1 et seq."},
    {"state_code": "NJ", "state_name": "New Jersey", "category": "disclosure",
     "requirement": "Lead paint disclosure required for residential housing built before 1978.",
     "regulatory_reference": "N.J.A.C. 8:51"},
    {"state_code": "NJ", "state_name": "New Jersey", "category": "fee_limit",
     "requirement": "High-cost home loan: points and fees > 6% of loan amount triggers NJ Home Ownership Security Act restrictions.",
     "regulatory_reference": "N.J. Stat. Ann. § 46:10B-22 et seq."},
    {"state_code": "NJ", "state_name": "New Jersey", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost home loans under the NJ Home Ownership Security Act.",
     "regulatory_reference": "N.J. Stat. Ann. § 46:10B-25(c)"},
    {"state_code": "NJ", "state_name": "New Jersey", "category": "special_rule",
     "requirement": "NJ is a judicial foreclosure state; foreclosure requires court filing, typically 200–400 days from default.",
     "regulatory_reference": "N.J. Ct. R. 4:65"},
    {"state_code": "NJ", "state_name": "New Jersey", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "N.J. Stat. Ann. § 2A:156A-4"},

    # =========================================================================
    # VIRGINIA
    # =========================================================================
    {"state_code": "VA", "state_name": "Virginia", "category": "licensing",
     "requirement": "Virginia Bureau of Financial Institutions license required under the Virginia Mortgage Lender and Broker Act. NMLS mandatory.",
     "regulatory_reference": "Va. Code Ann. § 6.2-1600 et seq."},
    {"state_code": "VA", "state_name": "Virginia", "category": "disclosure",
     "requirement": "Virginia Residential Property Disclosure Act: sellers must deliver disclosure or disclaimer statement.",
     "regulatory_reference": "Va. Code Ann. § 55.1-700 et seq."},
    {"state_code": "VA", "state_name": "Virginia", "category": "fee_limit",
     "requirement": "Virginia Consumer Protection Act applies to mortgage transactions; unconscionable or deceptive fee arrangements are prohibited.",
     "regulatory_reference": "Va. Code Ann. § 59.1-196 et seq."},
    {"state_code": "VA", "state_name": "Virginia", "category": "prepayment",
     "requirement": "No specific state prepayment penalty prohibition beyond federal rules. High-cost loan restrictions apply where triggered.",
     "regulatory_reference": "Va. Code Ann. § 6.2-422"},
    {"state_code": "VA", "state_name": "Virginia", "category": "special_rule",
     "requirement": "Virginia uses non-judicial (deed of trust) foreclosure; trustee sale can proceed without court action after proper notice.",
     "regulatory_reference": "Va. Code Ann. § 55.1-321"},
    {"state_code": "VA", "state_name": "Virginia", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Va. Code Ann. § 19.2-62"},

    # =========================================================================
    # WASHINGTON
    # =========================================================================
    {"state_code": "WA", "state_name": "Washington", "category": "licensing",
     "requirement": "Washington DFI Consumer Loan Company or Mortgage Broker license required. NMLS mandatory.",
     "regulatory_reference": "Wash. Rev. Code § 31.04.015; § 19.146.200"},
    {"state_code": "WA", "state_name": "Washington", "category": "disclosure",
     "requirement": "Seller Disclosure Statement required for residential sales of real property.",
     "regulatory_reference": "Wash. Rev. Code § 64.06.013"},
    {"state_code": "WA", "state_name": "Washington", "category": "disclosure",
     "requirement": "Washington's Predatory Lending Law requires good-faith estimate and closing cost disclosure consistent with TRID.",
     "regulatory_reference": "Wash. Rev. Code § 19.146.030"},
    {"state_code": "WA", "state_name": "Washington", "category": "fee_limit",
     "requirement": "High-cost home loan: points and fees > 5% of loan amount or $1,000 (whichever is greater). APR threshold applies.",
     "regulatory_reference": "Wash. Rev. Code § 19.144.020"},
    {"state_code": "WA", "state_name": "Washington", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost home loans.",
     "regulatory_reference": "Wash. Rev. Code § 19.144.040"},
    {"state_code": "WA", "state_name": "Washington", "category": "special_rule",
     "requirement": "Washington uses non-judicial (deed of trust) foreclosure with 190-day minimum process from notice of default.",
     "regulatory_reference": "Wash. Rev. Code § 61.24.030"},
    {"state_code": "WA", "state_name": "Washington", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Wash. Rev. Code § 9.73.030"},

    # =========================================================================
    # ARIZONA
    # =========================================================================
    {"state_code": "AZ", "state_name": "Arizona", "category": "licensing",
     "requirement": "Arizona Department of Financial Institutions Mortgage Banker/Broker license required. NMLS mandatory.",
     "regulatory_reference": "A.R.S. § 6-901 et seq."},
    {"state_code": "AZ", "state_name": "Arizona", "category": "disclosure",
     "requirement": "Arizona Residential Seller Property Disclosure Statement (SPDS) required in residential resales.",
     "regulatory_reference": "A.R.S. § 33-422"},
    {"state_code": "AZ", "state_name": "Arizona", "category": "fee_limit",
     "requirement": "No state-specific high-cost loan fee caps beyond federal HOEPA thresholds. Usury limits may apply to certain lenders.",
     "regulatory_reference": "A.R.S. § 44-1201"},
    {"state_code": "AZ", "state_name": "Arizona", "category": "prepayment",
     "requirement": "Prepayment penalties permitted by contract on most loans; no specific state prohibition except as triggered by federal rules.",
     "regulatory_reference": "A.R.S. § 33-806.01"},
    {"state_code": "AZ", "state_name": "Arizona", "category": "special_rule",
     "requirement": "Arizona is an anti-deficiency state: no deficiency judgment allowed on purchase-money mortgage on residential property (2.5 acres, single/2-family).",
     "regulatory_reference": "A.R.S. § 33-729"},
    {"state_code": "AZ", "state_name": "Arizona", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "A.R.S. § 13-3005"},

    # =========================================================================
    # MASSACHUSETTS
    # =========================================================================
    {"state_code": "MA", "state_name": "Massachusetts", "category": "licensing",
     "requirement": "Massachusetts Division of Banks Mortgage Loan Originator license required. NMLS mandatory.",
     "regulatory_reference": "Mass. Gen. Laws ch. 255E § 2"},
    {"state_code": "MA", "state_name": "Massachusetts", "category": "disclosure",
     "requirement": "Massachusetts Consumer Credit Cost Disclosure Act mandates APR disclosure in addition to TRID requirements.",
     "regulatory_reference": "Mass. Gen. Laws ch. 140D"},
    {"state_code": "MA", "state_name": "Massachusetts", "category": "disclosure",
     "requirement": "Mandatory homebuyer counseling for first-time buyers using MassHousing or MHP products.",
     "regulatory_reference": "760 C.M.R. § 56.00"},
    {"state_code": "MA", "state_name": "Massachusetts", "category": "fee_limit",
     "requirement": "High-cost home mortgage loan: points and fees > 5% of loan amount (or $800). APR threshold: 8% above T-bond rate.",
     "regulatory_reference": "Mass. Gen. Laws ch. 183C"},
    {"state_code": "MA", "state_name": "Massachusetts", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on high-cost home mortgage loans.",
     "regulatory_reference": "Mass. Gen. Laws ch. 183C § 7"},
    {"state_code": "MA", "state_name": "Massachusetts", "category": "special_rule",
     "requirement": "Massachusetts uses non-judicial (power of sale) foreclosure after right to cure period (150-day notice requirement).",
     "regulatory_reference": "Mass. Gen. Laws ch. 244 § 35A"},
    {"state_code": "MA", "state_name": "Massachusetts", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Mass. Gen. Laws ch. 272 § 99"},

    # =========================================================================
    # TENNESSEE
    # =========================================================================
    {"state_code": "TN", "state_name": "Tennessee", "category": "licensing",
     "requirement": "Tennessee Department of Financial Institutions license required under the Tennessee Residential Lending, Brokerage and Servicing Act. NMLS mandatory.",
     "regulatory_reference": "Tenn. Code Ann. § 45-13-101 et seq."},
    {"state_code": "TN", "state_name": "Tennessee", "category": "disclosure",
     "requirement": "Tennessee Residential Property Condition Disclosure required for all residential property transfers.",
     "regulatory_reference": "Tenn. Code Ann. § 66-5-202"},
    {"state_code": "TN", "state_name": "Tennessee", "category": "fee_limit",
     "requirement": "Home loan high-cost thresholds follow federal HOEPA. No additional state-specific fee caps on conventional loans.",
     "regulatory_reference": "Tenn. Code Ann. § 45-20-101"},
    {"state_code": "TN", "state_name": "Tennessee", "category": "special_rule",
     "requirement": "Tennessee uses non-judicial (trustee's sale) foreclosure; 20-day notice period required after advertisement.",
     "regulatory_reference": "Tenn. Code Ann. § 35-5-101"},
    {"state_code": "TN", "state_name": "Tennessee", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Tenn. Code Ann. § 39-13-601"},

    # =========================================================================
    # INDIANA
    # =========================================================================
    {"state_code": "IN", "state_name": "Indiana", "category": "licensing",
     "requirement": "Indiana Department of Financial Institutions license required. NMLS registration mandatory.",
     "regulatory_reference": "Ind. Code § 24-4.4-1-101 et seq."},
    {"state_code": "IN", "state_name": "Indiana", "category": "disclosure",
     "requirement": "Seller's Residential Real Estate Sales Disclosure required for sales of residential property (1–4 units).",
     "regulatory_reference": "Ind. Code § 32-21-5-7"},
    {"state_code": "IN", "state_name": "Indiana", "category": "fee_limit",
     "requirement": "First lien home loan rates governed by Indiana Uniform Consumer Credit Code. Rate and fee ceilings apply.",
     "regulatory_reference": "Ind. Code § 24-4.5-3-508"},
    {"state_code": "IN", "state_name": "Indiana", "category": "special_rule",
     "requirement": "Indiana requires judicial foreclosure; process typically takes 150–300 days.",
     "regulatory_reference": "Ind. Code § 32-30-10-1"},
    {"state_code": "IN", "state_name": "Indiana", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Ind. Code § 35-31.5-2-176"},

    # =========================================================================
    # MISSOURI
    # =========================================================================
    {"state_code": "MO", "state_name": "Missouri", "category": "licensing",
     "requirement": "Missouri Division of Finance Mortgage Loan Originator license required. NMLS mandatory.",
     "regulatory_reference": "Mo. Rev. Stat. § 443.800 et seq."},
    {"state_code": "MO", "state_name": "Missouri", "category": "disclosure",
     "requirement": "Missouri Seller Property Disclosure required in residential transactions; statutory form required.",
     "regulatory_reference": "Mo. Rev. Stat. § 339.730"},
    {"state_code": "MO", "state_name": "Missouri", "category": "fee_limit",
     "requirement": "High-cost home loans follow federal HOEPA thresholds. Missouri has no additional state-specific points and fees cap.",
     "regulatory_reference": "Mo. Rev. Stat. § 408.233"},
    {"state_code": "MO", "state_name": "Missouri", "category": "special_rule",
     "requirement": "Missouri allows both judicial and non-judicial (deed of trust with power of sale) foreclosure. Non-judicial takes ~60 days.",
     "regulatory_reference": "Mo. Rev. Stat. § 443.310"},
    {"state_code": "MO", "state_name": "Missouri", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Mo. Rev. Stat. § 542.402"},

    # =========================================================================
    # MARYLAND
    # =========================================================================
    {"state_code": "MD", "state_name": "Maryland", "category": "licensing",
     "requirement": "Maryland Commissioner of Financial Regulation license required under the Maryland Mortgage Lender Law. NMLS mandatory.",
     "regulatory_reference": "Md. Code Ann., Fin. Inst. § 11-501 et seq."},
    {"state_code": "MD", "state_name": "Maryland", "category": "disclosure",
     "requirement": "Maryland Residential Property Disclosure/Disclaimer Statement required in residential sales.",
     "regulatory_reference": "Md. Code Ann., Real Prop. § 10-702"},
    {"state_code": "MD", "state_name": "Maryland", "category": "disclosure",
     "requirement": "Mortgage loan originator disclosures required at application under Maryland Mortgage Disclosure Act.",
     "regulatory_reference": "Md. Code Ann., Real Prop. § 11-101"},
    {"state_code": "MD", "state_name": "Maryland", "category": "fee_limit",
     "requirement": "Maryland Mortgage Fraud Protection Act limits origination fees on first-time homebuyer loans to 1.5% of loan amount.",
     "regulatory_reference": "Md. Code Ann., Real Prop. § 7-113"},
    {"state_code": "MD", "state_name": "Maryland", "category": "prepayment",
     "requirement": "Prepayment penalties prohibited on variable rate mortgages and certain high-cost loans.",
     "regulatory_reference": "Md. Code Ann., Com. Law § 12-105"},
    {"state_code": "MD", "state_name": "Maryland", "category": "special_rule",
     "requirement": "Maryland requires judicial foreclosure (circuit court). Loss mitigation conference required before final order.",
     "regulatory_reference": "Md. Code Ann., Real Prop. § 7-105.1"},
    {"state_code": "MD", "state_name": "Maryland", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Md. Code Ann., Cts. & Jud. Proc. § 10-402"},

    # =========================================================================
    # WISCONSIN
    # =========================================================================
    {"state_code": "WI", "state_name": "Wisconsin", "category": "licensing",
     "requirement": "Wisconsin Department of Financial Institutions license required under the Wisconsin Mortgage Banking Act. NMLS mandatory.",
     "regulatory_reference": "Wis. Stat. § 224.71 et seq."},
    {"state_code": "WI", "state_name": "Wisconsin", "category": "disclosure",
     "requirement": "Real Estate Condition Report required in residential property sales (1–4 units); seller must complete within 10 days of acceptance.",
     "regulatory_reference": "Wis. Stat. § 709.03"},
    {"state_code": "WI", "state_name": "Wisconsin", "category": "fee_limit",
     "requirement": "Wisconsin high-cost home loan provisions mirror federal HOEPA thresholds. No additional state-specific points and fees cap.",
     "regulatory_reference": "Wis. Stat. § 428.208"},
    {"state_code": "WI", "state_name": "Wisconsin", "category": "prepayment",
     "requirement": "Prepayment permitted on residential mortgages; no state statutory prohibition on prepayment penalties beyond federal rules.",
     "regulatory_reference": "Wis. Stat. § 138.052"},
    {"state_code": "WI", "state_name": "Wisconsin", "category": "special_rule",
     "requirement": "Wisconsin uses judicial foreclosure; borrower has 12-month (or 6-month for abandoned property) right of redemption after sale.",
     "regulatory_reference": "Wis. Stat. § 846.13"},
    {"state_code": "WI", "state_name": "Wisconsin", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Wis. Stat. § 968.31"},

    # =========================================================================
    # REMAINING 31 STATES + DC  (licensing + key disclosure + recording consent)
    # =========================================================================

    # ALABAMA
    {"state_code": "AL", "state_name": "Alabama", "category": "licensing",
     "requirement": "Alabama State Banking Department license required. NMLS registration mandatory.",
     "regulatory_reference": "Ala. Code § 5-25-1 et seq."},
    {"state_code": "AL", "state_name": "Alabama", "category": "disclosure",
     "requirement": "Alabama residential property disclosure recommended; not statutorily mandated statewide but often required by contract.",
     "regulatory_reference": "Ala. Code § 6-5-102"},
    {"state_code": "AL", "state_name": "Alabama", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Ala. Code § 13A-11-30"},

    # ALASKA
    {"state_code": "AK", "state_name": "Alaska", "category": "licensing",
     "requirement": "Alaska Division of Banking and Securities license required. NMLS mandatory.",
     "regulatory_reference": "Alaska Stat. § 06.60.010 et seq."},
    {"state_code": "AK", "state_name": "Alaska", "category": "disclosure",
     "requirement": "Alaska Residential Real Property Transfer Disclosure required for residential sales.",
     "regulatory_reference": "Alaska Stat. § 34.70.010"},
    {"state_code": "AK", "state_name": "Alaska", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Alaska Stat. § 42.20.310"},

    # ARKANSAS
    {"state_code": "AR", "state_name": "Arkansas", "category": "licensing",
     "requirement": "Arkansas Securities Department license required. NMLS registration mandatory.",
     "regulatory_reference": "Ark. Code Ann. § 23-39-501 et seq."},
    {"state_code": "AR", "state_name": "Arkansas", "category": "disclosure",
     "requirement": "Seller property disclosure recommended; no statewide statutory mandate, but common by contract.",
     "regulatory_reference": "Ark. Code Ann. § 17-42-301"},
    {"state_code": "AR", "state_name": "Arkansas", "category": "special_rule",
     "requirement": "Arkansas usury constitution: maximum interest rate is 5% above Federal Reserve discount rate. Exemptions apply to certain institutional lenders.",
     "regulatory_reference": "Ark. Const. Amend. 89"},
    {"state_code": "AR", "state_name": "Arkansas", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Ark. Code Ann. § 5-60-120"},

    # COLORADO
    {"state_code": "CO", "state_name": "Colorado", "category": "licensing",
     "requirement": "Colorado Division of Real Estate or DORA license required. NMLS registration mandatory.",
     "regulatory_reference": "Colo. Rev. Stat. § 12-10-701 et seq."},
    {"state_code": "CO", "state_name": "Colorado", "category": "disclosure",
     "requirement": "Colorado Seller's Property Disclosure required in residential sales.",
     "regulatory_reference": "Colo. Rev. Stat. § 38-35.7-101"},
    {"state_code": "CO", "state_name": "Colorado", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Colo. Rev. Stat. § 18-9-304"},

    # CONNECTICUT
    {"state_code": "CT", "state_name": "Connecticut", "category": "licensing",
     "requirement": "Connecticut Department of Banking license required under the Connecticut Mortgage Act. NMLS mandatory.",
     "regulatory_reference": "Conn. Gen. Stat. § 36a-485 et seq."},
    {"state_code": "CT", "state_name": "Connecticut", "category": "disclosure",
     "requirement": "Connecticut Disclosure of Property Conditions required for residential sales.",
     "regulatory_reference": "Conn. Gen. Stat. § 20-327b"},
    {"state_code": "CT", "state_name": "Connecticut", "category": "special_rule",
     "requirement": "Connecticut anti-predatory lending: high-cost home loan law imposes counseling requirements and prohibits balloon payments in first 7 years.",
     "regulatory_reference": "Conn. Gen. Stat. § 36a-746a"},
    {"state_code": "CT", "state_name": "Connecticut", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Conn. Gen. Stat. § 52-570d"},

    # DELAWARE
    {"state_code": "DE", "state_name": "Delaware", "category": "licensing",
     "requirement": "Delaware Office of the State Bank Commissioner license required. NMLS registration mandatory.",
     "regulatory_reference": "Del. Code Ann. tit. 5, § 2101 et seq."},
    {"state_code": "DE", "state_name": "Delaware", "category": "disclosure",
     "requirement": "Delaware Seller's Disclosure of Real Property Condition required for residential sales.",
     "regulatory_reference": "Del. Code Ann. tit. 6, § 2572"},
    {"state_code": "DE", "state_name": "Delaware", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Del. Code Ann. tit. 11, § 2402"},

    # DISTRICT OF COLUMBIA
    {"state_code": "DC", "state_name": "District of Columbia", "category": "licensing",
     "requirement": "DC Department of Insurance, Securities and Banking license required. NMLS registration mandatory.",
     "regulatory_reference": "D.C. Code § 26-1101 et seq."},
    {"state_code": "DC", "state_name": "District of Columbia", "category": "disclosure",
     "requirement": "DC Seller Disclosure Act: written disclosure required for residential sales of 1–4 units.",
     "regulatory_reference": "D.C. Code § 42-1302"},
    {"state_code": "DC", "state_name": "District of Columbia", "category": "special_rule",
     "requirement": "DC Predatory Lending Amendment Act imposes strict high-cost loan restrictions, mandatory counseling, and borrower protections.",
     "regulatory_reference": "D.C. Code § 26-1151.01 et seq."},
    {"state_code": "DC", "state_name": "District of Columbia", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "D.C. Code § 23-542"},

    # HAWAII
    {"state_code": "HI", "state_name": "Hawaii", "category": "licensing",
     "requirement": "Hawaii Division of Financial Institutions license required. NMLS registration mandatory.",
     "regulatory_reference": "Haw. Rev. Stat. § 454F-1 et seq."},
    {"state_code": "HI", "state_name": "Hawaii", "category": "disclosure",
     "requirement": "Hawaii Seller's Disclosure Statement required. Leasehold vs. fee simple status must be disclosed prominently.",
     "regulatory_reference": "Haw. Rev. Stat. § 508D-4"},
    {"state_code": "HI", "state_name": "Hawaii", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Haw. Rev. Stat. § 803-42"},

    # IDAHO
    {"state_code": "ID", "state_name": "Idaho", "category": "licensing",
     "requirement": "Idaho Department of Finance license required. NMLS registration mandatory.",
     "regulatory_reference": "Idaho Code § 26-3101 et seq."},
    {"state_code": "ID", "state_name": "Idaho", "category": "disclosure",
     "requirement": "Seller Property Condition Disclosure Form required for residential sales in Idaho.",
     "regulatory_reference": "Idaho Code § 55-2501 et seq."},
    {"state_code": "ID", "state_name": "Idaho", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Idaho Code § 18-6702"},

    # IOWA
    {"state_code": "IA", "state_name": "Iowa", "category": "licensing",
     "requirement": "Iowa Division of Banking license required. NMLS registration mandatory.",
     "regulatory_reference": "Iowa Code § 535B.1 et seq."},
    {"state_code": "IA", "state_name": "Iowa", "category": "disclosure",
     "requirement": "Iowa Residential Property Seller Disclosure Statement required for residential sales.",
     "regulatory_reference": "Iowa Code § 558A.4"},
    {"state_code": "IA", "state_name": "Iowa", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Iowa Code § 808B.2"},

    # KANSAS
    {"state_code": "KS", "state_name": "Kansas", "category": "licensing",
     "requirement": "Kansas Office of the State Bank Commissioner license required. NMLS mandatory.",
     "regulatory_reference": "Kan. Stat. Ann. § 9-2201 et seq."},
    {"state_code": "KS", "state_name": "Kansas", "category": "disclosure",
     "requirement": "Kansas Seller's Disclosure of Property Condition required for residential sales.",
     "regulatory_reference": "Kan. Stat. Ann. § 58-30,105"},
    {"state_code": "KS", "state_name": "Kansas", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Kan. Stat. Ann. § 21-6101"},

    # KENTUCKY
    {"state_code": "KY", "state_name": "Kentucky", "category": "licensing",
     "requirement": "Kentucky Department of Financial Institutions license required. NMLS registration mandatory.",
     "regulatory_reference": "Ky. Rev. Stat. Ann. § 286.8-010 et seq."},
    {"state_code": "KY", "state_name": "Kentucky", "category": "disclosure",
     "requirement": "Kentucky Seller's Disclosure of Property Condition required for residential sales.",
     "regulatory_reference": "Ky. Rev. Stat. Ann. § 324.360"},
    {"state_code": "KY", "state_name": "Kentucky", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Ky. Rev. Stat. Ann. § 526.010"},

    # LOUISIANA
    {"state_code": "LA", "state_name": "Louisiana", "category": "licensing",
     "requirement": "Louisiana Office of Financial Institutions license required. NMLS registration mandatory.",
     "regulatory_reference": "La. Rev. Stat. Ann. § 6:1082 et seq."},
    {"state_code": "LA", "state_name": "Louisiana", "category": "disclosure",
     "requirement": "Louisiana Property Disclosure Document required for residential sales of 1–4 units.",
     "regulatory_reference": "La. Rev. Stat. Ann. § 9:3196 et seq."},
    {"state_code": "LA", "state_name": "Louisiana", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "La. Rev. Stat. Ann. § 15:1303"},

    # MAINE
    {"state_code": "ME", "state_name": "Maine", "category": "licensing",
     "requirement": "Maine Bureau of Consumer Credit Protection license required. NMLS registration mandatory.",
     "regulatory_reference": "Me. Rev. Stat. tit. 9-A, § 6-201 et seq."},
    {"state_code": "ME", "state_name": "Maine", "category": "disclosure",
     "requirement": "Maine Seller Disclosure of Property Condition required for residential real estate transfers.",
     "regulatory_reference": "Me. Rev. Stat. tit. 33, § 173"},
    {"state_code": "ME", "state_name": "Maine", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Me. Rev. Stat. tit. 15, § 710"},

    # MINNESOTA
    {"state_code": "MN", "state_name": "Minnesota", "category": "licensing",
     "requirement": "Minnesota Department of Commerce Residential Mortgage Originator license required. NMLS mandatory.",
     "regulatory_reference": "Minn. Stat. § 58A.04 et seq."},
    {"state_code": "MN", "state_name": "Minnesota", "category": "disclosure",
     "requirement": "Minnesota Seller's Property Disclosure required for residential property sales.",
     "regulatory_reference": "Minn. Stat. § 513.55"},
    {"state_code": "MN", "state_name": "Minnesota", "category": "special_rule",
     "requirement": "Minnesota Residential Mortgage Originator and Servicer Licensing Act imposes specific borrower notice requirements for servicing transfers.",
     "regulatory_reference": "Minn. Stat. § 58A.14"},
    {"state_code": "MN", "state_name": "Minnesota", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Minn. Stat. § 626A.02"},

    # MISSISSIPPI
    {"state_code": "MS", "state_name": "Mississippi", "category": "licensing",
     "requirement": "Mississippi Department of Banking and Consumer Finance license required. NMLS mandatory.",
     "regulatory_reference": "Miss. Code Ann. § 81-18-1 et seq."},
    {"state_code": "MS", "state_name": "Mississippi", "category": "disclosure",
     "requirement": "Seller disclosure of property condition required; statutory form promulgated by Mississippi Real Estate Commission.",
     "regulatory_reference": "Miss. Code Ann. § 89-1-501 et seq."},
    {"state_code": "MS", "state_name": "Mississippi", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Miss. Code Ann. § 41-29-531"},

    # MONTANA
    {"state_code": "MT", "state_name": "Montana", "category": "licensing",
     "requirement": "Montana Division of Banking and Financial Institutions license required. NMLS registration mandatory.",
     "regulatory_reference": "Mont. Code Ann. § 32-9-101 et seq."},
    {"state_code": "MT", "state_name": "Montana", "category": "disclosure",
     "requirement": "Montana Seller Disclosure Act requires written disclosure of known defects in residential property.",
     "regulatory_reference": "Mont. Code Ann. § 37-51-209"},
    {"state_code": "MT", "state_name": "Montana", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Mont. Code Ann. § 45-8-213"},

    # NEBRASKA
    {"state_code": "NE", "state_name": "Nebraska", "category": "licensing",
     "requirement": "Nebraska Department of Banking and Finance license required. NMLS mandatory.",
     "regulatory_reference": "Neb. Rev. Stat. § 45-725 et seq."},
    {"state_code": "NE", "state_name": "Nebraska", "category": "disclosure",
     "requirement": "Nebraska Seller Property Condition Disclosure Statement required for residential sales.",
     "regulatory_reference": "Neb. Rev. Stat. § 76-2,120"},
    {"state_code": "NE", "state_name": "Nebraska", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Neb. Rev. Stat. § 86-290"},

    # NEVADA
    {"state_code": "NV", "state_name": "Nevada", "category": "licensing",
     "requirement": "Nevada Division of Mortgage Lending license required. NMLS registration mandatory.",
     "regulatory_reference": "Nev. Rev. Stat. § 645B.010 et seq."},
    {"state_code": "NV", "state_name": "Nevada", "category": "disclosure",
     "requirement": "Nevada Seller's Real Property Disclosure Form (SRPD) required in residential sales.",
     "regulatory_reference": "Nev. Rev. Stat. § 113.130"},
    {"state_code": "NV", "state_name": "Nevada", "category": "special_rule",
     "requirement": "Nevada is an anti-deficiency state for purchase-money mortgages on single-family residences; lender cannot pursue deficiency after foreclosure.",
     "regulatory_reference": "Nev. Rev. Stat. § 40.455"},
    {"state_code": "NV", "state_name": "Nevada", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Nev. Rev. Stat. § 200.620"},

    # NEW HAMPSHIRE
    {"state_code": "NH", "state_name": "New Hampshire", "category": "licensing",
     "requirement": "New Hampshire Banking Department license required. NMLS registration mandatory.",
     "regulatory_reference": "N.H. Rev. Stat. Ann. § 397-A:1 et seq."},
    {"state_code": "NH", "state_name": "New Hampshire", "category": "disclosure",
     "requirement": "Seller Property Disclosure Form required for residential sales; covers structural, mechanical, and environmental conditions.",
     "regulatory_reference": "N.H. Rev. Stat. Ann. § 477:4-d"},
    {"state_code": "NH", "state_name": "New Hampshire", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "N.H. Rev. Stat. Ann. § 570-A:2"},

    # NEW MEXICO
    {"state_code": "NM", "state_name": "New Mexico", "category": "licensing",
     "requirement": "New Mexico Financial Institutions Division license required. NMLS mandatory.",
     "regulatory_reference": "N.M. Stat. Ann. § 58-21A-1 et seq."},
    {"state_code": "NM", "state_name": "New Mexico", "category": "disclosure",
     "requirement": "New Mexico Seller Property Disclosure Statement required for residential sales.",
     "regulatory_reference": "N.M. Stat. Ann. § 47-13-3"},
    {"state_code": "NM", "state_name": "New Mexico", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "N.M. Stat. Ann. § 30-12-1"},

    # NORTH DAKOTA
    {"state_code": "ND", "state_name": "North Dakota", "category": "licensing",
     "requirement": "North Dakota Department of Financial Institutions license required. NMLS mandatory.",
     "regulatory_reference": "N.D. Cent. Code § 13-11-01 et seq."},
    {"state_code": "ND", "state_name": "North Dakota", "category": "disclosure",
     "requirement": "North Dakota Seller Disclosure of Property Condition required for residential real estate sales.",
     "regulatory_reference": "N.D. Cent. Code § 47-10-02.3"},
    {"state_code": "ND", "state_name": "North Dakota", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "N.D. Cent. Code § 12.1-15-02"},

    # OKLAHOMA
    {"state_code": "OK", "state_name": "Oklahoma", "category": "licensing",
     "requirement": "Oklahoma Department of Consumer Credit license required. NMLS registration mandatory.",
     "regulatory_reference": "Okla. Stat. tit. 59, § 2095 et seq."},
    {"state_code": "OK", "state_name": "Oklahoma", "category": "disclosure",
     "requirement": "Oklahoma Residential Property Condition Disclosure required for residential sales.",
     "regulatory_reference": "Okla. Stat. tit. 60, § 831 et seq."},
    {"state_code": "OK", "state_name": "Oklahoma", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Okla. Stat. tit. 13, § 176.4"},

    # OREGON
    {"state_code": "OR", "state_name": "Oregon", "category": "licensing",
     "requirement": "Oregon Division of Financial Regulation license required. NMLS mandatory.",
     "regulatory_reference": "Or. Rev. Stat. § 86A.100 et seq."},
    {"state_code": "OR", "state_name": "Oregon", "category": "disclosure",
     "requirement": "Oregon Seller's Property Disclosure Statement required for residential sales of 1–4 units.",
     "regulatory_reference": "Or. Rev. Stat. § 105.465"},
    {"state_code": "OR", "state_name": "Oregon", "category": "special_rule",
     "requirement": "Oregon Home Loan Protection Act (OHLPA): high-cost home loan restrictions including mandatory counseling.",
     "regulatory_reference": "Or. Rev. Stat. § 86A.159"},
    {"state_code": "OR", "state_name": "Oregon", "category": "recording_consent",
     "requirement": "Two-party (all-party) consent required for recording telephone calls.",
     "regulatory_reference": "Or. Rev. Stat. § 165.540"},

    # RHODE ISLAND
    {"state_code": "RI", "state_name": "Rhode Island", "category": "licensing",
     "requirement": "Rhode Island Department of Business Regulation license required. NMLS registration mandatory.",
     "regulatory_reference": "R.I. Gen. Laws § 19-14.1-1 et seq."},
    {"state_code": "RI", "state_name": "Rhode Island", "category": "disclosure",
     "requirement": "Rhode Island mandatory disclosure of high-cost home loan terms; additional protections for subprime borrowers.",
     "regulatory_reference": "R.I. Gen. Laws § 34-25.2-6"},
    {"state_code": "RI", "state_name": "Rhode Island", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "R.I. Gen. Laws § 11-35-21"},

    # SOUTH CAROLINA
    {"state_code": "SC", "state_name": "South Carolina", "category": "licensing",
     "requirement": "South Carolina Department of Consumer Affairs license required. NMLS registration mandatory.",
     "regulatory_reference": "S.C. Code Ann. § 37-22-110 et seq."},
    {"state_code": "SC", "state_name": "South Carolina", "category": "disclosure",
     "requirement": "South Carolina Residential Property Condition Disclosure Statement required for residential sales.",
     "regulatory_reference": "S.C. Code Ann. § 27-50-10 et seq."},
    {"state_code": "SC", "state_name": "South Carolina", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "S.C. Code Ann. § 17-30-30"},

    # SOUTH DAKOTA
    {"state_code": "SD", "state_name": "South Dakota", "category": "licensing",
     "requirement": "South Dakota Division of Banking license required. NMLS registration mandatory.",
     "regulatory_reference": "S.D. Codified Laws § 36-21A-57 et seq."},
    {"state_code": "SD", "state_name": "South Dakota", "category": "disclosure",
     "requirement": "Seller Property Condition Disclosure required; statutory form required for residential property sales.",
     "regulatory_reference": "S.D. Codified Laws § 43-4-44"},
    {"state_code": "SD", "state_name": "South Dakota", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "S.D. Codified Laws § 23A-35A-20"},

    # UTAH
    {"state_code": "UT", "state_name": "Utah", "category": "licensing",
     "requirement": "Utah Department of Financial Institutions license required. NMLS registration mandatory.",
     "regulatory_reference": "Utah Code Ann. § 61-2c-101 et seq."},
    {"state_code": "UT", "state_name": "Utah", "category": "disclosure",
     "requirement": "Utah Seller Property Condition Disclosure required for residential sales of 1–5 units.",
     "regulatory_reference": "Utah Code Ann. § 57-27-101 et seq."},
    {"state_code": "UT", "state_name": "Utah", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Utah Code Ann. § 77-23a-4"},

    # VERMONT
    {"state_code": "VT", "state_name": "Vermont", "category": "licensing",
     "requirement": "Vermont Department of Financial Regulation license required. NMLS registration mandatory.",
     "regulatory_reference": "Vt. Stat. Ann. tit. 8, § 2200 et seq."},
    {"state_code": "VT", "state_name": "Vermont", "category": "disclosure",
     "requirement": "Vermont Seller's Property Disclosure Form required; covers structural, mechanical, environmental, and title issues.",
     "regulatory_reference": "Vt. Stat. Ann. tit. 27, § 834"},
    {"state_code": "VT", "state_name": "Vermont", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Vt. Stat. Ann. tit. 13, § 4601"},

    # WEST VIRGINIA
    {"state_code": "WV", "state_name": "West Virginia", "category": "licensing",
     "requirement": "West Virginia Division of Financial Institutions license required. NMLS mandatory.",
     "regulatory_reference": "W. Va. Code § 31-17-1 et seq."},
    {"state_code": "WV", "state_name": "West Virginia", "category": "disclosure",
     "requirement": "West Virginia Residential Property Disclosure required; seller must disclose known defects to buyer.",
     "regulatory_reference": "W. Va. Code § 36B-4-102"},
    {"state_code": "WV", "state_name": "West Virginia", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "W. Va. Code § 62-1D-3"},

    # WYOMING
    {"state_code": "WY", "state_name": "Wyoming", "category": "licensing",
     "requirement": "Wyoming Division of Banking license required. NMLS registration mandatory.",
     "regulatory_reference": "Wyo. Stat. Ann. § 40-23-101 et seq."},
    {"state_code": "WY", "state_name": "Wyoming", "category": "disclosure",
     "requirement": "Seller Property Disclosure Form required for residential sales; statutory form mandated.",
     "regulatory_reference": "Wyo. Stat. Ann. § 33-28-303"},
    {"state_code": "WY", "state_name": "Wyoming", "category": "recording_consent",
     "requirement": "One-party consent for recording telephone calls.",
     "regulatory_reference": "Wyo. Stat. Ann. § 7-3-702"},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_state_disclosures(db) -> int:
    """
    Seed the state_disclosures table.

    Skips seeding if any rows already exist.
    Returns the number of rows inserted.
    """
    from database.models.state_disclosure import StateDisclosure

    # Ensure table exists
    from database import Base
    from db import engine as _engine
    StateDisclosure.__table__.create(_engine, checkfirst=True)

    existing = db.query(StateDisclosure).count()
    if existing > 0:
        logger.info("state_disclosures already seeded (%d rows), skipping.", existing)
        return 0

    rows = [StateDisclosure(**entry) for entry in _DISCLOSURES]
    db.bulk_save_objects(rows)
    logger.info("Seeded %d state disclosure entries.", len(rows))
    return len(rows)


def clear_state_disclosures(db) -> int:
    """Delete all rows from state_disclosures. Returns number of deleted rows."""
    from database.models.state_disclosure import StateDisclosure
    deleted = db.query(StateDisclosure).delete()
    logger.info("Cleared %d state disclosure rows.", deleted)
    return deleted


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    from db import SessionLocal
    db = SessionLocal()
    try:
        count = seed_state_disclosures(db)
        db.commit()
        print(f"Done! Inserted {count} rows.")
    finally:
        db.close()
