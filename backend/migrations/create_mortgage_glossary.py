"""
Migration: Create mortgage glossary table for AI Orchestrator
This provides the AI with domain-specific mortgage terminology knowledge.
"""

from sqlalchemy import text

def run_migration(db):
    """Create mortgage glossary table and seed with 100 core terms"""

    # Create table
    db.execute(text("""
        DROP TABLE IF EXISTS mortgage_glossary;

        CREATE TABLE mortgage_glossary (
          id BIGSERIAL PRIMARY KEY,
          term TEXT NOT NULL,
          definition TEXT NOT NULL,
          category TEXT,
          subcategory TEXT,
          synonyms TEXT[] DEFAULT '{}',
          related_terms TEXT[] DEFAULT '{}',
          ai_usage TEXT,
          workflow_usage TEXT,
          compliance_tags TEXT[] DEFAULT '{}',
          last_updated TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX idx_glossary_term ON mortgage_glossary(term);
        CREATE INDEX idx_glossary_category ON mortgage_glossary(category);
        CREATE INDEX idx_glossary_term_search ON mortgage_glossary USING gin(to_tsvector('english', term || ' ' || definition));
    """))

    # Seed data - Core mortgage terms
    terms = [
        # Loan Purpose & Structure
        ('Purchase Loan', 'A mortgage used to finance the acquisition of real property, where the loan proceeds are used to buy a home or other real estate.', 'Origination', 'Loan Purpose', '{"Purchase","Home Purchase"}', '{"Refinance","Cash-Out Refinance","Rate-and-Term Refinance"}', 'Helps classify scenarios where the borrower is acquiring a new property; AI uses this to set correct eligibility and disclosure logic.', 'Drives product selection, pricing, disclosures, and workflow branching for purchase vs. refinance.', '{"RESPA","TILA","TRID"}'),

        ('Rate-and-Term Refinance', 'A refinance transaction where the primary purpose is to change the interest rate, loan term, or both, without taking significant cash out.', 'Origination', 'Loan Purpose', '{"R/T Refinance","No-Cash-Out Refinance"}', '{"Cash-Out Refinance","Limited Cash-Out Refinance","Purchase Loan"}', 'Signals reduced risk compared to cash-out; used in pricing, eligibility, and risk scoring models.', 'Routes file to appropriate refinance workflow, payoff verification, and new LE/CD generation.', '{"RESPA","TILA","TRID"}'),

        ('Cash-Out Refinance', 'A refinance in which the borrower receives cash at closing by borrowing more than the existing liens and allowable closing costs.', 'Origination', 'Loan Purpose', '{"Cash-Out"}', '{"Rate-and-Term Refinance","Seasoning","CLTV"}', 'AI uses this to check seasoning, LTV limits, cash-out caps, and investor-specific rules.', 'Triggers additional compliance checks, net proceeds calculations, and cash-out eligibility validation.', '{"GSE","QM/ATR","TRID"}'),

        ('Limited Cash-Out Refinance', 'A refinance where the borrower may receive a small, limited amount of cash back at closing, usually to cover minor expenses or prepaid items, within investor-defined limits.', 'Origination', 'Loan Purpose', '{"Limited Cash-Out","No-Cash-Out"}', '{"Rate-and-Term Refinance","Cash-Out Refinance"}', 'Used to distinguish between true cash-out and limited cash-back scenarios for pricing and eligibility.', 'Enforces maximum cash-back thresholds and documentation of use of funds.', '{"GSE","TRID"}'),

        ('Construction-to-Permanent Loan', 'A single loan that finances both the construction phase and the permanent mortgage, typically with a conversion at completion of construction.', 'Origination', 'Loan Structure', '{"C-to-P","Construction Perm","One-Time Close"}', '{"Construction Loan","Permanent Loan"}', 'AI uses this to align timelines, draw schedules, and conversion terms for underwriting and disclosures.', 'Routes loan through construction workflows, draw management, and conversion documentation at completion.', '{"TRID"}'),

        # Key Risk Ratios & Metrics
        ('Loan-to-Value Ratio (LTV)', 'The ratio of the loan amount to the property''s appraised value or purchase price, whichever is less, expressed as a percentage.', 'Underwriting', 'Risk Metrics', '{"LTV"}', '{"CLTV","HCLTV"}', 'Core input to eligibility, pricing, mortgage insurance, and Rate Lock Intelligence risk scoring.', 'Drives MI requirements, pricing adjustments, and product eligibility checks.', '{"GSE","QM/ATR"}'),

        ('Combined Loan-to-Value Ratio (CLTV)', 'The ratio of all loans secured by the property (first and subordinate liens) to the property value.', 'Underwriting', 'Risk Metrics', '{"CLTV"}', '{"LTV","HCLTV"}', 'AI uses CLTV when subordinated liens are present to evaluate overall leverage and investor limits.', 'Triggers subordinate financing review and overlays for aggregate lien exposure.', '{"GSE"}'),

        ('Home Equity Combined Loan-to-Value (HCLTV)', 'A ratio that includes the full amount of any home equity line of credit, whether drawn or undrawn, plus all other liens divided by property value.', 'Underwriting', 'Risk Metrics', '{"HCLTV"}', '{"CLTV","LTV","HELOC"}', 'Used by AI to apply more conservative risk treatment for HELOCs with unused capacity.', 'Impacts HELOC eligibility, pricing, and investor-specific exposure limits.', '{"GSE"}'),

        ('Debt-to-Income Ratio (DTI)', 'The percentage of a borrower''s gross monthly income that goes toward monthly debt obligations, including housing and other recurring debts.', 'Underwriting', 'Risk Metrics', '{"DTI"}', '{"Front-End DTI","Back-End DTI","Residual Income"}', 'Central to AUS decisions and manual underwriting risk scoring.', 'Determines approval thresholds, need for compensating factors, and potential product downgrades.', '{"QM/ATR"}'),

        ('Front-End DTI', 'The ratio of proposed housing expense (PITI and applicable HOA dues) to gross monthly income.', 'Underwriting', 'Risk Metrics', '{"Housing Ratio"}', '{"Back-End DTI","DTI"}', 'AI references this for affordability analysis and stress testing payment shock.', 'Used in product suitability checks and MI or DPA program eligibility.', '{"QM/ATR"}'),

        # Income & Employment
        ('W-2 Income', 'Income earned from employment where the borrower receives IRS Form W-2, typically including base pay and possibly overtime, bonus, or commission.', 'Underwriting', 'Income Type', '{"W2 Income","Wage Income"}', '{"Hourly Income","Salary Income","Bonus Income","Overtime Income"}', 'Used to determine documentation set (VOE, paystubs, W-2s) and income calculation logic.', 'Routes to standard income calc workflow and VOE requirements.', '{"GSE","FHA"}'),

        ('Self-Employment Income', 'Income derived from a borrower''s ownership interest in a business, typically evidenced by tax returns and business financial statements.', 'Underwriting', 'Income Type', '{"Self-Employed Income","SE Income"}', '{"Schedule C","K-1","Partnership Income"}', 'AI applies business stability checks, trending analysis, and add-back rules.', 'Triggers tax return analysis tasks, business liquidity review, and additional documentation.', '{"GSE","FHA"}'),

        ('Overtime Income', 'Income earned beyond the standard work schedule, often variable and subject to averaging over a defined historical period.', 'Underwriting', 'Income Type', '{"OT Income"}', '{"Bonus Income","Commission Income","Variable Income"}', 'AI evaluates history and likelihood of continuance before including in qualifying income.', 'Requires history documentation, employer confirmation, and trending analysis.', '{"GSE"}'),

        ('Bonus Income', 'Additional compensation paid to a borrower beyond base salary, typically discretionary or performance-based.', 'Underwriting', 'Income Type', '{"Incentive Pay","Performance Bonus"}', '{"Overtime Income","Commission Income"}', 'AI checks consistency, history, and likelihood of continuance for use in qualifying.', 'Routes to variable income policy checks and averaging calculations.', '{"GSE"}'),

        ('Commission Income', 'Compensation based on a percentage of sales or performance measures, often variable and requiring multi-year history.', 'Underwriting', 'Income Type', '{"Commission"}', '{"Bonus Income","Overtime Income","Self-Employment Income"}', 'Used in risk assessment of income stability and may trigger additional documentation.', 'Requires tax returns and robust verification under many agency guidelines.', '{"GSE"}'),

        # Credit & Liabilities
        ('Tri-Merge Credit Report', 'A credit report that consolidates data from all three major credit bureaus: Experian, Equifax, and TransUnion.', 'Credit', 'Documentation', '{"Tri-Merge","Three-Bureau Report"}', '{"Credit Score","Credit Pull"}', 'Provides unified view of tradelines, inquiries, and scores for underwriting.', 'Initiates credit review, liability verification, and dispute resolution workflows.', '{"FCRA"}'),

        ('Credit Score', 'A numerical representation of a consumer''s credit risk based on credit history and other factors.', 'Credit', 'Risk Assessment', '{"FICO Score","Score"}', '{"Tri-Merge Credit Report","Risk-Based Pricing"}', 'Feeds pricing, eligibility, and decision matrices for Rate Lock Intelligence.', 'Drives LLPAs, MI pricing, and overlay rules.', '{"FCRA"}'),

        ('Hard Credit Pull', 'A full credit inquiry that may impact a borrower''s credit score and is visible to other creditors.', 'Credit', 'Inquiries', '{"Hard Pull","Hard Inquiry"}', '{"Soft Pull","Tri-Merge Credit Report"}', 'AI uses this to determine when full tri-merge data is available versus pre-qualification only.', 'Controls consent requirements and re-pull strategies throughout the pipeline.', '{"FCRA"}'),

        ('Soft Credit Pull', 'A credit inquiry that does not impact the borrower''s credit score and is often used for pre-qualification.', 'Credit', 'Inquiries', '{"Soft Pull","Soft Inquiry"}', '{"Hard Credit Pull"}', 'Supports pre-qualification workflows and lead scoring without full underwriting exposure.', 'Initiates limited credit evaluation and marketing follow-up logic.', '{"FCRA"}'),

        ('Debt Consolidation', 'The use of a new mortgage or refinance to pay off multiple existing debts, consolidating them into one loan.', 'Origination', 'Loan Purpose', '{"Consolidation"}', '{"Cash-Out Refinance"}', 'AI identifies debt consolidation scenarios as potentially improved cash flow but with cash-out rules.', 'Requires payoff verification, consumer benefit analysis, and appropriate disclosures.', '{"UDAAP","TRID"}'),

        # Collateral & Appraisal
        ('Appraisal', 'An independent, professional opinion of the market value of a property, typically required for mortgage lending decisions.', 'Collateral', 'Valuation', '{"Real Estate Appraisal"}', '{"AVM","Hybrid Appraisal","1004 Form"}', 'AI uses this to confirm collateral adequacy and compare to AVMs and CU risk flags.', 'Triggers review of comparables, conditions, and appraisal-based conditions.', '{"AIR","GSE"}'),

        ('Automated Valuation Model (AVM)', 'A computer-based model that estimates property value using statistical techniques and market data.', 'Collateral', 'Valuation Technology', '{"AVM"}', '{"Appraisal","Hybrid Appraisal"}', 'Supports instant property valuation for pre-qual, risk monitoring, and waiver decisions.', 'Used in collateral risk checks, portfolio monitoring, and certain streamlined products.', '{"GSE"}'),

        ('Hybrid Appraisal', 'An appraisal that combines property data collected by a third party with a desktop valuation performed by a licensed appraiser.', 'Collateral', 'Valuation', '{"Desktop Hybrid"}', '{"Desktop Appraisal","Full Appraisal"}', 'AI determines when hybrid formats meet agency or investor guidelines to reduce cycle time.', 'Used to shorten appraisal timelines while managing collateral risk.', '{"GSE"}'),

        ('Collateral Underwriter (CU) Score', 'A risk score from Fannie Mae that evaluates appraisal quality and collateral risk.', 'Collateral', 'Risk Metrics', '{"CU Score"}', '{"Appraisal Review"}', 'AI factors CU score into appraisal scrutiny level and potential conditions.', 'Drives additional appraisal review steps or reconsideration of value requests.', '{"GSE"}'),

        ('Property Inspection Waiver (PIW)', 'An offer from an agency to waive the traditional appraisal requirement based on automated data and risk models.', 'Collateral', 'Waiver', '{"PIW","Appraisal Waiver"}', '{"Appraisal","AVM"}', 'AI checks eligibility for PIWs to accelerate approvals and reduce borrower costs.', 'Routes loans down simplified collateral documentation workflows when allowed.', '{"GSE"}'),

        # Disclosures & Compliance
        ('Loan Estimate (LE)', 'A standardized disclosure that provides a good faith estimate of loan terms and closing costs, required under TRID.', 'Compliance', 'Disclosures', '{"LE"}', '{"Closing Disclosure","TRID"}', 'AI ensures LE timing and accuracy in relation to application date and change-of-circumstance rules.', 'Triggers disclosure workflows, timing checks, and re-disclosure when terms change.', '{"TRID","TILA","RESPA"}'),

        ('Closing Disclosure (CD)', 'A standardized disclosure that provides the final details of the loan terms and costs, including cash to close, delivered prior to consummation.', 'Compliance', 'Disclosures', '{"CD"}', '{"Loan Estimate","TRID"}', 'AI validates fee tolerances, timing, and comparison to the LE.', 'Ensures 3-business-day rule, reconciles fees, and clears for closing.', '{"TRID","TILA","RESPA"}'),

        ('Change of Circumstance', 'A defined event that permits revised Loan Estimates or Closing Disclosures when certain loan or borrower information changes.', 'Compliance', 'Disclosures', '{"COC"}', '{"Loan Estimate","Closing Disclosure"}', 'AI flags potential COCs when loan terms or fees shift significantly.', 'Triggers re-disclosure analysis and documentation of the reason for change.', '{"TRID"}'),

        ('Right of Rescission', 'A borrower''s right, on certain refinance and home equity transactions secured by a primary residence, to cancel the loan within a specified period after closing.', 'Compliance', 'Consumer Protection', '{"Rescission Period"}', '{"Owner-Occupied Refinance","Closing Date"}', 'AI ensures funding timelines respect rescission requirements.', 'Adjusts funding dates and informs closing and post-closing workflows.', '{"TILA"}'),

        ('Adverse Action Notice', 'A required written notice to a consumer when credit is denied or offered on less favorable terms based on information in a credit report.', 'Compliance', 'Credit Decisioning', '{"AAN"}', '{"Decline","Counteroffer"}', 'AI identifies when adverse action has occurred and triggers required notifications.', 'Ensures compliant timing and content of notices for denied or withdrawn applications.', '{"ECOA","FCRA"}'),

        # Loan Processing & Documentation
        ('Title Commitment', 'A preliminary report from a title company indicating the condition of title and requirements to issue a final title policy.', 'Processing', 'Title', '{"Title Binder","Prelim Title"}', '{"Title Policy","Closing"}', 'AI uses this to check for liens, judgments, and required clear-to-close conditions.', 'Triggers title clearance workflows, including payoff demands and lien releases.', '{"State Law"}'),

        ('Title Insurance', 'An insurance policy that protects lenders and/or owners against losses from defects in title.', 'Processing', 'Title', '{"Lender''s Title Policy","Owner''s Title Policy"}', '{"Title Commitment"}', 'AI categorizes title premiums and ensures disclosures and cost calculations are correct.', 'Ensures proper coverage type, endorsements, and fee itemization on LE/CD.', '{"State Law"}'),

        ('Subordination Agreement', 'A document in which a lienholder agrees to remain in a junior position behind a new or existing lien.', 'Processing', 'Lien Position', '{"Subordination"}', '{"CLTV","Refinance"}', 'AI checks when subordinations are necessary in refinance transactions.', 'Triggers coordination with junior lienholders and condition tracking.', '{"GSE"}'),

        ('Verification of Employment (VOE)', 'A process of confirming a borrower''s employment status, position, and income with their employer.', 'Processing', 'Verification', '{"VOE"}', '{"Income Verification","Employment Verification"}', 'AI determines VOE timing requirements (initial and final) based on guidelines.', 'Schedules and tracks VOE completion as critical underwriting conditions.', '{"GSE","FHA"}'),

        ('Verification of Assets (VOA)', 'A process or document that confirms the existence and ownership of a borrower''s financial assets.', 'Processing', 'Verification', '{"VOA"}', '{"Bank Statements","Asset Documentation"}', 'AI validates sourcing and seasoning of funds for down payment and reserves.', 'Triggers asset documentation collection and large deposit explanation workflows.', '{"GSE"}'),

        # Closing & Funding
        ('Wet Funding', 'A closing where loan documents are signed and funds are disbursed at or very near the time of signing.', 'Closing', 'Funding', '{"Table Funding"}', '{"Dry Funding"}', 'AI considers state-specific funding practices that impact scheduling and disclosures.', 'Determines when to schedule funding wires and coordinate with closing agents.', '{"State Law"}'),

        ('Dry Funding', 'A closing where documents are signed but funds are disbursed only after conditions are reviewed and cleared by the lender.', 'Closing', 'Funding', '{"Dry Closing"}', '{"Wet Funding"}', 'AI anticipates additional post-closing review steps and timelines.', 'Sets expectations for funding delays and post-closing condition clearance.', '{"State Law"}'),

        ('Funding Number', 'A unique identifier assigned to a loan at the time funds are disbursed.', 'Closing', 'Funding', '{"Wire Reference"}', '{"Funding","Closing"}', 'AI references funding numbers for reconciliations and post-closing tracking.', 'Used in audit trails, accounting, and wire tracking workflows.', '{"Internal Control"}'),

        ('Cash to Close', 'The amount of money a borrower must bring to closing, including down payment, closing costs, and prepaid items, minus credits and adjustments.', 'Closing', 'Settlement', '{"CTC Amount"}', '{"Closing Disclosure","Down Payment"}', 'AI validates that cash-to-close remains accurate and sourced prior to closing.', 'Drives final verification of funds and closing coordination.', '{"TRID"}'),

        ('Seller Concessions', 'Costs paid by the property seller on behalf of the buyer, including contributions toward closing costs or prepaid items.', 'Closing', 'Credits', '{"Interested Party Contributions","IPC"}', '{"Closing Costs","Cash to Close"}', 'AI enforces limits on concessions by product and occupancy.', 'Ensures credits are properly reflected and do not exceed agency caps.', '{"GSE"}'),

        # Servicing Basics
        ('Mortgage Servicing', 'The administration of a mortgage loan after closing, including payment collection, escrow management, customer service, and default management.', 'Servicing', 'General', '{"Servicing"}', '{"MSR","Payment Processing"}', 'AI distinguishes origination vs. servicing workflows and responsibilities.', 'Feeds post-closing transfer decisions and borrower communication strategies.', '{"CFPB"}'),

        ('Servicer', 'The entity responsible for managing mortgage loan payments, escrow accounts, and customer interactions on behalf of the note holder or investor.', 'Servicing', 'General', '{"Loan Servicer"}', '{"MSR","Subservicer"}', 'AI routes servicing-related inquiries and determines who owns the borrower relationship.', 'Supports servicing transfer notices and contact information management.', '{"CFPB"}'),

        ('Mortgage Servicing Rights (MSR)', 'The contractual right to service a mortgage loan and receive servicing income, separated from the ownership of the loan itself.', 'Servicing', 'MSR', '{"MSR"}', '{"Servicer","Subservicer"}', 'AI uses MSR status for portfolio analysis, recapture strategies, and revenue models.', 'Informs decisions about retain vs. release at loan sale.', '{"GAAP"}'),

        ('Escrow Account', 'An account managed by the servicer to collect and disburse funds for property taxes, homeowners insurance, and other required items.', 'Servicing', 'Escrow', '{"Impound Account"}', '{"Escrow Analysis","Shortage","Surplus"}', 'AI evaluates escrow requirements and analyzes payment changes annually.', 'Triggers escrow setup, analysis, and borrower notices.', '{"RESPA"}'),

        ('Escrow Analysis', 'A periodic review of the escrow account to ensure sufficient funds to cover projected disbursements, resulting in potential payment adjustments.', 'Servicing', 'Escrow', '{"Annual Escrow Analysis"}', '{"Escrow Account","Shortage","Surplus"}', 'AI predicts payment changes and prepares communication for borrowers.', 'Generates required statements and adjustments to the monthly payment.', '{"RESPA"}'),

        # Default & Loss Mitigation
        ('Delinquency', 'The state of a loan when scheduled payments have not been made by the due date, typically measured in days past due (30, 60, 90, etc.).', 'Servicing', 'Default', '{"Past Due"}', '{"Loss Mitigation","Foreclosure"}', 'AI monitors delinquency buckets and triggers outreach or loss mitigation workflows.', 'Drives collections efforts, regulatory reporting, and risk analytics.', '{"CFPB"}'),

        ('Loss Mitigation', 'Strategies and programs used by servicers to help borrowers avoid foreclosure, such as repayment plans, modifications, and forbearance.', 'Servicing', 'Default', '{"Home Retention","Workout Options"}', '{"Modification","Forbearance"}', 'AI helps identify eligible borrowers and recommend appropriate workout solutions.', 'Initiates review of income, hardship, and investor guidelines for relief options.', '{"CFPB","HUD"}'),

        ('Forbearance', 'A temporary reduction or suspension of mortgage payments granted due to borrower hardship.', 'Servicing', 'Default', '{"Payment Forbearance"}', '{"Loss Mitigation","Delinquency"}', 'AI evaluates hardship claims and applicable investor or program rules.', 'Tracks forbearance periods and transition to post-forbearance options.', '{"CFPB","CARES Act"}'),

        ('Loan Modification', 'A permanent change in one or more terms of the loan to make payments more affordable or sustainable for the borrower.', 'Servicing', 'Default', '{"Modification","Mod"}', '{"Loss Mitigation","Forbearance"}', 'AI designs modification scenarios based on investor rules and affordability.', 'Calculates new payment, term, and rate options and generates approval packages.', '{"CFPB","HUD"}'),

        ('Foreclosure', 'A legal process by which a lender or investor takes possession of a property due to the borrower''s failure to meet repayment obligations.', 'Servicing', 'Default', '{"FC"}', '{"Delinquency","Loss Mitigation","REO"}', 'AI flags loans at risk of foreclosure and encourages earlier interventions.', 'Coordinates legal timelines, notices, and reporting requirements.', '{"State Law","CFPB"}'),

        # Secondary Market & Capital Markets
        ('Secondary Market', 'The marketplace where closed mortgage loans are sold to investors, securitized, or traded, providing liquidity to lenders.', 'Secondary Market', 'General', '{"Secondary"}', '{"MBS","Whole Loan Sale"}', 'AI classifies loans by execution path and investor for pricing and hedging.', 'Feeds lock desk, hedging, and best-execution decision engines.', '{"GSE"}'),

        ('Mortgage-Backed Security (MBS)', 'A security backed by a pool of mortgage loans that pays investors principal and interest based on the performance of the underlying loans.', 'Secondary Market', 'Securitization', '{"MBS"}', '{"TBA","Pool","Pass-Through"}', 'AI links product, coupon, and execution type to pricing and hedge strategies.', 'Supports analysis of prepayment risk, yield, and pool eligibility.', '{"SEC"}'),

        ('To-Be-Announced (TBA)', 'A forward contract for the purchase or sale of MBS at a future date, with key characteristics agreed upon but specific pools not yet identified.', 'Secondary Market', 'Hedging', '{"TBA Trade"}', '{"MBS","Hedge Position"}', 'AI uses TBA data to inform lock/float advice and evaluate pipeline risk.', 'Supports hedging, best execution, and pair-off cost analysis.', '{"SEC"}'),

        ('Best-Efforts Delivery', 'A lock execution type where the lender commits to deliver a specific loan if it closes, without mandatory delivery obligations for fallout.', 'Secondary Market', 'Execution Type', '{"Best Efforts"}', '{"Mandatory Delivery","Pair-Off"}', 'AI evaluates when best-efforts is preferable due to volume or volatility.', 'Used in pricing and pull-through modeling for small or volatile pipelines.', '{"Investor Guideline"}'),

        ('Mandatory Delivery', 'A lock execution where the lender commits to deliver a specified loan volume or face penalties (such as pair-off fees) for failure to deliver.', 'Secondary Market', 'Execution Type', '{"Mandatory"}', '{"Best-Efforts Delivery","Pair-Off"}', 'AI associates mandatory delivery with tighter pricing but greater hedge discipline.', 'Feeds pair-off risk analysis and performance monitoring.', '{"Investor Guideline"}'),

        ('Pair-Off Fee', 'A fee paid to an investor when a lender cannot deliver a loan or security under a mandatory delivery commitment and must close out the position.', 'Secondary Market', 'Hedging', '{"Pair-Off"}', '{"Mandatory Delivery","TBA","Fallout"}', 'AI factors expected pair-off costs into execution strategy and lock advice.', 'Supports assessment of pipeline fallout and hedge performance.', '{"Investor Guideline"}'),

        # Operations & KPIs
        ('Pull-Through Rate', 'The percentage of locked loans that ultimately close and fund, used as a key performance and hedging metric.', 'Operations', 'KPI', '{"Pull-Through"}', '{"Fallout Rate","Lock Volume"}', 'AI uses pull-through history to refine hedge ratios and pricing margins.', 'Helps evaluate LO performance and operational efficiency.', '{"Internal Metric"}'),

        ('Fallout Rate', 'The percentage of applications or locks that do not result in a funded loan.', 'Operations', 'KPI', '{"Fallout"}', '{"Pull-Through Rate"}', 'AI identifies where in the funnel borrowers are dropping out and why.', 'Supports funnel optimization, training, and pricing/lock strategy adjustments.', '{"Internal Metric"}'),

        ('Turn Time', 'The amount of time it takes to complete a defined process step, such as underwriting or closing, often measured in days.', 'Operations', 'Process', '{"Turn-Time"}', '{"SLA","Cycle Time"}', 'AI monitors turn times against SLAs and flags bottlenecks.', 'Drives staffing, priority routing, and service-level reporting.', '{"Internal Metric"}'),

        ('Service Level Agreement (SLA)', 'A defined standard or target for completing a process step within a certain time frame.', 'Operations', 'Process', '{"SLA"}', '{"Turn Time"}', 'AI manages priorities and alerts when SLAs are at risk of being breached.', 'Used to drive queue management and capacity planning.', '{"Internal Policy"}'),

        ('Loan Pipeline', 'The set of loans at various stages from lead or application through funding and sometimes early servicing.', 'Operations', 'Pipeline', '{"Pipeline"}', '{"Pull-Through Rate","Fallout Rate"}', 'AI orchestrates tasks and prioritization based on pipeline stage, risk, and timelines.', 'Supports reporting, forecasting, and resource allocation across stages.', '{"Internal Metric"}'),

        # NON-QM / ALT-DOC
        ('Non-QM Loan', 'A mortgage that does not meet the Qualified Mortgage standards, using alternative documentation or expanded credit criteria.', 'Origination', 'Non-QM', '{"Non-QM","Non-Qualified Mortgage"}', '{"Bank Statement Loan","DSCR Loan","Asset Depletion"}', 'AI determines expanded credit rules, pricing, and ability-to-repay logic.', 'Routes to Non-QM workflows and due-diligence checklists.', '{"ATR"}'),

        ('Bank Statement Loan', 'A loan qualified using business or personal bank deposits instead of tax returns.', 'Origination', 'Non-QM', '{"Bank Statement Program"}', '{"Non-QM","Self-Employment Income"}', 'AI performs deposit averaging and expense factor logic.', 'Triggers bank statement import, parsing, and income calculation tasks.', '{"ATR"}'),

        ('DSCR Loan', 'A mortgage qualified based on the property''s Debt Service Coverage Ratio instead of borrower income.', 'Origination', 'Non-QM', '{"DSCR"}', '{"Rental Income","Investor Cash Flow"}', 'AI calculates DSCR and evaluates investor overlays.', 'Routes to investor-cash-flow qualification workflows.', '{"Investor Guideline"}'),

        ('Asset Depletion Loan', 'A loan in which borrower assets are converted into qualifying income using investor-defined formulas.', 'Origination', 'Non-QM', '{"Asset-Based Income"}', '{"Non-QM","Liquid Assets"}', 'AI applies depletion formulas for available assets.', 'Triggers assets-to-income calculation workflow.', '{"Investor Guideline"}'),

        ('Interest-Only Mortgage', 'A mortgage in which the borrower pays only interest for a defined period before amortization begins.', 'Origination', 'Loan Structure', '{"IO Loan"}', '{"ARM","Non-QM"}', 'AI determines qualifying payment and IO risk adjustments.', 'Routes to IO-specific underwriting and ATR logic.', '{"ATR"}'),

        # FHA
        ('FHA Loan', 'A mortgage insured by the Federal Housing Administration, designed for low-to-moderate-income borrowers.', 'Origination', 'FHA', '{"FHA"}', '{"MIP","Manual Underwrite"}', 'AI applies FHA-specific guidelines for credit, DTI, and collateral.', 'Triggers FHA disclosures, MIP calculations, and CAIVRS checks.', '{"HUD"}'),

        ('Up-Front Mortgage Insurance Premium (UFMIP)', 'A one-time FHA mortgage insurance premium paid at closing or financed into the loan.', 'Origination', 'FHA', '{"UFMIP"}', '{"MIP"}', 'AI automatically calculates FHA UFMIP and total loan amount.', 'Adds UFMIP to cash-to-close and payment calculations.', '{"HUD"}'),

        ('Mortgage Insurance Premium (MIP)', 'The monthly FHA mortgage insurance premium collected as part of the PITI payment.', 'Origination', 'FHA', '{"MIP"}', '{"UFMIP","PMI"}', 'AI adds MIP to payment calculations and applies duration rules.', 'Affects payment shock, DTI, and borrower eligibility.', '{"HUD"}'),

        ('CAIVRS Check', 'A federal system used to check if a borrower has defaulted on prior government loans.', 'Compliance', 'FHA', '{"CAIVRS"}', '{"HUD","Federal Debt"}', 'AI ensures CAIVRS clearance for FHA/VA loans.', 'Blocks application advancement until resolved.', '{"HUD"}'),

        ('FHA Manual Underwrite', 'A manually underwritten FHA loan when AUS cannot approve the file.', 'Underwriting', 'FHA', '{"Manual Underwrite","Manual UW"}', '{"Compensating Factors"}', 'AI applies FHA-specific manual underwriting rules.', 'Triggers expanded documentation requirements.', '{"HUD"}'),

        # VA
        ('VA Loan', 'A mortgage guaranteed by the Department of Veterans Affairs, available to eligible veterans, service members, and surviving spouses.', 'Origination', 'VA', '{"Veterans Loan"}', '{"COE","VA Funding Fee"}', 'AI validates VA eligibility and applies VA underwriting logic.', 'Triggers COE verification, residual income calculation, and funding fee logic.', '{"VA"}'),

        ('Certificate of Eligibility (COE)', 'A document proving a borrower''s eligibility for a VA loan.', 'Origination', 'VA', '{"COE"}', '{"VA Loan","Military Service"}', 'AI checks eligibility and informs documentation workflow.', 'Required to start VA underwriting.', '{"VA"}'),

        ('VA Funding Fee', 'A mandatory fee charged on VA loans unless the borrower is exempt.', 'Origination', 'VA', '{"Funding Fee"}', '{"COE","VA Loan"}', 'AI auto-calculates funding fee based on service type and exemptions.', 'Affects cash-to-close and payment calculations.', '{"VA"}'),

        ('Residual Income', 'A VA-specific metric measuring how much income remains after debts and housing expenses.', 'Underwriting', 'VA', '{"VA Residual"}', '{"DTI","VA Loan"}', 'AI applies regional residual income tables.', 'Determines VA approval or need for compensating factors.', '{"VA"}'),

        ('Entitlement', 'A veteran''s VA-backed mortgage guarantee benefit amount.', 'Origination', 'VA', '{"VA Entitlement"}', '{"COE","VA Loan"}', 'AI determines partial vs. full entitlement for purchase power.', 'Affects maximum loan amounts and eligibility.', '{"VA"}'),

        # USDA
        ('USDA Loan', 'A mortgage backed by the USDA for rural housing with income and geographic eligibility restrictions.', 'Origination', 'USDA', '{"Rural Development Loan"}', '{"RD","Guarantee Fee"}', 'AI validates income limits and property eligibility.', 'Triggers USDA-specific workflow routing and GUS submission.', '{"USDA"}'),

        ('GUS (Guaranteed Underwriting System)', 'The USDA automated underwriting system.', 'Underwriting', 'USDA', '{"GUS"}', '{"USDA Loan"}', 'AI parses GUS findings for conditions and eligibility.', 'Routes underwriting steps per GUS feedback.', '{"USDA"}'),

        ('USDA Guarantee Fee', 'Upfront and annual fees paid on USDA loans.', 'Origination', 'USDA', '{"Guarantee Fee"}', '{"USDA Loan"}', 'AI adds guarantee fee to loan amount and payment.', 'Impacts cash-to-close and debt ratios.', '{"USDA"}'),

        # QC / AUDIT
        ('Pre-Fund QC', 'A quality control review performed prior to closing to detect defects.', 'QC', 'Audits', '{"Prefund QC"}', '{"Post-Closing QC","Audit"}', 'AI flags files for targeted QC based on risk scoring.', 'Triggers QC sampling and audit review steps.', '{"GSE"}'),

        ('Post-Closing QC', 'A quality check performed after closing to ensure documentation accuracy and compliance.', 'QC', 'Audits', '{"PCQC"}', '{"Pre-Fund QC"}', 'AI verifies completeness of final documents and detects defects.', 'Initiates corrective action workflow.', '{"GSE"}'),

        ('Defect Severity', 'A rating of how severe a QC defect is based on investor guidelines.', 'QC', 'Risk', '{"Defect"}', '{"QC Finding","Repurchase Risk"}', 'AI classifies findings into severity buckets.', 'Determines whether corrective action or repurchase may be required.', '{"GSE"}'),

        ('Repurchase Request', 'A demand from an investor that a lender buy back a loan due to defects.', 'QC', 'Risk', '{"Repurchase"}', '{"Defect","Indemnification"}', 'AI identifies conditions that may trigger repurchase exposure.', 'Triggers escalation and legal review workflow.', '{"GSE"}'),

        ('Indemnification Agreement', 'An agreement where a lender compensates an investor for losses without repurchase.', 'QC', 'Risk', '{"Indemnification"}', '{"Repurchase"}', 'AI flags indemnified loans and adjusts risk calculations.', 'Impacts reserve calculations and portfolio analytics.', '{"Investor Guideline"}'),

        # APPRAISAL / COLLATERAL EXPANDED
        ('1004 Appraisal', 'The standard Uniform Residential Appraisal Report for single-family homes.', 'Collateral', 'Forms', '{"1004"}', '{"Appraisal","1004D"}', 'AI ensures correct form type for property/loan type.', 'Routes report to CU risk analysis.', '{"GSE"}'),

        ('1004D Update/Completion', 'A form verifying completion of repairs or construction.', 'Collateral', 'Forms', '{"1004D"}', '{"Appraisal"}', 'AI checks repair status or final completion.', 'Triggers repair follow-up tasks.', '{"GSE"}'),

        ('Desk Review', 'A secondary review of an appraisal without a field inspection.', 'Collateral', 'Review', '{"Desk Review"}', '{"Appraisal","Field Review"}', 'AI determines when desk reviews are required.', 'Used for collateral risk management.', '{"Investor Guideline"}'),

        ('Field Review', 'A more robust appraisal review requiring an independent site visit.', 'Collateral', 'Review', '{"Field Review"}', '{"Desk Review","Appraisal"}', 'AI flags high-risk collateral requiring field review.', 'Triggers secondary valuation workflows.', '{"Investor Guideline"}'),

        # COMPLIANCE EXPANDED
        ('HMDA Reporting', 'Home Mortgage Disclosure Act reporting requirements capturing detailed loan data.', 'Compliance', 'Reporting', '{"HMDA"}', '{"LAR","Fair Lending"}', 'AI tracks HMDA reportable attributes.', 'Ensures data fields are captured and validated.', '{"HMDA"}'),

        ('LAR (Loan Application Register)', 'The dataset lenders submit annually under HMDA.', 'Compliance', 'Reporting', '{"HMDA LAR"}', '{"HMDA"}', 'AI validates fields and prevents submission errors.', 'Coordinates HMDA audits and remediations.', '{"HMDA"}'),

        ('ECOA Notice of Action Taken', 'A required notice sent when credit is approved, denied, incomplete, or withdrawn.', 'Compliance', 'Credit Decisioning', '{"ECOA Notice"}', '{"Adverse Action"}', 'AI determines when an ECOA clock starts.', 'Ensures notice timing requirements.', '{"ECOA"}'),

        ('Regulation B', 'A federal rule implementing ECOA governing credit decisioning and anti-discrimination.', 'Compliance', 'Regulations', '{"Reg B"}', '{"ECOA"}', 'AI checks compliance in underwriting logic and borrower communication.', 'Impacts data handling, decisioning, and disclosures.', '{"ECOA"}'),

        # OPERATIONS EXPANDED
        ('Pipeline Stage', 'A defined point in the loan lifecycle from lead to funded loan.', 'Operations', 'Pipeline', '{"Stage"}', '{"Milestones","Loan Pipeline"}', 'AI drives tasks based on stage changes.', 'Triggers milestone workflows and notifications.', '{"Internal"}'),

        ('Milestone', 'A significant event in the loan process (e.g., submitted, approved).', 'Operations', 'Workflow', '{"Milestone"}', '{"Pipeline Stage"}', 'AI triggers milestone-based automations.', 'Updates CRM, agent dashboards, and referral partners.', '{"Internal"}'),

        ('Conditions (PTD/PTF/CTC)', 'Required documents or actions needed before moving to the next stage.', 'Underwriting', 'Conditions', '{"Conditions"}', '{"Clear to Close","Underwriting","PTD"}', 'AI categorizes and prioritizes conditions.', 'Automates assignment and completion tracking.', '{"Internal"}'),

        ('Clear to Close (CTC)', 'An approval indicating all underwriting conditions are satisfied.', 'Operations', 'Closing', '{"CTC"}', '{"Approval","Closing"}', 'AI triggers final disclosures, scheduling, and closing workflow.', 'Final major milestone before closing.', '{"Internal"}'),

        ('Underwriting Submission', 'Delivery of the loan file to underwriting for review.', 'Operations', 'Underwriting', '{"UW Submission"}', '{"Processing","Underwriting"}', 'AI checks completeness before submission.', 'Triggers underwriting queue and SLA tracking.', '{"Internal"}'),

        # CAPITAL MARKETS ADVANCED
        ('SRP (Service Release Premium)', 'The premium received when selling a loan servicing-released.', 'Secondary Market', 'Pricing', '{"Service Release Premium"}', '{"MSR","Best Execution"}', 'AI calculates SRP impact on best execution.', 'Affects retain vs. release decision.', '{"Investor Guideline"}'),

        ('Hedge Ratio', 'The percentage of pipeline exposure hedged against market movements.', 'Secondary Market', 'Hedging', '{"Hedge Coverage"}', '{"TBA","Position Risk"}', 'AI optimizes hedge ratios using pull-through modeling.', 'Drives lock desk and hedge execution.', '{"Internal"}'),

        ('Fallout Adjustment', 'A pricing or hedge adjustment based on expected loan fallout.', 'Secondary Market', 'Risk', '{"Fallout Adjustment"}', '{"Pull-Through"}', 'AI applies fallout models to hedge and pricing strategy.', 'Ensures accurate exposure management.', '{"Internal"}'),

        ('Pipeline Duration', 'A measure of interest-rate sensitivity of the loan pipeline.', 'Secondary Market', 'Analytics', '{"Duration"}', '{"Hedge Ratio","Convexity"}', 'AI evaluates duration for hedging precision.', 'Supports capital markets analytics and volatility monitoring.', '{"Internal"}'),

        # SERVICING EXPANDED
        ('Payment Application', 'Allocation of borrower payment to interest, principal, escrow, and fees.', 'Servicing', 'Payments', '{"Apply Payment"}', '{"Escrow","Interest"}', 'AI audits payment accuracy and borrower inquiries.', 'Supports statements and reconciliation.', '{"CFPB"}'),

        ('Early Payoff', 'A loan paid off before expected maturity.', 'Servicing', 'Payoff', '{"Prepay"}', '{"Prepayment Penalty"}', 'AI forecasts runoff and recapture opportunities.', 'Impacts MSR valuation.', '{"Investor Guideline"}'),

        ('Recapture', 'The lender''s ability to refinance or retain a customer after payoff.', 'Servicing', 'Retention', '{"Customer Retention"}', '{"Refinance","MSR"}', 'AI identifies recapture candidates via rate monitoring.', 'Triggers outbound engagement workflows.', '{"Internal"}'),

        ('ARM Adjustment', 'Periodic change in interest rate on an adjustable-rate mortgage.', 'Servicing', 'ARM', '{"Rate Adjustment"}', '{"ARM","Index"}', 'AI calculates new payments based on margin/index.', 'Generates ARM adjustment notices.', '{"TILA"}'),

        ('Index + Margin', 'The two components of an ARM interest rate.', 'Servicing', 'ARM', '{"ARM Rate"}', '{"ARM Adjustment"}', 'AI evaluates upcoming ARM resets and borrower payment impact.', 'Schedules ARM notices and compliance tasks.', '{"TILA"}'),

        ('Escrow Shortage', 'Insufficient escrow funds to cover projected disbursements.', 'Servicing', 'Escrow', '{"Shortage"}', '{"Escrow Analysis"}', 'AI explains shortages to borrowers and recalculates payments.', 'Triggers shortage repayment options.', '{"RESPA"}'),

        ('Escrow Surplus', 'Excess funds in escrow beyond what is required.', 'Servicing', 'Escrow', '{"Surplus"}', '{"Escrow Analysis"}', 'AI calculates refunds and communicates with borrowers.', 'Creates refund workflows.', '{"RESPA"}'),

        # AI / FINTECH TERMS
        ('AI Underwriting', 'Use of artificial intelligence to evaluate credit, collateral, and capacity.', 'Technology', 'AI', '{"AI UW"}', '{"AUS","Automated Underwriting"}', 'AI improves risk scoring and pattern detection.', 'Integrated with automated conditions generation.', '{"Internal"}'),

        ('OCR (Optical Character Recognition)', 'Technology used to extract text from documents in mortgage files.', 'Technology', 'OCR', '{"Doc Extraction"}', '{"Classification","AI"}', 'AI parses income, assets, and ID docs.', 'Feeds document indexing and data mapping.', '{"Internal"}'),

        ('Document Classification', 'AI categorization of uploaded borrower documents by type.', 'Technology', 'AI', '{"Classification"}', '{"OCR","Document Tagging"}', 'AI ensures docs are correctly tagged for underwriting.', 'Automates routing to correct workflow buckets.', '{"Internal"}'),

        ('Email Intelligence', 'AI system that reads inbound/outbound emails and updates loan status or tasks.', 'Technology', 'AI', '{"Email Parsing"}', '{"Orchestrator","Workflow Automation"}', 'AI updates loan status from LOS emails.', 'Triggers task creation and milestone changes.', '{"Internal"}'),

        ('AI Rate Lock Advisor', 'AI module that advises when to lock or float based on market risk.', 'Secondary Market', 'AI', '{"Rate Lock AI"}', '{"Rate Lock","Hedging"}', 'AI analyzes volatility, coupon movement, and borrower profile.', 'Assists lock desk and borrower guidance workflows.', '{"Internal"}'),

        # ROLES & RESPONSIBILITIES
        ('Loan Officer (LO)', 'A licensed mortgage originator who works with borrowers to structure and originate mortgage loans.', 'Operations', 'Roles', '{"LO","Mortgage Loan Originator","MLO"}', '{"Processor","Underwriter","Closer"}', 'AI associates LO ownership with pipeline accountability and communication routing.', 'Used for pipeline reporting, compensation tracking, and borrower contact workflows.', '{"NMLS"}'),

        ('Loan Processor', 'The team member who gathers documentation, reviews the file for completeness, and prepares it for underwriting.', 'Operations', 'Roles', '{"Processor"}', '{"Underwriter","Loan Officer"}', 'AI directs doc requests and follow-ups through the processor role when appropriate.', 'Central to condition clearing and file readiness workflows.', '{"Internal"}'),

        ('Underwriter', 'The credit risk decision-maker who evaluates the borrower, collateral, and loan terms against guidelines.', 'Underwriting', 'Roles', '{"UW"}', '{"Loan Processor","Underwriting Submission"}', 'AI packages data in a way optimized for underwriting decisions and condition generation.', 'Used for SLA tracking and escalation management.', '{"Internal"}'),

        ('Closer', 'The staff member who prepares the final loan documents and coordinates with title and closing agents.', 'Closing', 'Roles', '{"Closing Specialist"}', '{"Closing Disclosure","Funding"}', 'AI routes clear-to-close files to closers and ensures docs are accurate and timely.', 'Coordinates document generation, balancing, and closing scheduling.', '{"Internal"}'),

        ('Post-Closer', 'A team member responsible for reviewing closed loan packages, resolving deficiencies, and delivering to investors.', 'Post-Closing', 'Roles', '{"Post Closing"}', '{"Post-Closing QC","Investor Delivery"}', 'AI checks for missing documents and trailing items after closing.', 'Drives post-closing conditions and purchase advice reconciliation.', '{"Internal"}'),

        ('Lock Desk Analyst', 'A capital markets/secondary team member who manages rate locks, pricing, and pipeline hedging.', 'Secondary Market', 'Roles', '{"Lock Desk"}', '{"Rate Lock","Hedging"}', 'AI surfaces rate-lock intelligence, market moves, and risk flags to the lock desk.', 'Used in lock change approvals, extensions, and concessions.', '{"Internal"}'),

        ('Secondary Marketing Trader', 'A professional who executes trades, hedges pipeline risk, and manages loan sales.', 'Secondary Market', 'Roles', '{"Trader","Secondary Trader"}', '{"TBA","Mandatory Delivery","Hedge Ratio"}', 'AI provides analytics, scenario modeling, and risk measures for trading decisions.', 'Feeds execution choices and hedge adjustments.', '{"Internal"}'),

        ('Servicing Manager', 'The individual responsible for oversight of servicing operations, performance, and compliance.', 'Servicing', 'Roles', '{"Servicing Director"}', '{"MSR","Default","Escrow"}', 'AI escalates systemic issues and performance metrics to servicing leadership.', 'Supports strategy on retention, recapture, and MSR sales.', '{"Internal"}'),

        # PRODUCT & PRICING DETAILS
        ('Fixed-Rate Mortgage', 'A mortgage with an interest rate that remains constant for the entire term of the loan.', 'Origination', 'Loan Product', '{"Fixed"}', '{"ARM","Interest-Only Mortgage"}', 'AI uses fixed-rate status to simplify payment projections and risk analysis.', 'Standard for vanilla pricing, disclosures, and eligibility.', '{"TILA"}'),

        ('Adjustable-Rate Mortgage (ARM)', 'A mortgage with an interest rate that can change at specified intervals based on an index and margin.', 'Origination', 'Loan Product', '{"ARM"}', '{"Fixed-Rate Mortgage","Index + Margin"}', 'AI predicts future payment scenarios and evaluates payment shock.', 'Triggers ARM-specific disclosures and adjustment notices.', '{"TILA"}'),

        ('ARM Teaser Rate', 'An initial, often lower, interest rate on an ARM before it adjusts.', 'Origination', 'Loan Product', '{"Introductory Rate"}', '{"Adjustable-Rate Mortgage (ARM)"}', 'AI evaluates attractiveness vs. future payment risk for borrowers.', 'Ensures accurate APR and disclosure content.', '{"TILA"}'),

        ('ARM Caps', 'Limits on how much an ARM interest rate can change at adjustment periods and over the life of the loan.', 'Origination', 'Loan Product', '{"Rate Caps"}', '{"Adjustable-Rate Mortgage (ARM)","Index + Margin"}', 'AI uses caps to bound payment projections and stress tests.', 'Supports borrower counseling about worst-case scenarios.', '{"TILA"}'),

        ('3-2-1 Buydown', 'A temporary buydown structure where the interest rate is reduced by 3% in year 1, 2% in year 2, and 1% in year 3.', 'Origination', 'Buydown', '{"321 Buydown"}', '{"2-1 Buydown","Temporary Buydown"}', 'AI models stepped payment schedule and qualifying rate rules.', 'Used to verify buydown funding and escrow for subsidy.', '{"GSE","Investor Guideline"}'),

        ('2-1 Buydown', 'A temporary buydown where the rate is 2% lower in year 1 and 1% lower in year 2.', 'Origination', 'Buydown', '{"2-1"}', '{"3-2-1 Buydown","Temporary Buydown"}', 'AI calculates qualifying payment at note rate while explaining buydown benefit.', 'Ensures buydown agreement and funding sources comply with guidelines.', '{"GSE"}'),

        ('Temporary Buydown', 'A structure where the borrower''s effective payment is reduced for a set period through a funded subsidy.', 'Origination', 'Buydown', '{"Temp Buydown"}', '{"2-1 Buydown","3-2-1 Buydown"}', 'AI checks eligible products and funding sources (seller, builder, lender).', 'Triggers creation of buydown escrow account and amortization schedule.', '{"GSE","RESPA"}'),

        ('Permanent Buydown', 'Buying down the interest rate for the entire term by paying discount points.', 'Origination', 'Pricing', '{"Rate Buydown","Discount Points"}', '{"Origination Points","Yield Spread Premium"}', 'AI compares permanent vs. temporary buydown value for the borrower.', 'Impacts APR, points-and-fees tests, and long-term savings analysis.', '{"TILA","HOEPA"}'),

        ('Discount Points', 'Fees paid by the borrower to reduce the interest rate on the mortgage.', 'Origination', 'Pricing', '{"Points"}', '{"Origination Fee","Permanent Buydown"}', 'AI evaluates breakeven horizon for paying points.', 'Affects APR calculations and high-cost tests.', '{"TILA","HOEPA"}'),

        ('Origination Fee', 'A fee charged by a lender or broker for processing a new loan application.', 'Origination', 'Fees', '{"Origination Charge"}', '{"Discount Points","LO Compensation"}', 'AI monitors fee levels for compliance with LO comp and points-and-fees caps.', 'Displays origination fee treatment in LE/CD.', '{"LO Comp","TILA"}'),

        ('Prepayment Penalty', 'A fee charged if the borrower pays off the loan earlier than scheduled, where allowed.', 'Origination', 'Loan Terms', '{"Prepay Penalty"}', '{"Early Payoff"}', 'AI flags potential prepayment penalties when refinance or sale is considered.', 'Triggers enhanced disclosures and suitability checks.', '{"HOEPA","State Law"}'),

        # PROPERTY TYPES & REAL ESTATE
        ('Primary Residence', 'The main home where the borrower lives most of the year.', 'Underwriting', 'Occupancy', '{"Owner-Occupied"}', '{"Second Home","Investment Property"}', 'AI uses occupancy to determine risk tier, pricing, and eligibility.', 'Drives appropriate documentation and occupancy attestations.', '{"GSE"}'),

        ('Second Home', 'A property used by the borrower for personal use but not as a primary residence.', 'Underwriting', 'Occupancy', '{"Vacation Home"}', '{"Primary Residence","Investment Property"}', 'AI applies specific LTV and reserve requirements.', 'Triggers second-home overlays and rental restrictions.', '{"GSE"}'),

        ('Investment Property', 'A property purchased primarily to generate rental income or capital gain.', 'Underwriting', 'Occupancy', '{"Non-Owner-Occupied","NOO"}', '{"Primary Residence","Second Home","DSCR Loan"}', 'AI applies higher risk-based pricing and stricter guidelines.', 'Requires rental income analysis and vacancy assumptions.', '{"GSE","Investor Guideline"}'),

        ('Condominium', 'A property type where a unit owner owns the interior space and shares common elements.', 'Collateral', 'Property Type', '{"Condo"}', '{"PUD","Co-op"}', 'AI recognizes condo-specific project approval requirements.', 'Triggers condo questionnaire, budget, and insurance review.', '{"GSE"}'),

        ('Planned Unit Development (PUD)', 'A real estate development with individually owned lots and common areas owned by an HOA.', 'Collateral', 'Property Type', '{"PUD"}', '{"Condominium","Single-Family Detached"}', 'AI flags PUDs for HOA and CCR review.', 'Ensures proper insurance and HOA dues are considered in DTI.', '{"GSE"}'),

        ('Cooperative (Co-op)', 'A property ownership structure where residents own shares in a corporation that owns the building.', 'Collateral', 'Property Type', '{"Co-op"}', '{"Condominium"}', 'AI applies co-op-specific lending requirements and restrictions.', 'Triggers specialized documentation and occupancy rules.', '{"Investor Guideline"}'),

        ('Homeowners Association (HOA)', 'An organization in a subdivision or condo complex that makes and enforces rules and collects dues.', 'Collateral', 'HOA', '{"HOA"}', '{"PUD","Condominium"}', 'AI adds HOA dues to housing payment and checks financial health of HOA.', 'Requires HOA docs, budgets, and insurance certificates.', '{"GSE"}'),

        ('Earnest Money Deposit (EMD)', 'A buyer''s deposit showing serious intent to purchase a property.', 'Origination', 'Purchase Contract', '{"EMD","Good Faith Deposit"}', '{"Purchase Agreement","Cash to Close"}', 'AI ensures EMD is sourced and applied correctly to cash to close.', 'Validates contract terms and contingency timelines.', '{"RESPA"}'),

        ('Purchase and Sale Agreement', 'The contract between buyer and seller outlining the terms of the property purchase.', 'Origination', 'Purchase Contract', '{"Purchase Contract","PSA"}', '{"Earnest Money Deposit (EMD)","Contingency"}', 'AI extracts key terms: price, dates, contingencies, concessions.', 'Drives timeline and condition management.', '{"State Law"}'),

        ('Inspection Contingency', 'A contract clause allowing the buyer to cancel or renegotiate based on property inspection results.', 'Origination', 'Contingency', '{"Home Inspection Contingency"}', '{"Purchase and Sale Agreement"}', 'AI tracks deadlines and inspection outcomes for risk.', 'Influences collateral risk evaluation and renegotiated terms.', '{"State Law"}'),

        ('Financing Contingency', 'A clause giving the buyer time to obtain loan approval and cancel if financing is not secured.', 'Origination', 'Contingency', '{"Mortgage Contingency"}', '{"Loan Approval","Purchase and Sale Agreement"}', 'AI coordinates financing contingency dates with underwriting.', 'Used for communication with agents and timeline expectations.', '{"State Law"}'),

        # FLOOD, HAZARD & INSURANCE
        ('Flood Zone', 'A geographic area defined by FEMA for flood risk purposes.', 'Collateral', 'Risk', '{"FEMA Zone"}', '{"Flood Insurance","Flood Certification"}', 'AI checks flood zone determinations and insurance requirements.', 'Ensures flood insurance is in place where required.', '{"NFIP"}'),

        ('Flood Certification', 'A report determining whether a property is located in a flood zone.', 'Collateral', 'Risk', '{"Flood Cert"}', '{"Flood Zone"}', 'AI ensures each loan has a valid flood cert.', 'Triggers insurance requirements when needed.', '{"NFIP"}'),

        ('Hazard Insurance', 'Insurance protecting against physical damage to the property.', 'Collateral', 'Insurance', '{"Homeowners Insurance","HOI"}', '{"Escrow Account"}', 'AI validates coverage amounts, deductibles, and mortgagee clause.', 'Ensures policy is active before closing.', '{"Investor Guideline"}'),

        ('Mortgagee Clause', 'A clause in an insurance policy naming the lender as beneficiary for claim payments.', 'Collateral', 'Insurance', '{"Lender Loss Payee"}', '{"Hazard Insurance","HOI"}', 'AI checks that the mortgagee clause is correctly listed.', 'Prevents funding until proper clause is verified.', '{"Investor Guideline"}'),

        # ACCOUNTING, WAREHOUSE & FINANCE
        ('Warehouse Line of Credit', 'A short-term credit facility used by mortgage lenders to fund loans before selling them.', 'Finance', 'Warehouse', '{"Warehouse Line","Warehouse Facility"}', '{"Bailee Letter","Dwell Time"}', 'AI monitors dwell time and capacity of warehouse lines.', 'Impacts funding availability and capital planning.', '{"Internal"}'),

        ('Dwell Time', 'The number of days a loan remains on the warehouse line before being sold.', 'Finance', 'Warehouse', '{"Line Dwell"}', '{"Warehouse Line of Credit","Early Payoff"}', 'AI flags loans exceeding target dwell times.', 'Encourages faster purchase by investors or pooling.', '{"Internal"}'),

        ('Bailee Letter', 'A letter from the warehouse bank to an investor confirming collateral custody for purchase.', 'Finance', 'Warehouse', '{"Bailee"}', '{"Warehouse Line of Credit"}', 'AI confirms Bailee letters are issued for shipped collateral.', 'Integral to purchase funding and collateral release workflows.', '{"Internal"}'),

        ('Gain-on-Sale', 'The profit realized when selling a loan or security above its recorded value.', 'Finance', 'Accounting', '{"GOS"}', '{"SRP","Mandatory Delivery"}', 'AI estimates gain-on-sale based on execution paths.', 'Feeds margin analysis and P&L reporting.', '{"GAAP"}'),

        ('MSR Valuation', 'The process of determining the value of mortgage servicing rights using cash flow models.', 'Servicing', 'MSR', '{"MSR Value"}', '{"Mortgage Servicing Rights (MSR)"}', 'AI projects servicing income and prepayment speeds.', 'Used for fair-value reporting and MSR sale/retain decisions.', '{"GAAP"}'),

        ('Servicing Advance', 'Funds advanced by a servicer to cover missed payments, taxes, or insurance until reimbursed by investors/insurers.', 'Servicing', 'Finance', '{"Advances"}', '{"Delinquency","MSR"}', 'AI tracks advance balances and recoverability.', 'Impacts servicing cash flow and liquidity management.', '{"Investor Guideline"}'),

        # FRAUD & RISK
        ('Occupancy Fraud', 'Misrepresentation of how a property will be occupied (e.g., claiming primary residence vs. investment).', 'Risk', 'Fraud', '{"Occ Fraud"}', '{"Primary Residence","Investment Property"}', 'AI detects red flags when stated occupancy conflicts with behavior or profile.', 'Triggers enhanced verification and possibly SAR filing.', '{"AML/BSA"}'),

        ('Straw Buyer', 'A person used to purchase a property or obtain a loan for someone else who cannot qualify.', 'Risk', 'Fraud', '{"Straw Borrower"}', '{"Identity Theft","Occupancy Fraud"}', 'AI checks for multiple loans, mismatched profiles, and unusual relationships.', 'Initiates fraud review workflows.', '{"AML/BSA"}'),

        ('Income Misrepresentation', 'Providing false or inflated income information to qualify for a loan.', 'Risk', 'Fraud', '{"Income Fraud"}', '{"Bank Statement Loan","Self-Employment Income"}', 'AI compares reported income against patterns, docs, and external data.', 'Escalates suspicion to human fraud analysts.', '{"AML/BSA"}'),

        ('Synthetic Identity', 'A fabricated identity created from pieces of real and fake information.', 'Risk', 'Fraud', '{"Synthetic ID"}', '{"Identity Theft"}', 'AI evaluates thin-file anomalies, SSN patterns, and inconsistent data.', 'Triggers additional KYC/ID verification steps.', '{"AML/BSA"}'),

        ('Red Flags Rule', 'Regulations requiring financial institutions to detect and respond to identity theft warning signs.', 'Compliance', 'Fraud', '{"Red Flags"}', '{"Identity Theft","AML/BSA"}', 'AI monitors cue patterns that constitute red flags.', 'Requires internal procedures for investigation and mitigation.', '{"FACTA"}'),

        # LO COMP, MARKETING & RESPA
        ('Loan Originator Compensation Rule', 'Regulations governing how loan originators may be paid to prevent steering and unfair practices.', 'Compliance', 'LO Comp', '{"LO Comp Rule"}', '{"Origination Fee","Yield Spread Premium"}', 'AI prevents pricing scenarios that violate comp rules.', 'Ensures consistent compensation plans regardless of loan terms.', '{"LO Comp","TILA"}'),

        ('Yield Spread Premium (YSP)', 'Compensation to a broker or lender based on selling a loan above par rate, subject to modern restrictions.', 'Origination', 'Compensation', '{"YSP"}', '{"LO Comp Rule","Discount Points"}', 'AI ensures old YSP-style comp is not structured in a non-compliant manner.', 'Used historically; now mainly for understanding legacy concepts and pricing history.', '{"RESPA","LO Comp"}'),

        ('Affiliated Business Arrangement (AfBA)', 'A relationship where a referral source has an ownership interest in a settlement service provider.', 'Compliance', 'RESPA', '{"AfBA"}', '{"RESPA Section 8","Disclosure"}', 'AI checks for required AfBA disclosures.', 'Prevents illegal kickbacks or referral fees.', '{"RESPA"}'),

        ('RESPA Section 8', 'The part of RESPA that prohibits kickbacks and unearned fees for referrals.', 'Compliance', 'RESPA', '{"Section 8"}', '{"Affiliated Business Arrangement (AfBA)","MSA"}', 'AI flags risky referral or fee-sharing structures.', 'Ensures MSA and AfBA arrangements comply with law.', '{"RESPA"}'),

        ('Marketing Services Agreement (MSA)', 'An agreement where a lender pays for actual marketing services performed by a partner, subject to RESPA restrictions.', 'Compliance', 'RESPA', '{"MSA"}', '{"RESPA Section 8","AfBA"}', 'AI analyzes marketing arrangements for potential RESPA violations.', 'Requires documentation of fair market value and actual services.', '{"RESPA"}'),

        # HIGH-COST, HPML & QM
        ('Annual Percentage Rate (APR)', 'A measure of the cost of credit, including interest and certain fees, expressed as a yearly rate.', 'Compliance', 'Pricing', '{"APR"}', '{"APOR","Finance Charge"}', 'AI recalculates APR with each pricing change.', 'Determines HOEPA and HPML status.', '{"TILA"}'),

        ('Average Prime Offer Rate (APOR)', 'An index used to compare loan APRs for determining HPML status.', 'Compliance', 'Pricing', '{"APOR"}', '{"APR","Higher-Priced Mortgage Loan (HPML)"}', 'AI checks APR vs. APOR spread.', 'Determines if HPML rules apply.', '{"TILA"}'),

        ('Higher-Priced Mortgage Loan (HPML)', 'A closed-end mortgage with an APR exceeding APOR by a defined threshold.', 'Compliance', 'High-Cost', '{"HPML"}', '{"HOEPA","APR"}', 'AI enforces HPML escrow, appraisal, and underwriting requirements.', 'Triggers specific counseling and documentation.', '{"TILA"}'),

        ('HOEPA Loan', 'A high-cost mortgage under the Home Ownership and Equity Protection Act, subject to special protections.', 'Compliance', 'High-Cost', '{"HOEPA","High-Cost Loan"}', '{"APR","Points and Fees"}', 'AI checks points, fees, and APR thresholds for HOEPA triggers.', 'Requires additional disclosures and restrictions.', '{"HOEPA","TILA"}'),

        ('Qualified Mortgage (QM)', 'A mortgage that meets specific underwriting and product criteria to provide ATR legal protections.', 'Compliance', 'QM', '{"QM"}', '{"Non-QM Loan","ATR"}', 'AI differentiates QM vs. Non-QM and related legal protections.', 'Applies product and underwriting restrictions such as no toxic features.', '{"QM/ATR"}'),

        ('Safe Harbor QM', 'A QM that is not higher-priced and gives the lender stronger legal protection.', 'Compliance', 'QM', '{"Safe Harbor"}', '{"Higher-Priced Mortgage Loan (HPML)","Rebuttable Presumption"}', 'AI identifies safe-harbor loans for lower litigation risk.', 'Useful in portfolio and secondary sale decisions.', '{"QM/ATR"}'),

        ('Rebuttable Presumption QM', 'A QM that is higher-priced and provides weaker legal protection than safe-harbor QM.', 'Compliance', 'QM', '{"Rebuttable Presumption"}', '{"Higher-Priced Mortgage Loan (HPML)","Safe Harbor QM"}', 'AI flags these as higher legal risk.', 'Impacts risk reserves, pricing, and investor acceptance.', '{"QM/ATR"}'),

        # E-CLOSING & DIGITAL MORTGAGE
        ('eClose', 'A closing process where some or all loan documents are signed electronically.', 'Technology', 'eClosing', '{"Electronic Closing","Hybrid eClose"}', '{"RON","eNote"}', 'AI determines eligibility for eClose vs. hybrid vs. wet signatures.', 'Coordinates e-sign invitations and compliance checks.', '{"ESIGN","UETA"}'),

        ('Hybrid eClose', 'A closing where certain documents are signed electronically and others on paper.', 'Technology', 'eClosing', '{"Hybrid Closing"}', '{"eClose","Wet Funding"}', 'AI chooses hybrid when full eClose is not feasible.', 'Splits package into e-sign and wet-sign components.', '{"ESIGN","UETA"}'),

        ('Remote Online Notarization (RON)', 'A form of notarization performed via audio-visual communication technology.', 'Technology', 'eClosing', '{"RON"}', '{"Notary","eClose"}', 'AI checks state and investor eligibility for RON.', 'Helps schedule RON sessions and manage digital closing.', '{"State Law"}'),

        ('eNote', 'An electronic version of a promissory note with legal enforceability.', 'Technology', 'eClosing', '{"Electronic Note"}', '{"MERS eRegistry","eVault"}', 'AI ensures eNotes are properly registered and vaulted.', 'Key element of digital mortgage and secondary delivery.', '{"UETA","ESIGN"}'),

        ('MERS (Mortgage Electronic Registration Systems)', 'A system that tracks servicing and ownership rights of mortgage loans electronically.', 'Technology', 'Registration', '{"MERS"}', '{"MIN","eNote"}', 'AI uses MIN to track chain-of-title and servicing rights.', 'Supports transfers and investor reporting.', '{"Investor Guideline"}'),

        ('MERS MIN (Mortgage Identification Number)', 'A unique identifier for loans registered with MERS.', 'Technology', 'Registration', '{"MIN"}', '{"MERS"}', 'AI uses MIN as a stable identifier for loan tracking.', 'Important for servicing transfers and investor communication.', '{"Investor Guideline"}'),

        # SERVICING – PAYMENT, ESCROW, STATEMENTS
        ('Payment Due Date', 'The scheduled date each month when the borrower''s mortgage payment is due.', 'Servicing', 'Payments', '{"Due Date"}', '{"Grace Period","Late Charge"}', 'AI uses due dates to monitor delinquency status and trigger reminders.', 'Drives payment reminder notifications and late-fee assessments.', '{"CFPB"}'),

        ('Grace Period', 'The time after the due date during which a borrower can make a payment without incurring a late fee.', 'Servicing', 'Payments', '{"Grace"}', '{"Payment Due Date","Late Charge"}', 'AI calculates last day of grace and flags upcoming late-fee events.', 'Controls timing of late-fee posting and borrower communications.', '{"State Law","CFPB"}'),

        ('Late Charge', 'A fee assessed when a payment is received after the grace period expires.', 'Servicing', 'Payments', '{"Late Fee"}', '{"Delinquency","Grace Period"}', 'AI checks compliance with limits on late charges and posting rules.', 'Automates late-fee assessment and reversal logic when appropriate.', '{"State Law","CFPB"}'),

        ('Payment Reversal', 'The process of undoing a payment application, typically due to return or error.', 'Servicing', 'Payments', '{"Reversal"}', '{"NSF","Payment Application"}', 'AI tracks reversals and re-evaluates delinquency buckets.', 'Triggers borrower notices and updated statements.', '{"CFPB"}'),

        ('NSF (Non-Sufficient Funds)', 'A returned payment due to insufficient funds in the borrower''s account.', 'Servicing', 'Payments', '{"NSF","Returned Check"}', '{"Payment Reversal","Delinquency"}', 'AI detects patterns of NSFs for risk and hardship indicators.', 'Triggers fees, reversals, and possible payment-plan discussions.', '{"CFPB"}'),

        ('Periodic Statement', 'A regular statement sent to borrowers summarizing account status, payments, and charges.', 'Servicing', 'Communications', '{"Mortgage Statement"}', '{"Payment History","Escrow Analysis"}', 'AI ensures content and timing comply with servicing rules.', 'Used to generate and audit borrower statements.', '{"CFPB"}'),

        ('Escrow Cushion', 'The extra amount held in escrow to cover unanticipated increases in taxes or insurance.', 'Servicing', 'Escrow', '{"Cushion","Reserve"}', '{"Escrow Account","Escrow Analysis"}', 'AI verifies cushion limits under RESPA.', 'Impacts escrow payment calculations and shortages/surpluses.', '{"RESPA"}'),

        ('Force-Placed Insurance', 'Insurance obtained by the servicer when the borrower''s policy lapses or is insufficient.', 'Servicing', 'Insurance', '{"Lender-Placed Insurance"}', '{"Hazard Insurance","Escrow Account"}', 'AI monitors lapse notices and triggers forced-placement when required.', 'Drives borrower notices, cost tracking, and cancellation upon proof of coverage.', '{"CFPB","RESPA"}'),

        ('Payoff Quote', 'A calculated amount required to fully pay off the loan as of a specific date.', 'Servicing', 'Payoff', '{"Payoff Demand","Payoff Statement"}', '{"Early Payoff","Per Diem Interest"}', 'AI generates payoff quotes based on principal, interest, and fees.', 'Supports refinance, sale, and lien release workflows.', '{"State Law"}'),

        ('Per Diem Interest', 'Daily interest accrued between the last payment date and payoff or funding date.', 'Servicing', 'Interest', '{"Daily Interest"}', '{"Payoff Quote","Funding"}', 'AI calculates per diem accurately for closings and payoffs.', 'Used in CD/closing documents and payoff statements.', '{"TILA"}'),

        # SERVICING DEFAULT – COLLECTIONS, FORECLOSURE, BANKRUPTCY
        ('Collections Call', 'A call made to a delinquent borrower to discuss missed payments and options.', 'Servicing', 'Collections', '{"Collection Contact"}', '{"Delinquency","Loss Mitigation"}', 'AI prioritizes accounts for outreach based on risk and stage.', 'Supports call scripting and logging for compliance.', '{"CFPB"}'),

        ('Right Party Contact (RPC)', 'Confirmation that the servicer is speaking with the borrower or authorized party.', 'Servicing', 'Collections', '{"RPC"}', '{"Borrower Contact","Collections Call"}', 'AI tracks RPC success rates and contact strategies.', 'Helps ensure proper disclosure and hardship discussion.', '{"CFPB"}'),

        ('Promise to Pay', 'A borrower''s commitment to make a payment by a specific date.', 'Servicing', 'Collections', '{"PTP"}', '{"Collections Call","Delinquency"}', 'AI monitors broken vs. kept promises for risk scoring.', 'Updates expected cash-flow timelines and follow-up tasks.', '{"Internal"}'),

        ('Notice of Default (NOD)', 'A formal notice indicating the borrower is in default and foreclosure proceedings may begin.', 'Servicing', 'Foreclosure', '{"Default Notice"}', '{"Delinquency","Foreclosure Sale"}', 'AI calculates statutory timelines and necessary notices before NOD.', 'Triggers legal referral and state-specific process tracking.', '{"State Law"}'),

        ('Foreclosure Sale', 'The auction or sale event where a property is sold to satisfy unpaid debt.', 'Servicing', 'Foreclosure', '{"Sheriff Sale","Trustee Sale"}', '{"REO","Notice of Default (NOD)"}', 'AI predicts foreclosure timelines and severity of loss.', 'Coordinates sale results, deficiency calculations, and REO intake.', '{"State Law"}'),

        ('REO (Real Estate Owned)', 'Property acquired by a lender or investor after an unsuccessful foreclosure sale.', 'Servicing', 'REO', '{"REO Property"}', '{"Foreclosure","Disposition"}', 'AI flags REO inventory for disposition strategies.', 'Feeds asset management, pricing, and marketing workflows.', '{"Investor Guideline"}'),

        ('Borrower Hardship', 'A condition causing difficulty in making payments, such as job loss or medical expenses.', 'Servicing', 'Loss Mitigation', '{"Hardship"}', '{"Loss Mitigation","Forbearance"}', 'AI detects hardship signals from borrower communication and behavior.', 'Suggests forbearance, modification, or other workout options.', '{"CFPB"}'),

        ('Bankruptcy Chapter 7', 'A liquidation bankruptcy where non-exempt assets may be sold to pay creditors.', 'Servicing', 'Bankruptcy', '{"Chapter 7"}', '{"Automatic Stay","Discharge"}', 'AI adjusts collections activity to comply with bankruptcy law.', 'Triggers legal review, proof-of-claim filing, and stay monitoring.', '{"Bankruptcy Law"}'),

        ('Bankruptcy Chapter 13', 'A reorganization bankruptcy with a repayment plan over several years.', 'Servicing', 'Bankruptcy', '{"Chapter 13"}', '{"Trustee","Plan Payment"}', 'AI coordinates loan payments with trustee plans and court orders.', 'Monitors plan performance and post-discharge status.', '{"Bankruptcy Law"}'),

        ('Automatic Stay', 'A legal injunction halting collection and foreclosure actions upon bankruptcy filing.', 'Servicing', 'Bankruptcy', '{"Stay"}', '{"Bankruptcy Chapter 7","Bankruptcy Chapter 13"}', 'AI stops collections and foreclosure triggers automatically.', 'Ensures compliance with legal restrictions and restarts only when allowed.', '{"Bankruptcy Law"}'),

        # CUSTOMER EXPERIENCE & RETENTION
        ('Customer Journey', 'The end-to-end path a borrower or prospect takes from lead to closed loan and beyond.', 'Operations', 'Customer Experience', '{"Borrower Journey"}', '{"Loan Pipeline","Touchpoint"}', 'AI maps communication and tasks to the borrower''s stage.', 'Supports personalized messaging and NPS measurement.', '{"Internal"}'),

        ('Net Promoter Score (NPS)', 'A metric measuring customer loyalty based on likelihood to recommend.', 'Operations', 'Customer Experience', '{"NPS"}', '{"Survey","Customer Satisfaction"}', 'AI uses NPS feedback to adjust retention and referral strategies.', 'Used in LO performance reviews and service improvement plans.', '{"Internal"}'),

        ('Borrower Portal', 'An online interface where borrowers can upload documents, track status, and communicate.', 'Technology', 'Portals', '{"Client Portal"}', '{"POS","Online Application"}', 'AI tailors portal content, tasks, and FAQs to loan stage.', 'Central channel for secure communication and doc upload.', '{"CFPB","Security"}'),

        ('Referral Partner Portal', 'A portal where real estate agents, builders, and other partners track shared clients.', 'Technology', 'Portals', '{"Partner Portal"}', '{"Realtor Portal","Builder Portal"}', 'AI surfaces pipeline, status, and co-branded content for partners.', 'Drives transparency, updates, and referral engagement.', '{"Internal"}'),

        ('Co-Branded Marketing', 'Marketing materials that feature both the lender and a partner''s branding.', 'Marketing', 'Partnerships', '{"Co-Branding"}', '{"Referral Partner","AfBA"}', 'AI ensures co-branded materials meet compliance and brand standards.', 'Automates creation of flyers, videos, and landing pages.', '{"RESPA","Brand Policy"}'),

        ('Customer Lifetime Value (CLV)', 'The estimated net profit from a customer relationship over time.', 'Operations', 'Analytics', '{"CLV","LTV (Customer)"}', '{"Recapture","Cross-Sell"}', 'AI calculates CLV to prioritize retention campaigns.', 'Informs spending on marketing and service enhancements.', '{"Internal"}'),

        # BUILDER, NEW CONSTRUCTION, RENOVATION
        ('Builder Spec Home', 'A new home built by a builder without a specific buyer identified.', 'Origination', 'Builder', '{"Spec Home"}', '{"Construction-to-Permanent Loan"}', 'AI recognizes spec inventory and builder relationships.', 'Supports pipeline projections and builder-finance analytics.', '{"Internal"}'),

        ('Lot Loan', 'A loan used to finance the purchase of land only.', 'Origination', 'Land', '{"Land Loan"}', '{"Construction Loan","C-to-P"}', 'AI applies different LTV and exit strategies than standard mortgages.', 'Triggers construction-takeout planning and collateral review.', '{"Investor Guideline"}'),

        ('Renovation Loan', 'A loan that finances both the purchase (or refinance) and renovation of a property.', 'Origination', 'Renovation', '{"Renovation Mortgage","Rehab Loan"}', '{"203(k)","Homestyle"}', 'AI coordinates draws, contractor docs, and after-repair value (ARV).', 'Uses renovation budgets and inspection milestones in workflow.', '{"HUD","GSE"}'),

        ('After-Repair Value (ARV)', 'The estimated property value after planned renovations are completed.', 'Collateral', 'Renovation', '{"ARV"}', '{"Renovation Loan","Appraisal"}', 'AI uses ARV in renovation underwriting and risk evaluation.', 'Impacts LTV and draw schedules.', '{"Investor Guideline"}'),

        ('Draw Schedule', 'A plan for incremental disbursement of funds during construction or renovation.', 'Servicing', 'Construction', '{"Draws"}', '{"Renovation Loan","Construction Loan"}', 'AI monitors draw completion, inspections, and lien waivers.', 'Ensures funds align with work progress and budget.', '{"Investor Guideline"}'),

        ('Retainage', 'A portion of construction funds withheld until completion.', 'Servicing', 'Construction', '{"Retainage Holdback"}', '{"Draw Schedule"}', 'AI tracks retainage amounts and release conditions.', 'Reduces risk of incomplete or defective work.', '{"Internal"}'),

        # HEL, HELOC, REVERSE
        ('Home Equity Loan', 'A closed-end loan secured by the borrower''s equity in their home, typically with a fixed rate.', 'Origination', 'Home Equity', '{"HEL"}', '{"HELOC","Cash-Out Refinance"}', 'AI compares HEL vs. cash-out options for best borrower outcome.', 'Impacts lien position, CLTV, and pricing.', '{"State Law"}'),

        ('Home Equity Line of Credit (HELOC)', 'An open-end line of credit secured by a borrower''s home, with a revolving balance.', 'Origination', 'Home Equity', '{"HELOC"}', '{"Home Equity Loan","HCLTV"}', 'AI monitors utilization, HCLTV, and payment changes.', 'Used for line management and draw controls.', '{"State Law"}'),

        ('Draw Period (HELOC)', 'The period during which a borrower can draw funds from a HELOC.', 'Servicing', 'Home Equity', '{"Draw Period"}', '{"Repayment Period","HELOC"}', 'AI explains transitions from interest-only draw to amortizing repayment.', 'Triggers borrower communications before period change.', '{"TILA"}'),

        ('Repayment Period (HELOC)', 'The period after the draw period during which the HELOC balance is repaid, often with no further advances.', 'Servicing', 'Home Equity', '{"Repayment"}', '{"Draw Period (HELOC)","HELOC"}', 'AI recalculates payments and flags payment-shock risk.', 'Prompts borrower education and refinancing options.', '{"TILA"}'),

        ('Reverse Mortgage', 'A loan for older homeowners that converts home equity into cash, with repayment due at maturity events such as death or sale.', 'Origination', 'Reverse', '{"HECM","Senior Mortgage"}', '{"Line of Credit","Tenure Payments"}', 'AI handles age, occupancy, and counseling requirements.', 'Requires special disclosures and servicing workflows.', '{"HUD"}'),

        ('HECM (Home Equity Conversion Mortgage)', 'The FHA-insured reverse mortgage program.', 'Origination', 'Reverse', '{"HECM"}', '{"Reverse Mortgage"}', 'AI ensures adherence to HUD rules for HECM.', 'Coordinates counseling, principal limit factors, and disbursement options.', '{"HUD"}'),

        # DATA, MODELING & ANALYTICS
        ('Prepayment Speed', 'The rate at which borrowers pay off or refinance loans ahead of schedule.', 'Analytics', 'Prepayment', '{"Prepayment Rate"}', '{"Early Payoff","CPR"}', 'AI forecasts cash-flow and MSR value sensitivity.', 'Used in pricing, pooling, and hedging strategies.', '{"Internal"}'),

        ('CPR (Conditional Prepayment Rate)', 'An annualized measure of prepayment speed for a pool of loans.', 'Analytics', 'Prepayment', '{"CPR"}', '{"Prepayment Speed","SMM"}', 'AI uses CPR assumptions in valuation and stress tests.', 'Impacts MSR valuation and MBS pricing.', '{"Investor Guideline"}'),

        ('SMM (Single Monthly Mortality)', 'A monthly measure of prepayment rate equivalent to CPR.', 'Analytics', 'Prepayment', '{"SMM"}', '{"CPR","Prepayment Speed"}', 'AI converts between SMM and CPR for modeling.', 'Used in tranche cash-flow analysis.', '{"Investor Guideline"}'),

        ('CDR (Conditional Default Rate)', 'The annualized rate at which loans in a pool default.', 'Analytics', 'Credit Risk', '{"CDR"}', '{"Delinquency","Loss Severity"}', 'AI uses CDR in portfolio and securitization models.', 'Supports stress testing and capital planning.', '{"Investor Guideline"}'),

        ('Loss Severity', 'The percentage of exposure lost after accounting for recoveries on defaulted loans.', 'Analytics', 'Credit Risk', '{"Severity"}', '{"CDR","Foreclosure"}', 'AI measures realized loss compared to UPB.', 'Used in pricing, reserving, and MSR analysis.', '{"Investor Guideline"}'),

        ('Vintage Analysis', 'Performance analysis based on origination period cohorts.', 'Analytics', 'Performance', '{"Vintage Curves"}', '{"CDR","CPR"}', 'AI evaluates performance of different origination cohorts.', 'Supports product, channel, and policy decisions.', '{"Internal"}'),

        # SECURITY, PRIVACY & KYC
        ('Know Your Customer (KYC)', 'Processes for verifying the identity of customers and assessing risk of illegal intent.', 'Compliance', 'AML/KYC', '{"KYC"}', '{"AML/BSA","Customer Identification Program (CIP)"}', 'AI checks KYC completion before loan approval.', 'Ensures identity documentation and screening are performed.', '{"AML/BSA"}'),

        ('Customer Identification Program (CIP)', 'Policies and procedures to collect and verify customer identity information.', 'Compliance', 'AML/KYC', '{"CIP"}', '{"KYC","OFAC Screening"}', 'AI verifies required data fields and documentary/non-documentary methods.', 'Blocks progression until CIP is satisfied.', '{"USA PATRIOT Act"}'),

        ('OFAC Screening', 'Checking borrowers against government lists of sanctioned individuals or entities.', 'Compliance', 'AML/KYC', '{"OFAC"}', '{"Sanctions","KYC"}', 'AI integrates OFAC screening with application intake.', 'Stops processing if a potential match is found until cleared.', '{"OFAC"}'),

        ('Suspicious Activity Report (SAR)', 'A confidential report filed with authorities when suspicious activity is detected.', 'Compliance', 'AML/KYC', '{"SAR"}', '{"Money Laundering","Fraud"}', 'AI flags unusual patterns that may warrant SAR review.', 'Supports compliance investigations and documentation.', '{"FinCEN"}'),

        ('Data Minimization', 'Collecting only the personal data necessary for a specific purpose.', 'Compliance', 'Privacy', '{"Minimal Data"}', '{"Privacy Policy"}', 'AI ensures prompts and workflows do not request unnecessary PII.', 'Reduces data risk and improves trust.', '{"Privacy Law"}'),

        ('Role-Based Access Control (RBAC)', 'A security model restricting data access based on user roles.', 'Technology', 'Security', '{"RBAC"}', '{"Least Privilege","User Permissions"}', 'AI respects RBAC when surfacing data and recommendations.', 'Ensures users see only information appropriate to their role.', '{"Internal","Security"}'),

        # AUTOMATED UNDERWRITING & AUS FINDINGS
        ('Desktop Underwriter (DU)', 'Fannie Mae''s automated underwriting system that evaluates loan risk and eligibility.', 'Underwriting', 'AUS', '{"DU","Desktop Originator"}', '{"Loan Product Advisor (LP)","AUS Findings"}', 'AI interprets DU findings and maps conditions to workflow tasks.', 'Drives condition generation and eligibility determination.', '{"GSE"}'),

        ('Loan Product Advisor (LP)', 'Freddie Mac''s automated underwriting system for risk assessment and eligibility.', 'Underwriting', 'AUS', '{"LP","Loan Prospector"}', '{"Desktop Underwriter (DU)","AUS Findings"}', 'AI parses LP feedback codes and recommendations.', 'Routes loans based on LP Accept/Caution results.', '{"GSE"}'),

        ('AUS Findings', 'The conditions, messages, and recommendations generated by an automated underwriting system.', 'Underwriting', 'AUS', '{"Findings","AUS Messages"}', '{"Desktop Underwriter (DU)","Loan Product Advisor (LP)"}', 'AI converts AUS findings into actionable conditions and doc requests.', 'Central to underwriting workflow and condition tracking.', '{"GSE"}'),

        ('Approve/Eligible', 'An AUS recommendation indicating the loan meets agency guidelines for approval.', 'Underwriting', 'AUS', '{"Approved","Eligible"}', '{"AUS Findings","Refer with Caution"}', 'AI recognizes approval status and routes for standard processing.', 'Triggers standard underwriting path with AUS conditions.', '{"GSE"}'),

        ('Refer with Caution', 'An AUS recommendation indicating the loan has risk factors requiring manual review.', 'Underwriting', 'AUS', '{"Refer","Caution"}', '{"Approve/Eligible","Manual Underwrite"}', 'AI flags files needing enhanced review or compensating factors.', 'Routes to senior underwriter or requires additional documentation.', '{"GSE"}'),

        ('Accept/Ineligible', 'An AUS result where the system accepts data but the loan is ineligible for standard delivery.', 'Underwriting', 'AUS', '{"Ineligible"}', '{"AUS Findings"}', 'AI identifies ineligibility reasons and suggests alternatives.', 'May route to non-agency or require guideline exception.', '{"GSE"}'),

        # RATE LOCK & PRICING
        ('Lock Period', 'The number of days a rate lock is guaranteed, typically 15, 30, 45, or 60 days.', 'Secondary Market', 'Rate Lock', '{"Lock Term"}', '{"Rate Lock","Lock Extension"}', 'AI recommends lock periods based on estimated closing timeline.', 'Impacts pricing and extension risk management.', '{"Internal"}'),

        ('Lock Extension', 'An extension of the rate lock period beyond the original term, usually for a fee.', 'Secondary Market', 'Rate Lock', '{"Extension"}', '{"Lock Period","Lock Expiration"}', 'AI calculates extension costs and alerts before expiration.', 'Triggers extension requests and fee calculations.', '{"Internal"}'),

        ('Lock Renegotiation', 'A change to lock terms due to loan amount, program, or other material changes.', 'Secondary Market', 'Rate Lock', '{"Relock","Renegotiation"}', '{"Rate Lock","Worst-Case Pricing"}', 'AI determines when relocks are required and calculates pricing impact.', 'Ensures accurate pricing after loan changes.', '{"Internal"}'),

        ('Worst-Case Pricing', 'The highest possible rate/fee combination used for disclosure purposes when final terms are uncertain.', 'Compliance', 'Disclosures', '{"Worst Case"}', '{"Loan Estimate","Lock Renegotiation"}', 'AI applies worst-case logic for initial disclosures.', 'Ensures tolerance compliance on LE/CD.', '{"TRID"}'),

        ('Float Down', 'An option allowing the borrower to reduce their locked rate if market rates improve.', 'Secondary Market', 'Rate Lock', '{"Float-Down Option"}', '{"Rate Lock","Market Movement"}', 'AI monitors rates and alerts when float-down may benefit borrower.', 'Triggers float-down execution within policy parameters.', '{"Internal"}'),

        ('Lock Confirmation', 'Documentation confirming the terms of a rate lock between lender and borrower.', 'Secondary Market', 'Rate Lock', '{"Rate Lock Confirmation"}', '{"Rate Lock","Loan Estimate"}', 'AI generates lock confirmations with accurate terms.', 'Provides audit trail for locked pricing.', '{"Internal"}'),

        ('LLPA (Loan-Level Price Adjustment)', 'Risk-based pricing adjustments applied to loans based on credit score, LTV, property type, and other factors.', 'Secondary Market', 'Pricing', '{"LLPA","Price Adjustment"}', '{"Credit Score","LTV","Pricing"}', 'AI calculates cumulative LLPAs for accurate rate quotes.', 'Drives pricing transparency and margin analysis.', '{"GSE"}'),

        # SPECIFIC LOAN PROGRAMS
        ('HomeReady', 'A Fannie Mae affordable lending program with flexible income and down payment options.', 'Origination', 'Affordable Lending', '{"HomeReady Mortgage"}', '{"Home Possible","DPA"}', 'AI checks HomeReady eligibility including income limits and geography.', 'Triggers program-specific disclosures and requirements.', '{"GSE"}'),

        ('Home Possible', 'A Freddie Mac affordable lending program for low-to-moderate income borrowers.', 'Origination', 'Affordable Lending', '{"Home Possible Mortgage"}', '{"HomeReady","DPA"}', 'AI validates income limits and census tract eligibility.', 'Routes to affordable lending workflow with reduced MI options.', '{"GSE"}'),

        ('Down Payment Assistance (DPA)', 'Programs providing grants or secondary financing to help borrowers with down payment and closing costs.', 'Origination', 'Affordable Lending', '{"DPA","Down Payment Grant"}', '{"HomeReady","Home Possible","Community Seconds"}', 'AI identifies DPA eligibility based on income, location, and program rules.', 'Coordinates with DPA providers and layered financing.', '{"State/Local"}'),

        ('Community Seconds', 'Subordinate financing from nonprofits or government agencies to assist with down payment.', 'Origination', 'Affordable Lending', '{"Community Second Mortgage"}', '{"DPA","CLTV"}', 'AI evaluates CLTV with community seconds and program compatibility.', 'Requires coordination with second-lien providers.', '{"GSE"}'),

        ('Bond Program', 'State or local housing finance agency programs offering below-market rates or assistance.', 'Origination', 'Affordable Lending', '{"HFA Program","State Bond"}', '{"DPA","First-Time Homebuyer"}', 'AI checks bond program eligibility including income and purchase price limits.', 'Routes to HFA-specific underwriting and compliance.', '{"State/Local"}'),

        ('203(k) Standard', 'An FHA renovation loan for substantial rehabilitation projects over $35,000.', 'Origination', 'Renovation', '{"Full 203k"}', '{"203(k) Limited","Renovation Loan"}', 'AI applies HUD consultant and draw requirements for standard 203k.', 'Requires detailed work write-up and multiple inspections.', '{"HUD"}'),

        ('203(k) Limited', 'An FHA renovation loan for minor repairs under $35,000 with simplified requirements.', 'Origination', 'Renovation', '{"Streamline 203k"}', '{"203(k) Standard","Renovation Loan"}', 'AI determines if repairs qualify for limited vs standard 203k.', 'Simplified process without HUD consultant requirement.', '{"HUD"}'),

        ('HomeStyle Renovation', 'A Fannie Mae renovation loan allowing financing of repairs with the purchase or refinance.', 'Origination', 'Renovation', '{"HomeStyle"}', '{"Renovation Loan","203(k)"}', 'AI evaluates ARV and renovation scope for HomeStyle eligibility.', 'Coordinates draws, inspections, and contractor documentation.', '{"GSE"}'),

        # ASSETS & RESERVES
        ('Gift Funds', 'Money given to a borrower by a family member or other acceptable donor for down payment or closing costs.', 'Underwriting', 'Assets', '{"Gift","Gifted Funds"}', '{"Gift Letter","Gift of Equity"}', 'AI verifies gift source, relationship, and documentation requirements.', 'Triggers gift letter collection and donor verification.', '{"GSE","FHA"}'),

        ('Gift Letter', 'A signed statement from the donor confirming the gift amount and that no repayment is expected.', 'Underwriting', 'Assets', '{"Gift Documentation"}', '{"Gift Funds"}', 'AI validates gift letter content meets agency requirements.', 'Required documentation for using gift funds.', '{"GSE","FHA"}'),

        ('Gift of Equity', 'A gift from a seller (usually family) representing the difference between sale price and market value.', 'Underwriting', 'Assets', '{"Equity Gift"}', '{"Gift Funds","Family Transaction"}', 'AI calculates equity gift and applies family transaction rules.', 'Requires specific documentation and appraisal considerations.', '{"GSE"}'),

        ('Reserves', 'Liquid assets remaining after closing, measured in months of mortgage payments.', 'Underwriting', 'Assets', '{"Months of Reserves","Post-Close Reserves"}', '{"Assets","Post-Close Liquidity"}', 'AI calculates required reserves based on property type and risk factors.', 'Determines if borrower meets reserve requirements.', '{"GSE"}'),

        ('Post-Close Liquidity', 'The amount of liquid assets a borrower will have after paying down payment and closing costs.', 'Underwriting', 'Assets', '{"Remaining Assets"}', '{"Reserves","Cash to Close"}', 'AI evaluates post-close liquidity as a compensating factor.', 'Supports risk assessment for borderline files.', '{"GSE"}'),

        ('Large Deposit', 'A deposit that exceeds a percentage of income and requires sourcing documentation.', 'Underwriting', 'Assets', '{"Unusual Deposit"}', '{"Bank Statements","Asset Documentation"}', 'AI flags large deposits for explanation and paper trail.', 'Triggers additional documentation requests.', '{"GSE","FHA"}'),

        ('Paper Trail', 'Documentation showing the movement of funds from source to borrower''s account.', 'Underwriting', 'Assets', '{"Funds Trail","Source of Funds"}', '{"Large Deposit","Gift Funds"}', 'AI tracks fund movements and identifies gaps in documentation.', 'Ensures compliance with asset sourcing requirements.', '{"GSE"}'),

        # CREDIT EVENTS & SEASONING
        ('Bankruptcy Seasoning', 'The waiting period required after bankruptcy discharge before loan eligibility.', 'Underwriting', 'Credit Events', '{"BK Seasoning"}', '{"Chapter 7","Chapter 13","Re-established Credit"}', 'AI calculates seasoning from discharge date per program guidelines.', 'Determines eligibility and may require extenuating circumstances.', '{"GSE","FHA","VA"}'),

        ('Foreclosure Seasoning', 'The waiting period required after foreclosure before loan eligibility.', 'Underwriting', 'Credit Events', '{"FC Seasoning"}', '{"Housing Event","Re-established Credit"}', 'AI tracks foreclosure date and required waiting period by program.', 'May allow reduced seasoning with extenuating circumstances.', '{"GSE","FHA","VA"}'),

        ('Short Sale Seasoning', 'The waiting period required after a short sale before loan eligibility.', 'Underwriting', 'Credit Events', '{"Short Sale Waiting Period"}', '{"Housing Event","Deed-in-Lieu"}', 'AI determines seasoning based on deficiency and program rules.', 'Impacts timing of new loan application.', '{"GSE","FHA"}'),

        ('Deed-in-Lieu', 'A foreclosure alternative where the borrower transfers property ownership to the lender.', 'Underwriting', 'Credit Events', '{"DIL","Deed in Lieu of Foreclosure"}', '{"Short Sale","Foreclosure Seasoning"}', 'AI applies deed-in-lieu seasoning requirements similar to foreclosure.', 'Requires credit re-establishment documentation.', '{"GSE"}'),

        ('Housing Event', 'A significant derogatory event such as foreclosure, short sale, or deed-in-lieu.', 'Underwriting', 'Credit Events', '{"Major Derogatory"}', '{"Bankruptcy Seasoning","Foreclosure Seasoning"}', 'AI identifies housing events and applies appropriate seasoning rules.', 'Central to eligibility determination for prior homeowners.', '{"GSE"}'),

        ('Re-established Credit', 'Credit history rebuilt after a significant derogatory event demonstrating responsible use.', 'Underwriting', 'Credit Events', '{"Credit Re-establishment"}', '{"Housing Event","Tradelines"}', 'AI evaluates new tradelines, payment history, and time since event.', 'Required to show creditworthiness after derogatory events.', '{"GSE","FHA"}'),

        # SPECIFIC FORMS
        ('1003 (Uniform Residential Loan Application)', 'The standard mortgage application form used to collect borrower information.', 'Processing', 'Forms', '{"URLA","Loan Application"}', '{"Application Date","Borrower Information"}', 'AI extracts and validates data from 1003 for underwriting.', 'Foundation document for all loan processing.', '{"GSE"}'),

        ('1004 (URAR)', 'The Uniform Residential Appraisal Report for single-family properties.', 'Collateral', 'Forms', '{"URAR","Appraisal Report"}', '{"Appraisal","1004D"}', 'AI parses 1004 data for value, condition, and comparables analysis.', 'Standard appraisal form for most residential loans.', '{"GSE"}'),

        ('1005 (Verification of Employment)', 'The standard form used to verify employment status, income, and probability of continuance.', 'Processing', 'Forms', '{"VOE Form"}', '{"VOE","Income Verification"}', 'AI validates 1005 completeness and income calculation accuracy.', 'Key document for employment and income verification.', '{"GSE"}'),

        ('1008 (Transmittal Summary)', 'A summary form transmitted with the loan file to the investor or insurer.', 'Processing', 'Forms', '{"Transmittal","Loan Summary"}', '{"Underwriting","Investor Delivery"}', 'AI populates 1008 with loan characteristics for delivery.', 'Required for agency and investor submissions.', '{"GSE"}'),

        ('4506-C (Request for Transcript of Tax Return)', 'IRS form authorizing the lender to obtain tax return transcripts.', 'Processing', 'Forms', '{"4506-C","Tax Transcript Request"}', '{"Tax Returns","Income Verification"}', 'AI ensures 4506-C is signed and submitted for transcript validation.', 'Used to verify reported income against IRS records.', '{"IRS"}'),

        ('SSA-89 (Social Security Verification)', 'Form authorizing verification of Social Security number with the SSA.', 'Processing', 'Forms', '{"SSA-89","SSN Verification"}', '{"Identity Verification","Fraud Prevention"}', 'AI triggers SSA-89 for identity and SSN validation.', 'Helps prevent identity fraud and synthetic identities.', '{"SSA"}'),

        # CHANNELS & BUSINESS MODELS
        ('Retail Lending', 'A business model where the lender originates loans directly with consumers through employed loan officers.', 'Operations', 'Channels', '{"Retail","Direct Lending"}', '{"Wholesale","Correspondent"}', 'AI recognizes retail channel for compensation and compliance rules.', 'Drives LO comp tracking and consumer-direct workflows.', '{"Internal"}'),

        ('Wholesale Lending', 'A business model where loans are originated through independent mortgage brokers.', 'Operations', 'Channels', '{"Wholesale","Broker Channel"}', '{"Retail Lending","Correspondent"}', 'AI applies broker comp rules and disclosure requirements.', 'Routes to broker-specific pricing and compliance workflows.', '{"RESPA","LO Comp"}'),

        ('Correspondent Lending', 'A business model where smaller lenders originate and close loans, then sell them to larger investors.', 'Operations', 'Channels', '{"Correspondent","Corr"}', '{"Wholesale","Delegated"}', 'AI determines delegated vs non-delegated correspondent rules.', 'Manages purchase timelines and trailing document requirements.', '{"Investor Guideline"}'),

        ('Consumer Direct', 'A channel where loans are originated through online/phone contact without in-person interaction.', 'Operations', 'Channels', '{"Direct-to-Consumer","Online Lending"}', '{"Retail Lending"}', 'AI supports digital workflows and e-consent processes.', 'Optimized for self-service and rapid response.', '{"Internal"}'),

        ('Mini-Correspondent', 'A hybrid model where brokers close loans in their name but immediately sell to a sponsor.', 'Operations', 'Channels', '{"Mini-Corr"}', '{"Correspondent","Wholesale"}', 'AI tracks mini-corr specific requirements and timelines.', 'Combines broker flexibility with closed-loan delivery.', '{"Investor Guideline"}'),

        # INVESTOR & AGENCY
        ('Fannie Mae', 'A government-sponsored enterprise that buys and securitizes conventional mortgages.', 'Secondary Market', 'Investors', '{"FNMA","Federal National Mortgage Association"}', '{"Freddie Mac","Conforming Loan"}', 'AI applies Fannie Mae guidelines and selling guide requirements.', 'Primary investor for conventional conforming loans.', '{"GSE"}'),

        ('Freddie Mac', 'A government-sponsored enterprise that buys and securitizes conventional mortgages.', 'Secondary Market', 'Investors', '{"FHLMC","Federal Home Loan Mortgage Corporation"}', '{"Fannie Mae","Conforming Loan"}', 'AI applies Freddie Mac guidelines and eligibility requirements.', 'Alternative agency investor for conventional loans.', '{"GSE"}'),

        ('Ginnie Mae', 'A government agency that guarantees MBS backed by FHA, VA, and USDA loans.', 'Secondary Market', 'Investors', '{"GNMA","Government National Mortgage Association"}', '{"FHA Loan","VA Loan"}', 'AI routes government loans to Ginnie Mae securitization.', 'Provides liquidity for government-insured loans.', '{"HUD"}'),

        ('Investor Overlay', 'Additional requirements imposed by an investor beyond standard agency guidelines.', 'Underwriting', 'Guidelines', '{"Overlay"}', '{"Fannie Mae","Freddie Mac"}', 'AI applies overlays on top of base agency guidelines.', 'May restrict credit scores, DTI, or documentation requirements.', '{"Investor Guideline"}'),

        ('Delegated vs Non-Delegated', 'Authority levels determining if a correspondent can underwrite without investor review.', 'Operations', 'Correspondent', '{"Delegated Underwriting"}', '{"Correspondent"}', 'AI routes files based on delegated authority and risk tier.', 'Impacts turn time and underwriting responsibility.', '{"Investor Guideline"}'),

        ('Purchase Advice', 'Notification from an investor that a loan has been purchased and funded.', 'Post-Closing', 'Delivery', '{"Purchase Confirmation"}', '{"Investor Delivery","Funding"}', 'AI reconciles purchase advice with expected proceeds.', 'Confirms loan sale completion and triggers accounting entries.', '{"Internal"}'),

        # POST-CLOSING
        ('Trailing Documents', 'Documents received after closing that must be delivered to complete the loan file.', 'Post-Closing', 'Documents', '{"Trailing Docs","Post-Close Docs"}', '{"Final Title Policy","Recorded Mortgage"}', 'AI tracks outstanding trailing docs and delivery deadlines.', 'Ensures complete file delivery to investor.', '{"Investor Guideline"}'),

        ('Final Title Policy', 'The title insurance policy issued after recording, confirming clear title and lien position.', 'Post-Closing', 'Title', '{"Title Policy"}', '{"Title Commitment","Trailing Documents"}', 'AI monitors receipt of final policy for file completion.', 'Required trailing document for investor delivery.', '{"State Law"}'),

        ('Recorded Mortgage', 'The mortgage or deed of trust after it has been recorded with the county recorder.', 'Post-Closing', 'Documents', '{"Recorded DOT","Recorded Security Instrument"}', '{"Trailing Documents","Lien Position"}', 'AI tracks recording confirmation and document return.', 'Confirms lien perfection and provides final loan number.', '{"State Law"}'),

        ('Investor Delivery', 'The process of submitting the complete loan package to the purchasing investor.', 'Post-Closing', 'Delivery', '{"Loan Delivery","File Delivery"}', '{"Purchase Advice","Trailing Documents"}', 'AI monitors delivery deadlines and missing document lists.', 'Triggers delivery workflows and exception management.', '{"Investor Guideline"}'),

        ('Stip Clearing', 'The process of satisfying outstanding stipulations or conditions post-closing.', 'Post-Closing', 'Conditions', '{"Post-Close Stips","Outstanding Conditions"}', '{"Trailing Documents","Investor Delivery"}', 'AI prioritizes stips by investor deadline and severity.', 'Prevents purchase suspensions and repurchase risk.', '{"Investor Guideline"}'),

        # ARM INDEXES
        ('SOFR (Secured Overnight Financing Rate)', 'A benchmark interest rate based on overnight Treasury repo transactions, replacing LIBOR.', 'Origination', 'ARM Index', '{"SOFR"}', '{"ARM","Index + Margin"}', 'AI uses SOFR for ARM rate calculations and adjustment projections.', 'Standard index for new ARM products.', '{"Federal Reserve"}'),

        ('Treasury Index', 'A benchmark rate based on U.S. Treasury securities used for some ARM products.', 'Origination', 'ARM Index', '{"CMT","Constant Maturity Treasury"}', '{"ARM","SOFR"}', 'AI calculates ARM adjustments based on Treasury index values.', 'Alternative index for certain ARM products.', '{"Federal Reserve"}'),

        ('LIBOR (Legacy)', 'The former London Interbank Offered Rate used as an ARM index, now discontinued.', 'Origination', 'ARM Index', '{"LIBOR"}', '{"SOFR","ARM"}', 'AI handles legacy LIBOR ARMs transitioning to replacement indexes.', 'Requires servicing updates for existing LIBOR-based loans.', '{"Regulatory"}'),

        ('Adjustment Caps', 'Limits on rate changes at initial adjustment, periodic adjustments, and over the life of an ARM.', 'Origination', 'ARM', '{"Rate Caps","Cap Structure"}', '{"ARM","ARM Adjustment"}', 'AI applies cap structures to payment projections and worst-case scenarios.', 'Disclosed in ARM program descriptions and notes.', '{"TILA"}'),

        ('Conversion Option', 'An ARM feature allowing the borrower to convert to a fixed rate under specified conditions.', 'Origination', 'ARM', '{"ARM Conversion"}', '{"ARM","Fixed-Rate Mortgage"}', 'AI tracks conversion windows and calculates conversion pricing.', 'Triggers borrower notification during conversion periods.', '{"TILA"}'),

        # QUALITY & EARLY DEFAULT
        ('EPD (Early Payment Default)', 'A loan that becomes 60+ days delinquent within the first six payments.', 'QC', 'Performance', '{"EPD","Early Default"}', '{"FPD","Repurchase Request"}', 'AI monitors early payment performance for quality and fraud signals.', 'Triggers enhanced review and potential repurchase exposure.', '{"Investor Guideline"}'),

        ('FPD (First Payment Default)', 'Failure to make the first scheduled payment on a new loan.', 'QC', 'Performance', '{"FPD","First Payment Miss"}', '{"EPD","Fraud"}', 'AI flags FPD as high-risk fraud or quality indicator.', 'Requires immediate investigation and investor notification.', '{"Investor Guideline"}'),

        ('Compensating Factors', 'Positive attributes that offset risk factors and support loan approval.', 'Underwriting', 'Risk Assessment', '{"Comp Factors"}', '{"Reserves","Residual Income","Credit Score"}', 'AI identifies and documents compensating factors for borderline files.', 'Supports approval with higher DTI or lower credit scores.', '{"GSE","FHA"}'),

        ('Credit Exception', 'An approval outside standard credit guidelines requiring additional justification.', 'Underwriting', 'Exceptions', '{"Exception","Guideline Exception"}', '{"Compensating Factors","Overlay"}', 'AI documents exception rationale and required approvals.', 'Routes to authorized exception approvers.', '{"Internal"}'),

        ('Guideline Variance', 'A documented deviation from standard underwriting guidelines.', 'Underwriting', 'Exceptions', '{"Variance","Policy Exception"}', '{"Credit Exception","Compensating Factors"}', 'AI tracks variances for QC review and trend analysis.', 'Requires management approval and documentation.', '{"Internal"}'),

        # STATE-SPECIFIC
        ('Attorney State', 'A state where an attorney must conduct or supervise real estate closings.', 'Closing', 'State Law', '{"Attorney Closing State"}', '{"Title State","Closing Agent"}', 'AI applies attorney state requirements to closing workflows.', 'Impacts closing costs, timelines, and document preparation.', '{"State Law"}'),

        ('Title State', 'A state where title companies typically handle closings without attorney requirement.', 'Closing', 'State Law', '{"Title Company State"}', '{"Attorney State","Title Agent"}', 'AI routes closings to appropriate settlement agents by state.', 'Standard closing process in most states.', '{"State Law"}'),

        ('Judicial vs Non-Judicial Foreclosure', 'Whether foreclosure requires court proceedings (judicial) or follows statutory process (non-judicial).', 'Servicing', 'State Law', '{"Foreclosure Type"}', '{"Foreclosure","Notice of Default (NOD)"}', 'AI applies state-specific foreclosure timelines and processes.', 'Impacts loss severity projections and timeline management.', '{"State Law"}'),

        ('Recording Fees', 'Government fees charged to record mortgage documents with the county.', 'Closing', 'Fees', '{"Recording Charges"}', '{"Closing Costs","Government Fees"}', 'AI calculates recording fees based on state/county schedules.', 'Disclosed on LE/CD as government recording charges.', '{"State Law"}'),

        ('Transfer Tax', 'A state or local tax on the transfer of real property ownership.', 'Closing', 'Fees', '{"Stamp Tax","Documentary Tax","Mansion Tax"}', '{"Closing Costs","Government Fees"}', 'AI calculates transfer taxes based on sale price and location.', 'Varies significantly by state and locality.', '{"State Law"}'),

        # TECHNOLOGY/SYSTEMS
        ('LOS (Loan Origination System)', 'Software used to manage the mortgage process from application through closing.', 'Technology', 'Systems', '{"LOS","Origination Platform"}', '{"Encompass","POS"}', 'AI integrates with LOS for data exchange and workflow automation.', 'Central system of record for loan processing.', '{"Internal"}'),

        ('POS (Point of Sale)', 'A borrower-facing application portal for loan applications and document upload.', 'Technology', 'Systems', '{"Point of Sale","Application Portal"}', '{"Borrower Portal","LOS"}', 'AI personalizes POS experience based on loan scenario.', 'First touchpoint for digital mortgage experience.', '{"Internal"}'),

        ('Pricing Engine', 'Software that calculates loan pricing based on rate sheets, LLPAs, and loan characteristics.', 'Technology', 'Systems', '{"Pricing System","Rate Engine"}', '{"LLPA","Rate Lock"}', 'AI uses pricing engine data for rate quotes and lock recommendations.', 'Ensures accurate and compliant pricing.', '{"Internal"}'),

        ('Document Management System', 'Software for storing, organizing, and retrieving loan documents.', 'Technology', 'Systems', '{"DMS","Doc Management"}', '{"eVault","Image Repository"}', 'AI interfaces with DMS for document classification and retrieval.', 'Supports compliance, audit, and investor delivery.', '{"Internal"}'),

        ('Encompass', 'A widely-used loan origination system by ICE Mortgage Technology.', 'Technology', 'Systems', '{"Encompass LOS"}', '{"LOS","Loan Origination System"}', 'AI integrates with Encompass APIs for data and workflow automation.', 'Common LOS platform requiring specific integration patterns.', '{"Internal"}'),

        # MORTGAGE INSURANCE SPECIFICS
        ('Private Mortgage Insurance (PMI)', 'Insurance required on conventional loans with LTV over 80%, protecting the lender against default.', 'Origination', 'Mortgage Insurance', '{"PMI","MI"}', '{"BPMI","LPMI","MI Cancellation"}', 'AI calculates PMI premiums and determines cancellation eligibility.', 'Impacts monthly payment, DTI, and borrower cost analysis.', '{"HPA"}'),

        ('Lender-Paid MI (LPMI)', 'Mortgage insurance where the lender pays the premium, typically in exchange for a higher interest rate.', 'Origination', 'Mortgage Insurance', '{"LPMI"}', '{"BPMI","PMI"}', 'AI compares LPMI vs BPMI for optimal borrower outcome.', 'Results in higher rate but no separate MI payment.', '{"HPA"}'),

        ('Borrower-Paid MI (BPMI)', 'Traditional mortgage insurance where the borrower pays monthly or upfront premiums.', 'Origination', 'Mortgage Insurance', '{"BPMI"}', '{"LPMI","PMI"}', 'AI calculates monthly BPMI and factors into qualifying ratios.', 'Most common MI structure with cancellation rights.', '{"HPA"}'),

        ('Split Premium MI', 'A mortgage insurance structure combining upfront and monthly premium payments.', 'Origination', 'Mortgage Insurance', '{"Split Premium"}', '{"BPMI","Single Premium"}', 'AI evaluates split premium for lower monthly cost scenarios.', 'Balances upfront cost with ongoing payment reduction.', '{"Investor Guideline"}'),

        ('MI Cancellation', 'The termination of mortgage insurance when LTV reaches required thresholds.', 'Servicing', 'Mortgage Insurance', '{"PMI Cancellation","MI Termination"}', '{"HPA","LTV"}', 'AI tracks LTV and notifies borrowers of cancellation eligibility.', 'Triggers borrower notification and automatic termination at 78% LTV.', '{"HPA"}'),

        ('MI Certificate', 'Documentation from the MI company confirming coverage terms and certificate number.', 'Processing', 'Mortgage Insurance', '{"MI Cert","Certificate of Insurance"}', '{"PMI","MI Commitment"}', 'AI validates MI certificate receipt and terms match loan data.', 'Required for closing and investor delivery.', '{"Investor Guideline"}'),

        ('Single Premium MI', 'Mortgage insurance paid entirely upfront at closing, either by borrower or financed.', 'Origination', 'Mortgage Insurance', '{"Single Premium"}', '{"BPMI","Split Premium"}', 'AI calculates financed single premium impact on loan amount and LTV.', 'No monthly MI payment but may not be refundable.', '{"Investor Guideline"}'),

        # LOAN LIMITS & CONFORMING
        ('Conforming Loan Limit', 'The maximum loan amount eligible for purchase by Fannie Mae or Freddie Mac.', 'Origination', 'Loan Limits', '{"Conforming Limit","Loan Limit"}', '{"High-Balance Loan","Jumbo Loan"}', 'AI applies current year conforming limits by county.', 'Determines agency eligibility and pricing tier.', '{"FHFA"}'),

        ('High-Balance Loan', 'A conforming loan exceeding standard limits but within high-cost area limits.', 'Origination', 'Loan Limits', '{"Super Conforming","High-Cost Area Loan"}', '{"Conforming Loan Limit","Jumbo Loan"}', 'AI identifies high-balance counties and applies appropriate LLPAs.', 'Agency-eligible but with pricing adjustments.', '{"GSE"}'),

        ('Jumbo Loan', 'A loan exceeding conforming limits that must be sold to non-agency investors.', 'Origination', 'Loan Limits', '{"Non-Conforming","Jumbo Mortgage"}', '{"Conforming Loan Limit","High-Balance Loan"}', 'AI routes jumbo loans to appropriate investors with specific guidelines.', 'Typically requires stronger credit profile and larger reserves.', '{"Investor Guideline"}'),

        ('Non-Conforming Loan', 'Any loan that does not meet GSE purchase criteria due to size, documentation, or other factors.', 'Origination', 'Loan Limits', '{"Non-Conforming"}', '{"Jumbo Loan","Non-QM Loan"}', 'AI identifies non-conforming characteristics and routes appropriately.', 'Requires non-agency investor or portfolio retention.', '{"Investor Guideline"}'),

        # APPRAISAL TECHNOLOGY & REVIEW
        ('UCDP (Uniform Collateral Data Portal)', 'Fannie Mae and Freddie Mac''s portal for electronic appraisal submission and review.', 'Collateral', 'Technology', '{"UCDP"}', '{"EAD","Appraisal"}', 'AI monitors UCDP submission status and SSR results.', 'Required for agency loan delivery.', '{"GSE"}'),

        ('EAD (Encompass Appraisal Direct)', 'Integration between Encompass LOS and appraisal management for ordering and delivery.', 'Technology', 'Appraisal', '{"EAD"}', '{"UCDP","AMC"}', 'AI tracks appraisal orders and delivery through EAD integration.', 'Streamlines appraisal workflow within LOS.', '{"Internal"}'),

        ('Reconsideration of Value (ROV)', 'A formal request for the appraiser to reconsider value based on additional comparables or corrections.', 'Collateral', 'Appraisal Review', '{"ROV","Value Appeal"}', '{"Appraisal","Comparable Sales"}', 'AI identifies when ROV may be warranted based on data analysis.', 'Must include valid comparable sales or factual corrections.', '{"AIR"}'),

        ('Appraisal Independence Requirements (AIR)', 'Regulations ensuring appraisers are free from undue influence in the valuation process.', 'Compliance', 'Appraisal', '{"AIR"}', '{"Appraisal","AMC"}', 'AI enforces AIR compliance in appraisal ordering and communication.', 'Prohibits value pressure and ensures appraiser independence.', '{"Dodd-Frank"}'),

        ('AMC (Appraisal Management Company)', 'A third-party company that manages appraisal orders and appraiser panels for lenders.', 'Collateral', 'Vendors', '{"AMC"}', '{"Appraisal","AIR"}', 'AI interfaces with AMCs for ordering, tracking, and delivery.', 'Ensures compliance with independence requirements.', '{"State Law"}'),

        # TITLE & LEGAL
        ('Chain of Title', 'The sequence of historical transfers of property ownership.', 'Processing', 'Title', '{"Title Chain"}', '{"Title Commitment","Cloud on Title"}', 'AI reviews chain of title for gaps or irregularities.', 'Must show clear ownership history for title insurance.', '{"State Law"}'),

        ('Cloud on Title', 'Any claim, lien, or encumbrance that may impair the owner''s title to property.', 'Processing', 'Title', '{"Title Defect"}', '{"Chain of Title","Quiet Title Action"}', 'AI identifies clouds that must be cleared before closing.', 'Requires resolution or exception in title policy.', '{"State Law"}'),

        ('Easement', 'A right to use another''s property for a specific purpose, such as access or utilities.', 'Collateral', 'Legal', '{"Right of Way"}', '{"Encumbrance","Title Commitment"}', 'AI evaluates easement impact on property use and value.', 'Typically shown as exception in title commitment.', '{"State Law"}'),

        ('Encumbrance', 'Any claim or liability attached to property that may affect its value or transferability.', 'Collateral', 'Legal', '{"Lien","Restriction"}', '{"Easement","Cloud on Title"}', 'AI identifies encumbrances that affect collateral value or lien position.', 'Must be evaluated for impact on lending decision.', '{"State Law"}'),

        ('Lis Pendens', 'A recorded notice indicating pending litigation affecting title to property.', 'Processing', 'Title', '{"Pending Litigation"}', '{"Cloud on Title","Title Commitment"}', 'AI flags lis pendens as serious title issue requiring resolution.', 'Typically must be resolved before closing.', '{"State Law"}'),

        ('Mechanic''s Lien', 'A lien filed by contractors or suppliers for unpaid work or materials on property.', 'Processing', 'Title', '{"Construction Lien","Materialman''s Lien"}', '{"Encumbrance","Lien Waiver"}', 'AI tracks mechanic''s lien risk on renovation and construction loans.', 'Requires lien waivers to protect lien position.', '{"State Law"}'),

        ('Quiet Title Action', 'A lawsuit to establish ownership and remove clouds on title.', 'Processing', 'Title', '{"Quiet Title"}', '{"Cloud on Title","Chain of Title"}', 'AI identifies when quiet title may be needed for clear conveyance.', 'May delay closing until court resolution.', '{"State Law"}'),

        # LOAN TERMS & STRUCTURE
        ('15-Year Fixed', 'A fixed-rate mortgage with a 15-year amortization period.', 'Origination', 'Loan Terms', '{"15-Year","15 Yr Fixed"}', '{"30-Year Fixed","Loan Term"}', 'AI calculates higher payments but significant interest savings.', 'Popular for refinance and wealth-building borrowers.', '{"TILA"}'),

        ('30-Year Fixed', 'A fixed-rate mortgage with a 30-year amortization period.', 'Origination', 'Loan Terms', '{"30-Year","30 Yr Fixed"}', '{"15-Year Fixed","Loan Term"}', 'AI uses 30-year as standard for qualifying and comparison.', 'Most common mortgage product in the US.', '{"TILA"}'),

        ('40-Year Term', 'An extended mortgage term of 40 years, typically for payment reduction.', 'Origination', 'Loan Terms', '{"40-Year Mortgage"}', '{"30-Year Fixed","Loan Modification"}', 'AI evaluates 40-year terms for affordability in modifications.', 'May be used for loss mitigation or Non-QM products.', '{"Investor Guideline"}'),

        ('Balloon Mortgage', 'A loan with a large final payment due at the end of a shorter term.', 'Origination', 'Loan Terms', '{"Balloon Payment"}', '{"ARM","Non-QM"}', 'AI identifies balloon features for disclosure and QM determination.', 'Not permitted for QM loans due to risky feature.', '{"QM/ATR"}'),

        ('Biweekly Payment', 'A payment schedule with payments every two weeks, resulting in extra annual payments.', 'Servicing', 'Payments', '{"Biweekly Mortgage"}', '{"Monthly Payment","Accelerated Payoff"}', 'AI calculates accelerated payoff and interest savings.', 'Results in 13 monthly payments per year.', '{"Internal"}'),

        ('Simple Interest Mortgage', 'A loan where interest accrues daily on the outstanding principal balance.', 'Servicing', 'Interest', '{"Daily Simple Interest"}', '{"Per Diem Interest","Payment Application"}', 'AI calculates daily interest accrual for payment timing impact.', 'Early payments reduce interest; late payments increase it.', '{"TILA"}'),

        # CONDITION TYPES
        ('Prior to Documents (PTD)', 'Conditions that must be satisfied before loan documents can be drawn.', 'Underwriting', 'Conditions', '{"PTD","Pre-Doc Conditions"}', '{"Prior to Funding","Clear to Close"}', 'AI prioritizes PTD conditions for timely doc preparation.', 'Must be cleared before final CD and doc drawing.', '{"Internal"}'),

        ('Prior to Funding (PTF)', 'Conditions that must be satisfied before the loan can fund.', 'Underwriting', 'Conditions', '{"PTF","Funding Conditions"}', '{"Prior to Documents","Closing"}', 'AI tracks PTF items for funding day clearance.', 'Last conditions before wire release.', '{"Internal"}'),

        ('Prior to Purchase (PTP)', 'Conditions that must be satisfied before investor will purchase the loan.', 'Post-Closing', 'Conditions', '{"PTP","Post-Close Conditions"}', '{"Investor Delivery","Trailing Documents"}', 'AI monitors PTP deadlines to prevent purchase suspensions.', 'Failure to clear may result in repurchase.', '{"Investor Guideline"}'),

        ('Suspense Condition', 'A condition placed in suspense pending additional information or documentation.', 'Underwriting', 'Conditions', '{"Suspended","Pending Review"}', '{"Conditions","Underwriting"}', 'AI tracks suspense reasons and required follow-up.', 'Indicates incomplete information for decision.', '{"Internal"}'),

        ('Waived Condition', 'A condition removed by authorized personnel without requiring satisfaction.', 'Underwriting', 'Conditions', '{"Waiver"}', '{"Conditions","Credit Exception"}', 'AI documents waiver authority and rationale for audit trail.', 'Requires appropriate approval level.', '{"Internal"}'),

        # BORROWER SITUATIONS
        ('Non-Occupant Co-Borrower', 'A co-borrower who will not occupy the property but is on the loan for qualifying purposes.', 'Underwriting', 'Borrower Types', '{"Non-Occ Co-Borrower","NOCB"}', '{"Co-Signer","Occupancy"}', 'AI applies non-occupant co-borrower rules for income and liability treatment.', 'Common for family assistance on purchases.', '{"GSE","FHA"}'),

        ('Co-Signer', 'A party who signs the note but typically not on title, providing additional credit support.', 'Underwriting', 'Borrower Types', '{"Cosigner"}', '{"Non-Occupant Co-Borrower","Guarantor"}', 'AI distinguishes co-signer treatment from co-borrower for liability.', 'Less common than non-occupant co-borrower structure.', '{"Investor Guideline"}'),

        ('Power of Attorney (POA)', 'Legal authority for one person to act on behalf of another in signing documents.', 'Closing', 'Legal', '{"POA","Attorney-in-Fact"}', '{"POA Closing","Trust"}', 'AI validates POA acceptability per investor and state requirements.', 'Requires specific language and may need investor approval.', '{"Investor Guideline","State Law"}'),

        ('Trust Vesting', 'Taking title to property in the name of a trust rather than individuals.', 'Closing', 'Legal', '{"Living Trust","Revocable Trust"}', '{"Inter Vivos Trust","Title"}', 'AI reviews trust documents for borrower authority and terms.', 'Requires trust certification or full trust review.', '{"Investor Guideline"}'),

        ('LLC/Entity Borrower', 'A borrower that is a legal entity rather than an individual.', 'Underwriting', 'Borrower Types', '{"Entity Borrower","Corporate Borrower"}', '{"Trust Vesting","Investment Property"}', 'AI applies entity borrower requirements for Non-QM or commercial.', 'Generally not eligible for agency residential loans.', '{"Investor Guideline"}'),

        ('Inter Vivos Trust', 'A living trust created during the grantor''s lifetime for estate planning.', 'Closing', 'Legal', '{"Living Trust","Revocable Trust"}', '{"Trust Vesting","Trust Review"}', 'AI verifies trust is valid and borrower has authority to encumber.', 'Most common trust type for residential mortgages.', '{"Investor Guideline"}'),

        # EMPLOYMENT SPECIFICS
        ('Employment Gap', 'A period of unemployment in the borrower''s work history requiring explanation.', 'Underwriting', 'Employment', '{"Gap in Employment"}', '{"VOE","Employment History"}', 'AI identifies gaps exceeding threshold and requests explanation.', 'Typically 30+ day gaps require LOE.', '{"GSE"}'),

        ('Verbal VOE', 'Telephone verification of employment conducted shortly before closing.', 'Processing', 'Verification', '{"VVOE","Phone VOE"}', '{"Written VOE","Employment Verification"}', 'AI schedules verbal VOE within required timeframe before closing.', 'Confirms continued employment; typically within 10 days.', '{"GSE","FHA"}'),

        ('Written VOE', 'Formal employment verification completed by the employer on standard form.', 'Processing', 'Verification', '{"VOE","1005"}', '{"Verbal VOE","Employment Verification"}', 'AI validates written VOE completeness and income calculation.', 'Alternative to paystubs and W-2s for income documentation.', '{"GSE"}'),

        ('Employment Offer Letter', 'Documentation of a future job offer used to qualify with anticipated income.', 'Underwriting', 'Employment', '{"Offer Letter","Future Employment"}', '{"Relocation","New Job"}', 'AI applies offer letter requirements for start date and income verification.', 'Must meet specific criteria for use in qualifying.', '{"GSE"}'),

        # PROPERTY SITUATIONS
        ('Property Flip', 'A property resold within a short period after acquisition, often with significant price increase.', 'Underwriting', 'Property', '{"Flip","Quick Resale"}', '{"Seasoning","Value"}', 'AI applies flip rules based on ownership period and price change.', 'May require second appraisal or additional documentation.', '{"FHA","GSE"}'),

        ('Multiple Financed Properties', 'A borrower owning several properties with mortgages, triggering additional requirements.', 'Underwriting', 'Property', '{"Multiple Properties","Financed Properties"}', '{"Investment Property","Reserves"}', 'AI counts financed properties and applies reserve and eligibility rules.', 'Limits apply based on investor and program.', '{"GSE"}'),

        ('Non-Arm''s Length Transaction', 'A transaction between parties with a relationship that may affect terms.', 'Underwriting', 'Property', '{"Identity of Interest","Related Party"}', '{"Family Transaction","Gift of Equity"}', 'AI identifies non-arm''s length and applies specific requirements.', 'Requires additional documentation and restrictions.', '{"GSE","FHA"}'),

        ('Identity of Interest', 'A transaction where buyer and seller have a relationship affecting independence.', 'Underwriting', 'Property', '{"IOI"}', '{"Non-Arm''s Length Transaction","Family Sale"}', 'AI applies identity of interest LTV restrictions and requirements.', 'Common with family sales and employer relocations.', '{"FHA"}'),

        # GEOGRAPHIC & LIMITS
        ('MSA (Metropolitan Statistical Area)', 'A geographic region with a core urban area used for various lending determinations.', 'Compliance', 'Geography', '{"MSA","Metro Area"}', '{"Census Tract","High-Cost Area"}', 'AI uses MSA for pricing, limits, and program eligibility.', 'Defines conforming loan limits and CRA assessment areas.', '{"Federal"}'),

        ('Census Tract', 'A small geographic area used for demographic data and lending program eligibility.', 'Compliance', 'Geography', '{"Tract"}', '{"MSA","Underserved Area"}', 'AI checks census tract for DPA eligibility and CRA credit.', 'Used for HomeReady/Home Possible income limits.', '{"Federal"}'),

        ('Declining Market', 'An area where property values are decreasing, triggering additional requirements.', 'Collateral', 'Market', '{"Soft Market"}', '{"Appraisal","LTV"}', 'AI identifies declining markets for conservative LTV and conditions.', 'May require additional appraisal scrutiny.', '{"GSE"}'),

        ('Disaster Area', 'A federally declared disaster zone affecting property eligibility and inspection requirements.', 'Collateral', 'Risk', '{"FEMA Disaster","Disaster Declaration"}', '{"Appraisal","Re-inspection"}', 'AI checks disaster declarations and applies inspection requirements.', 'May require property re-inspection before closing.', '{"FEMA"}'),

        # TAX & IRS
        ('Tax Transcript', 'IRS document confirming the content of a filed tax return.', 'Processing', 'Documentation', '{"IRS Transcript","4506-C Transcript"}', '{"4506-C","Tax Returns"}', 'AI compares transcripts to provided returns for income validation.', 'Required for most loans to verify reported income.', '{"GSE","IRS"}'),

        ('Tax Lien', 'A lien filed by IRS or state for unpaid taxes.', 'Credit', 'Liens', '{"IRS Lien","Federal Tax Lien"}', '{"Subordination","Payoff"}', 'AI identifies tax liens and determines payoff or subordination requirement.', 'Federal tax liens must typically be paid or subordinated.', '{"IRS"}'),

        ('IRS Installment Agreement', 'A payment plan with IRS for outstanding tax debt.', 'Underwriting', 'Liabilities', '{"IRS Payment Plan"}', '{"Tax Lien","DTI"}', 'AI includes installment payments in DTI and verifies current status.', 'Requires documentation of agreement and payment history.', '{"GSE"}'),

        # INSURANCE SPECIFICS
        ('Condo Master Policy', 'Insurance policy covering the common elements and structure of a condominium project.', 'Collateral', 'Insurance', '{"Master Policy","HOA Insurance"}', '{"HO-6 Policy","Condominium"}', 'AI verifies master policy coverage meets investor requirements.', 'Must cover replacement cost of structures and common areas.', '{"GSE"}'),

        ('HO-6 Policy', 'Insurance policy for condominium unit owners covering interior and personal property.', 'Collateral', 'Insurance', '{"Condo Unit Policy","Walls-In Coverage"}', '{"Condo Master Policy","Hazard Insurance"}', 'AI ensures HO-6 provides adequate walls-in coverage.', 'Supplements master policy for unit owner protection.', '{"Investor Guideline"}'),

        ('Wind/Hail Insurance', 'Separate insurance coverage for wind and hail damage in coastal or high-risk areas.', 'Collateral', 'Insurance', '{"Windstorm Insurance"}', '{"Hazard Insurance","Coastal Property"}', 'AI identifies properties requiring separate wind coverage.', 'Common in Florida, Texas coast, and hurricane zones.', '{"Investor Guideline"}'),

        ('Declarations Page', 'Summary page of an insurance policy showing coverage amounts, deductibles, and named insured.', 'Processing', 'Insurance', '{"Dec Page","Insurance Evidence"}', '{"Hazard Insurance","Mortgagee Clause"}', 'AI validates dec page shows required coverage and mortgagee clause.', 'Required documentation for closing and ongoing compliance.', '{"Investor Guideline"}'),

        # CONDO/PROJECT APPROVAL
        ('Warrantable Condo', 'A condominium project that meets agency guidelines for standard financing.', 'Collateral', 'Condo', '{"Warrantable"}', '{"Non-Warrantable Condo","Project Approval"}', 'AI evaluates condo characteristics against warrantability criteria.', 'Eligible for standard agency pricing and terms.', '{"GSE"}'),

        ('Non-Warrantable Condo', 'A condominium project that does not meet agency guidelines, requiring non-agency financing.', 'Collateral', 'Condo', '{"Non-Warrantable"}', '{"Warrantable Condo","Jumbo Loan"}', 'AI identifies non-warrantable characteristics and routes to appropriate investors.', 'May require portfolio or Non-QM execution.', '{"Investor Guideline"}'),

        ('Project Approval', 'Formal review and approval of a condominium project for agency financing.', 'Collateral', 'Condo', '{"PERS","CPM","Project Review"}', '{"Warrantable Condo","Condo Questionnaire"}', 'AI determines if full project review or limited review applies.', 'Required for agency condo financing.', '{"GSE"}'),

        ('Condo Questionnaire', 'Standardized questionnaire completed by HOA providing project information.', 'Processing', 'Condo', '{"Condo Cert","HOA Questionnaire"}', '{"Project Approval","HOA"}', 'AI parses questionnaire for warrantability red flags.', 'Key document for condo project evaluation.', '{"GSE"}'),

        ('Owner-Occupancy Ratio', 'The percentage of units in a condo project occupied by owners versus renters.', 'Collateral', 'Condo', '{"OO Ratio","Occupancy Ratio"}', '{"Warrantable Condo","Project Approval"}', 'AI checks occupancy ratio against minimum requirements.', 'Critical warrantability factor for condos.', '{"GSE"}'),

        # CLOSING SPECIFICS
        ('Mail-Away Closing', 'A closing where documents are sent to the borrower for signing at a remote location.', 'Closing', 'Process', '{"Remote Closing"}', '{"eClose","Mobile Notary"}', 'AI schedules mail-away with adequate time for shipping and return.', 'Common for out-of-state borrowers or relocation.', '{"Internal"}'),

        ('Mobile Notary', 'A notary public who travels to the signer''s location for document execution.', 'Closing', 'Services', '{"Traveling Notary","Signing Agent"}', '{"RON","Mail-Away Closing"}', 'AI schedules mobile notary for borrower convenience.', 'Alternative to closing at title company or attorney office.', '{"State Law"}'),

        ('Signing Agent', 'A trained professional who guides borrowers through closing documents.', 'Closing', 'Services', '{"Notary Signing Agent","NSA"}', '{"Mobile Notary","Closer"}', 'AI coordinates signing agent for document execution quality.', 'Ensures proper execution of all documents.', '{"Internal"}'),

        ('Closing Protection Letter (CPL)', 'A letter from a title insurer protecting the lender against closing agent misconduct.', 'Closing', 'Title', '{"CPL"}', '{"Title Insurance","Closing Agent"}', 'AI verifies CPL is in place before closing.', 'Protects against fraud or errors by closing agent.', '{"State Law"}'),

        # SERVICING ADVANCED
        ('Assumption', 'Transfer of mortgage obligation from seller to buyer with lender approval.', 'Servicing', 'Transfer', '{"Loan Assumption"}', '{"Release of Liability","FHA Loan"}', 'AI processes assumption applications and creditworthiness evaluation.', 'Common for FHA/VA loans; rare for conventional.', '{"HUD","VA"}'),

        ('Release of Liability', 'Formal release of a borrower from mortgage obligation after assumption or refinance.', 'Servicing', 'Transfer', '{"Liability Release"}', '{"Assumption","Divorce"}', 'AI tracks release requests and documents liability transfer.', 'Important for divorced borrowers or property transfers.', '{"Investor Guideline"}'),

        ('Partial Release', 'Release of a portion of property from the mortgage lien, typically for subdivision.', 'Servicing', 'Lien', '{"Partial Lien Release"}', '{"Subordination","Lot Release"}', 'AI evaluates partial release requests for remaining collateral adequacy.', 'Common for land development and subdivisions.', '{"Investor Guideline"}'),

        # SECONDARY MARKET ADVANCED
        ('Coupon (MBS)', 'The interest rate paid to MBS investors, typically in 0.5% increments.', 'Secondary Market', 'Securities', '{"Pass-Through Rate"}', '{"MBS","TBA"}', 'AI matches loan rates to appropriate coupon for best execution.', 'Determines which MBS pools loans can be delivered into.', '{"SEC"}'),

        ('Spec Pool', 'An MBS pool with specific loan characteristics that command premium pricing.', 'Secondary Market', 'Securities', '{"Specified Pool"}', '{"TBA","Coupon"}', 'AI identifies loans eligible for spec pool premium execution.', 'Low balance, high LTV, or geographic pools may command premium.', '{"Investor Guideline"}'),

        ('Stipulated Pool', 'A pool delivery with specific loan count or characteristics agreed upon with investor.', 'Secondary Market', 'Delivery', '{"Stip"}', '{"Mandatory Delivery","TBA"}', 'AI tracks stipulated delivery requirements and deadlines.', 'Contractual obligation with investor for specific loan delivery.', '{"Investor Guideline"}'),

        ('Dollar Roll', 'A financing technique involving simultaneous sale and repurchase of MBS for different settlement dates.', 'Secondary Market', 'Trading', '{"Roll"}', '{"TBA","Carry Cost"}', 'AI evaluates roll economics for optimal pipeline management.', 'Used to manage settlement timing and financing costs.', '{"Internal"}'),

        # LEAD & MARKETING
        ('Lead Source', 'The origin or channel through which a prospective borrower was acquired.', 'Marketing', 'Analytics', '{"Source","Lead Channel"}', '{"Cost Per Lead","Conversion Rate"}', 'AI tracks lead sources for ROI analysis and optimization.', 'Critical for marketing spend allocation.', '{"Internal"}'),

        ('Cost Per Lead (CPL)', 'The average cost to acquire a single prospective borrower.', 'Marketing', 'Metrics', '{"CPL"}', '{"Lead Source","ROI"}', 'AI calculates CPL by source and campaign for optimization.', 'Key metric for marketing efficiency.', '{"Internal"}'),

        ('Speed to Lead', 'The time between lead creation and first contact attempt.', 'Operations', 'Metrics', '{"Response Time","Lead Response"}', '{"Lead Source","Conversion Rate"}', 'AI monitors speed to lead and alerts for delayed follow-up.', 'Critical factor in lead conversion success.', '{"Internal"}'),

        ('Lead Nurturing', 'Ongoing communication with prospects not yet ready to apply.', 'Marketing', 'Process', '{"Drip Campaign","Nurture"}', '{"Lead Source","Recapture"}', 'AI automates nurture sequences based on borrower profile and behavior.', 'Maintains engagement until borrower is ready.', '{"Internal"}'),

        ('Recapture Rate', 'The percentage of past customers who return for subsequent transactions.', 'Marketing', 'Metrics', '{"Retention Rate","Repeat Rate"}', '{"Recapture","CLV"}', 'AI identifies recapture opportunities and measures success rate.', 'High-value metric for customer lifetime value.', '{"Internal"}'),

        # COMPLIANCE TESTS
        ('Points and Fees Test', 'A QM test limiting total points and fees to 3% of loan amount.', 'Compliance', 'QM', '{"3% Test","Fee Cap"}', '{"Qualified Mortgage (QM)","HOEPA"}', 'AI calculates points and fees for QM compliance determination.', 'Exceeding cap results in Non-QM or HOEPA loan.', '{"QM/ATR"}'),

        ('Ability to Repay (ATR)', 'The requirement that lenders make reasonable determination borrower can repay.', 'Compliance', 'Underwriting', '{"ATR"}', '{"QM","DTI"}', 'AI documents ATR factors and determination rationale.', 'Core consumer protection requirement for all mortgages.', '{"Dodd-Frank"}'),

        ('3% Fee Cap', 'The maximum allowable points and fees for Qualified Mortgage status.', 'Compliance', 'QM', '{"Fee Limit"}', '{"Points and Fees Test","QM"}', 'AI monitors cumulative fees against 3% threshold.', 'Different thresholds apply for smaller loan amounts.', '{"QM/ATR"}'),

        ('Anti-Steering', 'Rules prohibiting LOs from steering borrowers to loans not in their interest for compensation.', 'Compliance', 'LO Comp', '{"Steering"}', '{"LO Comp Rule","Suitability"}', 'AI ensures pricing options meet borrower needs, not comp incentives.', 'Requires presenting appropriate loan options.', '{"LO Comp","RESPA"}'),

        # INVESTOR/AGENCY SPECIFICS
        ('HomeReady', 'Fannie Mae''s affordable lending program for low-to-moderate income borrowers with flexible income sources and down payment options.', 'Origination', 'Program', '{"Fannie Mae HomeReady"}', '{"Home Possible","DPA","LMI"}', 'AI checks income limits, AMI requirements, and homeownership education for eligibility.', 'Routes to affordable housing workflow with DPA and grant coordination.', '{"GSE","Fair Lending"}'),

        ('Home Possible', 'Freddie Mac''s affordable lending program allowing low down payments and flexible income sources for LMI borrowers.', 'Origination', 'Program', '{"Freddie Mac Home Possible"}', '{"HomeReady","DPA","LMI"}', 'AI validates AMI thresholds and eligible income types for qualification.', 'Triggers affordable housing compliance and counseling requirements.', '{"GSE","Fair Lending"}'),

        ('FHA 203(k)', 'FHA rehabilitation loan program that allows borrowers to finance both purchase and renovation costs in one mortgage.', 'Origination', 'Program', '{"203k","FHA Rehab Loan","Renovation Loan"}', '{"FHA","Construction Loan","Appraisal"}', 'AI evaluates scope of work, contractor requirements, and feasibility for approval.', 'Requires HUD consultant, draw schedules, and as-completed appraisal.', '{"FHA","HUD"}'),

        ('VA IRRRL', 'Interest Rate Reduction Refinance Loan - VA''s streamlined refinance program requiring minimal documentation.', 'Origination', 'Program', '{"IRRRL","VA Streamline"}', '{"VA Loan","Rate-and-Term Refinance"}', 'AI checks prior VA loan status, net tangible benefit, and recoupment period.', 'Simplified workflow with reduced documentation and no appraisal required.', '{"VA","Net Tangible Benefit"}'),

        ('USDA Guaranteed Loan', 'USDA loan program where approved lenders originate loans with government guarantee for rural borrowers.', 'Origination', 'Program', '{"Section 502 Guaranteed","Rural Development"}', '{"USDA Direct","Rural Property","Income Limits"}', 'AI validates property eligibility, income limits, and household size for approval.', 'Routes to USDA guarantee workflow and geographic eligibility check.', '{"USDA","Rural Development"}'),

        ('USDA Direct Loan', 'USDA loan made directly by Rural Development to very low and low income borrowers with payment subsidy.', 'Origination', 'Program', '{"Section 502 Direct"}', '{"USDA Guaranteed","Rural Property"}', 'AI distinguishes direct from guaranteed programs for proper routing.', 'Different process - borrower applies directly to USDA.', '{"USDA","Rural Development"}'),

        ('Non-Agency Jumbo', 'A jumbo loan that exceeds conforming limits and is not eligible for sale to Fannie Mae or Freddie Mac.', 'Origination', 'Product', '{"Portfolio Jumbo","Bank Jumbo"}', '{"Jumbo Loan","Conforming Loan"}', 'AI applies investor-specific overlays and enhanced documentation requirements.', 'Routes to portfolio or correspondent investor delivery channels.', '{"Investor Guideline"}'),

        ('Bank Statement Program', 'A Non-QM loan product using bank statements instead of tax returns for self-employed income verification.', 'Origination', 'Program', '{"Bank Statement Loan","12-Month Bank Statement","24-Month Bank Statement"}', '{"Non-QM","Self-Employment Income"}', 'AI calculates deposits and expense ratios from bank statements for qualification.', 'Requires 12-24 months statements and expense factor application.', '{"Non-QM"}'),

        # SPECIFIC DOCUMENT TYPES
        ('Schedule C', 'IRS form used by sole proprietors to report business income and expenses, key document for self-employed income calculation.', 'Underwriting', 'Documentation', '{"Form 1040 Schedule C","Sole Proprietor Income"}', '{"Self-Employment Income","Tax Return","Business Income"}', 'AI extracts gross receipts, expenses, and net profit for income averaging.', 'Required for all self-employed borrowers with unincorporated businesses.', '{"GSE","IRS"}'),

        ('Schedule E', 'IRS form reporting rental income, royalties, partnerships, S-corps, and estate/trust income.', 'Underwriting', 'Documentation', '{"Form 1040 Schedule E","Rental Income Form"}', '{"Rental Income","Partnership Income","K-1"}', 'AI calculates net rental income including depreciation add-backs.', 'Required for borrowers with rental properties or passive income.', '{"GSE","IRS"}'),

        ('K-1', 'Tax form reporting a partner''s or S-corp shareholder''s share of income, deductions, and credits.', 'Underwriting', 'Documentation', '{"Schedule K-1","Partnership K-1","S-Corp K-1"}', '{"Schedule E","Partnership Income","Self-Employment Income"}', 'AI uses K-1 to calculate qualifying income from business ownership.', 'Required for partners, LLC members, and S-corp shareholders.', '{"GSE","IRS"}'),

        ('4506-C', 'IRS form authorizing lender to request tax transcripts directly from the IRS.', 'Underwriting', 'Documentation', '{"IRS Transcript Request","4506C"}', '{"Tax Transcript","Tax Return"}', 'AI triggers 4506-C for income verification and fraud prevention.', 'Required pre-closing to validate tax return authenticity.', '{"GSE","IRS"}'),

        ('SSA-89', 'Social Security Administration form authorizing third-party verification of Social Security number and benefits.', 'Underwriting', 'Documentation', '{"Social Security Verification"}', '{"SSI Income","Social Security Income"}', 'AI uses for SSN validation and Social Security income verification.', 'Required for borrowers claiming Social Security benefits as income.', '{"SSA"}'),

        ('VOE', 'Verification of Employment - Written confirmation from employer of borrower''s employment status and income.', 'Underwriting', 'Documentation', '{"Verification of Employment","Employment Verification"}', '{"Paystub","W-2 Income","Verbal VOE"}', 'AI tracks VOE status and validates income figures against paystubs.', 'Required within 10 business days of closing.', '{"GSE","FHA"}'),

        ('VOR', 'Verification of Rent - Written confirmation from landlord of borrower''s rental payment history.', 'Underwriting', 'Documentation', '{"Verification of Rent","Rental History"}', '{"Housing History","Alternative Credit"}', 'AI uses VOR for payment history when borrower lacks mortgage tradelines.', 'Required for first-time homebuyers or borrowers with limited credit.', '{"GSE","FHA"}'),

        # ARM SPECIFIC STRUCTURES
        ('5/1 ARM', 'Adjustable-rate mortgage with rate fixed for first 5 years, then adjusting annually thereafter.', 'Origination', 'Product', '{"5-Year ARM"}', '{"ARM","Index","Margin"}', 'AI calculates payment shock and qualifying rate for 5/1 ARM products.', 'Must qualify at higher of note rate or fully indexed rate plus margin.', '{"GSE","QM/ATR"}'),

        ('7/1 ARM', 'Adjustable-rate mortgage with rate fixed for first 7 years, then adjusting annually thereafter.', 'Origination', 'Product', '{"7-Year ARM"}', '{"ARM","5/1 ARM","10/1 ARM"}', 'AI applies appropriate qualifying rate based on initial fixed period.', 'Longer initial period may reduce qualifying rate requirements.', '{"GSE","QM/ATR"}'),

        ('10/1 ARM', 'Adjustable-rate mortgage with rate fixed for first 10 years, then adjusting annually thereafter.', 'Origination', 'Product', '{"10-Year ARM"}', '{"ARM","7/1 ARM","Fixed-Rate"}', 'AI determines if loan qualifies as higher-priced with longer fixed period.', 'Often qualifies at note rate due to 5+ year initial period.', '{"GSE","QM/ATR"}'),

        ('Interest-Only ARM', 'ARM with initial period where only interest payments are required, principal payments begin later.', 'Origination', 'Product', '{"IO ARM","Interest-Only Period"}', '{"ARM","Payment Shock","Non-QM"}', 'AI calculates full payment shock when IO period ends.', 'Typically Non-QM - must qualify at fully amortizing payment.', '{"Non-QM","QM/ATR"}'),

        ('Hybrid ARM', 'An ARM product combining an initial fixed-rate period with subsequent adjustable-rate period.', 'Origination', 'Product', '{"Fixed-Period ARM"}', '{"5/1 ARM","7/1 ARM","10/1 ARM"}', 'AI classifies hybrid ARMs for appropriate qualifying rate rules.', 'All X/1 ARMs are hybrid ARMs with initial fixed period.', '{"GSE"}'),

        ('SOFR Index', 'Secured Overnight Financing Rate - The primary index used for ARM rate adjustments after LIBOR phase-out.', 'Origination', 'Index', '{"SOFR","Secured Overnight Financing Rate"}', '{"ARM","Margin","Treasury Index"}', 'AI uses SOFR for ARM qualifying rate and payment calculations.', 'Replaced LIBOR as standard ARM index.', '{"GSE","Federal Reserve"}'),

        ('Treasury Index', 'U.S. Treasury securities rate used as index for some ARM products.', 'Origination', 'Index', '{"CMT","Constant Maturity Treasury"}', '{"SOFR Index","ARM","Margin"}', 'AI applies appropriate Treasury maturity for ARM calculations.', '1-year CMT commonly used for ARM adjustments.', '{"GSE","Treasury"}'),

        # MI COMPANY TERMS
        ('BPMI', 'Borrower-Paid Mortgage Insurance - MI where the borrower pays monthly or upfront premiums.', 'Mortgage Insurance', 'Premium Type', '{"Borrower-Paid MI","Monthly MI"}', '{"LPMI","Split Premium MI","PMI"}', 'AI compares BPMI vs LPMI for optimal borrower cost structure.', 'Cancellable at 80% LTV per HPA.', '{"HPA"}'),

        ('LPMI', 'Lender-Paid Mortgage Insurance - MI where lender pays premium via higher interest rate.', 'Mortgage Insurance', 'Premium Type', '{"Lender-Paid MI"}', '{"BPMI","Split Premium MI"}', 'AI calculates rate increase needed to offset LPMI premium.', 'Not cancellable - built into rate for life of loan.', '{"Investor Guideline"}'),

        ('Split Premium MI', 'MI structure with portion paid upfront and remainder paid monthly.', 'Mortgage Insurance', 'Premium Type', '{"Split MI","Hybrid MI"}', '{"BPMI","LPMI"}', 'AI optimizes upfront/monthly split for borrower cash flow.', 'Reduces monthly payment while limiting upfront cost.', '{"HPA"}'),

        ('Single Premium MI', 'MI where entire premium is paid upfront at closing, either by borrower or financed.', 'Mortgage Insurance', 'Premium Type', '{"Single Pay MI","Upfront MI"}', '{"BPMI","LPMI"}', 'AI calculates single premium cost and potential financing scenarios.', 'May be financed into loan amount if LTV permits.', '{"HPA"}'),

        ('Monthly Premium MI', 'MI with premium paid in monthly installments as part of mortgage payment.', 'Mortgage Insurance', 'Premium Type', '{"Monthly MI"}', '{"BPMI","Single Premium MI"}', 'AI calculates monthly MI premium based on LTV and credit score.', 'Most common MI structure for conventional loans.', '{"HPA"}'),

        # COMPLIANCE SPECIFICS
        ('CRA', 'Community Reinvestment Act - Requires banks to meet credit needs of entire communities including LMI areas.', 'Compliance', 'Regulation', '{"Community Reinvestment Act"}', '{"Fair Lending","LMI","HMDA"}', 'AI tracks CRA-eligible loans for bank regulatory compliance.', 'Banks track CRA performance for examiner review.', '{"CRA","Fair Lending"}'),

        ('ECOA', 'Equal Credit Opportunity Act - Prohibits discrimination in credit transactions.', 'Compliance', 'Regulation', '{"Equal Credit Opportunity Act","Regulation B"}', '{"Fair Lending","Adverse Action Notice","HMDA"}', 'AI ensures all applicants receive equal treatment regardless of protected class.', 'Requires adverse action notices and prohibits discriminatory practices.', '{"ECOA","Fair Lending"}'),

        ('ATR Rule', 'Ability to Repay Rule requiring lenders to verify borrower''s ability to repay the mortgage.', 'Compliance', 'Underwriting', '{"Ability to Repay","ATR"}', '{"QM","DTI","Residual Income"}', 'AI documents the eight ATR factors for every loan decision.', 'Core requirement for all residential mortgages under Dodd-Frank.', '{"Dodd-Frank","QM/ATR"}'),

        ('Right to Rescind', 'Borrower''s right to cancel refinance of primary residence within 3 business days of closing.', 'Compliance', 'Consumer Protection', '{"Rescission","3-Day Rescission"}', '{"Refinance","Closing Date"}', 'AI schedules funding dates accounting for rescission period.', 'Applies to owner-occupied refinances and HELOCs.', '{"TILA"}'),

        # CREDIT EVENT DETAILS
        ('Tradeline', 'An individual credit account reported on a credit report.', 'Credit', 'Report Components', '{"Credit Account","Trade Line"}', '{"Credit Report","Payment History"}', 'AI analyzes tradeline history for payment patterns and utilization.', 'Key component of credit analysis and score factors.', '{"FCRA"}'),

        ('Authorized User', 'A person authorized to use another''s credit account but not responsible for payments.', 'Credit', 'Account Types', '{"AU"}', '{"Tradeline","Credit Score"}', 'AI determines if AU tradelines can be used for qualification.', 'May require letter explaining relationship and access to funds.', '{"GSE"}'),

        ('Credit Utilization', 'The percentage of available revolving credit currently being used.', 'Credit', 'Risk Metrics', '{"Utilization Ratio","Credit Usage"}', '{"Credit Score","Revolving Debt"}', 'AI monitors utilization for credit score optimization advice.', 'High utilization negatively impacts credit scores.', '{"FCRA"}'),

        ('Rapid Rescore', 'Expedited credit score update after paying down balances or correcting errors.', 'Credit', 'Process', '{"Rescore","Quick Score Update"}', '{"Credit Score","Credit Utilization"}', 'AI recommends rapid rescore when score improvement would change pricing.', 'Takes 3-5 days vs weeks for normal reporting cycle.', '{"Internal"}'),

        ('Credit Supplement', 'Updated credit information added to credit report for specific tradelines.', 'Credit', 'Documentation', '{"Credit Update","Account Update"}', '{"Credit Report","Tradeline"}', 'AI identifies tradelines needing supplements for accurate data.', 'Used to update balances or payment history during loan process.', '{"FCRA"}'),

        # TITLE/LEGAL SPECIFICS
        ('Warranty Deed', 'Deed providing full warranties of clear title from grantor to grantee.', 'Title', 'Deed Types', '{"General Warranty Deed"}', '{"Quitclaim Deed","Special Warranty Deed"}', 'AI verifies warranty deed for arms-length purchase transactions.', 'Standard deed type for purchase transactions.', '{"State Law"}'),

        ('Quitclaim Deed', 'Deed transferring whatever interest grantor has without warranties of clear title.', 'Title', 'Deed Types', '{"Quit Claim","QC Deed"}', '{"Warranty Deed","Interspousal Transfer"}', 'AI flags quitclaim deeds as potential title seasoning or non-arms-length issues.', 'Common for family transfers, divorce, or clearing title defects.', '{"State Law"}'),

        ('Trust Deed State', 'A state where mortgages are secured by deed of trust with power of sale foreclosure.', 'Title', 'Legal Structure', '{"Deed of Trust State","Non-Judicial Foreclosure"}', '{"Mortgage State","Foreclosure"}', 'AI applies state-specific foreclosure timelines and procedures.', 'Faster non-judicial foreclosure process.', '{"State Law"}'),

        ('Mortgage State', 'A state where loans are secured by mortgages requiring judicial foreclosure.', 'Title', 'Legal Structure', '{"Judicial Foreclosure State"}', '{"Trust Deed State","Foreclosure"}', 'AI applies longer judicial foreclosure timelines for risk assessment.', 'Requires court process for foreclosure.', '{"State Law"}'),

        ('Subordination Agreement', 'Agreement where existing lienholder agrees to subordinate their lien position.', 'Title', 'Legal Documents', '{"Subordination","Sub Agreement"}', '{"HELOC","Second Lien","CLTV"}', 'AI identifies when subordination is needed for refinance transactions.', 'Required when existing second lien will remain in place.', '{"Investor Guideline"}'),

        ('ALTA Policy', 'American Land Title Association title insurance policy with standardized coverage.', 'Title', 'Insurance', '{"ALTA","Title Policy"}', '{"Owner''s Policy","Lender''s Policy"}', 'AI verifies appropriate ALTA endorsements for loan type.', 'Standard lender''s policy required for all mortgages.', '{"State Law"}'),

        ('Mechanic''s Lien', 'Lien placed by contractors or suppliers for unpaid work on property.', 'Title', 'Encumbrances', '{"Construction Lien","Materialman''s Lien"}', '{"Title Search","Lien","Clear Title"}', 'AI flags mechanic''s lien risk for recent construction or renovation.', 'Requires lien waivers or payoff documentation.', '{"State Law"}'),
    ]

    # Insert all terms
    for term_data in terms:
        db.execute(text("""
            INSERT INTO mortgage_glossary
            (term, definition, category, subcategory, synonyms, related_terms, ai_usage, workflow_usage, compliance_tags)
            VALUES (:term, :definition, :category, :subcategory, :synonyms::text[], :related_terms::text[], :ai_usage, :workflow_usage, :compliance_tags::text[])
        """), {
            "term": term_data[0],
            "definition": term_data[1],
            "category": term_data[2],
            "subcategory": term_data[3],
            "synonyms": term_data[4],
            "related_terms": term_data[5],
            "ai_usage": term_data[6],
            "workflow_usage": term_data[7],
            "compliance_tags": term_data[8]
        })

    db.commit()
    print(f"✓ Created mortgage_glossary table with {len(terms)} terms")
    return True


if __name__ == "__main__":
    from database import SessionLocal
    db = SessionLocal()
    try:
        run_migration(db)
    finally:
        db.close()
