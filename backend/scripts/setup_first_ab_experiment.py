"""
Setup First A/B Experiment - AI Response Quality Optimization

This script creates the first production A/B experiment to test
prompt variations for improving AI response quality.

Experiment: "AI Response Prompt V2"
- Control: Current production prompt
- Treatment: Enhanced prompt with few-shot examples and clearer guidelines

Metrics tracked:
- response_quality: Heuristic quality score (0-1)
- sentiment_score: Conversation sentiment (0-1)
- resolution_rate: Whether user intent was understood (0-1)
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def create_first_experiment():
    """Create the first A/B experiment for AI prompt optimization"""

    from ab_testing.experiment_service import ExperimentService

    db = SessionLocal()

    try:
        service = ExperimentService(db)

        # Define the experiment
        experiment_data = {
            "name": "ai_response_prompt_v2",
            "description": "Testing enhanced AI prompt with few-shot examples and mortgage-specific guidelines for improved response quality",
            "experiment_type": "prompt",
            "primary_metric": "response_quality",
            "secondary_metrics": ["sentiment_score", "resolution_rate"],
            "min_sample_size": 100,
            "confidence_level": 0.95,
            "target_percentage": 100.0,  # All users participate
        }

        # Define variants
        control_config = {
            "system_prompt": """You are an intelligent AI assistant for a mortgage CRM system. Your role is to help mortgage loan officers manage their business efficiently.

You have access to conversation history and context. Use this information to provide personalized, relevant responses.

## RESPONSE GUIDELINES:
1. Reference past conversations naturally when relevant
2. Be concise but informative
3. Maintain professional mortgage industry tone
4. Highlight important details and action items""",
            "include_examples": False,
            "version": "v1_control"
        }

        treatment_config = {
            "system_prompt": """You are an expert AI assistant for mortgage professionals. You help loan officers close more deals by providing quick, accurate information and actionable insights.

## YOUR EXPERTISE:
- Mortgage loan types (Conventional, FHA, VA, USDA, Jumbo)
- Rate analysis and lock recommendations
- Pipeline management and prioritization
- Compliance requirements (TRID, RESPA, Fair Lending)
- Document collection and processing

## RESPONSE STYLE:
- Lead with the most important information
- Use bullet points for clarity
- Include specific next steps when applicable
- Reference borrower/loan context naturally""",
            "include_examples": True,
            "examples": [
                "User: What's the status of John Smith's loan?\nAssistant: John Smith's loan is in underwriting (Day 3 of 5 typical). Key items:\n- Appraisal received: $425,000 (supports value)\n- Income docs: Verified\n- Pending: VOE from employer\n\n**Next step:** Follow up with HR at Acme Corp for VOE - I can draft that email for you.",

                "User: Which loans should I focus on today?\nAssistant: Top 3 priorities for today:\n1. **Martinez loan** - Lock expires tomorrow, rate still favorable. Recommend locking now.\n2. **Johnson file** - CTC pending one condition (updated bank statement). Borrower uploaded 2 hours ago.\n3. **Williams application** - Hot lead, submitted yesterday. First-time homebuyer, very motivated.\n\nWant me to pull details on any of these?",

                "User: How do I explain PMI to my borrower?\nAssistant: Here's a clear PMI explanation:\n\n**What it is:** Insurance that protects the lender if you default. Required when down payment is <20%.\n\n**Cost:** Typically 0.5-1% of loan amount annually ($1,250-2,500/year on a $250K loan).\n\n**Good news:** It's removable! Once you reach 20% equity (usually 2-5 years), you can request removal.\n\n**Pro tip:** For price-conscious borrowers, mention that PMI enables homeownership sooner vs. waiting to save 20%."
            ],
            "response_guidelines": """## RESPONSE GUIDELINES:
1. Start with a direct answer to the question
2. Include relevant context from borrower/loan data
3. Provide clear next steps or recommendations
4. Keep responses focused - avoid unnecessary information
5. Use formatting (bullets, bold) for scannability""",
            "version": "v2_enhanced"
        }

        variants = [
            {
                "name": "Control - Current Prompt",
                "is_control": True,
                "traffic_allocation": 50.0,
                "config": control_config
            },
            {
                "name": "Treatment - Enhanced with Examples",
                "is_control": False,
                "traffic_allocation": 50.0,
                "config": treatment_config
            }
        ]

        # Create the experiment
        print("Creating A/B experiment: ai_response_prompt_v2")
        print("-" * 50)

        experiment = service.create_experiment(
            name=experiment_data["name"],
            description=experiment_data["description"],
            experiment_type=experiment_data["experiment_type"],
            primary_metric=experiment_data["primary_metric"],
            secondary_metrics=experiment_data["secondary_metrics"],
            variants=variants,
            min_sample_size=experiment_data["min_sample_size"],
            confidence_level=experiment_data["confidence_level"],
            target_percentage=experiment_data["target_percentage"]
        )

        if experiment:
            print(f"✅ Experiment created successfully!")
            print(f"   ID: {experiment.id}")
            print(f"   Name: {experiment.name}")
            print(f"   Status: {experiment.status}")
            print(f"   Variants: {len(variants)}")
            print()

            # Start the experiment
            print("Starting experiment...")
            started = service.start_experiment(experiment.id)

            if started:
                print(f"✅ Experiment is now RUNNING!")
                print()
                print("=" * 50)
                print("EXPERIMENT DETAILS")
                print("=" * 50)
                print(f"Name: {experiment.name}")
                print(f"Type: {experiment.experiment_type}")
                print(f"Primary Metric: {experiment.primary_metric}")
                print(f"Target Sample Size: {experiment.min_sample_size}")
                print(f"Traffic Split: 50/50")
                print()
                print("Variants:")
                print("  1. Control - Current Prompt (50%)")
                print("  2. Treatment - Enhanced with Examples (50%)")
                print()
                print("Metrics tracked:")
                print("  - response_quality")
                print("  - sentiment_score")
                print("  - resolution_rate")
                print()
                print("=" * 50)
                print("NEXT STEPS")
                print("=" * 50)
                print("1. The experiment is now collecting data automatically")
                print("2. Monitor progress at: /api/v1/experiments/{}/analyze".format(experiment.id))
                print("3. View dashboard at: /experiments (frontend)")
                print("4. Once 100+ samples collected, analysis will be statistically significant")
                print()
            else:
                print("❌ Failed to start experiment")
        else:
            print("❌ Failed to create experiment")

        return experiment

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()


def check_existing_experiments():
    """Check if experiment already exists"""
    from ab_testing_models import Experiment

    db = SessionLocal()
    try:
        existing = db.query(Experiment).filter(
            Experiment.name == "ai_response_prompt_v2"
        ).first()

        if existing:
            print(f"Experiment 'ai_response_prompt_v2' already exists!")
            print(f"  ID: {existing.id}")
            print(f"  Status: {existing.status}")
            print(f"  Created: {existing.created_at}")
            return existing
        return None
    finally:
        db.close()


if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  PERENNIA AI - First A/B Experiment Setup")
    print("=" * 60)
    print()

    # Check if already exists
    existing = check_existing_experiments()

    if existing:
        print()
        print("Use --force to recreate the experiment")
        if len(sys.argv) > 1 and sys.argv[1] == "--force":
            print("Recreating experiment...")
            # Delete existing
            db = SessionLocal()
            from ab_testing_models import Experiment
            db.query(Experiment).filter(Experiment.name == "ai_response_prompt_v2").delete()
            db.commit()
            db.close()
            create_first_experiment()
    else:
        create_first_experiment()

    print()
