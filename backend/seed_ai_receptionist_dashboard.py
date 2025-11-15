#!/usr/bin/env python3
"""
Seed AI Receptionist Dashboard with Sample Data
Populates all 6 tables with realistic test data for verification
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import random
from datetime import datetime, timedelta, timezone, date
from database import SessionLocal
from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistMetricsDaily,
    AIReceptionistSkill,
    AIReceptionistError,
    AIReceptionistSystemHealth,
    AIReceptionistConversation
)
import uuid

def seed_activity_feed(db, days=7):
    """Generate sample activity data for the last N days"""
    print(f"\n📊 Seeding activity feed ({days} days)...")

    action_types = [
        ('incoming_call', 0.4),
        ('incoming_text', 0.3),
        ('outbound_followup', 0.05),
        ('appointment_booked', 0.1),
        ('faq_answered', 0.08),
        ('lead_prescreened', 0.03),
        ('crm_updated', 0.02),
        ('escalated', 0.015),
        ('ai_uncertainty', 0.005),
    ]

    channels = ['sms', 'voice']
    outcomes = ['success', 'failed', 'escalated', 'pending']
    lead_stages = ['prospect', 'application', 'processing', 'closed', 'archived']

    client_names = [
        "John Smith", "Sarah Johnson", "Michael Brown", "Emily Davis",
        "David Wilson", "Lisa Anderson", "Robert Taylor", "Jennifer Martinez",
        "William Garcia", "Mary Rodriguez", "James Lee", "Patricia White",
        "Christopher Harris", "Barbara Clark", "Daniel Lewis", "Susan Walker"
    ]

    total_created = 0

    for day in range(days):
        target_date = datetime.now(timezone.utc) - timedelta(days=day)
        # More activities on recent days
        num_activities = random.randint(80, 150) if day < 3 else random.randint(40, 80)

        for _ in range(num_activities):
            # Weighted random choice for action type
            action_type = random.choices(
                [a[0] for a in action_types],
                weights=[a[1] for a in action_types]
            )[0]

            activity_time = target_date.replace(
                hour=random.randint(8, 20),
                minute=random.randint(0, 59),
                second=random.randint(0, 59)
            )

            client_name = random.choice(client_names)
            client_id = str(abs(hash(client_name)) % 1000)

            activity = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=activity_time,
                client_id=client_id,
                client_name=client_name,
                client_phone=f"+1{random.randint(2000000000, 9999999999)}",
                client_email=f"{client_name.lower().replace(' ', '.')}@example.com",
                action_type=action_type,
                channel=random.choice(channels),
                message_in=f"Client inquiry about {random.choice(['rates', 'application status', 'documents', 'appointment', 'conditions'])}",
                message_out=f"AI responded with {random.choice(['information', 'appointment booking', 'document request', 'FAQ answer'])}",
                confidence_score=random.uniform(0.6, 0.99),
                ai_version="gpt-4o-realtime-v1",
                lead_stage=random.choice(lead_stages),
                assigned_to=f"LO-{random.randint(1, 10)}" if random.random() > 0.3 else None,
                outcome_status=random.choice(outcomes),
                conversation_id=str(uuid.uuid4()),
                extra_data={
                    "duration_seconds": random.randint(30, 600),
                    "turns": random.randint(2, 15)
                }
            )
            db.add(activity)
            total_created += 1

    db.commit()
    print(f"✅ Created {total_created} activity feed items")
    return total_created


def seed_daily_metrics(db, days=14):
    """Create sample daily metrics for the last N days"""
    print(f"\n📈 Seeding daily metrics ({days} days)...")

    total_created = 0

    for day in range(days):
        metric_date = date.today() - timedelta(days=day)

        # Realistic metrics with some variance
        total_convos = random.randint(80, 200)
        appointments = random.randint(10, 30)
        escalations = random.randint(2, 15)

        metric = AIReceptionistMetricsDaily(
            date=metric_date,
            total_conversations=total_convos,
            inbound_calls=random.randint(int(total_convos * 0.5), int(total_convos * 0.7)),
            inbound_texts=random.randint(int(total_convos * 0.3), int(total_convos * 0.5)),
            outbound_messages=random.randint(20, 50),
            response_time_avg_seconds=random.uniform(2.5, 8.0),
            response_time_p95_seconds=random.uniform(8.0, 15.0),
            appointments_scheduled=appointments,
            forms_completed=random.randint(5, 20),
            loan_apps_initiated=random.randint(3, 12),
            lead_updates=random.randint(30, 80),
            task_updates=random.randint(10, 40),
            documents_requested=random.randint(15, 45),
            escalations=escalations,
            ai_confusion_count=random.randint(1, 10),
            successful_resolutions=random.randint(int(total_convos * 0.7), int(total_convos * 0.9)),
            lead_qualification_rate=random.uniform(0.65, 0.85),
            appointment_show_rate=random.uniform(0.75, 0.92),
            ai_coverage_percentage=(1 - (escalations / total_convos)) * 100,
            estimated_revenue_created=appointments * random.uniform(1200, 2500),
            saved_labor_hours=random.uniform(8, 20),
            cost_per_interaction=random.uniform(0.35, 0.65),
            avg_confidence_score=random.uniform(0.82, 0.94),
            error_rate=random.uniform(0.02, 0.08),
            extra_data={
                "peak_hour": random.randint(9, 17),
                "busiest_day": metric_date.strftime("%A")
            }
        )
        db.add(metric)
        total_created += 1

    db.commit()
    print(f"✅ Created {total_created} daily metric records")
    return total_created


def seed_skills(db):
    """Create sample skill performance data"""
    print(f"\n🎯 Seeding AI skills...")

    skills_data = [
        ('Appointment Scheduling', 'scheduling', 0.95, 'improving'),
        ('Lead Inquiry Handling', 'lead_management', 0.88, 'stable'),
        ('Rate Questions', 'faq', 0.72, 'declining'),
        ('Document Requests', 'operations', 0.85, 'improving'),
        ('Existing Borrower Support', 'support', 0.90, 'stable'),
        ('Builder Updates', 'coordination', 0.78, 'stable'),
        ('Contract Updates', 'legal', 0.82, 'improving'),
        ('Underwriting Conditions', 'operations', 0.75, 'declining'),
        ('Voicemail Handling', 'communication', 0.93, 'improving'),
        ('Emergency Escalation', 'support', 0.97, 'stable'),
        ('Payment Processing', 'financial', 0.68, 'declining'),
        ('Compliance Questions', 'legal', 0.80, 'stable'),
    ]

    total_created = 0

    for name, category, accuracy, trend in skills_data:
        # Calculate 7-day and 30-day averages with realistic variance
        accuracy_7day = accuracy + random.uniform(-0.03, 0.03)
        accuracy_30day = accuracy + random.uniform(-0.05, 0.05)

        # Calculate trends
        trend_7day = ((accuracy - accuracy_7day) / accuracy_7day) * 100
        trend_30day = ((accuracy - accuracy_30day) / accuracy_30day) * 100

        usage = random.randint(50, 500)
        failures = int(usage * (1 - accuracy))

        skill = AIReceptionistSkill(
            id=str(uuid.uuid4()),
            skill_name=name,
            skill_category=category,
            description=f"AI capability to handle {name.lower()}",
            accuracy_score=accuracy,
            accuracy_score_7day=accuracy_7day,
            accuracy_score_30day=accuracy_30day,
            trend_7day=trend_7day,
            trend_30day=trend_30day,
            trend_direction=trend,
            usage_count=usage,
            success_count=usage - failures,
            failure_count=failures,
            needs_retraining=(accuracy < 0.75),
            last_trained_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
            last_updated=datetime.now(timezone.utc),
            extra_data={
                "training_iterations": random.randint(5, 50),
                "last_improvement": f"{random.uniform(0, 10):.1f}%"
            }
        )
        db.add(skill)
        total_created += 1

    db.commit()
    print(f"✅ Created {total_created} skill records")
    return total_created


def seed_errors(db):
    """Create sample error log entries"""
    print(f"\n🚨 Seeding error logs...")

    error_types = [
        ('unrecognized_request', 'medium'),
        ('missing_context', 'low'),
        ('model_uncertainty', 'high'),
        ('out_of_scope', 'medium'),
        ('api_failure', 'critical'),
        ('integration_error', 'high'),
        ('timeout', 'medium'),
    ]

    sample_errors = [
        {
            'type': 'unrecognized_request',
            'snippet': "Can you refinance my underwater mortgage with no equity?",
            'cause': "Missing training data for underwater refinance scenarios",
            'fix': "Add FAQ entry for underwater refinancing options (HARP, streamline refi)"
        },
        {
            'type': 'missing_context',
            'snippet': "What's the status?",
            'cause': "No conversation history available, unclear what 'status' refers to",
            'fix': "Implement context retention across conversation sessions"
        },
        {
            'type': 'model_uncertainty',
            'snippet': "I need to talk about my escrow analysis adjustment notice",
            'cause': "Confidence score 0.42 - complex escrow terminology",
            'fix': "Add escrow-specific training examples and terminology"
        },
        {
            'type': 'api_failure',
            'snippet': "Schedule appointment for tomorrow at 2pm",
            'cause': "Calendly API returned 503 Service Unavailable",
            'fix': "Implement retry logic with exponential backoff"
        },
        {
            'type': 'out_of_scope',
            'snippet': "Can you help me with my credit card debt consolidation?",
            'cause': "Request outside mortgage lending scope",
            'fix': "Add routing to refer non-mortgage inquiries to appropriate resources"
        },
        {
            'type': 'integration_error',
            'snippet': "Update my loan file with the new appraisal",
            'cause': "CRM API authentication token expired",
            'fix': "Implement automatic token refresh before expiry"
        },
        {
            'type': 'timeout',
            'snippet': "Tell me about all the FHA programs you offer",
            'cause': "Knowledge base query took >30 seconds",
            'fix': "Optimize vector search indexing and implement caching"
        },
        {
            'type': 'model_uncertainty',
            'snippet': "What's your opinion on interest rate trends?",
            'cause': "AI uncertain about providing financial advice (confidence 0.38)",
            'fix': "Add disclaimer templates and route to licensed LO for rate predictions"
        },
    ]

    total_created = 0

    for i, error_data in enumerate(sample_errors):
        days_ago = random.randint(0, 10)

        error = AIReceptionistError(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(0, 23)),
            error_type=error_data['type'],
            severity=next(s[1] for s in error_types if s[0] == error_data['type']),
            context=f"Error occurred during {'voice' if i % 2 == 0 else 'SMS'} interaction",
            conversation_snippet=error_data['snippet'],
            conversation_id=str(uuid.uuid4()),
            root_cause=error_data['cause'],
            recommended_fix=error_data['fix'],
            auto_fix_proposed=error_data['fix'] if random.random() > 0.5 else None,
            needs_human_review=(random.random() > 0.3),
            resolution_status='unresolved' if days_ago < 3 else random.choice(['unresolved', 'auto_fixed', 'manually_fixed']),
            extra_data={
                "occurrence_count": random.randint(1, 10),
                "first_seen": (datetime.now(timezone.utc) - timedelta(days=days_ago+5)).isoformat()
            }
        )
        db.add(error)
        total_created += 1

    # Add 2 more unresolved errors for testing
    for _ in range(2):
        error = AIReceptionistError(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 12)),
            error_type=random.choice([e[0] for e in error_types]),
            severity='high',
            context="Recent error requiring review",
            conversation_snippet="Error snippet for testing",
            needs_human_review=True,
            resolution_status='unresolved',
            extra_data={"test_data": True}
        )
        db.add(error)
        total_created += 1

    db.commit()
    print(f"✅ Created {total_created} error records")
    return total_created


def seed_system_health(db):
    """Initialize system health components"""
    print(f"\n💚 Seeding system health...")

    components = [
        ('sms_integration', 'active', 120, 0.5, 99.8),
        ('voice_endpoint', 'active', 150, 0.3, 99.9),
        ('calendly_api', 'active', 200, 0.8, 99.5),
        ('crm_pipeline', 'degraded', 450, 5.2, 95.0),
        ('outlook_sync', 'active', 300, 1.0, 99.2),
        ('teams_sync', 'active', 250, 0.6, 99.6),
        ('zapier_triggers', 'down', 5000, 45.0, 60.0),
        ('document_module', 'active', 180, 0.4, 99.7),
        ('openai_api', 'active', 350, 1.2, 99.4),
        ('claude_api', 'active', 280, 0.9, 99.5),
        ('pinecone_db', 'active', 90, 0.2, 99.9),
    ]

    total_created = 0

    for name, status, latency, error_rate, uptime in components:
        now = datetime.now(timezone.utc)

        health = AIReceptionistSystemHealth(
            component_name=name,
            status=status,
            latency_ms=latency,
            error_rate=error_rate,
            uptime_percentage=uptime,
            last_checked=now,
            last_success=now if status == 'active' else now - timedelta(hours=random.randint(1, 24)),
            last_failure=now - timedelta(days=random.randint(1, 7)) if status != 'down' else now - timedelta(minutes=30),
            consecutive_failures=0 if status == 'active' else random.randint(1, 10),
            alert_sent=(status == 'down'),
            alert_sent_at=now - timedelta(minutes=25) if status == 'down' else None,
            notes=f"Component {'operational' if status == 'active' else 'experiencing issues'}",
            endpoint_url=f"https://api.service.com/{name.replace('_', '-')}",
            extra_data={
                "version": f"v{random.randint(1, 5)}.{random.randint(0, 20)}.{random.randint(0, 10)}",
                "region": random.choice(["us-east-1", "us-west-2"])
            }
        )
        db.add(health)
        total_created += 1

    db.commit()
    print(f"✅ Created {total_created} system health records")
    return total_created


def seed_conversations(db):
    """Create sample conversation transcripts"""
    print(f"\n💬 Seeding conversations...")

    sample_conversations = [
        {
            'summary': 'Appointment scheduled for loan application consultation',
            'intent': 'appointment_scheduling',
            'sentiment': 'positive',
            'outcome': 'appointment_booked',
            'transcript': """
