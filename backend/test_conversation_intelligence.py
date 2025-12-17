#!/usr/bin/env python3
"""
Test Script for Unified Conversation Intelligence System

Tests the ConversationIntelligence service and QualificationAgent
across both email and SMS channels.

Run with: python test_conversation_intelligence.py
"""

import sys
sys.path.insert(0, '.')

from services.conversation_intelligence import (
    ConversationIntelligenceService,
    analyze_tone,
    extract_qualification_data,
    get_next_qualification_question,
    check_for_objections,
    Channel,
    ConversationStage,
    QualificationStatus
)

from agents.qualification_agent import (
    QualificationAgent,
    create_qualification_agent,
    process_qualification_message
)


def test_tone_analysis():
    """Test tone analysis across various scenarios."""
    print("\n" + "="*60)
    print("Testing Tone Analysis")
    print("="*60)

    test_cases = [
        {
            "text": "I'm so frustrated! I've been waiting for weeks and nobody has called me back!",
            "expected_emotion": "frustrated",
            "expected_urgency": "high"
        },
        {
            "text": "This is amazing news! I can't wait to move into our dream home!",
            "expected_emotion": "excited",
            "expected_sentiment": "very_positive"
        },
        {
            "text": "URGENT: I need this resolved immediately. This is unacceptable.",
            "expected_emotion": "angry",
            "expected_urgency": "critical"
        },
        {
            "text": "I don't understand the difference between FHA and conventional. Can you explain?",
            "expected_emotion": "confused",
            "expected_style": "casual"
        },
        {
            "text": "Thank you so much for all your help. You've been wonderful!",
            "expected_emotion": "grateful",
            "expected_sentiment": "very_positive"
        }
    ]

    passed = 0
    for case in test_cases:
        result = analyze_tone(case["text"])

        checks = []
        if "expected_emotion" in case:
            emotion_match = result.emotional_state["primary_emotion"] == case["expected_emotion"]
            checks.append(("emotion", emotion_match, case["expected_emotion"], result.emotional_state["primary_emotion"]))

        if "expected_urgency" in case:
            urgency_match = result.urgency["urgency_level"] == case["expected_urgency"]
            checks.append(("urgency", urgency_match, case["expected_urgency"], result.urgency["urgency_level"]))

        if "expected_sentiment" in case:
            sentiment_match = result.sentiment["sentiment_category"] == case["expected_sentiment"]
            checks.append(("sentiment", sentiment_match, case["expected_sentiment"], result.sentiment["sentiment_category"]))

        if "expected_style" in case:
            style_match = result.communication_style["primary_style"] == case["expected_style"]
            checks.append(("style", style_match, case["expected_style"], result.communication_style["primary_style"]))

        all_passed = all(c[1] for c in checks)
        status = "PASS" if all_passed else "FAIL"
        passed += 1 if all_passed else 0

        print(f"\n{status}: {case['text'][:60]}...")
        for check_name, check_passed, expected, actual in checks:
            print(f"  {check_name}: expected={expected}, actual={actual} {'✓' if check_passed else '✗'}")

    print(f"\n{passed}/{len(test_cases)} tone analysis tests passed")
    return passed == len(test_cases)


def test_qualification_extraction():
    """Test qualification data extraction."""
    print("\n" + "="*60)
    print("Testing Qualification Data Extraction")
    print("="*60)

    test_cases = [
        {
            "text": "I'm looking to purchase a home around $450,000",
            "expected": {"loan_purpose": "purchase", "property_value": 450000}
        },
        {
            "text": "We want to refinance, hoping to close within 30 days",
            "expected": {"loan_purpose": "refinance", "closing_timeline": "30_days"}
        },
        {
            "text": "My name is John and my email is john@example.com",
            "expected": {"first_name": "John", "email": "john@example.com"}
        },
        {
            "text": "I've already been pre-approved by another lender",
            "expected": {"pre_approved_elsewhere": True}
        },
        {
            "text": "This is my first home, I'm a first-time buyer",
            "expected": {"first_time_buyer": True}
        }
    ]

    passed = 0
    for case in test_cases:
        result = extract_qualification_data(case["text"])

        checks = []
        for field, expected_value in case["expected"].items():
            actual_value = getattr(result, field)
            match = actual_value == expected_value
            checks.append((field, match, expected_value, actual_value))

        all_passed = all(c[1] for c in checks)
        status = "PASS" if all_passed else "FAIL"
        passed += 1 if all_passed else 0

        print(f"\n{status}: {case['text'][:60]}...")
        for field, match, expected, actual in checks:
            print(f"  {field}: expected={expected}, actual={actual} {'✓' if match else '✗'}")

    print(f"\n{passed}/{len(test_cases)} extraction tests passed")
    return passed == len(test_cases)


