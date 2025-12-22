"""
Chat Simulator - Conversation Testing & QA

This module provides tools for testing the chat state machine:
- Pre-defined conversation templates for common scenarios
- Automated conversation simulation
- Response quality validation
- Phase progression testing
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# CONVERSATION TEMPLATES
# =============================================================================

CONVERSATION_TEMPLATES = {
    'first_time_buyer_qualified': {
        'description': 'High-intent first-time homebuyer with good qualifications',
        'expected_outcome': {
            'min_phase': 4,
            'min_intent_score': 70,
            'expected_cta': 'call_now',
        },
        'messages': [
            "Hi, I'm looking to buy my first home",
            "I'm looking in the Charleston area, around $350k",
            "I have about $25k saved for down payment",
            "I'd like to close within the next 2-3 months",
            "My credit score is around 720",
            "What are my options?",
        ],
    },

    'urgent_refinance': {
        'description': 'Homeowner with urgent refinance needs',
        'expected_outcome': {
            'min_phase': 4,
            'min_intent_score': 75,
            'expected_cta': 'call_now',
        },
        'messages': [
            "I need to refinance ASAP",
            "My rate is 6.5% right now",
            "Home is worth about $400k, I owe $280k",
            "Need to lower my payment quickly",
            "Can you help today?",
        ],
    },

    'explorer_uncertain': {
        'description': 'Early-stage explorer, not committed',
        'expected_outcome': {
            'min_phase': 2,
            'max_phase': 3,
            'min_intent_score': 20,
            'max_intent_score': 50,
            'expected_cta': None,
        },
        'messages': [
            "Just looking at options",
            "Not sure if I'm ready to buy",
            "How much do I need for down payment?",
            "What about closing costs?",
            "Maybe I'll think about it",
        ],
    },

    'high_intent_investor': {
        'description': 'Experienced investor looking for investment property',
        'expected_outcome': {
            'min_phase': 4,
            'min_intent_score': 80,
            'expected_cta': 'call_now',
        },
        'messages': [
            "Looking at an investment property",
            "$225k purchase price",
            "Planning to rent it out",
            "Have 25% down payment ready",
            "Want to close in 30 days",
            "I've bought 3 rentals before",
            "What rates can you offer for investment properties?",
        ],
    },

    'va_buyer': {
        'description': 'Veteran looking to use VA benefits',
        'expected_outcome': {
            'min_phase': 3,
            'min_intent_score': 60,
            'expected_cta': 'schedule',
        },
        'messages': [
            "I'm a veteran looking to buy a home",
            "Want to use my VA loan benefit",
            "Looking at houses around $300k",
            "Not in a huge rush, maybe 6 months",
            "Is it true I don't need a down payment?",
        ],
    },

    'refinance_rate_shopper': {
        'description': 'Rate-focused refinance shopper',
        'expected_outcome': {
            'min_phase': 3,
            'min_intent_score': 50,
        },
        'messages': [
            "What refinance rates do you have?",
            "I'm currently at 7.25%",
            "Owe about $350k on my home",
            "Just want to lower my rate, no cash out",
            "What's the best you can do?",
        ],
    },

    'fha_buyer_credit_concerns': {
        'description': 'Buyer with credit concerns exploring FHA',
        'expected_outcome': {
            'min_phase': 3,
            'min_intent_score': 45,
        },
        'messages': [
            "Can I buy a house with a 620 credit score?",
            "I've heard about FHA loans",
            "Looking at homes around $250k",
            "I have about 5% to put down",
            "How does this work with lower credit?",
        ],
    },

    'cta_decline_graceful': {
        'description': 'User who declines CTA - tests graceful handling',
        'expected_outcome': {
            'min_phase': 4,
            'cta_declined': True,
        },
        'messages': [
            "I want to buy a house in the next month",
            "Budget is $400k, putting 20% down",
            "Credit is excellent, around 780",
            "Looking at conventional loans",
            "Not ready to talk yet, just researching",
            "I'll reach out when I'm ready",
        ],
    },
}


# =============================================================================
# SIMULATOR CLASS
# =============================================================================

@dataclass
class SimulationResult:
    """Result from a conversation simulation"""
    template_name: str
    session_id: str
    success: bool
    final_phase: int
    final_intent_score: int
    cta_offered: Optional[str]
    cta_accepted: bool
    turn_count: int
    conversation_log: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_seconds: float = 0


class ChatSimulator:
    """Simulate borrower conversations for testing"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize simulator.

        Args:
            base_url: Base URL of the chat API
        """
        self.base_url = base_url.rstrip('/')

    async def simulate_conversation(
        self,
        template_name: str,
        microsite_id: Optional[int] = None,
        delay_between_messages: float = 0.5,
        validate_expectations: bool = True,
    ) -> SimulationResult:
        """
        Run a full conversation simulation.

        Args:
            template_name: Name of template from CONVERSATION_TEMPLATES
            microsite_id: Optional microsite context
            delay_between_messages: Seconds to wait between messages
            validate_expectations: Whether to validate against expected outcomes

        Returns:
            SimulationResult with full conversation log and validation
        """
        if template_name not in CONVERSATION_TEMPLATES:
            return SimulationResult(
                template_name=template_name,
                session_id='',
                success=False,
                final_phase=0,
                final_intent_score=0,
                cta_offered=None,
                cta_accepted=False,
                turn_count=0,
                error=f"Unknown template: {template_name}"
            )

        template = CONVERSATION_TEMPLATES[template_name]
        messages = template['messages']
        visitor_id = f"test_{uuid.uuid4()}"

        start_time = datetime.now()
        conversation_log = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Create session
                session_response = await client.post(
                    f"{self.base_url}/api/v1/chat/sessions",
                    json={
                        "visitor_id": visitor_id,
                        "microsite_id": microsite_id,
                    }
                )
                session_response.raise_for_status()
                session_data = session_response.json()
                session_id = session_data.get('id')

                if not session_id:
                    raise ValueError("No session ID returned")

                # Send each message
                final_response = None
                for i, user_message in enumerate(messages):
                    # Send message
                    msg_response = await client.post(
                        f"{self.base_url}/api/v1/chat/sessions/{session_id}/messages",
                        json={"content": user_message}
                    )
                    msg_response.raise_for_status()
                    result = msg_response.json()

                    # Log the exchange
                    conversation_log.append({
                        'turn': i + 1,
                        'user': user_message,
                        'assistant': result.get('message', {}).get('content', ''),
                        'phase': result.get('session', {}).get('currentPhase'),
                        'intent_score': result.get('session', {}).get('intentScore'),
                        'cta_offered': result.get('session', {}).get('ctaOffered'),
                        'timestamp': datetime.now().isoformat(),
                    })

                    final_response = result

                    # Wait before next message
                    if i < len(messages) - 1 and delay_between_messages > 0:
                        await asyncio.sleep(delay_between_messages)

                # Extract final state
                final_session = final_response.get('session', {}) if final_response else {}
                final_phase = final_session.get('currentPhase', 1)
                final_intent_score = final_session.get('intentScore', 0)
                cta_offered = final_session.get('ctaOffered')
                cta_accepted = final_session.get('ctaAccepted', False)

                # Validate expectations
                validation_results = {}
                if validate_expectations and 'expected_outcome' in template:
                    validation_results = self._validate_expectations(
                        template['expected_outcome'],
                        final_phase,
                        final_intent_score,
                        cta_offered,
                        cta_accepted,
                    )

                duration = (datetime.now() - start_time).total_seconds()

                return SimulationResult(
                    template_name=template_name,
                    session_id=session_id,
                    success=all(v.get('passed', True) for v in validation_results.values()) if validation_results else True,
                    final_phase=final_phase,
                    final_intent_score=final_intent_score,
                    cta_offered=cta_offered,
                    cta_accepted=cta_accepted,
                    turn_count=len(messages),
                    conversation_log=conversation_log,
                    validation_results=validation_results,
                    duration_seconds=duration,
                )

            except httpx.HTTPStatusError as e:
                return SimulationResult(
                    template_name=template_name,
                    session_id='',
                    success=False,
                    final_phase=0,
                    final_intent_score=0,
                    cta_offered=None,
                    cta_accepted=False,
                    turn_count=len(conversation_log),
                    conversation_log=conversation_log,
                    error=f"HTTP error: {e.response.status_code} - {e.response.text}"
                )
            except Exception as e:
                return SimulationResult(
                    template_name=template_name,
                    session_id='',
                    success=False,
                    final_phase=0,
                    final_intent_score=0,
                    cta_offered=None,
                    cta_accepted=False,
                    turn_count=len(conversation_log),
                    conversation_log=conversation_log,
                    error=str(e)
                )

    def _validate_expectations(
        self,
        expected: Dict[str, Any],
        final_phase: int,
        final_intent_score: int,
        cta_offered: Optional[str],
        cta_accepted: bool,
    ) -> Dict[str, Any]:
        """Validate simulation results against expectations"""
        results = {}

        # Phase validation
        if 'min_phase' in expected:
            results['min_phase'] = {
                'expected': f">= {expected['min_phase']}",
                'actual': final_phase,
                'passed': final_phase >= expected['min_phase'],
            }

        if 'max_phase' in expected:
            results['max_phase'] = {
                'expected': f"<= {expected['max_phase']}",
                'actual': final_phase,
                'passed': final_phase <= expected['max_phase'],
            }

        # Intent score validation
        if 'min_intent_score' in expected:
            results['min_intent_score'] = {
                'expected': f">= {expected['min_intent_score']}",
                'actual': final_intent_score,
                'passed': final_intent_score >= expected['min_intent_score'],
            }

        if 'max_intent_score' in expected:
            results['max_intent_score'] = {
                'expected': f"<= {expected['max_intent_score']}",
                'actual': final_intent_score,
                'passed': final_intent_score <= expected['max_intent_score'],
            }

        # CTA validation
        if 'expected_cta' in expected:
            results['expected_cta'] = {
                'expected': expected['expected_cta'],
                'actual': cta_offered,
                'passed': cta_offered == expected['expected_cta'] if expected['expected_cta'] else cta_offered is None,
            }

        return results

    async def run_all_templates(
        self,
        microsite_id: Optional[int] = None,
    ) -> Dict[str, SimulationResult]:
        """
        Run all conversation templates for comprehensive testing.

        Returns:
            Dict mapping template name to SimulationResult
        """
        results = {}
        for template_name in CONVERSATION_TEMPLATES:
            logger.info(f"Running simulation: {template_name}")
            result = await self.simulate_conversation(
                template_name=template_name,
                microsite_id=microsite_id,
            )
            results[template_name] = result
            logger.info(f"  Result: {'PASS' if result.success else 'FAIL'} - Phase {result.final_phase}, Score {result.final_intent_score}")

        return results

    def generate_test_report(self, results: Dict[str, SimulationResult]) -> str:
        """Generate human-readable test report"""
        lines = [
            "=" * 70,
            "CHAT SIMULATION TEST REPORT",
            f"Generated: {datetime.now().isoformat()}",
            "=" * 70,
            "",
        ]

        passed = sum(1 for r in results.values() if r.success)
        failed = len(results) - passed

        lines.append(f"SUMMARY: {passed}/{len(results)} passed ({failed} failed)")
        lines.append("")

        for template_name, result in results.items():
            status = "✓ PASS" if result.success else "✗ FAIL"
            lines.append(f"{status} - {template_name}")
            lines.append(f"    Phase: {result.final_phase}, Intent: {result.final_intent_score}")
            lines.append(f"    CTA: {result.cta_offered or 'none'}")
            lines.append(f"    Duration: {result.duration_seconds:.1f}s")

            if result.error:
                lines.append(f"    ERROR: {result.error}")

            if result.validation_results:
                for check_name, check_result in result.validation_results.items():
                    if not check_result.get('passed'):
                        lines.append(f"    FAILED: {check_name} - expected {check_result['expected']}, got {check_result['actual']}")

            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)


# =============================================================================
# CLI RUNNER
# =============================================================================

async def run_simulation_cli():
    """CLI entry point for running simulations"""
    import argparse

    parser = argparse.ArgumentParser(description='Run chat simulation tests')
    parser.add_argument('--template', '-t', help='Specific template to run')
    parser.add_argument('--base-url', default='http://localhost:8000', help='API base URL')
    parser.add_argument('--microsite', '-m', type=int, help='Microsite ID')
    parser.add_argument('--all', '-a', action='store_true', help='Run all templates')

    args = parser.parse_args()

    simulator = ChatSimulator(base_url=args.base_url)

    if args.all:
        results = await simulator.run_all_templates(microsite_id=args.microsite)
        print(simulator.generate_test_report(results))
    elif args.template:
        result = await simulator.simulate_conversation(
            template_name=args.template,
            microsite_id=args.microsite,
        )
        print(f"Template: {result.template_name}")
        print(f"Success: {result.success}")
        print(f"Final Phase: {result.final_phase}")
        print(f"Final Intent Score: {result.final_intent_score}")
        print(f"CTA Offered: {result.cta_offered}")
        print(f"Duration: {result.duration_seconds:.1f}s")
        if result.error:
            print(f"Error: {result.error}")
        print("\nConversation:")
        for turn in result.conversation_log:
            print(f"\n[Turn {turn['turn']}]")
            print(f"User: {turn['user']}")
            print(f"Assistant: {turn['assistant'][:200]}...")
    else:
        print("Available templates:")
        for name, template in CONVERSATION_TEMPLATES.items():
            print(f"  {name}: {template['description']}")
        print("\nUse --template <name> or --all to run simulations")


if __name__ == "__main__":
    asyncio.run(run_simulation_cli())