AI: Hello! Thanks for calling. How can I help you today?
Client: Hi, I'd like to schedule a consultation about a home loan.
AI: I'd be happy to help you schedule that. What day works best for you?
Client: How about Thursday at 2 PM?
AI: Perfect! I've scheduled you for Thursday at 2 PM with one of our loan officers. You'll receive a confirmation email shortly.
Client: Great, thank you!
            """.strip()
        },
        {
            'summary': 'Client inquiry about current mortgage rates',
            'intent': 'rate_question',
            'sentiment': 'neutral',
            'outcome': 'info_provided',
            'transcript': """
AI: Hello! How may I assist you today?
Client: What are your current mortgage rates?
AI: Current rates vary based on loan type, credit score, and down payment. Our rates start at around 6.5% for qualified borrowers. Would you like me to connect you with a loan officer who can provide a personalized quote?
Client: Yes, please.
AI: I'll transfer you now to one of our licensed loan officers.
            """.strip()
        },
        {
            'summary': 'Document upload assistance for existing application',
            'intent': 'document_request',
            'sentiment': 'neutral',
            'outcome': 'info_provided',
            'transcript': """
AI: Hi! How can I help you today?
Client: I need to upload my W2s for my loan application.
AI: I can help with that. I'm sending you a secure document upload link via text message. You'll be able to upload your W2s there.
Client: Perfect, thanks!
AI: You're welcome! Is there anything else I can help with?
Client: No, that's all. Thank you!
            """.strip()
        },
    ]

    total_created = 0

    for i, conv in enumerate(sample_conversations):
        days_ago = random.randint(0, 7)
        start_time = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=random.randint(8, 18))
        duration = random.randint(60, 300)

        conversation = AIReceptionistConversation(
            id=str(uuid.uuid4()),
            started_at=start_time,
            ended_at=start_time + timedelta(seconds=duration),
            duration_seconds=duration,
            client_id=str(random.randint(1, 100)),
            client_name=f"Client-{random.randint(1, 50)}",
            client_phone=f"+1{random.randint(2000000000, 9999999999)}",
            channel=random.choice(['sms', 'voice']),
            direction='inbound',
            transcript=conv['transcript'],
            transcript_json={
                "turns": conv['transcript'].split('\n'),
                "timestamps": [start_time.isoformat()]
            },
            summary=conv['summary'],
            intent_detected=conv['intent'],
            sentiment=conv['sentiment'],
            key_topics=['mortgage', 'loan', random.choice(['rates', 'documents', 'appointment'])],
            outcome=conv['outcome'],
            avg_confidence_score=random.uniform(0.85, 0.98),
            total_turns=len([l for l in conv['transcript'].split('\n') if l.strip()]),
            extra_data={
                "language": "en",
                "ai_model": "gpt-4o-realtime"
            }
        )
        db.add(conversation)
        total_created += 1

    db.commit()
    print(f"✅ Created {total_created} conversation records")
    return total_created


def main():
    """Main seeding function"""
    print("=" * 60)
    print("AI RECEPTIONIST DASHBOARD - DATA SEEDING SCRIPT")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Seed all tables
        stats = {
            'activities': seed_activity_feed(db, days=7),
            'daily_metrics': seed_daily_metrics(db, days=14),
            'skills': seed_skills(db),
            'errors': seed_errors(db),
            'system_health': seed_system_health(db),
            'conversations': seed_conversations(db)
        }

        print("\n" + "=" * 60)
        print("✅ SEEDING COMPLETE!")
        print("=" * 60)
        print("\nRecords Created:")
        for table, count in stats.items():
            print(f"  • {table:20s}: {count:4d} records")

        print(f"\nTotal Records: {sum(stats.values())}")
        print("\n📊 Dashboard is now ready for testing with sample data!")
        print("\nNext steps:")
        print("  1. Test all API endpoints")
        print("  2. Verify data in database")
        print("  3. Check dashboard UI")

        return True

    except Exception as e:
        print(f"\n❌ Error during seeding: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