def test_objection_detection():
    """Test objection detection."""
    print("\n" + "="*60)
    print("Testing Objection Detection")
    print("="*60)

    test_cases = [
        ("Not interested, please don't contact me again", True, "not_interested"),
        ("I'm already working with another lender", True, "using_another"),
        ("This isn't a good time, I'm busy", True, "bad_timing"),
        ("The rates are too high right now", True, "rate_concern"),
        ("I'm just looking, not ready yet", True, "not_ready"),
        ("Sounds great! When can we talk?", False, None),
        ("I'd love to learn more about my options", False, None),
    ]

    passed = 0
    for text, expected_objection, expected_type in test_cases:
        has_objection, objection_type = check_for_objections(text)

        objection_match = has_objection == expected_objection
        type_match = objection_type == expected_type if expected_objection else True

        all_passed = objection_match and type_match
        status = "PASS" if all_passed else "FAIL"
        passed += 1 if all_passed else 0

        print(f"\n{status}: {text[:50]}...")
        print(f"  has_objection: expected={expected_objection}, actual={has_objection}")
        if expected_type or objection_type:
            print(f"  type: expected={expected_type}, actual={objection_type}")

    print(f"\n{passed}/{len(test_cases)} objection tests passed")
    return passed == len(test_cases)


def test_qualification_agent_sms():
    """Test the QualificationAgent with an SMS conversation flow."""
    print("\n" + "="*60)
    print("Testing QualificationAgent - SMS Channel")
    print("="*60)

    agent = create_qualification_agent()
    conversation_id = "test_sms_conv_001"

    # Simulate a conversation
    messages = [
        ("Hi, I saw your ad about home loans", None),
        ("I'm looking to buy my first home", {"loan_purpose": "purchase", "first_time_buyer": True}),
        ("Around $350,000", {"property_value": 350000}),
        ("Hoping to close in about 2 months", {"closing_timeline": "60_days"}),
        ("No, I haven't been pre-approved yet", {"pre_approved_elsewhere": False}),
        ("My name is Sarah", {"first_name": "Sarah"}),
        ("Sure, my email is sarah@test.com", {"email": "sarah@test.com"}),
    ]

    print("\n--- Simulating SMS Conversation ---\n")

    for i, (message, expected_updates) in enumerate(messages):
        print(f"USER: {message}")

        result = agent.process_message(
            conversation_id=conversation_id,
            message=message,
            channel="sms",
            sender_info={"phone": "5551234567"} if i == 0 else None
        )

        print(f"AGENT [{result['response_type']}]: {result['response']}")
        print(f"       Qualification: {result['qualification']['completion_percentage']:.0f}%")

        if expected_updates:
            qual_data = result['qualification']['data']
            for field, expected in expected_updates.items():
                actual = qual_data.get(field)
                match = actual == expected
                if not match:
                    print(f"       WARNING: {field} expected={expected}, got={actual}")

        print()

    # Check final state
    final_completion = result['qualification']['completion_percentage']
    print(f"Final qualification completion: {final_completion}%")
    print(f"Final stage: {result['conversation_state']['stage']}")

    success = final_completion >= 80
    print(f"\n{'PASS' if success else 'FAIL'}: SMS conversation flow")
    return success


def test_qualification_agent_email():
    """Test the QualificationAgent with an email conversation flow."""
    print("\n" + "="*60)
    print("Testing QualificationAgent - Email Channel")
    print("="*60)

    agent = create_qualification_agent()
    conversation_id = "test_email_conv_001"

    # Simulate email conversation (emails tend to have more info per message)
    messages = [
        "Subject: Interested in refinancing\n\nHi, I'm interested in refinancing my home. The property is worth about $500,000. My name is Michael.",
        "I'm hoping to close within the next 60 days if possible. I've already been pre-approved by my bank but wanted to shop around.",
        "My phone number is 555-987-6543 if you want to call me to discuss.",
    ]

    print("\n--- Simulating Email Conversation ---\n")

    for i, message in enumerate(messages):
        print(f"EMAIL #{i+1}:")
        print(f"  {message[:100]}...")

        result = agent.process_message(
            conversation_id=conversation_id,
            message=message,
            channel="email",
            sender_info={"email": "michael@test.com"} if i == 0 else None
        )

        print(f"\nAGENT RESPONSE [{result['response_type']}]:")
        print(f"  {result['response'][:150]}...")
        print(f"\n  Qualification: {result['qualification']['completion_percentage']:.0f}%")
        print(f"  Stage: {result['conversation_state']['stage']}")
        print(f"  Tone: {result['tone_analysis']['emotional_state']['primary_emotion']}")
        print()

    # Check final state
    final_completion = result['qualification']['completion_percentage']
    print(f"Final qualification completion: {final_completion}%")

    success = final_completion >= 80
    print(f"\n{'PASS' if success else 'FAIL'}: Email conversation flow")
    return success


