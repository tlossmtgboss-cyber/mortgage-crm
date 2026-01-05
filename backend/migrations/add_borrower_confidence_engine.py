"""
Borrower Confidence Engine + Mortgage Decision Lab Database Migration

Creates tables for:
- Confidence Questions & Responses
- Loan Scenarios & Simulations
- Pricing Snapshots
- Recommendation Engine
- Education System (Lessons, Overlays, Quizzes)
- Artifacts & Reports

Based on the Borrower Confidence Manifesto specification.
"""

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_migration(db: Session):
    """Run the Borrower Confidence Engine migration."""

    logger.info("🚀 Starting Borrower Confidence Engine migration...")

    # =============================================================================
    # CORE CONFIDENCE ENGINE TABLES
    # =============================================================================

    # Confidence Questions - adaptive questions that build confidence profile
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS confidence_questions (
            id SERIAL PRIMARY KEY,
            code VARCHAR(100) UNIQUE NOT NULL,
            category VARCHAR(50) NOT NULL,
            subcategory VARCHAR(50),
            question_text TEXT NOT NULL,
            question_type VARCHAR(30) NOT NULL DEFAULT 'single_choice',
            options JSONB,
            validation_rules JSONB,
            weight DECIMAL(3,2) DEFAULT 1.0,
            display_order INTEGER DEFAULT 0,
            dependencies JSONB,
            education_overlay_id INTEGER,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Confidence Responses - borrower answers with confidence tracking
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS confidence_responses (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            borrower_profile_id UUID,
            application_id UUID,
            question_id INTEGER REFERENCES confidence_questions(id),
            response_value JSONB NOT NULL,
            confidence_level INTEGER CHECK (confidence_level BETWEEN 1 AND 5),
            time_to_answer_ms INTEGER,
            revision_count INTEGER DEFAULT 0,
            education_viewed BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Confidence Scores - aggregated confidence metrics
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS confidence_scores (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            borrower_profile_id UUID,
            application_id UUID,
            overall_score DECIMAL(5,2),
            category_scores JSONB,
            readiness_level VARCHAR(30),
            key_strengths JSONB,
            areas_for_improvement JSONB,
            recommended_actions JSONB,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # =============================================================================
    # LOAN SCENARIOS & SIMULATIONS
    # =============================================================================

    # Loan Scenarios - saved scenario configurations
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_scenarios (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            borrower_profile_id UUID,
            application_id UUID,
            name VARCHAR(255),
            scenario_type VARCHAR(50) NOT NULL,
            loan_amount DECIMAL(12,2) NOT NULL,
            purchase_price DECIMAL(12,2),
            down_payment DECIMAL(12,2),
            down_payment_percent DECIMAL(5,2),
            property_type VARCHAR(50),
            occupancy_type VARCHAR(50),
            property_state VARCHAR(2),
            property_county VARCHAR(100),
            credit_score INTEGER,
            dti_ratio DECIMAL(5,2),
            ltv_ratio DECIMAL(5,2),
            is_baseline BOOLEAN DEFAULT false,
            is_favorite BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Loan Options - calculated loan products for scenarios
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_options (
            id SERIAL PRIMARY KEY,
            scenario_id INTEGER REFERENCES loan_scenarios(id) ON DELETE CASCADE,
            product_type VARCHAR(50) NOT NULL,
            product_name VARCHAR(100),
            lender_name VARCHAR(100),
            interest_rate DECIMAL(6,4),
            apr DECIMAL(6,4),
            term_months INTEGER,
            monthly_payment DECIMAL(10,2),
            monthly_pi DECIMAL(10,2),
            monthly_taxes DECIMAL(10,2),
            monthly_insurance DECIMAL(10,2),
            monthly_pmi DECIMAL(10,2),
            monthly_hoa DECIMAL(10,2),
            closing_costs DECIMAL(10,2),
            prepaid_items DECIMAL(10,2),
            total_cash_to_close DECIMAL(12,2),
            total_interest_paid DECIMAL(14,2),
            total_cost DECIMAL(14,2),
            breakeven_months INTEGER,
            pros JSONB,
            cons JSONB,
            eligibility_notes JSONB,
            rank INTEGER,
            is_recommended BOOLEAN DEFAULT false,
            recommendation_reasons JSONB,
            pricing_snapshot_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Pricing Snapshots - point-in-time rate captures
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS pricing_snapshots (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,
            capture_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            product_type VARCHAR(50) NOT NULL,
            base_rate DECIMAL(6,4) NOT NULL,
            par_rate DECIMAL(6,4),
            lock_period_days INTEGER,
            adjustments JSONB,
            market_conditions JSONB,
            is_current BOOLEAN DEFAULT true,
            expires_at TIMESTAMP
        )
    """))

    # Scenario Comparisons - side-by-side comparison records
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS scenario_comparisons (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            scenario_ids INTEGER[] NOT NULL,
            comparison_type VARCHAR(50),
            summary JSONB,
            winner_id INTEGER,
            winner_reasons JSONB,
            user_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # =============================================================================
    # RECOMMENDATION ENGINE
    # =============================================================================

    # Recommendations - personalized loan suggestions
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS loan_recommendations (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            borrower_profile_id UUID,
            application_id UUID,
            recommendation_type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 0,
            confidence_score DECIMAL(5,2),
            supporting_factors JSONB,
            action_items JSONB,
            related_scenario_id INTEGER REFERENCES loan_scenarios(id),
            related_option_id INTEGER REFERENCES loan_options(id),
            status VARCHAR(30) DEFAULT 'pending',
            user_response VARCHAR(30),
            response_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # =============================================================================
    # EDUCATION SYSTEM
    # =============================================================================

    # Education Lessons - structured learning content
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS education_lessons (
            id SERIAL PRIMARY KEY,
            code VARCHAR(100) UNIQUE NOT NULL,
            category VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT,
            content JSONB NOT NULL,
            difficulty_level VARCHAR(20) DEFAULT 'beginner',
            estimated_minutes INTEGER DEFAULT 5,
            prerequisites INTEGER[],
            related_questions INTEGER[],
            display_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Education Overlays - contextual help that appears during the journey
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS education_overlays (
            id SERIAL PRIMARY KEY,
            code VARCHAR(100) UNIQUE NOT NULL,
            trigger_context VARCHAR(100) NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            content_type VARCHAR(30) DEFAULT 'text',
            media_url VARCHAR(500),
            display_position VARCHAR(30) DEFAULT 'tooltip',
            auto_dismiss_seconds INTEGER,
            show_once BOOLEAN DEFAULT false,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Education Progress - tracking what users have learned
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS education_progress (
            id SERIAL PRIMARY KEY,
            borrower_profile_id UUID NOT NULL,
            lesson_id INTEGER REFERENCES education_lessons(id),
            overlay_id INTEGER REFERENCES education_overlays(id),
            status VARCHAR(30) DEFAULT 'started',
            progress_percent INTEGER DEFAULT 0,
            quiz_score DECIMAL(5,2),
            time_spent_seconds INTEGER DEFAULT 0,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Quiz Questions - knowledge checks
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS education_quiz_questions (
            id SERIAL PRIMARY KEY,
            lesson_id INTEGER REFERENCES education_lessons(id),
            question_text TEXT NOT NULL,
            question_type VARCHAR(30) DEFAULT 'multiple_choice',
            options JSONB NOT NULL,
            correct_answer JSONB NOT NULL,
            explanation TEXT,
            display_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # =============================================================================
    # ARTIFACTS & REPORTS
    # =============================================================================

    # Confidence Artifacts - generated reports and documents
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS confidence_artifacts (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            borrower_profile_id UUID,
            application_id UUID,
            artifact_type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            content JSONB NOT NULL,
            format VARCHAR(30) DEFAULT 'json',
            file_url VARCHAR(500),
            is_shared BOOLEAN DEFAULT false,
            shared_with JSONB,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # User Interactions - detailed event log for analytics
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS confidence_interactions (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            borrower_profile_id UUID,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB,
            page_context VARCHAR(100),
            element_id VARCHAR(100),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # =============================================================================
    # INDEXES FOR PERFORMANCE
    # =============================================================================

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_confidence_responses_session ON confidence_responses(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_confidence_responses_borrower ON confidence_responses(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_confidence_scores_session ON confidence_scores(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_loan_scenarios_session ON loan_scenarios(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_loan_scenarios_borrower ON loan_scenarios(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_loan_options_scenario ON loan_options(scenario_id)",
        "CREATE INDEX IF NOT EXISTS idx_pricing_snapshots_current ON pricing_snapshots(is_current, product_type)",
        "CREATE INDEX IF NOT EXISTS idx_recommendations_session ON loan_recommendations(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_education_progress_borrower ON education_progress(borrower_profile_id)",
        "CREATE INDEX IF NOT EXISTS idx_confidence_interactions_session ON confidence_interactions(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_confidence_interactions_type ON confidence_interactions(event_type)",
    ]

    for idx_sql in indexes:
        try:
            db.execute(text(idx_sql))
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    db.commit()
    logger.info("✅ Borrower Confidence Engine migration completed successfully!")

    return True


def seed_initial_data(db: Session):
    """Seed initial confidence questions and education content."""
    import json

    logger.info("🌱 Seeding initial Borrower Confidence Engine data...")

    # Seed confidence questions by category
    questions = [
        # FINANCIAL READINESS
        {
            "code": "FIN_MONTHLY_BUDGET",
            "category": "financial_readiness",
            "subcategory": "budgeting",
            "question_text": "How confident are you in your understanding of your monthly budget?",
            "question_type": "scale",
            "options": {"min": 1, "max": 5, "labels": ["Not at all", "Slightly", "Somewhat", "Very", "Extremely"]},
            "weight": 1.2,
            "display_order": 1
        },
        {
            "code": "FIN_EMERGENCY_FUND",
            "category": "financial_readiness",
            "subcategory": "savings",
            "question_text": "Do you have an emergency fund with at least 3-6 months of expenses?",
            "question_type": "single_choice",
            "options": [
                {"value": "yes_6plus", "label": "Yes, 6+ months", "score": 5},
                {"value": "yes_3to6", "label": "Yes, 3-6 months", "score": 4},
                {"value": "yes_1to3", "label": "Yes, 1-3 months", "score": 3},
                {"value": "building", "label": "Currently building", "score": 2},
                {"value": "no", "label": "Not yet", "score": 1}
            ],
            "weight": 1.0,
            "display_order": 2
        },
        {
            "code": "FIN_DOWN_PAYMENT",
            "category": "financial_readiness",
            "subcategory": "down_payment",
            "question_text": "What percentage of the home price do you plan to put down?",
            "question_type": "single_choice",
            "options": [
                {"value": "20plus", "label": "20% or more", "score": 5},
                {"value": "10to20", "label": "10-20%", "score": 4},
                {"value": "5to10", "label": "5-10%", "score": 3},
                {"value": "3to5", "label": "3-5%", "score": 2},
                {"value": "under3", "label": "Under 3%", "score": 1}
            ],
            "weight": 1.5,
            "display_order": 3
        },

        # CREDIT UNDERSTANDING
        {
            "code": "CREDIT_SCORE_KNOWLEDGE",
            "category": "credit_understanding",
            "subcategory": "score",
            "question_text": "Do you know your current credit score?",
            "question_type": "single_choice",
            "options": [
                {"value": "exact", "label": "Yes, I check it regularly", "score": 5},
                {"value": "approximate", "label": "I have a general idea", "score": 3},
                {"value": "unknown", "label": "I'm not sure", "score": 1}
            ],
            "weight": 1.0,
            "display_order": 10
        },
        {
            "code": "CREDIT_SCORE_RANGE",
            "category": "credit_understanding",
            "subcategory": "score",
            "question_text": "What is your approximate credit score?",
            "question_type": "single_choice",
            "options": [
                {"value": "excellent", "label": "760+", "score": 5},
                {"value": "good", "label": "700-759", "score": 4},
                {"value": "fair", "label": "640-699", "score": 3},
                {"value": "needs_work", "label": "580-639", "score": 2},
                {"value": "building", "label": "Below 580 or building credit", "score": 1}
            ],
            "weight": 1.5,
            "display_order": 11,
            "dependencies": [{"question": "CREDIT_SCORE_KNOWLEDGE", "values": ["exact", "approximate"]}]
        },

        # MORTGAGE KNOWLEDGE
        {
            "code": "MTG_RATE_TYPES",
            "category": "mortgage_knowledge",
            "subcategory": "products",
            "question_text": "How well do you understand the difference between fixed and adjustable rate mortgages?",
            "question_type": "scale",
            "options": {"min": 1, "max": 5, "labels": ["Not at all", "A little", "Somewhat", "Well", "Very well"]},
            "weight": 0.8,
            "display_order": 20
        },
        {
            "code": "MTG_TOTAL_COST",
            "category": "mortgage_knowledge",
            "subcategory": "costs",
            "question_text": "Are you aware that your monthly payment includes more than just principal and interest?",
            "question_type": "single_choice",
            "options": [
                {"value": "yes_detailed", "label": "Yes, I know about taxes, insurance, PMI, and HOA", "score": 5},
                {"value": "yes_basic", "label": "Yes, I know about taxes and insurance", "score": 3},
                {"value": "no", "label": "I wasn't aware of this", "score": 1}
            ],
            "weight": 1.0,
            "display_order": 21
        },

        # PROCESS UNDERSTANDING
        {
            "code": "PROC_TIMELINE",
            "category": "process_understanding",
            "subcategory": "timeline",
            "question_text": "Do you have realistic expectations about how long the mortgage process takes?",
            "question_type": "single_choice",
            "options": [
                {"value": "yes", "label": "Yes, I expect 30-45 days typically", "score": 5},
                {"value": "somewhat", "label": "I have a general idea", "score": 3},
                {"value": "no", "label": "I'm not sure", "score": 1}
            ],
            "weight": 0.5,
            "display_order": 30
        },
        {
            "code": "PROC_DOCS_READY",
            "category": "process_understanding",
            "subcategory": "documents",
            "question_text": "Do you have easy access to your financial documents (pay stubs, W2s, tax returns, bank statements)?",
            "question_type": "single_choice",
            "options": [
                {"value": "all_ready", "label": "Yes, I have everything organized", "score": 5},
                {"value": "mostly", "label": "I have most of them", "score": 4},
                {"value": "some", "label": "I have some", "score": 2},
                {"value": "need_to_gather", "label": "I need to gather them", "score": 1}
            ],
            "weight": 1.2,
            "display_order": 31
        }
    ]

    for q in questions:
        try:
            options_json = json.dumps(q["options"]) if q.get("options") else '{}'
            deps_json = json.dumps(q.get("dependencies", [])) if q.get("dependencies") else '[]'

            db.execute(text("""
                INSERT INTO confidence_questions (
                    code, category, subcategory, question_text, question_type,
                    options, weight, display_order, dependencies, is_active
                ) VALUES (
                    :code, :category, :subcategory, :question_text, :question_type,
                    :options::jsonb, :weight, :display_order, :dependencies::jsonb, true
                ) ON CONFLICT (code) DO UPDATE SET
                    question_text = EXCLUDED.question_text,
                    options = EXCLUDED.options,
                    weight = EXCLUDED.weight,
                    display_order = EXCLUDED.display_order
            """), {
                "code": q["code"],
                "category": q["category"],
                "subcategory": q.get("subcategory"),
                "question_text": q["question_text"],
                "question_type": q["question_type"],
                "options": options_json,
                "weight": q.get("weight", 1.0),
                "display_order": q.get("display_order", 0),
                "dependencies": deps_json
            })
            logger.info(f"✅ Inserted/updated question: {q['code']}")
        except Exception as e:
            logger.warning(f"Question insert warning ({q['code']}): {e}")

    # Seed education overlays
    overlays = [
        {
            "code": "DTI_EXPLAINED",
            "trigger_context": "confidence_question:FIN_MONTHLY_BUDGET",
            "title": "Understanding Debt-to-Income Ratio",
            "content": "Your debt-to-income (DTI) ratio is one of the most important factors lenders consider. It's calculated by dividing your monthly debt payments by your gross monthly income. Most lenders prefer a DTI of 43% or lower, though some loan programs allow higher ratios.",
            "content_type": "text",
            "display_position": "sidebar"
        },
        {
            "code": "CREDIT_SCORE_IMPACT",
            "trigger_context": "confidence_question:CREDIT_SCORE_RANGE",
            "title": "How Credit Scores Affect Your Rate",
            "content": "Your credit score significantly impacts the interest rate you'll receive. Generally:\n• 760+ = Best rates available\n• 700-759 = Very good rates\n• 640-699 = Good rates, may need higher down payment\n• Below 640 = Limited options, may need alternative programs",
            "content_type": "text",
            "display_position": "tooltip"
        },
        {
            "code": "PMI_EXPLAINED",
            "trigger_context": "confidence_question:FIN_DOWN_PAYMENT",
            "title": "Private Mortgage Insurance (PMI)",
            "content": "If you put down less than 20%, you'll typically need to pay PMI. This protects the lender if you default. PMI usually costs 0.5-1% of the loan amount annually and can be removed once you have 20% equity.",
            "content_type": "text",
            "display_position": "modal"
        }
    ]

    for o in overlays:
        try:
            db.execute(text("""
                INSERT INTO education_overlays (
                    code, trigger_context, title, content, content_type, display_position, is_active
                ) VALUES (
                    :code, :trigger_context, :title, :content, :content_type, :display_position, true
                ) ON CONFLICT (code) DO UPDATE SET
                    trigger_context = EXCLUDED.trigger_context,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    content_type = EXCLUDED.content_type,
                    display_position = EXCLUDED.display_position
            """), o)
            logger.info(f"✅ Inserted/updated overlay: {o['code']}")
        except Exception as e:
            logger.warning(f"Overlay insert warning ({o['code']}): {e}")

    db.commit()
    logger.info("✅ Initial data seeding completed!")

    return True


if __name__ == "__main__":
    from database import SessionLocal

    db = SessionLocal()
    try:
        run_migration(db)
        seed_initial_data(db)
    finally:
        db.close()
