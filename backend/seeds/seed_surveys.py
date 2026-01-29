"""
Seed Survey Templates
Pre-built survey templates for common mortgage industry use cases.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Sample survey templates with questions
SURVEY_TEMPLATES = [
    {
        "name": "Post-Close NPS Survey",
        "description": "Measure customer satisfaction after loan closing using Net Promoter Score",
        "survey_type": "nps",
        "trigger_type": "loan_funded",
        "trigger_config": {"days_after": 3},
        "intro_message": "Congratulations on your new home! We'd love to hear about your experience working with us.",
        "thank_you_message": "Thank you for your feedback! Your response helps us continue to improve our service.",
        "questions": [
            {
                "question_text": "How likely are you to recommend us to a friend or colleague?",
                "question_type": "nps_scale",
                "help_text": "0 = Not at all likely, 10 = Extremely likely",
                "is_required": True,
                "min_value": 0,
                "max_value": 10,
                "order": 1,
                "weight": 2.0,
            },
            {
                "question_text": "What was the primary reason for your score?",
                "question_type": "text_long",
                "help_text": "Please share any specific feedback about your experience",
                "is_required": False,
                "order": 2,
                "weight": 1.0,
            },
            {
                "question_text": "How would you rate the communication from your loan officer?",
                "question_type": "rating",
                "help_text": "1 = Poor, 5 = Excellent",
                "is_required": True,
                "min_value": 1,
                "max_value": 5,
                "order": 3,
                "weight": 1.0,
            },
            {
                "question_text": "How would you rate the overall speed of the loan process?",
                "question_type": "rating",
                "is_required": True,
                "min_value": 1,
                "max_value": 5,
                "order": 4,
                "weight": 1.0,
            },
            {
                "question_text": "Is there anything we could have done better?",
                "question_type": "text_long",
                "is_required": False,
                "order": 5,
                "weight": 1.0,
            },
        ],
    },
    {
        "name": "Customer Satisfaction Survey (CSAT)",
        "description": "Quick satisfaction survey for ongoing customer touchpoints",
        "survey_type": "csat",
        "trigger_type": "manual",
        "intro_message": "We value your feedback! Please take a moment to rate your recent experience.",
        "thank_you_message": "Thank you for sharing your feedback!",
        "questions": [
            {
                "question_text": "Overall, how satisfied are you with your experience?",
                "question_type": "csat_scale",
                "help_text": "1 = Very Dissatisfied, 5 = Very Satisfied",
                "is_required": True,
                "min_value": 1,
                "max_value": 5,
                "order": 1,
                "weight": 2.0,
            },
            {
                "question_text": "How easy was it to work with our team?",
                "question_type": "csat_scale",
                "is_required": True,
                "min_value": 1,
                "max_value": 5,
                "order": 2,
                "weight": 1.0,
            },
            {
                "question_text": "Did we meet your expectations?",
                "question_type": "yes_no",
                "is_required": True,
                "order": 3,
                "weight": 1.0,
            },
            {
                "question_text": "Any additional comments?",
                "question_type": "text",
                "is_required": False,
                "order": 4,
                "weight": 1.0,
            },
        ],
    },
    {
        "name": "Customer Effort Score (CES)",
        "description": "Measure how easy it was for customers to get what they needed",
        "survey_type": "ces",
        "trigger_type": "milestone_reached",
        "trigger_config": {"milestone": "disclosure_sent"},
        "intro_message": "Quick question about your recent experience with us.",
        "thank_you_message": "Thanks for letting us know!",
        "questions": [
            {
                "question_text": "How easy was it to get the help you needed?",
                "question_type": "likert",
                "options": ["Very Difficult", "Difficult", "Neutral", "Easy", "Very Easy"],
                "is_required": True,
                "order": 1,
                "weight": 2.0,
            },
            {
                "question_text": "What could we do to make things easier?",
                "question_type": "text",
                "is_required": False,
                "order": 2,
                "weight": 1.0,
            },
        ],
    },
    {
        "name": "Savings Validation Survey",
        "description": "Validate that promised savings were realized by the customer",
        "survey_type": "savings",
        "trigger_type": "days_after_close",
        "trigger_config": {"days_after": 90},
        "intro_message": "It's been a few months since we helped you with your mortgage. We'd love to verify your savings experience.",
        "thank_you_message": "Thank you! Your feedback helps us ensure we deliver on our promises.",
        "questions": [
            {
                "question_text": "Have you noticed the monthly savings we discussed?",
                "question_type": "yes_no",
                "is_required": True,
                "order": 1,
                "weight": 2.0,
            },
            {
                "question_text": "Approximately how much are you saving each month?",
                "question_type": "multiple_choice",
                "options": ["Less than $100", "$100-$250", "$250-$500", "$500-$1000", "More than $1000", "Not sure"],
                "is_required": True,
                "order": 2,
                "weight": 1.5,
            },
            {
                "question_text": "How satisfied are you with your refinance decision?",
                "question_type": "csat_scale",
                "is_required": True,
                "min_value": 1,
                "max_value": 5,
                "order": 3,
                "weight": 1.0,
            },
            {
                "question_text": "Would you recommend our refinance services to others?",
                "question_type": "nps_scale",
                "is_required": True,
                "min_value": 0,
                "max_value": 10,
                "order": 4,
                "weight": 1.5,
            },
            {
                "question_text": "Any additional feedback about your savings experience?",
                "question_type": "text_long",
                "is_required": False,
                "order": 5,
                "weight": 1.0,
            },
        ],
    },
    {
        "name": "Milestone Check-in Survey",
        "description": "Quick pulse check at key milestones in the loan process",
        "survey_type": "milestone",
        "trigger_type": "milestone_reached",
        "intro_message": "Quick question - how's everything going so far?",
        "thank_you_message": "Thanks for the update!",
        "questions": [
            {
                "question_text": "How would you rate your experience so far?",
                "question_type": "rating",
                "is_required": True,
                "min_value": 1,
                "max_value": 5,
                "order": 1,
                "weight": 1.5,
            },
            {
                "question_text": "Is there anything you need help with?",
                "question_type": "yes_no",
                "is_required": True,
                "order": 2,
                "weight": 1.0,
            },
            {
                "question_text": "If yes, please describe:",
                "question_type": "text",
                "is_required": False,
                "conditional_logic": {"show_if": {"question_order": 2, "value": "yes"}},
                "order": 3,
                "weight": 1.0,
            },
        ],
    },
]


def seed_surveys(organization_id: int = 1, created_by_id: int = None):
    """
    Seed survey templates for an organization.

    Args:
        organization_id: The organization to create templates for
        created_by_id: The user ID to attribute as creator
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    try:
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        created_count = 0

        for template_data in SURVEY_TEMPLATES:
            # Check if template already exists
            existing = session.execute(
                text("""
                    SELECT id FROM survey_templates
                    WHERE organization_id = :org_id AND name = :name
                """),
                {"org_id": organization_id, "name": template_data["name"]}
            ).fetchone()

            if existing:
                logger.info(f"Template '{template_data['name']}' already exists, skipping")
                continue

            # Create template
            result = session.execute(
                text("""
                    INSERT INTO survey_templates (
                        organization_id, name, description, survey_type, status,
                        trigger_type, trigger_config, intro_message, thank_you_message,
                        created_by, created_at
                    ) VALUES (
                        :org_id, :name, :description, :survey_type, 'active',
                        :trigger_type, :trigger_config, :intro_message, :thank_you_message,
                        :created_by, CURRENT_TIMESTAMP
                    ) RETURNING id
                """),
                {
                    "org_id": organization_id,
                    "name": template_data["name"],
                    "description": template_data["description"],
                    "survey_type": template_data["survey_type"],
                    "trigger_type": template_data.get("trigger_type", "manual"),
                    "trigger_config": str(template_data.get("trigger_config", {})).replace("'", '"'),
                    "intro_message": template_data.get("intro_message"),
                    "thank_you_message": template_data.get("thank_you_message"),
                    "created_by": created_by_id,
                }
            )
            template_id = result.fetchone()[0]

            # Create questions
            for question_data in template_data.get("questions", []):
                session.execute(
                    text("""
                        INSERT INTO survey_questions (
                            template_id, question_text, question_type, help_text,
                            options, is_required, min_value, max_value,
                            "order", weight, conditional_logic, created_at
                        ) VALUES (
                            :template_id, :question_text, :question_type, :help_text,
                            :options, :is_required, :min_value, :max_value,
                            :order, :weight, :conditional_logic, CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "template_id": template_id,
                        "question_text": question_data["question_text"],
                        "question_type": question_data["question_type"],
                        "help_text": question_data.get("help_text"),
                        "options": str(question_data.get("options", [])).replace("'", '"'),
                        "is_required": question_data.get("is_required", True),
                        "min_value": question_data.get("min_value"),
                        "max_value": question_data.get("max_value"),
                        "order": question_data.get("order", 0),
                        "weight": question_data.get("weight", 1.0),
                        "conditional_logic": str(question_data.get("conditional_logic", {})).replace("'", '"') if question_data.get("conditional_logic") else None,
                    }
                )

            created_count += 1
            logger.info(f"✅ Created template: {template_data['name']}")

        session.commit()
        session.close()

        logger.info(f"✅ Seeded {created_count} survey templates")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to seed surveys: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Seeding survey templates...")
    if seed_surveys():
        print("Survey templates seeded successfully!")
    else:
        print("Failed to seed surveys. Check logs for details.")
