"""
User Context Manager
Provides personalized context for AI interactions based on:
- User profile and role
- Performance metrics
- Communication preferences (learned and explicit)
- Behavioral patterns
- Interaction history
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class UserContextManager:
    """
    Manages user context for AI personalization.

    Provides rich context about users including:
    - Profile information (name, role, branch)
    - Performance metrics (closing rate, pipeline value)
    - Communication preferences (detail level, tone, focus areas)
    - Behavioral patterns (when they work, what they ask about)
    - Interaction history (total messages, common topics)
    """

    # Default preferences for new users or when learning
    DEFAULT_PREFERENCES = {
        'detail_level': 'moderate',  # 'concise', 'moderate', 'detailed'
        'tone': 'professional',  # 'casual', 'professional', 'formal'
        'focus_areas': [],  # ['revenue', 'compliance', 'efficiency', 'client_satisfaction']
        'proactive_suggestions': True,
        'include_metrics': True,
        'preferred_greeting': 'standard',  # 'standard', 'brief', 'personalized'
    }

    @staticmethod
    async def get_context(
        db: Session,
        user_id: int,
        include_performance: bool = True,
        include_preferences: bool = True,
        include_behavior: bool = True,
        organization_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive user context for AI personalization.

        Args:
            db: Database session
            user_id: User's ID
            include_performance: Include performance metrics
            include_preferences: Include learned preferences
            include_behavior: Include behavioral patterns
            organization_id: Tenant org ID for defense-in-depth isolation

        Returns:
            Dict with user context for AI system prompt injection
        """
        try:
            context = {
                'profile': await UserContextManager._get_profile(db, user_id),
                'summary': '',  # Will be built at the end
            }

            if include_performance:
                context['performance'] = await UserContextManager._get_performance_metrics(db, user_id, organization_id)

            if include_preferences:
                context['preferences'] = await UserContextManager._get_preferences(db, user_id, organization_id)

            if include_behavior:
                context['behavior'] = await UserContextManager._get_behavioral_patterns(db, user_id, organization_id)

            # Build human-readable summary for AI
            context['summary'] = UserContextManager._build_context_summary(context)

            return context

        except Exception as e:
            logger.error(f"Error getting user context: {e}")
            # Rollback to clear any failed transaction state
            try:
                db.rollback()
            except Exception:
                pass
            return {
                'profile': {'role': 'loan_officer', 'name': 'User'},
                'summary': 'User context unavailable.',
                'error': str(e)
            }

    @staticmethod
    async def _get_profile(db: Session, user_id: int) -> Dict[str, Any]:
        """Get basic user profile information."""
        try:
            result = db.execute(text("""
                SELECT
                    u.id,
                    u.full_name,
                    u.email,
                    u.role,
                    u.permission_role,
                    u.current_role,
                    u.nmls_number,
                    u.phone,
                    u.created_at,
                    u.onboarding_completed,
                    b.name as branch_name,
                    o.name as organization_name
                FROM users u
                LEFT JOIN branches b ON u.branch_id = b.id
                LEFT JOIN organizations o ON u.organization_id = o.id
                WHERE u.id = :user_id
            """), {"user_id": user_id})

            row = result.fetchone()
            if not row:
                return {'role': 'loan_officer', 'name': 'User'}

            # Calculate tenure
            created_at = row[8]
            tenure_days = (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).days if created_at else 0

            return {
                'id': row[0],
                'name': row[1] or 'User',
                'email': row[2],
                'role': row[3] or 'loan_officer',
                'permission_role': row[4] or 'sales',
                'current_role': row[5],
                'nmls_number': row[6],
                'phone': row[7],
                'branch': row[10],
                'organization': row[11],
                'tenure_days': tenure_days,
                'onboarding_completed': row[9] or False,
                'is_new_user': tenure_days < 30,
                'is_experienced': tenure_days > 180
            }

        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return {'role': 'loan_officer', 'name': 'User'}

    @staticmethod
    async def _get_performance_metrics(db: Session, user_id: int, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """Get user's performance metrics for context."""
        try:
            # Get loan pipeline stats
            # Note: Stage values must match LoanStage enum in main.py exactly
            pipeline_result = db.execute(text("""
                SELECT
                    COUNT(*) as total_loans,
                    COUNT(CASE WHEN stage NOT IN ('Funded') THEN 1 END) as active_loans,
                    COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as closed_loans,
                    COALESCE(SUM(CASE WHEN stage NOT IN ('Funded') THEN amount END), 0) as active_pipeline_value,
                    COALESCE(SUM(CASE WHEN stage = 'Funded' THEN amount END), 0) as closed_volume,
                    COUNT(CASE WHEN stage NOT IN ('Funded')
                          AND closing_date < NOW() + INTERVAL '7 days' THEN 1 END) as closing_this_week
                FROM loans
                WHERE loan_officer_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND created_at > NOW() - INTERVAL '90 days'
            """), {"user_id": user_id, "org_id": organization_id})

            pipeline = pipeline_result.fetchone()

            # Get lead conversion rate
            lead_result = db.execute(text("""
                SELECT
                    COUNT(*) as total_leads,
                    COUNT(CASE WHEN stage IN ('converted', 'application') THEN 1 END) as converted_leads,
                    AVG(EXTRACT(DAY FROM updated_at - created_at)) as avg_days_to_convert
                FROM leads
                WHERE owner_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND created_at > NOW() - INTERVAL '90 days'
            """), {"user_id": user_id, "org_id": organization_id})

            leads = lead_result.fetchone()

            # Get task completion rate
            task_result = db.execute(text("""
                SELECT
                    COUNT(*) as total_tasks,
                    COUNT(CASE WHEN type = 'Completed' THEN 1 END) as completed_tasks,
                    COUNT(CASE WHEN due_date < NOW() AND type != 'Completed' THEN 1 END) as overdue_tasks
                FROM ai_tasks
                WHERE assigned_to_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND created_at > NOW() - INTERVAL '30 days'
            """), {"user_id": user_id, "org_id": organization_id})

            tasks = task_result.fetchone()

            # Calculate metrics
            total_leads = leads[0] or 0
            converted_leads = leads[1] or 0
            total_tasks = tasks[0] or 0
            completed_tasks = tasks[1] or 0

            conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
            completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

            # Determine performance tier
            if pipeline[5] >= 3 and conversion_rate >= 30:
                performance_tier = 'top_performer'
            elif pipeline[5] >= 1 and conversion_rate >= 15:
                performance_tier = 'solid_performer'
            elif pipeline[1] > 0:
                performance_tier = 'developing'
            else:
                performance_tier = 'new_or_inactive'

            return {
                'total_loans_90d': pipeline[0] or 0,
                'active_loans': pipeline[1] or 0,
                'closed_loans_90d': pipeline[2] or 0,
                'active_pipeline_value': float(pipeline[3] or 0),
                'closed_volume_90d': float(pipeline[4] or 0),
                'closing_this_week': pipeline[5] or 0,
                'lead_conversion_rate': round(conversion_rate, 1),
                'avg_days_to_convert': round(leads[2] or 0, 1),
                'task_completion_rate': round(completion_rate, 1),
                'overdue_tasks': tasks[2] or 0,
                'performance_tier': performance_tier
            }

        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return {
                'performance_tier': 'unknown',
                'active_loans': 0,
                'active_pipeline_value': 0
            }

    @staticmethod
    async def _get_preferences(db: Session, user_id: int, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """Get user's AI interaction preferences (stored and learned)."""
        try:
            # Check for explicit user preferences in settings
            settings_result = db.execute(text("""
                SELECT setting_key, setting_value
                FROM user_settings
                WHERE user_id = :user_id
                AND setting_key LIKE 'ai_%'
            """), {"user_id": user_id})

            explicit_prefs = {}
            for row in settings_result:
                key = row[0].replace('ai_', '')
                try:
                    explicit_prefs[key] = json.loads(row[1])
                except (json.JSONDecodeError, TypeError):
                    explicit_prefs[key] = row[1]

            # Learn preferences from conversation history
            learned_prefs = await UserContextManager._learn_preferences_from_history(db, user_id, organization_id)

            # Merge: explicit preferences override learned ones
            preferences = {**UserContextManager.DEFAULT_PREFERENCES}
            preferences.update(learned_prefs)
            preferences.update(explicit_prefs)

            return preferences

        except Exception as e:
            logger.error(f"Error getting preferences: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return UserContextManager.DEFAULT_PREFERENCES.copy()

    @staticmethod
    async def _learn_preferences_from_history(db: Session, user_id: int, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """Learn user preferences from their conversation history."""
        try:
            # Analyze conversation patterns (tenant-scoped for defense-in-depth)
            history_result = db.execute(text("""
                SELECT
                    role,
                    content,
                    LENGTH(content) as content_length,
                    created_at
                FROM ai_conversation_memory
                WHERE user_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                ORDER BY created_at DESC
                LIMIT 100
            """), {"user_id": user_id, "org_id": organization_id})

            messages = list(history_result)
            if not messages:
                return {}

            learned = {}

            # Analyze user message patterns
            user_messages = [m for m in messages if m[0] == 'user']
            if user_messages:
                avg_user_length = sum(m[2] for m in user_messages) / len(user_messages)

                # Short messages = prefers concise responses
                if avg_user_length < 50:
                    learned['detail_level'] = 'concise'
                elif avg_user_length > 150:
                    learned['detail_level'] = 'detailed'

            # Detect focus areas from keywords
            all_user_content = ' '.join(m[1] for m in user_messages).lower()

            focus_areas = []
            if any(word in all_user_content for word in ['revenue', 'money', 'profit', 'commission', 'income']):
                focus_areas.append('revenue')
            if any(word in all_user_content for word in ['compliant', 'compliance', 'regulation', 'trid', 'audit']):
                focus_areas.append('compliance')
            if any(word in all_user_content for word in ['faster', 'quick', 'efficient', 'streamline', 'automate']):
                focus_areas.append('efficiency')
            if any(word in all_user_content for word in ['client', 'borrower', 'satisfaction', 'experience', 'happy']):
                focus_areas.append('client_satisfaction')

            if focus_areas:
                learned['focus_areas'] = focus_areas

            # Detect tone preference from AI response feedback patterns
            # (If they keep asking follow-ups, the AI might be too brief)
            consecutive_followups = 0
            for i, msg in enumerate(user_messages[:-1]):
                # Check if next message is a clarifying question
                next_content = user_messages[i+1][1].lower() if i+1 < len(user_messages) else ''
                if any(word in next_content for word in ['what do you mean', 'explain', 'more detail', 'elaborate']):
                    consecutive_followups += 1

            if consecutive_followups > 3:
                learned['detail_level'] = 'detailed'

            return learned

        except Exception as e:
            logger.error(f"Error learning preferences: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return {}

    @staticmethod
    async def _get_behavioral_patterns(db: Session, user_id: int, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """Analyze user's behavioral patterns."""
        try:
            # Get activity timing patterns (tenant-scoped for defense-in-depth)
            timing_result = db.execute(text("""
                SELECT
                    EXTRACT(HOUR FROM created_at) as hour,
                    COUNT(*) as count
                FROM ai_conversation_memory
                WHERE user_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND created_at > NOW() - INTERVAL '30 days'
                GROUP BY EXTRACT(HOUR FROM created_at)
                ORDER BY count DESC
                LIMIT 3
            """), {"user_id": user_id, "org_id": organization_id})

            peak_hours = [int(row[0]) for row in timing_result]

            # Determine work pattern
            if peak_hours:
                avg_peak = sum(peak_hours) / len(peak_hours)
                if avg_peak < 9:
                    work_pattern = 'early_bird'
                elif avg_peak > 17:
                    work_pattern = 'night_owl'
                else:
                    work_pattern = 'standard_hours'
            else:
                work_pattern = 'unknown'

            # Get common question topics
            topics_result = db.execute(text("""
                SELECT content
                FROM ai_conversation_memory
                WHERE user_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND role = 'user'
                AND created_at > NOW() - INTERVAL '30 days'
                LIMIT 50
            """), {"user_id": user_id, "org_id": organization_id})

            all_content = ' '.join(row[0].lower() for row in topics_result)

            common_topics = []
            topic_keywords = {
                'tasks': ['task', 'priority', 'todo', 'focus', 'do today'],
                'pipeline': ['pipeline', 'loan', 'deal', 'closing'],
                'rates': ['rate', 'lock', 'float', 'market'],
                'leads': ['lead', 'prospect', 'follow-up', 'nurture'],
                'performance': ['metrics', 'performance', 'how am i', 'results']
            }

            for topic, keywords in topic_keywords.items():
                if any(kw in all_content for kw in keywords):
                    common_topics.append(topic)

            # Get total interaction count
            count_result = db.execute(text("""
                SELECT COUNT(*) FROM ai_conversation_memory
                WHERE user_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
            """), {"user_id": user_id, "org_id": organization_id})
            total_interactions = count_result.scalar() or 0

            # Get last interaction
            last_result = db.execute(text("""
                SELECT created_at FROM ai_conversation_memory
                WHERE user_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                ORDER BY created_at DESC LIMIT 1
            """), {"user_id": user_id, "org_id": organization_id})
            last_row = last_result.fetchone()
            last_interaction = last_row[0] if last_row else None

            return {
                'peak_hours': peak_hours,
                'work_pattern': work_pattern,
                'common_topics': common_topics,
                'total_interactions': total_interactions,
                'last_interaction': last_interaction.isoformat() if last_interaction else None,
                'is_frequent_user': total_interactions > 50,
                'is_new_to_ai': total_interactions < 10
            }

        except Exception as e:
            logger.error(f"Error getting behavioral patterns: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return {
                'work_pattern': 'unknown',
                'common_topics': [],
                'total_interactions': 0
            }

    @staticmethod
    def _build_context_summary(context: Dict[str, Any]) -> str:
        """Build a human-readable summary for AI system prompt."""
        parts = []

        profile = context.get('profile', {})
        performance = context.get('performance', {})
        preferences = context.get('preferences', {})
        behavior = context.get('behavior', {})

        # Name and role
        name = profile.get('name', 'User')
        role = profile.get('current_role') or profile.get('role', 'loan_officer')
        parts.append(f"User: {name} ({role})")

        # Branch/org
        if profile.get('branch'):
            parts.append(f"Branch: {profile['branch']}")

        # Performance context
        if performance:
            tier = performance.get('performance_tier', 'unknown')
            if tier == 'top_performer':
                parts.append("Performance: Top performer - high conversion rate, multiple closings")
            elif tier == 'solid_performer':
                parts.append("Performance: Solid performer - consistent results")
            elif tier == 'developing':
                parts.append("Performance: Developing - building pipeline")

            if performance.get('closing_this_week', 0) > 0:
                parts.append(f"Closing {performance['closing_this_week']} loan(s) this week")

            if performance.get('overdue_tasks', 0) > 2:
                parts.append(f"Has {performance['overdue_tasks']} overdue tasks")

        # Communication preferences
        if preferences:
            detail = preferences.get('detail_level', 'moderate')
            if detail == 'concise':
                parts.append("Prefers concise, bullet-point responses")
            elif detail == 'detailed':
                parts.append("Prefers detailed explanations")

            focus = preferences.get('focus_areas', [])
            if focus:
                parts.append(f"Focus areas: {', '.join(focus)}")

        # Behavioral insights
        if behavior:
            if behavior.get('is_new_to_ai'):
                parts.append("New to AI assistant - may need more guidance")
            elif behavior.get('is_frequent_user'):
                parts.append("Experienced AI user - familiar with capabilities")

            topics = behavior.get('common_topics', [])
            if topics:
                parts.append(f"Usually asks about: {', '.join(topics)}")

        return ' | '.join(parts)

    @staticmethod
    async def save_preference(
        db: Session,
        user_id: int,
        key: str,
        value: Any
    ) -> bool:
        """Save a user preference."""
        try:
            setting_key = f"ai_{key}" if not key.startswith('ai_') else key
            setting_value = json.dumps(value) if not isinstance(value, str) else value

            # Upsert preference
            db.execute(text("""
                INSERT INTO user_settings (user_id, setting_key, setting_value, created_at, updated_at)
                VALUES (:user_id, :key, :value, NOW(), NOW())
                ON CONFLICT (user_id, setting_key)
                DO UPDATE SET setting_value = :value, updated_at = NOW()
            """), {
                "user_id": user_id,
                "key": setting_key,
                "value": setting_value
            })
            db.commit()

            logger.info(f"Saved preference {key} for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving preference: {e}")
            db.rollback()
            return False

    @staticmethod
    async def update_from_interaction(
        db: Session,
        user_id: int,
        message: str,
        response: str,
        feedback: Optional[str] = None
    ) -> None:
        """
        Update user context based on an interaction.
        Called after each AI interaction to learn preferences.
        """
        try:
            # This could be expanded to:
            # 1. Analyze if user asked for more/less detail
            # 2. Track topics of interest
            # 3. Note positive/negative feedback
            # 4. Update learned preferences accordingly

            # For now, just log for future ML training
            logger.debug(f"Interaction recorded for user {user_id}: {len(message)} chars -> {len(response)} chars")

        except Exception as e:
            logger.error(f"Error updating from interaction: {e}")