def test_objection_handling():
    """Test objection handling in the agent."""
    print("\n" + "="*60)
    print("Testing Objection Handling")
    print("="*60)

    agent = create_qualification_agent()
    conversation_id = "test_objection_conv"

    # First, establish the conversation
    result = agent.process_message(
        conversation_id=conversation_id,
        message="Hi, I saw your ad",
        channel="sms"
    )
    print(f"USER: Hi, I saw your ad")
    print(f"AGENT: {result['response']}\n")

    # Now send an objection
    result = agent.process_message(
        conversation_id=conversation_id,
        message="I'm not interested, I'm already working with another lender",
        channel="sms"
    )

    print(f"USER: I'm not interested, I'm already working with another lender")
    print(f"AGENT [{result['response_type']}]: {result['response']}")
    print(f"Objection detected: {result.get('should_escalate', False)}")
    print(f"Objection count: {result['conversation_state'].get('objection_count', 0)}")

    success = result['response_type'] == 'objection_handling'
    print(f"\n{'PASS' if success else 'FAIL'}: Objection handling")
    return success


def test_escalation():
    """Test escalation triggers."""
    print("\n" + "="*60)
    print("Testing Escalation Triggers")
    print("="*60)

    agent = create_qualification_agent()
    conversation_id = "test_escalation_conv"

    # Angry message that should trigger escalation
    result = agent.process_message(
        conversation_id=conversation_id,
        message="This is UNACCEPTABLE! I've been waiting for WEEKS! I want to speak to your supervisor immediately or I'm calling my attorney!",
        channel="email"
    )

    print(f"USER: [Angry message about wanting supervisor/attorney]")
    print(f"AGENT [{result['response_type']}]: {result['response'][:100]}...")
    print(f"Should escalate: {result['should_escalate']}")
    print(f"Escalation reason: {result.get('escalation_reason')}")
    print(f"Tone risk level: {result['tone_analysis']['risk_level']}")

    success = result['should_escalate'] == True
    print(f"\n{'PASS' if success else 'FAIL'}: Escalation trigger")
    return success


def test_white_label():
    """Test white-label organization customization."""
    print("\n" + "="*60)
    print("Testing White-Label Customization")
    print("="*60)

    # Custom organization
    custom_org = {
        "id": 123,
        "brand_name": "ABC Mortgage",
        "website": "https://abcmortgage.com",
        "agent_personas": {
            "qualification_agent": {
                "name": "Mike",
                "role": "Mortgage Advisor"
            }
        }
    }

    agent = create_qualification_agent(organization=custom_org)

    result = agent.process_message(
        conversation_id="test_whitelabel",
        message="Hi, I'm interested in a loan",
        channel="sms"
    )

    print(f"Organization: ABC Mortgage")
    print(f"Agent name: {result['metadata']['persona']}")
    print(f"Company: {result['metadata']['company']}")

    success = result['metadata']['company'] == "ABC Mortgage" and result['metadata']['persona'] == "Mike"
    print(f"\n{'PASS' if success else 'FAIL'}: White-label customization")
    return success


def main():
    print("="*60)
    print("Unified Conversation Intelligence Test Suite")
    print("="*60)

    results = {
        "Tone Analysis": test_tone_analysis(),
        "Qualification Extraction": test_qualification_extraction(),
        "Objection Detection": test_objection_detection(),
        "SMS Conversation Flow": test_qualification_agent_sms(),
        "Email Conversation Flow": test_qualification_agent_email(),
        "Objection Handling": test_objection_handling(),
        "Escalation Triggers": test_escalation(),
        "White-Label": test_white_label(),
    }

    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)

    all_passed = True
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    print("="*60)
    if all_passed:
        print("All tests PASSED!")
    else:
        print("Some tests FAILED - review output above")
    print("="*60)

    print("\nUsage Examples:")
    print("-" * 40)
    print("""
# Process an SMS message:
from agents.qualification_agent import process_qualification_message

result = process_qualification_message(
    conversation_id="sms_5551234567",
    message="I want to buy a $400k home",
    channel="sms",
    sender_info={"phone": "5551234567"}
)
print(result['response'])  # Agent's response
print(result['qualification']['completion_percentage'])  # Progress

# Process an email:
result = process_qualification_message(
    conversation_id="email_conv_123",
    message="Subject: Refinance inquiry...",
    channel="email",
    sender_info={"email": "user@example.com"}
)

# Analyze tone only:
from services.conversation_intelligence import get_tone_analysis
tone = get_tone_analysis("I'm frustrated with the process")
print(tone['emotional_state']['primary_emotion'])  # 'frustrated'
""")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
