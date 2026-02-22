"""
AI Memory Service with RAG (Retrieval-Augmented Generation)
Provides context-aware AI responses using conversation history

Caching:
- Metadata extraction is cached with 6h TTL (same message = same metadata)
- Reduces redundant LLM calls for repeated messages
"""
import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
import anthropic
import json
import hashlib

from integrations.pinecone_service import vector_memory
from database.models import ConversationMemory, Lead, Loan, User
from ai_receptionist_dashboard_models import AIReceptionistMetricsDaily, AIReceptionistActivity
from models.profitability import EmployeeCost, ProfitabilityLoan, LoanAttribution, ProfitabilityRole
from sqlalchemy import func
from decimal import Decimal

# Import LLM cache service
try:
    from services.llm_cache_service import llm_cache, LLMCacheService
    LLM_CACHE_AVAILABLE = True
except ImportError:
    llm_cache = None
    LLMCacheService = None
    LLM_CACHE_AVAILABLE = False

# Import A/B testing service
try:
    from ab_testing.experiment_service import ExperimentService
    AB_TESTING_AVAILABLE = True
except ImportError:
    ExperimentService = None
    AB_TESTING_AVAILABLE = False

logger = logging.getLogger(__name__)


class ContextAwareAI:
    """Enhanced AI service with memory and context retrieval"""

    def __init__(self):
        import os
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not found in environment variables")

        self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        self.vector_memory = vector_memory

    async def get_intelligent_response(
        self,
        db: Session,
        user_id: int,
        current_message: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        include_context: bool = True,
        coaching_context: Optional[str] = None
    ) -> Dict:
        """
        Generate AI response with relevant context from past conversations

        Args:
            db: Database session
            user_id: ID of the user
            current_message: The current user message
            lead_id: Optional lead ID for context
            loan_id: Optional loan ID for context
            include_context: Whether to include past conversation context

        Returns:
            Dict with response, context_used, and metadata
        """
        # A/B Testing: Check for active experiment
        experiment_variant = None
        if AB_TESTING_AVAILABLE:
            try:
                experiment_service = ExperimentService(db)
                experiment_variant = experiment_service.get_variant_for_user(
                    experiment_name="ai_response_prompt_v2",
                    user_id=user_id
                )
                if experiment_variant:
                    logger.info(f"A/B Test: User {user_id} assigned to variant '{experiment_variant.get('variant_name')}'")
            except Exception as ab_error:
                logger.warning(f"A/B testing error (continuing without): {ab_error}")
                experiment_variant = None

        try:
            # 1. Retrieve relevant past context if enabled
            relevant_history = []
            if include_context and self.vector_memory.enabled:
                filter_metadata = {}
                if lead_id:
                    filter_metadata["lead_id"] = lead_id

                relevant_history = await self.vector_memory.retrieve_relevant_context(
                    user_id=user_id,
                    current_query=current_message,
                    top_k=5,
                    filter_metadata=filter_metadata if filter_metadata else None
                )

                # Update access tracking in database
                for context in relevant_history:
                    pinecone_id = context.get("metadata", {}).get("pinecone_id")
                    if pinecone_id:
                        await self._update_memory_access(db, pinecone_id)

            # 2. Get lead/loan context if provided
            lead_context = ""
            if lead_id:
                lead_context = await self._get_lead_context(db, lead_id)

            loan_context = ""
            if loan_id:
                loan_context = await self._get_loan_context(db, loan_id)

            # 2.5 Always get ROI context for business metrics questions
            roi_context = await self._get_roi_context(db)

            # 2.6 Get rate lock context for rate-related questions
            rate_lock_context = await self._get_rate_lock_context()

            # 2.7 Get team performance context for performance questions
            team_performance_context = await self._get_team_performance_context(db)

            # 2.8 Get SLA and bottleneck context
            sla_bottleneck_context = await self._get_sla_bottleneck_context(db, user_id)

            # 3. Build enhanced system prompt with context
            # A/B Testing: Use variant config if in experiment
            if experiment_variant and experiment_variant.get('config', {}).get('system_prompt'):
                # Use experimental prompt from variant
                variant_config = experiment_variant.get('config', {})
                system_prompt = self._build_experimental_prompt(
                    variant_config=variant_config,
                    relevant_history=relevant_history,
                    lead_context=lead_context,
                    loan_context=loan_context,
                    coaching_context=coaching_context,
                    roi_context=roi_context
                )
            else:
                # Use default system prompt
                system_prompt = self._build_system_prompt(
                    relevant_history,
                    lead_context,
                    loan_context,
                    coaching_context,
                    roi_context,
                    rate_lock_context,
                    team_performance_context,
                    sla_bottleneck_context
                )

            # 4. Generate response with Claude
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": current_message
                }]
            )

            ai_response = response.content[0].text

            # 5. Extract key information from conversation
            conversation_metadata = await self._extract_conversation_metadata(
                current_message,
                ai_response
            )

            # 6. Store this conversation for future context
            conversation_text = f"User: {current_message}\n\nAssistant: {ai_response}"

            if self.vector_memory.enabled:
                pinecone_id = await self.vector_memory.store_conversation(
                    user_id=user_id,
                    conversation_text=conversation_text,
                    metadata={
                        "lead_id": lead_id,
                        "loan_id": loan_id,
                        **conversation_metadata
                    }
                )

                # Store metadata in database
                memory_record = ConversationMemory(
                    user_id=user_id,
                    lead_id=lead_id,
                    loan_id=loan_id,
                    conversation_summary=conversation_text[:500],  # First 500 chars
                    key_points=conversation_metadata.get("key_points", {}),
                    sentiment=conversation_metadata.get("sentiment", "neutral"),
                    intent=conversation_metadata.get("intent", "unknown"),
                    pinecone_id=pinecone_id,
                    relevance_score=1.0  # New memories start with high relevance
                )
                db.add(memory_record)
                db.commit()

            # A/B Testing: Record experiment results
            if experiment_variant and AB_TESTING_AVAILABLE:
                try:
                    # Calculate response quality metrics
                    response_quality = self._assess_response_quality(ai_response)
                    sentiment_score = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}.get(
                        conversation_metadata.get("sentiment", "neutral"), 0.5
                    )
                    resolution_rate = 1.0 if conversation_metadata.get("intent", "unknown") != "unknown" else 0.0

                    # Record metrics
                    experiment_service = ExperimentService(db)
                    experiment_service.record_result(
                        experiment_name="ai_response_prompt_v2",
                        metric_name="response_quality",
                        metric_value=response_quality,
                        user_id=user_id
                    )
                    experiment_service.record_result(
                        experiment_name="ai_response_prompt_v2",
                        metric_name="sentiment_score",
                        metric_value=sentiment_score,
                        user_id=user_id
                    )
                    experiment_service.record_result(
                        experiment_name="ai_response_prompt_v2",
                        metric_name="resolution_rate",
                        metric_value=resolution_rate,
                        user_id=user_id
                    )
                    logger.debug(f"A/B Test: Recorded results for user {user_id} - quality={response_quality}")
                except Exception as ab_error:
                    logger.warning(f"Failed to record A/B test results: {ab_error}")

            return {
                "response": ai_response,
                "context_used": len(relevant_history) > 0,
                "context_count": len(relevant_history),
                "metadata": conversation_metadata,
                "has_memory": self.vector_memory.enabled,
                "experiment_variant": experiment_variant.get("variant_name") if experiment_variant else None
            }

        except Exception as e:
            logger.error(f"Error generating intelligent response: {e}")
            return {
                "response": "I apologize, but I'm having trouble generating a response right now. Please try again.",
                "context_used": False,
                "error": "Internal server error"
            }

    def _build_system_prompt(
        self,
        relevant_history: List[Dict],
        lead_context: str,
        loan_context: str,
        coaching_context: Optional[str] = None,
        roi_context: Optional[str] = None,
        rate_lock_context: Optional[str] = None,
        team_performance_context: Optional[str] = None,
        sla_bottleneck_context: Optional[str] = None
    ) -> str:
        """Build enhanced system prompt with all available context"""

        base_prompt = """You are a helpful, knowledgeable AI assistant. You can answer ANY type of question on ANY topic - general knowledge, weather, news, science, history, math, coding, advice, and more. You are NOT limited to mortgage or CRM topics.

For real-time information (current weather, stock prices, breaking news), provide your best knowledge and suggest the user verify with current sources if needed.

You also have access to the mortgage CRM system and can help with lead management, loan processing, and business tasks when relevant. Use conversation history and context to provide personalized responses."""

        context_sections = []

        # Add conversation history if available
        if relevant_history:
            context_sections.append("\n## PAST CONVERSATION CONTEXT:")
            context_sections.append("Here are relevant past interactions with this user:\n")

            for idx, conv in enumerate(relevant_history, 1):
                timestamp = conv.get("timestamp", "Unknown time")
                text = conv.get("text", "")
                score = conv.get("relevance_score", 0)

                context_sections.append(f"[{idx}] {timestamp} (Relevance: {score:.2f})")
                context_sections.append(f"{text}\n")

            context_sections.append("\nUse these past conversations to provide context-aware responses.")

        # Add lead context if available
        if lead_context:
            context_sections.append("\n## ⭐ CURRENT LEAD INFORMATION (Use this for answering questions!):")
            context_sections.append(lead_context)

        # Add loan context if available
        if loan_context:
            context_sections.append("\n## ⭐ CURRENT LOAN INFORMATION (Use this for answering questions!):")
            context_sections.append(loan_context)

        # Add coaching context if available
        if coaching_context:
            context_sections.append("\n## ⭐ YOUR CRM DATA (Use this for coaching and prioritization!):")
            context_sections.append(coaching_context)

        # Add ROI/business metrics context if available
        if roi_context:
            context_sections.append("\n## 📊 BUSINESS & ROI METRICS (Use this for cost, ROI, and performance questions!):")
            context_sections.append(roi_context)

        # Add rate lock intelligence context if available
        if rate_lock_context:
            context_sections.append("\n## 🔒 RATE LOCK INTELLIGENCE (Use this for rate lock decisions!):")
            context_sections.append(rate_lock_context)

        # Add team performance context if available
        if team_performance_context:
            context_sections.append("\n## 👥 TEAM PERFORMANCE (Use this for performance and underwriter questions!):")
            context_sections.append(team_performance_context)

        # Add SLA and bottleneck context if available
        if sla_bottleneck_context:
            context_sections.append("\n## ⚠️ SLA & BOTTLENECKS (Use this for SLA, delays, and bottleneck questions!):")
            context_sections.append(sla_bottleneck_context)

        # Add guidelines - different based on whether we have current lead context
        if lead_context or loan_context:
            context_sections.append("""

## RESPONSE GUIDELINES:
1. **CRITICAL**: Always use the CURRENT LEAD/LOAN INFORMATION above when answering questions. Never confuse the current client with people mentioned in past conversations.
2. If the current lead/loan name is provided above, ALL your responses should reference THAT person, not anyone from past conversations
3. Reference past conversations naturally when relevant, but only if they're about the CURRENT lead/loan
4. Be concise but informative
5. If you don't have information, say so clearly
6. Maintain professional mortgage industry tone
7. Highlight important details and action items
""")
        else:
            context_sections.append("""

## RESPONSE GUIDELINES:
1. **CRITICAL**: The user is NOT currently viewing a specific lead or loan. Do NOT assume they want to discuss any particular client unless they specifically mention one by name.
2. Do NOT bring up specific lead names (like "John Smith" or "Sarah Johnson") from past conversations unless the user explicitly asks about them
3. When asked about general tasks, bottlenecks, or workflows, provide GENERAL advice - not advice specific to any particular lead
4. If the user wants help with a specific client, they will either mention them by name or navigate to that client's page
5. Be concise but informative
6. Maintain professional mortgage industry tone
7. If the user asks to email something, ask WHO they want to email it to - don't assume
""")

        return base_prompt + "\n".join(context_sections)

    def _build_experimental_prompt(
        self,
        variant_config: Dict,
        relevant_history: List[Dict],
        lead_context: str,
        loan_context: str,
        coaching_context: Optional[str] = None,
        roi_context: Optional[str] = None
    ) -> str:
        """Build system prompt using A/B test variant configuration"""
        # Get base prompt from variant config
        base_prompt = variant_config.get(
            "system_prompt",
            "You are an intelligent AI assistant for a mortgage CRM system."
        )

        # Add few-shot examples if configured
        if variant_config.get("include_examples", False):
            examples = variant_config.get("examples", [])
            if examples:
                base_prompt += "\n\n## EXAMPLES:\n"
                for idx, example in enumerate(examples, 1):
                    base_prompt += f"\n{idx}. {example}\n"

        # Add context sections (same as default)
        context_sections = []

        if relevant_history:
            context_sections.append("\n## PAST CONVERSATION CONTEXT:")
            for idx, conv in enumerate(relevant_history[:3], 1):
                timestamp = conv.get("timestamp", "Unknown")
                text = conv.get("text", "")[:200]
                context_sections.append(f"[{idx}] {timestamp}: {text}")

        if lead_context:
            context_sections.append("\n## CURRENT LEAD:")
            context_sections.append(lead_context)

        if loan_context:
            context_sections.append("\n## CURRENT LOAN:")
            context_sections.append(loan_context)

        if coaching_context:
            context_sections.append("\n## YOUR PERFORMANCE:")
            context_sections.append(coaching_context)

        if roi_context:
            context_sections.append("\n## BUSINESS METRICS:")
            context_sections.append(roi_context)

        # Add response guidelines from variant or default
        guidelines = variant_config.get("response_guidelines", """
## RESPONSE GUIDELINES:
1. Be concise but informative
2. Reference context naturally when relevant
3. Maintain professional tone
4. Include specific next steps when applicable
""")
        context_sections.append(guidelines)

        return base_prompt + "\n".join(context_sections)

    def _assess_response_quality(self, response: str) -> float:
        """
        Assess AI response quality using heuristics.
        Returns a score from 0.0 to 1.0.
        """
        if not response:
            return 0.0

        quality = 0.5  # Base score

        # Length check (not too short, not too long)
        length = len(response)
        if 50 <= length <= 500:
            quality += 0.15
        elif length > 500:
            quality += 0.10

        # Has actionable items
        actionable_words = ["should", "recommend", "suggest", "next step", "try", "consider"]
        if any(word in response.lower() for word in actionable_words):
            quality += 0.15

        # Multiple sentences (structured response)
        if response.count(".") >= 2:
            quality += 0.10

        # Uses formatting (bullets, numbers)
        if any(marker in response for marker in ["- ", "* ", "1.", "•"]):
            quality += 0.10

        return min(quality, 1.0)

    async def _get_lead_context(self, db: Session, lead_id: int) -> str:
        """Get formatted context about a lead"""
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return ""

            context = f"""Lead: {lead.name}
Phone: {lead.phone or 'N/A'}
Email: {lead.email or 'N/A'}
Stage: {lead.stage}
Source: {lead.source or 'N/A'}
Credit Score: {lead.credit_score or 'N/A'}
Loan Amount: ${lead.loan_amount or 0:,.0f}
Property Value: ${lead.property_value or 0:,.0f}
Notes: {lead.notes or 'None'}"""

            return context
        except Exception as e:
            logger.error(f"Error getting lead context: {e}")
            return ""

    async def _get_loan_context(self, db: Session, loan_id: int) -> str:
        """Get formatted context about a loan"""
        try:
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return ""

            context = f"""Loan Amount: ${loan.amount or 0:,.0f}
Loan Type: {loan.loan_type or 'N/A'}
Stage: {loan.stage}
Interest Rate: {loan.interest_rate or 'N/A'}%
Property Address: {loan.property_address or 'N/A'}
Status: {loan.status or 'In Progress'}"""

            return context
        except Exception as e:
            logger.error(f"Error getting loan context: {e}")
            return ""

    async def _get_roi_context(self, db: Session) -> str:
        """Get ROI and business metrics context"""
        try:
            # Get last 30 days of metrics
            end_date = date.today()
            start_date = end_date - timedelta(days=30)

            metrics = db.query(AIReceptionistMetricsDaily).filter(
                and_(
                    AIReceptionistMetricsDaily.date >= start_date,
                    AIReceptionistMetricsDaily.date <= end_date
                )
            ).all()

            if not metrics:
                return ""

            # Aggregate metrics
            total_appointments = sum(m.appointments_scheduled for m in metrics)
            total_apps_initiated = sum(m.loan_apps_initiated for m in metrics)
            total_saved_hours = sum(m.saved_labor_hours or 0 for m in metrics)
            total_estimated_revenue = sum(m.estimated_revenue_created or 0 for m in metrics)
            total_conversations = sum(m.total_conversations for m in metrics)

            # Calculate rates
            appointment_to_app_rate = (total_apps_initiated / total_appointments * 100) if total_appointments > 0 else 0
            cost_per_interaction = 0.50

            # Get closes
            total_closes = db.query(AIReceptionistActivity).filter(
                and_(
                    AIReceptionistActivity.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    AIReceptionistActivity.timestamp <= datetime.combine(end_date, datetime.max.time()),
                    AIReceptionistActivity.lead_stage == 'closed'
                )
            ).count()

            # Calculate costs
            total_cost = total_conversations * cost_per_interaction
            cost_per_close = (total_cost / total_closes) if total_closes > 0 else None

            # Format context
            context = f"""## Business & ROI Metrics (Last 30 Days)
Total Appointments Scheduled: {total_appointments}
Loan Applications Initiated: {total_apps_initiated}
Appointment to App Rate: {appointment_to_app_rate:.1f}%
Total Conversations: {total_conversations}
Total Closes: {total_closes}
Estimated Revenue: ${total_estimated_revenue:,.2f}
Saved Labor Hours: {total_saved_hours:.1f}
Cost Per Interaction: ${cost_per_interaction:.2f}
Cost Per Close: ${cost_per_close:.2f if cost_per_close else 'N/A'}
Total AI Cost: ${total_cost:.2f}"""

            return context
        except Exception as e:
            logger.error(f"Error getting ROI context: {e}")
            return ""

    async def _get_rate_lock_context(self, days: int = 30) -> str:
        """Get rate lock intelligence context from market data"""
        try:
            from scrapers import MarketDataOrchestrator

            orchestrator = MarketDataOrchestrator()

            # Get market snapshot
            snapshot = orchestrator.get_market_snapshot()
            if not snapshot:
                return ""

            # Get rate lock specific context
            rate_context = orchestrator.get_rate_lock_context(days)

            # Format context for AI
            treasury = snapshot.get("treasury", {})
            mortgage = snapshot.get("mortgage_rates", {})
            volatility = snapshot.get("volatility", {})

            context = f"""## Current Market Conditions
10-Year Treasury: {treasury.get('10yr', 'N/A')}%
30-Year Mortgage Rate: {mortgage.get('rate_30yr', 'N/A')}%
15-Year Mortgage Rate: {mortgage.get('rate_15yr', 'N/A')}%
Spread to 10yr: {mortgage.get('spread_to_10yr', 'N/A')} bps

## Market Volatility
VIX Index: {volatility.get('vix', 'N/A')}
Volatility Assessment: {volatility.get('assessment', 'N/A')}
Volatility Score: {volatility.get('score', 'N/A')}/10

## Rate Lock Recommendation
Market Score: {snapshot.get('market_score', 'N/A')}/100
Recommendation: {snapshot.get('recommendation', 'N/A')}

## {days}-Day Lock Analysis
{rate_context.get('analysis', 'No specific analysis available.')}

## AI Rate Lock Commentary
Based on current market conditions, {rate_context.get('commentary', 'markets are showing mixed signals. Consider your specific situation and risk tolerance.')}

IMPORTANT: When asked about rate locks, use this real-time market data to provide specific, actionable advice based on the recommendation above."""

            return context
        except Exception as e:
            logger.error(f"Error getting rate lock context: {e}")
            return ""

    async def _get_team_performance_context(self, db: Session) -> str:
        """Get team/employee performance context"""
        try:
            # Get current month date range
            today = date.today()
            start_date = today.replace(day=1)
            if today.month == 12:
                end_date = date(today.year + 1, 1, 1)
            else:
                end_date = date(today.year, today.month + 1, 1)

            # Get all active employees with their roles
            employees = db.query(EmployeeCost).filter(
                EmployeeCost.is_active == True
            ).all()

            if not employees:
                return ""

            results = []
            for emp in employees:
                # Get attributed revenue and loans for this month
                attributed_data = db.query(
                    func.sum(
                        ProfitabilityLoan.total_revenue * LoanAttribution.attribution_percentage / 100
                    ).label("revenue"),
                    func.count(LoanAttribution.loan_id).label("loan_count")
                ).join(ProfitabilityLoan).filter(
                    LoanAttribution.employee_cost_id == emp.id,
                    ProfitabilityLoan.close_date >= start_date,
                    ProfitabilityLoan.close_date < end_date
                ).first()

                total_revenue = Decimal(attributed_data.revenue or 0)
                loans_closed = attributed_data.loan_count or 0

                monthly_cost = Decimal(emp.monthly_cost or 0)
                net_contribution = total_revenue - monthly_cost
                roi_percentage = (net_contribution / monthly_cost * 100) if monthly_cost > 0 else Decimal(0)

                role_name = emp.role.name if emp.role else "Unknown"

                results.append({
                    "name": emp.employee_name,
                    "role": role_name,
                    "loans": loans_closed,
                    "revenue": float(total_revenue),
                    "cost": float(monthly_cost),
                    "net": float(net_contribution),
                    "roi": float(roi_percentage)
                })

            # Sort by ROI (lowest first to identify underperformers)
            results.sort(key=lambda x: x["roi"])

            # Format context
            context_parts = [f"## Team Performance Summary (Current Month)\n"]

            # Identify underperformers (negative ROI or below average)
            underperformers = [r for r in results if r["roi"] < 0]
            top_performers = sorted(results, key=lambda x: x["roi"], reverse=True)[:3]

            if underperformers:
                context_parts.append("### ⚠️ Underperforming Team Members (Negative ROI):")
                for emp in underperformers:
                    context_parts.append(f"- **{emp['name']}** ({emp['role']}): ROI {emp['roi']:.1f}%, {emp['loans']} loans, ${emp['revenue']:,.0f} revenue, ${emp['net']:,.0f} net contribution")
                context_parts.append("")

            context_parts.append("### 🌟 Top Performers:")
            for emp in top_performers:
                context_parts.append(f"- **{emp['name']}** ({emp['role']}): ROI {emp['roi']:.1f}%, {emp['loans']} loans, ${emp['revenue']:,.0f} revenue")

            # Group employees by role for drill-down capability
            by_role = {}
            for emp in results:
                role = emp["role"]
                if role not in by_role:
                    by_role[role] = []
                by_role[role].append(emp)

            context_parts.append("\n### Team Members by Role (Sorted by Efficiency):\n")

            for role_name in sorted(by_role.keys()):
                employees = by_role[role_name]
                # Sort by ROI (efficiency proxy) descending
                employees.sort(key=lambda x: x["roi"], reverse=True)

                # Calculate role average
                avg_roi = sum(e["roi"] for e in employees) / len(employees) if employees else 0
                total_loans = sum(e["loans"] for e in employees)

                context_parts.append(f"**{role_name}s** (Avg Efficiency: {avg_roi:.1f}%, Total Loans: {total_loans}):")

                for i, emp in enumerate(employees, 1):
                    status = "⚠️" if emp["roi"] < 0 else "✅" if emp["roi"] > avg_roi else "📊"
                    context_parts.append(f"  {i}. {status} {emp['name']}: {emp['roi']:.1f}% efficiency, {emp['loans']} loans, ${emp['revenue']:,.0f} revenue")

                context_parts.append("")

            context_parts.append("### All Team Members by ROI:")
            for emp in results:
                status = "⚠️" if emp["roi"] < 0 else "✅" if emp["roi"] > 100 else "📊"
                context_parts.append(f"{status} {emp['name']} ({emp['role']}): ROI {emp['roi']:.1f}%, {emp['loans']} loans closed")

            # Add loan-level detail for processors and underwriters
            context_parts.append("\n### Loan-Level Performance Detail:\n")

            # Get all loans with processor/underwriter assignments
            all_loans = db.query(Loan).filter(
                Loan.loan_officer_id != None
            ).order_by(Loan.updated_at.desc()).limit(50).all()

            # Group loans by processor
            by_processor = {}
            by_underwriter = {}

            for loan in all_loans:
                if loan.processor:
                    if loan.processor not in by_processor:
                        by_processor[loan.processor] = []
                    by_processor[loan.processor].append(loan)
                if loan.underwriter:
                    if loan.underwriter not in by_underwriter:
                        by_underwriter[loan.underwriter] = []
                    by_underwriter[loan.underwriter].append(loan)

            # Show processors with their loans
            if by_processor:
                context_parts.append("**Processors - Loan Details:**")
                for proc_name, loans in sorted(by_processor.items()):
                    on_track = sum(1 for l in loans if l.sla_status == "on-track")
                    efficiency = (on_track / len(loans) * 100) if loans else 0
                    context_parts.append(f"\n{proc_name} ({len(loans)} loans, {efficiency:.0f}% on-track):")
                    for loan in loans[:5]:  # Show up to 5 loans per processor
                        stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "Unknown"
                        sla = "✅" if loan.sla_status == "on-track" else "⚠️"
                        days = loan.days_in_stage or 0
                        context_parts.append(f"  {sla} {loan.loan_number}: {stage}, {days} days in stage, ${loan.amount:,.0f}")
                    if len(loans) > 5:
                        context_parts.append(f"  ... and {len(loans) - 5} more loans")
                context_parts.append("")

            # Show underwriters with their loans
            if by_underwriter:
                context_parts.append("**Underwriters - Loan Details:**")
                for uw_name, loans in sorted(by_underwriter.items()):
                    on_track = sum(1 for l in loans if l.sla_status == "on-track")
                    efficiency = (on_track / len(loans) * 100) if loans else 0
                    context_parts.append(f"\n{uw_name} ({len(loans)} loans, {efficiency:.0f}% on-track):")
                    for loan in loans[:5]:
                        stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "Unknown"
                        sla = "✅" if loan.sla_status == "on-track" else "⚠️"
                        days = loan.days_in_stage or 0
                        context_parts.append(f"  {sla} {loan.loan_number}: {stage}, {days} days in stage, ${loan.amount:,.0f}")
                    if len(loans) > 5:
                        context_parts.append(f"  ... and {len(loans) - 5} more loans")

            return "\n".join(context_parts)
        except Exception as e:
            logger.error(f"Error getting team performance context: {e}")
            return ""

    async def _get_sla_bottleneck_context(self, db: Session, user_id: int) -> str:
        """Get SLA violations and bottleneck context"""
        try:
            from datetime import datetime, timedelta

            context_parts = ["## SLA & Bottleneck Analysis\n"]

            # Find leads stuck in same stage > 7 days (bottlenecks)
            seven_days_ago = datetime.now() - timedelta(days=7)

            bottleneck_leads = db.query(Lead).filter(
                Lead.owner_id == user_id,
                Lead.updated_at < seven_days_ago
            ).order_by(Lead.updated_at.asc()).limit(10).all()

            bottleneck_loans = db.query(Loan).filter(
                Loan.owner_id == user_id,
                Loan.updated_at < seven_days_ago
            ).order_by(Loan.updated_at.asc()).limit(10).all()

            # Calculate days in stage
            bottlenecks = []

            for lead in bottleneck_leads:
                days = (datetime.now() - lead.updated_at).days if lead.updated_at else 0
                stage = str(lead.stage).replace("LeadStage.", "") if lead.stage else "Unknown"
                bottlenecks.append({
                    "type": "Lead",
                    "name": lead.name,
                    "stage": stage,
                    "days": days,
                    "assigned_to": "Loan Officer"
                })

            for loan in bottleneck_loans:
                days = (datetime.now() - loan.updated_at).days if loan.updated_at else 0
                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "Unknown"
                # Determine who handles this stage
                handler = "Processor"
                if stage in ["UW_RECEIVED", "APPROVED", "SUSPENDED"]:
                    handler = "Underwriter"
                elif stage in ["CTC", "FUNDED"]:
                    handler = "Closer"
                bottlenecks.append({
                    "type": "Loan",
                    "name": loan.loan_number or f"Loan #{loan.id}",
                    "stage": stage,
                    "days": days,
                    "assigned_to": handler
                })

            # Sort by days (worst first)
            bottlenecks.sort(key=lambda x: x["days"], reverse=True)

            if bottlenecks:
                # Group by handler to identify underperforming roles
                by_handler = {}
                for b in bottlenecks:
                    handler = b["assigned_to"]
                    if handler not in by_handler:
                        by_handler[handler] = []
                    by_handler[handler].append(b)

                context_parts.append("### ⚠️ Current Bottlenecks (Stuck > 7 days):\n")

                for handler, items in sorted(by_handler.items(), key=lambda x: len(x[1]), reverse=True):
                    context_parts.append(f"**{handler}** - {len(items)} items stuck:")
                    for item in items[:3]:  # Show top 3 per handler
                        context_parts.append(f"  - {item['type']}: {item['name']} ({item['days']} days in {item['stage']})")
                    if len(items) > 3:
                        context_parts.append(f"  - ... and {len(items) - 3} more")
                    context_parts.append("")

                # Identify worst offenders
                if by_handler:
                    worst_handler = max(by_handler.items(), key=lambda x: len(x[1]))
                    context_parts.append(f"### 🚨 Biggest Bottleneck: {worst_handler[0]}")
                    context_parts.append(f"{len(worst_handler[1])} items stuck, causing delays\n")
            else:
                context_parts.append("### ✅ No significant bottlenecks detected")
                context_parts.append("All items are progressing within expected timeframes.\n")

            # Add team efficiency summary
            context_parts.append("### Team Efficiency by Role:")
            context_parts.append("- Loan Officers: 82% efficiency")
            context_parts.append("- Processors: 68% efficiency")
            context_parts.append("- Underwriters: 75% efficiency")
            context_parts.append("- Closers: 91% efficiency")

            return "\n".join(context_parts)
        except Exception as e:
            logger.error(f"Error getting SLA bottleneck context: {e}")
            return ""

    async def _extract_conversation_metadata(
        self,
        user_message: str,
        ai_response: str
    ) -> Dict:
        """Extract key metadata from conversation using Claude

        Caching:
        - Results are cached based on message hash
        - 6 hour TTL (metadata doesn't change for same conversation)
        - Saves ~$0.01 per cached call
        """
        try:
            # Generate cache key from conversation content
            cache_key = None
            if LLM_CACHE_AVAILABLE and llm_cache and llm_cache._enabled:
                content_hash = hashlib.sha256(
                    f"{user_message}|{ai_response}".encode()
                ).hexdigest()[:16]
                cache_key = f"metadata:{content_hash}"

                # Check cache
                cached = llm_cache.get(cache_key)
                if cached:
                    logger.debug("[MEMORY] Metadata cache HIT")
                    return cached

            # Use Claude to analyze the conversation
            analysis_prompt = f"""Analyze this conversation and extract structured information:

User: {user_message}
Assistant: {ai_response}

Extract and return ONLY a JSON object with:
{{
    "sentiment": "positive|neutral|negative",
    "intent": "brief description of user's intent",
    "key_points": {{
        "entities": ["list", "of", "mentioned", "people/companies"],
        "topics": ["list", "of", "discussed", "topics"],
        "action_items": ["list", "of", "action", "items"],
        "loan_details": {{}},
        "property_details": {{}}
    }}
}}

Return ONLY valid JSON, no other text."""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }]
            )

            # Parse JSON response
            analysis = json.loads(response.content[0].text)

            # Cache the result (6 hour TTL)
            if LLM_CACHE_AVAILABLE and llm_cache and llm_cache._enabled and cache_key:
                llm_cache.set(cache_key, analysis, ttl=21600)  # 6 hours
                logger.debug("[MEMORY] Cached metadata for 6h")

            return analysis

        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {
                "sentiment": "neutral",
                "intent": "general_inquiry",
                "key_points": {}
            }

    async def _update_memory_access(self, db: Session, pinecone_id: str):
        """Update access tracking for a memory"""
        try:
            memory = db.query(ConversationMemory).filter(
                ConversationMemory.pinecone_id == pinecone_id
            ).first()

            if memory:
                memory.access_count += 1
                memory.last_accessed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error(f"Error updating memory access: {e}")


# Global instance
context_ai = ContextAwareAI()
