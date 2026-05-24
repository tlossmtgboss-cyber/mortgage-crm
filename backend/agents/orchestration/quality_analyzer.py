"""
Quality Analyzer for AI Agent Prompts

Analyzes prompts against best practices from "The Instant AI Agency":
- Identity & Role clarity
- Conversation style definition
- Qualification process
- Objection handling
- Rules & guardrails
- FAQ coverage
"""

from typing import Dict, List, Any, Optional
import re
import logging

logger = logging.getLogger(__name__)


class QualityAnalyzer:
    """
    Analyze agent prompts for quality and adherence to best practices.

    Scoring Categories:
    1. Identity & Role (15 points)
    2. Conversation Style (10 points)
    3. Qualification Process (20 points)
    4. Objection Handling (20 points)
    5. Rules & Guardrails (20 points)
    6. FAQ & Knowledge (10 points)
    7. Compliance & Safety (5 points)

    Total: 100 points
    """

    QUALITY_CHECKLIST = {
        "Identity & Role": {
            "weight": 15,
            "checks": [
                ("has_name", "Agent has a clear name"),
                ("has_role", "Agent has defined role"),
                ("not_ai_statement", "Agent is NOT positioned as AI"),
                ("has_expertise", "Expertise areas defined"),
                ("has_company", "Company affiliation clear"),
            ],
        },
        "Conversation Style": {
            "weight": 10,
            "checks": [
                ("has_output_style", "Output style defined"),
                ("has_tone", "Tone matches use case"),
                ("conversational", "Language is natural/conversational"),
            ],
        },
        "Qualification Process": {
            "weight": 20,
            "checks": [
                ("has_objective", "Clear objective defined"),
                ("has_required_info", "Required information listed"),
                ("has_questions", "Qualifying questions provided"),
                ("one_question_rule", "One question at a time rule"),
                ("has_success_criteria", "Success criteria defined"),
            ],
        },
        "Objection Handling": {
            "weight": 20,
            "checks": [
                ("has_objections", "Common objections addressed"),
                ("has_strategies", "Response strategies provided"),
                ("no_conciliatory", "Avoids conciliatory phrases rule"),
                ("has_sales_methodology", "Sales methodology referenced"),
                ("persistent_engagement", "Persistent engagement rule"),
            ],
        },
        "Rules & Guardrails": {
            "weight": 20,
            "checks": [
                ("max_questions_rule", "Max questions per message set"),
                ("stay_on_topic", "Stay on topic rule"),
                ("word_limit", "Response word limit set"),
                ("clear_cta", "Clear call-to-action encouraged"),
                ("escalation_path", "Escalation path defined"),
            ],
        },
        "FAQ & Knowledge": {
            "weight": 10,
            "checks": [
                ("has_faqs", "FAQs provided"),
                ("has_out_of_scope", "Out-of-scope handling defined"),
            ],
        },
        "Compliance & Safety": {
            "weight": 5,
            "checks": [
                ("has_opt_out", "Opt-out mechanism clear"),
                ("no_misleading", "No misleading claims"),
            ],
        },
    }

    # Keywords to detect in prompts
    DETECTION_PATTERNS = {
        "has_name": [r"you are (\w+)", r"I'm (\w+)", r"my name is (\w+)"],
        "has_role": [r"role", r"specialist", r"coordinator", r"manager", r"agent"],
        "not_ai_statement": [r"you are NOT an AI", r"NOT an AI assistant", r"real person"],
        "has_expertise": [r"expertise", r"specialized in", r"expert in"],
        "has_company": [r"Perennia", r"at \w+ AI", r"company"],
        "has_output_style": [r"output style", r"your style", r"writing style"],
        "has_tone": [r"professional", r"casual", r"friendly", r"urgent"],
        "conversational": [r"conversational", r"natural", r"casual"],
        "has_objective": [r"your job is", r"objective", r"goal is", r"your task"],
        "has_required_info": [r"must gather", r"required information", r"need to collect"],
        "has_questions": [r"ask these questions", r"qualifying questions", r"\d+\.\s+"],
        "one_question_rule": [r"one question at a time", r"only ask ONE", r"single question"],
        "has_success_criteria": [r"success criteria", r"success is", r"qualified .* is"],
        "has_objections": [r"objection", r"if they say", r"when they say"],
        "has_strategies": [r"you say:", r"respond with", r"strategy:"],
        "no_conciliatory": [r"do NOT use conciliatory", r"avoid.*I understand", r"no conciliatory"],
        "has_sales_methodology": [r"SPIN", r"Challenger", r"sales methodology", r"sales training"],
        "persistent_engagement": [r"persistent", r"never accept rejection", r"re-engage"],
        "max_questions_rule": [r"one question", r"single question", r"max.*question"],
        "stay_on_topic": [r"stay on topic", r"guide the conversation", r"focus on"],
        "word_limit": [r"under \d+ words", r"word limit", r"keep.*short"],
        "clear_cta": [r"call-to-action", r"next step", r"schedule", r"book"],
        "escalation_path": [r"escalate", r"transfer", r"specialist"],
        "has_faqs": [r"FAQ", r"Q:", r"question.*answer"],
        "has_out_of_scope": [r"out of scope", r"can't answer", r"specialist can"],
        "has_opt_out": [r"STOP", r"opt-out", r"unsubscribe"],
        "no_misleading": [r"honest", r"accurate", r"truthful"],
    }

    def analyze(self, prompt: str) -> Dict[str, Any]:
        """
        Analyze a prompt for quality.

        Args:
            prompt: The agent prompt to analyze

        Returns:
            Analysis results with score, breakdown, and recommendations
        """
        prompt_lower = prompt.lower()
        results = {
            "total_score": 0,
            "max_score": 100,
            "category_scores": {},
            "checks_passed": [],
            "checks_failed": [],
            "recommendations": [],
        }

        for category, config in self.QUALITY_CHECKLIST.items():
            category_passed = 0
            category_total = len(config["checks"])

            for check_id, check_description in config["checks"]:
                passed = self._check_pattern(check_id, prompt_lower)

                if passed:
                    category_passed += 1
                    results["checks_passed"].append({
                        "category": category,
                        "check": check_id,
                        "description": check_description,
                    })
                else:
                    results["checks_failed"].append({
                        "category": category,
                        "check": check_id,
                        "description": check_description,
                    })
                    # Add recommendation
                    results["recommendations"].append(
                        f"[{category}] {check_description}"
                    )

            # Calculate category score (proportional to weight)
            category_score = (category_passed / category_total) * config["weight"]
            results["category_scores"][category] = {
                "score": round(category_score, 1),
                "max": config["weight"],
                "passed": category_passed,
                "total": category_total,
                "percentage": round(category_passed / category_total * 100, 1),
            }
            results["total_score"] += category_score

        # Round total score
        results["total_score"] = round(results["total_score"], 1)
        results["percentage"] = round(results["total_score"], 1)
        results["grade"] = self._get_grade(results["total_score"])

        # Prioritize recommendations
        results["recommendations"] = self._prioritize_recommendations(
            results["recommendations"],
            results["category_scores"]
        )

        return results

    def _check_pattern(self, check_id: str, prompt_lower: str) -> bool:
        """Check if a pattern is present in the prompt"""
        patterns = self.DETECTION_PATTERNS.get(check_id, [])
        for pattern in patterns:
            if re.search(pattern, prompt_lower, re.IGNORECASE):
                return True
        return False

    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _prioritize_recommendations(
        self,
        recommendations: List[str],
        category_scores: Dict[str, Dict]
    ) -> List[str]:
        """Prioritize recommendations by impact"""
        # Sort categories by how far below 100% they are
        priority_order = sorted(
            category_scores.items(),
            key=lambda x: x[1]["percentage"]
        )

        prioritized = []
        for category, _ in priority_order:
            category_recs = [r for r in recommendations if r.startswith(f"[{category}]")]
            prioritized.extend(category_recs[:3])  # Top 3 per category

        return prioritized[:10]  # Top 10 overall

    def get_quick_score(self, prompt: str) -> int:
        """
        Get a quick quality score (0-100) without full analysis.
        """
        prompt_lower = prompt.lower()
        score = 0
        max_checks = len(self.DETECTION_PATTERNS)

        for check_id in self.DETECTION_PATTERNS:
            if self._check_pattern(check_id, prompt_lower):
                score += 1

        return int((score / max_checks) * 100)

    def compare_prompts(
        self,
        prompt_a: str,
        prompt_b: str,
        labels: tuple = ("A", "B")
    ) -> Dict[str, Any]:
        """
        Compare two prompts.
        """
        analysis_a = self.analyze(prompt_a)
        analysis_b = self.analyze(prompt_b)

        return {
            labels[0]: {
                "score": analysis_a["total_score"],
                "grade": analysis_a["grade"],
                "category_scores": analysis_a["category_scores"],
            },
            labels[1]: {
                "score": analysis_b["total_score"],
                "grade": analysis_b["grade"],
                "category_scores": analysis_b["category_scores"],
            },
            "winner": labels[0] if analysis_a["total_score"] > analysis_b["total_score"] else labels[1],
            "score_difference": abs(analysis_a["total_score"] - analysis_b["total_score"]),
            "category_comparison": {
                category: {
                    labels[0]: analysis_a["category_scores"].get(category, {}).get("percentage", 0),
                    labels[1]: analysis_b["category_scores"].get(category, {}).get("percentage", 0),
                }
                for category in self.QUALITY_CHECKLIST.keys()
            },
        }

    def suggest_improvements(self, prompt: str) -> List[Dict[str, str]]:
        """
        Generate specific improvement suggestions.
        """
        analysis = self.analyze(prompt)
        suggestions = []

        for failed in analysis["checks_failed"][:5]:  # Top 5 failures
            suggestion = self._get_improvement_suggestion(failed["check"])
            if suggestion:
                suggestions.append({
                    "category": failed["category"],
                    "issue": failed["description"],
                    "suggestion": suggestion,
                    "example": self._get_example(failed["check"]),
                })

        return suggestions

    def _get_improvement_suggestion(self, check_id: str) -> Optional[str]:
        """Get improvement suggestion for a failed check"""
        suggestions = {
            "has_name": "Add a specific name for your agent (e.g., 'You are Sarah, a Mortgage Specialist')",
            "not_ai_statement": "Add 'You are NOT an AI assistant - you are a real person doing your job'",
            "one_question_rule": "Add 'Only ask ONE question at a time to find out one piece of information'",
            "no_conciliatory": "Add 'Do NOT use conciliatory phrases (\"I understand,\" \"No worries\") when user expresses disinterest'",
            "has_sales_methodology": "Reference sales training (e.g., 'Use SPIN Selling & Challenger Sale methodologies')",
            "persistent_engagement": "Add 'Persistently engage - never accept rejection on the first attempt'",
            "has_objective": "Start with 'Your job is to [specific objective]'",
            "has_success_criteria": "End with 'Success Criteria: [what success looks like]'",
            "has_out_of_scope": "Add handling for out-of-scope questions (e.g., 'That's a great question for our specialist')",
            "has_opt_out": "Ensure opt-out keywords (STOP, UNSUBSCRIBE) are handled by the compliance gate",
        }
        return suggestions.get(check_id)

    def _get_example(self, check_id: str) -> Optional[str]:
        """Get example for a check"""
        examples = {
            "has_name": "You are Sarah, a Mortgage Specialist at The Tim Loss Team.",
            "not_ai_statement": "You are NOT an AI assistant - you are a real person doing your job.",
            "one_question_rule": "Only ask ONE question at a time to find out one piece of information.",
            "no_conciliatory": 'Do NOT use conciliatory phrases ("I understand," "I hear you") when the user expresses disinterest.',
            "has_sales_methodology": "Your Training: SPIN Selling, The Challenger Sale, Mortgage Lending",
            "persistent_engagement": "Persistently engage with the user, avoiding any phrases that acknowledge rejection.",
        }
        return examples.get(check_id)


def generate_quality_report(prompt: str, agent_name: str = "Agent") -> str:
    """
    Generate a formatted quality report for a prompt.
    """
    analyzer = QualityAnalyzer()
    analysis = analyzer.analyze(prompt)

    report = [
        f"# Quality Report: {agent_name}",
        f"",
        f"## Overall Score: {analysis['total_score']}/100 (Grade: {analysis['grade']})",
        f"",
        f"## Category Breakdown:",
    ]

    for category, scores in analysis["category_scores"].items():
        bar = "█" * int(scores["percentage"] / 10) + "░" * (10 - int(scores["percentage"] / 10))
        report.append(f"- {category}: {bar} {scores['percentage']}%")

    if analysis["recommendations"]:
        report.extend([
            "",
            "## Top Recommendations:",
        ])
        for i, rec in enumerate(analysis["recommendations"][:5], 1):
            report.append(f"{i}. {rec}")

    return "\n".join(report)
