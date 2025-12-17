#!/usr/bin/env python3
"""
Test script for Enhanced Tone Analysis in Email Intelligence
Tests emotional state, communication style, sentiment intensity, and urgency detection.
"""

import sys
sys.path.insert(0, '.')

from agents.tools.email_intel import (
    parse_email,
    analyze_tone,
    _analyze_emotional_state,
    _analyze_communication_style,
    _calculate_sentiment_intensity,
    _detect_urgency_level,
)


def test_emotional_states():
    """Test emotional state detection with various email samples."""
    print("\n" + "="*60)
    print("Testing Emotional State Detection")
    print("="*60)

    test_cases = [
        {
            "name": "Angry customer",
            "text": "This is absolutely unacceptable! I've been waiting for weeks and nobody has helped me. I want to speak to your supervisor immediately. If this isn't resolved, I'm contacting my attorney.",
            "expected_emotion": "angry"
        },
        {
            "name": "Frustrated customer",
            "text": "I'm so frustrated with this process. It feels like a waste of time. Every time I call, I get different information. This is ridiculous.",
            "expected_emotion": "frustrated"
        },
        {
            "name": "Confused customer",
            "text": "I don't understand what you mean by debt-to-income ratio. Can you explain this? I'm not sure what documents you need. It's all very confusing.",
            "expected_emotion": "confused"
        },
        {
            "name": "Excited customer",
            "text": "This is amazing news! I'm so thrilled we got approved! Can't wait to move into our dream home. You've been fantastic!",
            "expected_emotion": "excited"
        },
        {
            "name": "Anxious customer",
            "text": "I'm worried about the deadline. What if we don't close on time? I'm nervous about the rate lock expiring. This is overwhelming.",
            "expected_emotion": "anxious"
        },
        {
            "name": "Grateful customer",
            "text": "Thank you so much for all your help! I really appreciate everything you've done. You went above and beyond. Exceptional service!",
            "expected_emotion": "grateful"
        },
    ]

    passed = 0
    for case in test_cases:
        result = _analyze_emotional_state(case["text"])
        match = result["primary_emotion"] == case["expected_emotion"]
        status = "PASS" if match else "FAIL"
        passed += 1 if match else 0

        print(f"\n{status}: {case['name']}")
        print(f"  Expected: {case['expected_emotion']}")
        print(f"  Detected: {result['primary_emotion']} (score: {result['primary_score']})")
        if result["all_emotions"]:
            print(f"  All emotions: {result['all_emotions']}")

    print(f"\n{passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_communication_styles():
    """Test communication style detection."""
    print("\n" + "="*60)
    print("Testing Communication Style Detection")
    print("="*60)

    test_cases = [
        {
            "name": "Formal style",
            "text": "Dear Mr. Johnson, I am writing to inquire about the status of my loan application. I would appreciate your prompt attention to this matter. Sincerely yours, Robert Smith",
            "expected_style": "formal"
        },
        {
            "name": "Casual style",
            "text": "Hey! Thanks for the update! Awesome news about the approval. No worries about the docs, I'll get them over soon. Btw, is there anything else you need?",
            "expected_style": "casual"
        },
        {
            "name": "Urgent style",
            "text": "URGENT: I need this resolved immediately!! This is time sensitive - the deadline is TODAY. Please call me ASAP!!!",
            "expected_style": "urgent"
        },
        {
            "name": "Professional style",
            "text": "Please advise on the next steps. As discussed, I've attached the documents for your review. Following up on our conversation, kindly confirm receipt.",
            "expected_style": "professional"
        },
        {
            "name": "Friendly style",
            "text": "Hope you're doing well! It was such a pleasure meeting with you. Happy to help with anything you need. Feel free to reach out anytime!",
            "expected_style": "friendly"
        },
    ]

    passed = 0
    for case in test_cases:
        result = _analyze_communication_style(case["text"])
        match = result["primary_style"] == case["expected_style"]
        status = "PASS" if match else "FAIL"
        passed += 1 if match else 0

        print(f"\n{status}: {case['name']}")
        print(f"  Expected: {case['expected_style']}")
        print(f"  Detected: {result['primary_style']} (score: {result['primary_score']})")
        if result["secondary_style"]:
            print(f"  Secondary: {result['secondary_style']}")

    print(f"\n{passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_sentiment_intensity():
    """Test sentiment intensity detection."""
    print("\n" + "="*60)
    print("Testing Sentiment Intensity Detection")
    print("="*60)

    test_cases = [
        {
            "name": "Very positive",
            "text": "Absolutely amazing! This is perfect, exactly what I wanted. Excellent service, wonderful experience. I'm so happy and grateful!",
            "expected_category": "very_positive"
        },
        {
            "name": "Positive",
            "text": "Thanks for the update. Good news about the approval. Everything looks fine.",
            "expected_category": "positive"
        },
        {
            "name": "Neutral",
            "text": "I received the documents. Please let me know the next steps.",
            "expected_category": "neutral"
        },
        {
            "name": "Negative",
            "text": "There's a problem with the application. The process has been disappointing and frustrating.",
            "expected_category": "negative"
        },
        {
            "name": "Very negative",
            "text": "This is terrible! Worst experience ever. Horrible service, incompetent staff. I'm angry and upset about this awful situation.",
            "expected_category": "very_negative"
        },
    ]

    passed = 0
    for case in test_cases:
        result = _calculate_sentiment_intensity(case["text"])
        match = result["sentiment_category"] == case["expected_category"]
        status = "PASS" if match else "FAIL"
        passed += 1 if match else 0

        print(f"\n{status}: {case['name']}")
        print(f"  Expected: {case['expected_category']}")
        print(f"  Detected: {result['sentiment_category']} (score: {result['sentiment_score']}, intensity: {result['intensity_level']})")
        print(f"  Positive words: {result['positive_words'][:5]}")
        print(f"  Negative words: {result['negative_words'][:5]}")

    print(f"\n{passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_urgency_detection():
    """Test urgency level detection."""
    print("\n" + "="*60)
    print("Testing Urgency Detection")
    print("="*60)

    test_cases = [
        {
            "name": "Critical urgency",
            "text": "EMERGENCY! I need this handled immediately. This is urgent and time sensitive!",
            "expected_level": "critical"
        },
        {
            "name": "High urgency",
            "text": "Please handle this today. The deadline is tomorrow and time is running out.",
            "expected_level": "high"
        },
        {
            "name": "Medium urgency",
            "text": "Following up on our conversation. Please get back to me this week when you can.",
            "expected_level": "medium"
        },
        {
            "name": "Low urgency",
            "text": "Just wanted to share this FYI. No rush, whenever you have time. At your convenience.",
            "expected_level": "low"
        },
    ]

    passed = 0
    for case in test_cases:
        result = _detect_urgency_level(case["text"])
        match = result["urgency_level"] == case["expected_level"]
        status = "PASS" if match else "FAIL"
        passed += 1 if match else 0

        print(f"\n{status}: {case['name']}")
        print(f"  Expected: {case['expected_level']}")
        print(f"  Detected: {result['urgency_level']} (score: {result['urgency_score']})")
        if result["urgency_indicators"]:
            print(f"  Indicators: {result['urgency_indicators']}")

    print(f"\n{passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_parse_email_with_tone():
    """Test the enhanced parse_email function."""
    print("\n" + "="*60)
    print("Testing Enhanced parse_email Function")
    print("="*60)

    result = parse_email(
        subject="URGENT: Very disappointed with the process",
        body="""I'm extremely frustrated with this situation. I've been waiting for weeks
        and nobody has given me a clear answer. Can you please explain what's happening?
        This is unacceptable. I expected much better service. Please call me immediately.

        Thanks,
        John""",
        from_email="john@example.com"
    )

    print(f"\nParse result status: {result.status}")
    data = result.data

    print(f"\nBasic Analysis:")
    print(f"  Primary Intent: {data['primary_intent']}")
    print(f"  Sentiment: {data['sentiment']}")
    print(f"  Urgency: {data['urgency']}")
    print(f"  Response Priority: {data['response_priority']}")
    print(f"  Suggested Response Tone: {data['suggested_response_tone']}")

    if "tone_analysis" in data:
        tone = data["tone_analysis"]
        print(f"\nDetailed Tone Analysis:")
        print(f"  Emotional State: {tone['emotional_state']['primary']} (score: {tone['emotional_state']['score']})")
        print(f"  Communication Style: {tone['communication_style']['primary']}")
        print(f"  Sentiment: {tone['sentiment']['category']} (intensity: {tone['sentiment']['intensity']})")
        print(f"  Urgency: {tone['urgency']['level']}")

    return result.status.value == "success"


def test_analyze_tone_tool():
    """Test the standalone analyze_tone tool."""
    print("\n" + "="*60)
    print("Testing analyze_tone Tool")
    print("="*60)

    text = """I really appreciate all your help with this! The process has been smooth
    and you've been so helpful in explaining everything. Looking forward to closing soon!
    Please let me know if there's anything else you need from me."""

    result = analyze_tone(text=text)

    print(f"\nAnalyze tone result: {result.status}")
    data = result.data

    print(f"\nEmotional State:")
    print(f"  Primary: {data['emotional_state']['primary_emotion']}")
    print(f"  Score: {data['emotional_state']['emotion_score']}")
    print(f"  Category: {data['emotional_state']['emotion_category']}")

    print(f"\nCommunication Style:")
    print(f"  Primary: {data['communication_style']['primary_style']}")
    print(f"  Secondary: {data['communication_style']['secondary_style']}")

    print(f"\nSentiment:")
    print(f"  Category: {data['sentiment']['category']}")
    print(f"  Score: {data['sentiment']['score']}")
    print(f"  Intensity: {data['sentiment']['intensity']}")

    print(f"\nRisk Assessment:")
    print(f"  Level: {data['risk_assessment']['level']}")

    print(f"\nResponse Guidance:")
    print(f"  Suggested Tone: {data['response_guidance']['suggested_tone']}")
    print(f"  Recommendations:")
    for rec in data['response_guidance']['recommendations'][:3]:
        print(f"    - {rec}")

    return result.status.value == "success"


def main():
    print("="*60)
    print("Enhanced Tone Analysis Test Suite")
    print("="*60)

    results = {
        "Emotional States": test_emotional_states(),
        "Communication Styles": test_communication_styles(),
        "Sentiment Intensity": test_sentiment_intensity(),
        "Urgency Detection": test_urgency_detection(),
        "parse_email Enhanced": test_parse_email_with_tone(),
        "analyze_tone Tool": test_analyze_tone_tool(),
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

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
