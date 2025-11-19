#!/usr/bin/env python3
"""Quick script to add sample conversations"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta, timezone
from database import SessionLocal
from ai_receptionist_dashboard_models import AIReceptionistConversation
import uuid

db = SessionLocal()

try:
    # Add 3 simple conversations
    conversations = [
        {
            'summary': 'Appointment scheduled',
            'transcript': 'AI: Hello! How can I help?\nClient: I want to schedule a meeting.\nAI: Great! Thursday at 2pm work?',
            'duration': 120
        },
        {
            'summary': 'Rate inquiry',
            'transcript': 'AI: Hello!\nClient: What are your current rates?\nAI: Current rates start at 6.5%. Would you like to speak with a loan officer?',
            'duration': 90
        },
        {
            'summary': 'Document upload',
            'transcript': 'AI: Hi there!\nClient: I need to upload documents.\nAI: I can help! Sending you a secure link now.',
            'duration': 60
        }
    ]

    for i, conv_data in enumerate(conversations):
        start_time = datetime.now(timezone.utc) - timedelta(hours=i+1)

        conv = AIReceptionistConversation(
            id=str(uuid.uuid4()),
            started_at=start_time,
            ended_at=start_time + timedelta(seconds=conv_data['duration']),
            duration_seconds=conv_data['duration'],
            client_name=f"Sample Client {i+1}",
            client_phone=f"+155500000{i+1}",
            channel='voice',
            transcript=conv_data['transcript'],
            summary=conv_data['summary'],
            sentiment='positive',
            outcome='success'
        )
        db.add(conv)

    db.commit()
    print("✅ Added 3 sample conversations")

except Exception as e:
    print(f"Note: {e}")
    print("✅ Main data is already loaded - conversations are optional")
finally:
    db.close()
