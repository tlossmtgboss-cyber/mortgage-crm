"""
Example: Using the A/B Testing Framework
Demonstrates how to create and run experiments for AI optimization
"""
import requests
import json
import time

# API base URL
BASE_URL = "http://localhost:8000"  # Change to your API URL


def create_prompt_experiment():
    """
    Example 1: Create an experiment to test different AI prompts
    """
    print("\n" + "="*80)
    print("EXAMPLE 1: Creating Prompt Experiment")
    print("="*80)

    experiment_data = {
        "name": "Lead Qualification Prompt Test",
        "description": "Testing new prompt with few-shot examples vs current prompt",
        "experiment_type": "prompt",
        "primary_metric": "resolution_rate",
        "secondary_metrics": ["satisfaction_score", "response_time"],
        "variants": [
            {
                "name": "Control - Current Prompt",
                "is_control": True,
                "traffic_allocation": 50.0,
                "config": {
                    "system_prompt": "You are an AI assistant for a mortgage CRM system. Help loan officers manage their business efficiently.",
                    "include_examples": False
                }
            },
            {
                "name": "Treatment - Few Shot Examples",
                "is_control": False,
                "traffic_allocation": 50.0,
                "config": {
                    "system_prompt": "You are an AI assistant for a mortgage CRM system. Help loan officers manage their business efficiently.",
                    "include_examples": True,
                    "examples": [
                        "User: What documents do I need for a purchase loan? Assistant: For a purchase loan, you'll typically need: 1) Last 2 years of tax returns, 2) Recent pay stubs (30 days), 3) Bank statements (2 months), 4) Purchase agreement, 5) ID. I'll help you prepare these.",
                        "User: How long does approval take? Assistant: Typical approval timeline is 3-5 business days for pre-approval, and 30-45 days total for closing. Let me check your specific loan status..."
                    ],
                    "response_guidelines": "Use concrete examples from past conversations"
                }
            }
        ],
        "target_percentage": 100.0,
        "min_sample_size": 100,
        "confidence_level": 0.95
    }

    response = requests.post(
        f"{BASE_URL}/api/v1/experiments/",
        json=experiment_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 201:
        experiment_id = response.json()["id"]
        print(f"\n✅ Experiment created successfully! ID: {experiment_id}")
        return experiment_id
    else:
        print(f"\n❌ Failed to create experiment")
        return None


def create_model_comparison_experiment():
    """
    Example 2: Compare Claude vs GPT-4
    """
    print("\n" + "="*80)
    print("EXAMPLE 2: Creating Model Comparison Experiment")
    print("="*80)

    experiment_data = {
        "name": "Claude vs GPT-4 for Lead Scoring",
        "description": "Testing which model performs better for automated lead qualification",
        "experiment_type": "model",
        "primary_metric": "accuracy",
        "secondary_metrics": ["response_time", "cost_per_request"],
        "variants": [
            {
                "name": "Claude 3.5 Sonnet",
                "is_control": True,
                "traffic_allocation": 50.0,
                "config": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 2000,
                    "temperature": 0.7
                }
            },
            {
                "name": "GPT-4 Turbo",
                "is_control": False,
                "traffic_allocation": 50.0,
                "config": {
                    "provider": "openai",
                    "model": "gpt-4-turbo-preview",
                    "max_tokens": 2000,
                    "temperature": 0.7
                }
            }
        ],
        "target_percentage": 100.0,
        "min_sample_size": 200,
        "confidence_level": 0.95
    }

    response = requests.post(
        f"{BASE_URL}/api/v1/experiments/",
        json=experiment_data
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 201:
        experiment_id = response.json()["id"]
        print(f"\n✅ Experiment created successfully! ID: {experiment_id}")
        return experiment_id
    else:
        print(f"\n❌ Failed to create experiment")
        return None


def start_experiment(experiment_id):
    """Start an experiment"""
    print(f"\n📊 Starting experiment {experiment_id}...")

    response = requests.post(
        f"{BASE_URL}/api/v1/experiments/{experiment_id}/start"
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

    if response.status_code == 200:
        print(f"✅ Experiment {experiment_id} started!")
        return True
    else:
        print(f"❌ Failed to start experiment")
        return False


def simulate_user_interactions(experiment_name, num_users=50):
    """
    Simulate user interactions to generate experiment data
    """
    print(f"\n🔄 Simulating {num_users} user interactions for '{experiment_name}'...")

    import random

    for i in range(num_users):
        user_id = 1000 + i  # Simulated user IDs

        # 1. Get variant assignment
        variant_response = requests.post(
            f"{BASE_URL}/api/v1/experiments/get-variant",
            json={
                "experiment_name": experiment_name,
                "user_id": user_id
            }
        )

        if variant_response.status_code != 200:
            continue

        variant_data = variant_response.json()

        if not variant_data.get("in_experiment"):
            continue

        variant = variant_data["variant"]
        print(f"User {user_id} assigned to: {variant['variant_name']}")

        # 2. Simulate metrics based on variant
        # Treatment variant should perform ~10-15% better
        is_treatment = not variant["is_control"]

        # Resolution rate (0 or 1)
        base_resolution_rate = 0.70
        if is_treatment:
            resolution_rate = 1.0 if random.random() < (base_resolution_rate + 0.15) else 0.0
        else:
            resolution_rate = 1.0 if random.random() < base_resolution_rate else 0.0

        # Satisfaction score (1-5 scale)
        base_satisfaction = 3.5
        if is_treatment:
            satisfaction = min(5.0, base_satisfaction + random.uniform(0.5, 1.0))
        else:
            satisfaction = min(5.0, base_satisfaction + random.uniform(0, 0.5))

        # Response time (seconds)
        response_time = random.uniform(1.0, 3.0)

        # Record results
        metrics = [
            ("resolution_rate", resolution_rate),
            ("satisfaction_score", satisfaction),
            ("response_time", response_time)
        ]

        for metric_name, metric_value in metrics:
            requests.post(
                f"{BASE_URL}/api/v1/experiments/record-result",
                json={
                    "experiment_name": experiment_name,
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "user_id": user_id
                }
            )

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{num_users} users...")

    print(f"✅ Completed {num_users} simulated interactions")


def analyze_experiment(experiment_id):
    """Analyze experiment results"""
    print(f"\n📈 Analyzing experiment {experiment_id}...")

    response = requests.get(
        f"{BASE_URL}/api/v1/experiments/{experiment_id}/analyze"
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        analysis = response.json()
        print("\n" + "="*80)
        print("ANALYSIS RESULTS")
        print("="*80)
        print(f"P-Value: {analysis['p_value']:.4f}")
        print(f"Statistically Significant: {'✅ YES' if analysis['is_significant'] else '❌ NO'}")
        print(f"Sample Size: {analysis['current_sample_size']} / {analysis['required_sample_size']}")
        print(f"Sufficient Samples: {'✅ YES' if analysis['sufficient_sample_size'] else '❌ NO'}")
        print(f"\nRecommended Winner: Variant {analysis['recommended_winner_id']}")
        print(f"Confidence: {analysis['recommendation_confidence']:.1%}")
        print(f"Reason: {analysis['recommendation_reason']}")

        print("\n" + "-"*80)
        print("VARIANT STATISTICS")
        print("-"*80)
        for variant_id, stats in analysis['variant_stats'].items():
            print(f"\nVariant {variant_id}:")
            print(f"  Mean: {stats['mean']:.3f}")
            print(f"  Std Dev: {stats['std']:.3f}")
            print(f"  Samples: {stats['count']}")
            print(f"  Min: {stats['min']:.3f}")
            print(f"  Max: {stats['max']:.3f}")

        return analysis
    else:
        print(f"❌ Analysis failed: {response.text}")
        return None


def get_experiment_summary(experiment_id):
    """Get human-readable summary"""
    print(f"\n📋 Getting summary for experiment {experiment_id}...")

    response = requests.get(
        f"{BASE_URL}/api/v1/experiments/{experiment_id}/summary"
    )

    if response.status_code == 200:
        summary = response.json()
        print("\n" + "="*80)
        print("EXPERIMENT SUMMARY")
        print("="*80)
        print(f"Name: {summary['experiment_name']}")
        print(f"Status: {summary['status']}")
        print(f"Primary Metric: {summary['primary_metric']}")
        print(f"\nVariants:")
        for variant in summary['variants']:
            winner_badge = " 🏆 WINNER" if variant['is_winner'] else ""
            control_badge = " (Control)" if variant['is_control'] else ""
            print(f"  - {variant['name']}{control_badge}{winner_badge}")
            print(f"    Mean: {variant['mean']:.3f} | Samples: {variant['count']}")

        if summary['is_significant']:
            print(f"\n✅ Statistically significant result (p={summary['p_value']:.4f})")
            print(f"Recommendation: {summary['recommendation_reason']}")
        else:
            print(f"\n⚠️  Not yet statistically significant (p={summary['p_value']:.4f})")
            print("Need more data or effect size is too small.")

        return summary
    else:
        print(f"❌ Failed to get summary")
        return None


def stop_experiment(experiment_id, declare_winner=True):
    """Stop experiment and optionally declare winner"""
    print(f"\n🛑 Stopping experiment {experiment_id}...")

    response = requests.post(
        f"{BASE_URL}/api/v1/experiments/{experiment_id}/stop?declare_winner={declare_winner}"
    )

    if response.status_code == 200:
        print(f"✅ Experiment {experiment_id} stopped successfully!")
        if declare_winner:
            print("🏆 Winner has been declared!")
        return True
    else:
        print(f"❌ Failed to stop experiment")
        return False


def list_all_experiments():
    """List all experiments"""
    print("\n📚 Listing all experiments...")

    response = requests.get(f"{BASE_URL}/api/v1/experiments/")

    if response.status_code == 200:
        data = response.json()
        experiments = data['experiments']
        print(f"\nFound {data['count']} experiments:")
        for exp in experiments:
            print(f"\n  ID: {exp['id']}")
            print(f"  Name: {exp['name']}")
            print(f"  Type: {exp['type']}")
            print(f"  Status: {exp['status']}")
            print(f"  Metric: {exp['primary_metric']}")
        return experiments
    else:
        print("❌ Failed to list experiments")
        return []


# ============================================================================
# MAIN DEMO
# ============================================================================

def run_full_demo():
    """Run complete A/B testing demonstration"""
    print("\n" + "="*80)
    print("A/B TESTING FRAMEWORK - COMPLETE DEMONSTRATION")
    print("="*80)

    # 1. Create experiment
    experiment_id = create_prompt_experiment()
    if not experiment_id:
        print("Demo failed - couldn't create experiment")
        return

    # 2. Start experiment
    if not start_experiment(experiment_id):
        print("Demo failed - couldn't start experiment")
        return

    # 3. Simulate user interactions
    simulate_user_interactions(
        experiment_name="Lead Qualification Prompt Test",
        num_users=120  # Should exceed min_sample_size of 100
    )

    # 4. Analyze results
    time.sleep(2)  # Give database a moment
    analysis = analyze_experiment(experiment_id)

    # 5. Get summary
    time.sleep(1)
    summary = get_experiment_summary(experiment_id)

    # 6. Stop experiment if significant
    if analysis and analysis['is_significant']:
        print("\n🎉 Significant result found! Stopping experiment and declaring winner...")
        stop_experiment(experiment_id, declare_winner=True)
    else:
        print("\n⚠️  Not significant yet. In production, continue collecting data.")

    # 7. List all experiments
    list_all_experiments()

    print("\n" + "="*80)
    print("DEMO COMPLETE!")
    print("="*80)
    print("\nNext steps:")
    print("1. Check the experiment details at: http://localhost:8000/docs")
    print("2. Integrate with your AI services using ai_memory_service_with_ab_testing.py")
    print("3. Create more experiments to continuously optimize AI performance")
    print("\nSee AB_TESTING_GUIDE.md for complete documentation")


if __name__ == "__main__":
    print("A/B Testing Framework - Example Usage")
    print("Make sure your API is running at http://localhost:8000")
    print("\nPress Enter to start demo, or Ctrl+C to exit...")
    input()

    try:
        run_full_demo()
    except KeyboardInterrupt:
        print("\n\n Demo cancelled by user")
    except requests.exceptions.ConnectionError:
        print("\n\n❌ ERROR: Could not connect to API at http://localhost:8000")
        print("Make sure the backend is running: python main.py")
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
