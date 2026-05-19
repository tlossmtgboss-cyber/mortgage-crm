"""Auto-extracted from seed_full_demo.py — mechanical decomposition (no logic changes)."""
import json
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from ._shared import (
    NOW,
    TODAY,
    ORG_NAME,
    ORG_SLUG,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    pwd_context,
    days_ago,
    days_from_now,
    date_ago,
    date_from_now,
    exists,
    get_id,
)


def seed_sms_conversations(conn, org_id, user_ids, lead_ids):
    """Create demo SMS conversation threads (10 threads with 3-8 messages each)."""

    TELNYX_NUMBER = "+18438838956"

    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")

    # Conversation definitions: each entry maps to one lead
    # lead_email, assigned LO, category, messages (list of dicts)
    CONVERSATIONS = [
        # --- Scheduling (3 threads) ---
        {
            "lead_email": "derek.hollis@yahoo.com",
            "lead_phone": "+18432110103",
            "lead_name": "Derek Hollis",
            "user_id": lo_sarah_id,
            "days_ago_start": 2,
            "messages": [
                {"dir": "inbound",  "text": "Hi! This is Derek Hollis. I filled out a form on your website — I'm interested in getting pre-approved.",  "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Derek! Great to hear from you. I'm Sarah Chen, your loan officer at Summit Home Loans. I'd love to schedule a quick 30-minute discovery call. Are you available Thursday?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Thursday works for me. What time?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "How about 11 AM Eastern? I can send a Zoom link.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Perfect. See you then!", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Appointment confirmed for Thursday at 11 AM. You'll receive a calendar invite shortly. Looking forward to it!", "ai": True, "offset_hours": 3},
            ],
        },
        {
            "lead_email": "carter.webb@icloud.com",
            "lead_phone": "+18432110105",
            "lead_name": "Carter Webb",
            "user_id": lo_sarah_id,
            "days_ago_start": 5,
            "messages": [
                {"dir": "inbound",  "text": "Hi Sarah, I saw your listing on Zillow. I'm curious about rates right now.", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Carter! Happy to help. 30-year fixed is running around 6.875% today for well-qualified buyers. Would you like to hop on a quick call to see what you'd qualify for?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "That sounds good. Can we do a call Friday morning?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Friday morning works great. I have 9 AM open. Shall I book that?", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Yes please!", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Done! I've booked Friday at 9 AM. I'll send you a few questions to review beforehand so we can make the most of our time.", "ai": True, "offset_hours": 4},
                {"dir": "inbound",  "text": "Sounds great, thanks!", "ai": False, "offset_hours": 5},
            ],
        },
        {
            "lead_email": "monique.duval@gmail.com",
            "lead_phone": "+18432110104",
            "lead_name": "Monique Duval",
            "user_id": lo_marcus_id,
            "days_ago_start": 3,
            "messages": [
                {"dir": "outbound", "text": "Hi Monique, this is Aria from Summit Home Loans following up on your Realtor.com inquiry. Are you available for a quick 15-minute call this week?", "ai": True, "offset_hours": 0},
                {"dir": "inbound",  "text": "Sorry, been really busy. Can we do next week?", "ai": False, "offset_hours": 4},
                {"dir": "outbound", "text": "No problem at all! I have Monday at 2 PM or Tuesday at 10 AM open. Which works better?", "ai": True, "offset_hours": 4},
                {"dir": "inbound",  "text": "Monday at 2 works.", "ai": False, "offset_hours": 5},
                {"dir": "outbound", "text": "Perfect! Booked for Monday at 2 PM. Marcus Johnson will be on the call — he specializes in FHA programs and can walk you through your options.", "ai": True, "offset_hours": 5},
            ],
        },
        # --- Document requests (2 threads) ---
        {
            "lead_email": "tanya.morrison@gmail.com",
            "lead_phone": "+18432110114",
            "lead_name": "Tanya Morrison",
            "user_id": lo_sarah_id,
            "days_ago_start": 4,
            "messages": [
                {"dir": "outbound", "text": "Hi Tanya, Sarah here. Your loan application is looking great! I just need your 2022 tax returns to complete the file. Can you upload them to your borrower portal?", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "I don't have digital copies. Can I bring them in?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Of course! You can scan them with your phone camera in the portal app — it works really well. Or drop by the office any time. We're at 123 Meeting St.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Just uploaded them through the app. Did you get them?", "ai": False, "offset_hours": 6},
                {"dir": "outbound", "text": "Got them! I can see both 2021 and 2022 returns uploaded successfully. I'll have Emily start processing right away. You're on track for your closing date!", "ai": True, "offset_hours": 6},
            ],
        },
        {
            "lead_email": "roberto.sandoval@hotmail.com",
            "lead_phone": "+18432110115",
            "lead_name": "Roberto Sandoval",
            "user_id": lo_marcus_id,
            "days_ago_start": 6,
            "messages": [
                {"dir": "outbound", "text": "Hi Roberto, Marcus here. We're moving along nicely on your FHA loan. The appraiser needs access to the property next Tuesday — can you confirm with the listing agent?", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "Done, agent says Tuesday between 10-12 works.", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Perfect, I'll get the appraiser scheduled. Also, can you send your latest pay stub? We need the most current one in the file.", "ai": True, "offset_hours": 3},
                {"dir": "inbound",  "text": "Just sent it via email.", "ai": False, "offset_hours": 5},
                {"dir": "outbound", "text": "Got it, thank you! Everything looks on track. I'll update you after the appraisal comes back.", "ai": True, "offset_hours": 6},
                {"dir": "inbound",  "text": "Appreciate it. This is exciting!", "ai": False, "offset_hours": 7},
            ],
        },
        # --- Status updates (2 threads) ---
        {
            "lead_email": "kevin.albright@gmail.com",
            "lead_phone": "+18432110109",
            "lead_name": "Kevin Albright",
            "user_id": lo_marcus_id,
            "days_ago_start": 7,
            "messages": [
                {"dir": "outbound", "text": "Hi Kevin! Great news — your loan has been submitted to underwriting. This stage typically takes 5-7 business days.", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "That's awesome! How long does underwriting usually take?", "ai": False, "offset_hours": 1},
                {"dir": "outbound", "text": "For conventional loans like yours, usually 5-7 business days. Your file looks clean so we're optimistic. I'll text you as soon as we hear back.", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Thanks! The seller is getting anxious about the timeline.", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Totally understandable. You're on track — your closing date isn't at risk. If the seller needs a letter of assurance, I can provide that today.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "Yes please, that would help a lot!", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Done! Just emailed you and the listing agent a status letter. You're in great shape, Kevin.", "ai": True, "offset_hours": 3},
            ],
        },
        {
            "lead_email": "brianna.okafor@gmail.com",
            "lead_phone": "+18432110106",
            "lead_name": "Brianna Okafor",
            "user_id": lo_sarah_id,
            "days_ago_start": 2,
            "messages": [
                {"dir": "outbound", "text": "Hi Brianna! Excellent news — you've received a Conditional Approval. We just need two items: letter of explanation for the gap in employment (2022) and one more month of bank statements.", "ai": False, "offset_hours": 0},
                {"dir": "inbound",  "text": "Great news! What's a letter of explanation?", "ai": False, "offset_hours": 1},
                {"dir": "outbound", "text": "It's just a brief note explaining what happened — for example, 'I was between jobs for 3 months while relocating from Atlanta.' A few sentences is all we need. Want me to send a template?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Yes please, that would be super helpful.", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Template sent to your email! Once you upload both items to the portal, Emily will have them reviewed within 24 hours and you'll be Clear to Close.", "ai": True, "offset_hours": 2},
            ],
        },
        # --- Rate inquiries (2 threads) ---
        {
            "lead_email": "simone.arceneaux@gmail.com",
            "lead_phone": "+18432110108",
            "lead_name": "Simone Arceneaux",
            "user_id": lo_sarah_id,
            "days_ago_start": 1,
            "messages": [
                {"dir": "inbound",  "text": "Hi, what are rates looking like today? My closing is in 2 days.", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Simone! Great timing. 30-year conventional is at 6.500% today for your loan profile — that's an excellent rate. You're already locked, so you're good. Want to confirm your final numbers?", "ai": True, "offset_hours": 0},
                {"dir": "inbound",  "text": "Yes! What's my final monthly payment?", "ai": False, "offset_hours": 1},
                {"dir": "outbound", "text": "Your principal and interest is $3,003/month. Add taxes and insurance and your total PITI is approximately $3,580/month. The CD with exact figures will be sent 3 days before closing.", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Perfect. I'm so excited! See you at closing.", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "We're excited for you too, Simone! See you Thursday. Don't forget to bring your photo ID and a cashier's check for $76,420 (closing costs + down payment).", "ai": False, "offset_hours": 2},
            ],
        },
        {
            "lead_email": "jasmine.winters@yahoo.com",
            "lead_phone": "+18432110110",
            "lead_name": "Jasmine Winters",
            "user_id": lo_sarah_id,
            "days_ago_start": 8,
            "messages": [
                {"dir": "inbound",  "text": "Hi Sarah, rates have been moving a lot. Should I lock in now?", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Hi Jasmine! Great question. Today's rate for your loan is 6.875%. The 30-day trend is flat-to-slightly-higher. Your float window closes in 18 days. I'd recommend locking now — want me to start the lock process?", "ai": True, "offset_hours": 1},
                {"dir": "inbound",  "text": "Will rates drop before my closing?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "Rates could move either direction — nobody knows for sure. What I can tell you is that 6.875% is a solid rate historically, and locking protects you from upside risk. Floating is a gamble. The peace of mind is worth it.", "ai": True, "offset_hours": 2},
                {"dir": "inbound",  "text": "OK let's lock it in.", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "Rate locked at 6.875% for 30 days! I'll send the lock confirmation email now. You're protected through your closing date.", "ai": True, "offset_hours": 3},
            ],
        },
        # --- General (1 thread) ---
        {
            "lead_email": "michelle.osei@gmail.com",
            "lead_phone": "+18432110122",
            "lead_name": "Michelle Osei",
            "user_id": lo_sarah_id,
            "days_ago_start": 10,
            "messages": [
                {"dir": "inbound",  "text": "Hi Sarah, just wanted to say thank you for everything. The closing went so smoothly!", "ai": False, "offset_hours": 0},
                {"dir": "outbound", "text": "Michelle, congratulations!! 🎉 It was such a pleasure working with you. Enjoy your new home — you deserve it!", "ai": False, "offset_hours": 1},
                {"dir": "inbound",  "text": "We love it already. Do you happen to have any referrals for a good contractor?", "ai": False, "offset_hours": 2},
                {"dir": "outbound", "text": "I know a few great ones in Charleston! I'll send you my preferred vendor list. Also, if you know anyone looking to buy, I'd love an introduction — referrals mean the world to us.", "ai": False, "offset_hours": 2},
                {"dir": "inbound",  "text": "Of course! My neighbor is actually looking right now. I'll have them reach out.", "ai": False, "offset_hours": 3},
                {"dir": "outbound", "text": "That's wonderful, thank you so much Michelle! I'll reach out to them right away. Have fun in the new home!", "ai": False, "offset_hours": 4},
                {"dir": "inbound",  "text": "Thanks Sarah! Reach out anytime.", "ai": False, "offset_hours": 5},
                {"dir": "outbound", "text": "Will do! Enjoy every minute. 🏠", "ai": False, "offset_hours": 6},
            ],
        },
    ]

    conv_inserted = 0
    conv_skipped = 0
    msg_inserted = 0

    for convo in CONVERSATIONS:
        lead_id = lead_ids.get(convo["lead_email"])

        # Check if conversation already exists for this lead
        existing_conv = conn.execute(
            text("""
                SELECT id FROM sms_conversations
                WHERE organization_id = :org_id
                  AND phone_number = :phone
                LIMIT 1
            """),
            {"org_id": org_id, "phone": convo["lead_phone"]},
        ).fetchone()

        if existing_conv:
            conv_skipped += 1
            continue

        # Timestamps for conversation
        conv_start = days_ago(convo["days_ago_start"])
        last_msg_offset = max(m["offset_hours"] for m in convo["messages"])
        last_msg_at = conv_start + timedelta(hours=last_msg_offset)

        # Insert conversation
        result = conn.execute(
            text("""
                INSERT INTO sms_conversations
                    (organization_id, phone_number, user_id, lead_id,
                     contact_name, is_active, ai_enabled,
                     last_message_at, message_count, created_at, updated_at)
                VALUES
                    (:org_id, :phone, :user_id, :lead_id,
                     :contact_name, :is_active, :ai_enabled,
                     :last_msg_at, :msg_count, :now, :now)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "phone": convo["lead_phone"],
                "user_id": convo["user_id"],
                "lead_id": lead_id,
                "contact_name": convo["lead_name"],
                "is_active": True,
                "ai_enabled": True,
                "last_msg_at": last_msg_at,
                "msg_count": len(convo["messages"]),
                "now": conv_start,
            },
        )
        conv_id = result.fetchone()[0]
        conv_inserted += 1

        # Insert messages
        for i, msg in enumerate(convo["messages"]):
            msg_at = conv_start + timedelta(hours=msg["offset_hours"])
            from_num = convo["lead_phone"] if msg["dir"] == "inbound" else TELNYX_NUMBER
            to_num = TELNYX_NUMBER if msg["dir"] == "inbound" else convo["lead_phone"]
            status = "read" if msg["dir"] == "inbound" else "delivered"

            conn.execute(
                text("""
                    INSERT INTO sms_messages
                        (organization_id, user_id, lead_id, conversation_id,
                         to_number, from_number, message, direction, status,
                         ai_generated, delivery_status, created_at)
                    VALUES
                        (:org_id, :user_id, :lead_id, :conv_id,
                         :to_num, :from_num, :message, :direction, :status,
                         :ai_gen, :delivery_status, :created_at)
                """),
                {
                    "org_id": org_id,
                    "user_id": convo["user_id"],
                    "lead_id": lead_id,
                    "conv_id": conv_id,
                    "to_num": to_num,
                    "from_num": from_num,
                    "message": msg["text"],
                    "direction": msg["dir"],
                    "status": status,
                    "ai_gen": msg["ai"],
                    "delivery_status": "delivered" if msg["dir"] == "outbound" else "received",
                    "created_at": msg_at,
                },
            )
            msg_inserted += 1

    conn.commit()
    print(f"✅ Seeded {conv_inserted} SMS conversations, {msg_inserted} messages ({conv_skipped} conversations already existed)")


def seed_call_intelligence(conn, org_id, user_ids, lead_ids):
    """Create demo VapiCall records with AI analysis (8 calls)."""

    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")
    manager_id = user_ids.get("manager")

    CALLS = [
        # --- Inbound (AI receptionist) ---
        {
            "vapi_call_id": "demo-call-001",
            "phone_number": "+18432110103",
            "caller_name": "Derek Hollis",
            "direction": "inbound",
            "days_ago": 6,
            "hour": 10,
            "duration": 247,
            "lead_email": "derek.hollis@yahoo.com",
            "sentiment": "positive",
            "intent": "inquiry",
            "ci_extractions_count": 4,
            "ci_tasks_created": 2,
            "transcript": (
                "Aria: Thank you for calling Summit Home Loans! I'm Aria, your AI assistant. How can I help you today?\n"
                "Caller: Hi, my name is Derek Hollis. I'm looking to get pre-approved for a home purchase.\n"
                "Aria: Wonderful, Derek! Congratulations on taking that step. I'd love to help. Are you looking to buy in the Charleston area?\n"
                "Caller: Yes, primarily around the historic district. We have our eye on a few properties in the $550,000 range.\n"
                "Aria: That's a beautiful area! Just to get a general sense — do you have an idea of your credit score range and annual household income?\n"
                "Caller: My score is around 760 and I make about $145,000 a year.\n"
                "Aria: You sound like an excellent candidate for a conventional loan! I'd love to connect you with Sarah Chen, one of our senior loan officers. She has deep experience with high-end Charleston properties. Are you available for a 30-minute call later this week?\n"
                "Caller: Thursday morning works for me.\n"
                "Aria: Perfect! I'm booking you with Sarah on Thursday at 11 AM. You'll receive a confirmation text and calendar invite shortly.\n"
                "Caller: Great, thanks!\n"
                "Aria: My pleasure, Derek. Is there anything else I can help with today?\n"
                "Caller: No, that's all. Thanks so much.\n"
                "Aria: You're welcome! We look forward to helping you find your dream home. Have a wonderful day!"
            ),
            "summary": (
                "Inbound inquiry from Derek Hollis, a high-credit (760) buyer with $145K income seeking pre-approval for a $550K purchase "
                "in Charleston's historic district. AI receptionist Aria captured key qualification data and booked a consultation with "
                "Sarah Chen for Thursday at 11 AM. Task created: follow up with pre-approval checklist and income doc request."
            ),
        },
        {
            "vapi_call_id": "demo-call-002",
            "phone_number": "+18432110109",
            "caller_name": "Kevin Albright",
            "direction": "inbound",
            "days_ago": 4,
            "hour": 14,
            "duration": 183,
            "lead_email": "kevin.albright@gmail.com",
            "sentiment": "positive",
            "intent": "follow_up",
            "ci_extractions_count": 3,
            "ci_tasks_created": 1,
            "transcript": (
                "Aria: Thank you for calling Summit Home Loans! I'm Aria. How can I assist you?\n"
                "Caller: Hi, I'm Kevin Albright. I wanted to check on the status of my loan — it's with Marcus Johnson.\n"
                "Aria: Hi Kevin! Let me pull up your file. Your loan SHL-2026-0006 is currently in Underwriting. It was submitted 7 days ago.\n"
                "Caller: How long does underwriting usually take?\n"
                "Aria: For a conventional loan with a strong profile like yours, typically 5-7 business days. You're right on track.\n"
                "Caller: Any conditions yet?\n"
                "Aria: No conditions have been flagged as of today. Marcus will call you as soon as the underwriter's decision comes in.\n"
                "Caller: OK great. I also wanted to ask about bringing my brother as a co-borrower. Is it too late?\n"
                "Aria: That's a great question — it could affect the timeline. I'm going to flag this for Marcus and have him call you back today. Is your cell phone the best number?\n"
                "Caller: Yes, same number I'm calling from.\n"
                "Aria: Perfect. I've sent Marcus a priority message. Anything else I can help with?\n"
                "Caller: No, that's it. Thanks!\n"
                "Aria: My pleasure! Have a great afternoon, Kevin."
            ),
            "summary": (
                "Kevin Albright called to check on his underwriting status for loan SHL-2026-0006. AI confirmed loan is in underwriting "
                "with no conditions flagged at day 7. Kevin raised a potential co-borrower addition (his brother) — a time-sensitive "
                "question that could affect the loan structure. AI created a priority task for Marcus Johnson to call back same day."
            ),
        },
        {
            "vapi_call_id": "demo-call-003",
            "phone_number": "+18432110116",
            "caller_name": "Aisha Coleman",
            "direction": "inbound",
            "days_ago": 2,
            "hour": 11,
            "duration": 312,
            "lead_email": "aisha.coleman@gmail.com",
            "sentiment": "positive",
            "intent": "inquiry",
            "ci_extractions_count": 5,
            "ci_tasks_created": 3,
            "transcript": (
                "Aria: Thank you for calling Summit Home Loans! I'm Aria. How can I help?\n"
                "Caller: Hi, I'm Aisha Coleman. I'm under contract on a new construction home and I wanted to know about rate lock options.\n"
                "Aria: Hi Aisha! Congratulations on being under contract! New construction rate locks work a bit differently. How far out is your projected closing?\n"
                "Caller: The builder says 60 days, but it could be 45.\n"
                "Aria: Got it. For that window, you'd typically want a 60-day lock, which is available but carries a slight premium over a standard 30-day lock. Current rates for your loan type are around 6.875% on a 60-day lock.\n"
                "Caller: What about a float-to-lock option? My builder mentioned that.\n"
                "Aria: Great question! A float-down lock lets you start locked in and drop if rates fall by a certain threshold — usually 0.25%. I want to make sure Sarah gives you accurate numbers on that. Want me to schedule a call?\n"
                "Caller: Yes, please.\n"
                "Aria: I'll book Sarah for tomorrow at 2 PM to walk you through all rate lock options. I'll also send you a rate lock comparison document tonight.\n"
                "Caller: Also, the builder is asking for a copy of my pre-approval letter. Can you resend it?\n"
                "Aria: Absolutely. I'll have Sarah email the updated letter to you within the hour.\n"
                "Caller: Perfect. You've been so helpful!\n"
                "Aria: My pleasure, Aisha! Looking forward to getting you to the closing table."
            ),
            "summary": (
                "Aisha Coleman called with questions about rate lock options for her new construction purchase (60-day projected close). "
                "She asked about float-to-lock options and requested a pre-approval letter resend. AI scheduled a rate lock strategy call "
                "with Sarah for tomorrow at 2 PM, created tasks for: rate lock comparison doc, pre-approval letter resend, and follow-up "
                "after builder confirms closing window."
            ),
        },
        # --- Outbound (LO follow-up) ---
        {
            "vapi_call_id": "demo-call-004",
            "phone_number": "+18432110106",
            "caller_name": "Brianna Okafor",
            "direction": "outbound",
            "days_ago": 3,
            "hour": 10,
            "duration": 268,
            "lead_email": "brianna.okafor@gmail.com",
            "sentiment": "positive",
            "intent": "follow_up",
            "ci_extractions_count": 3,
            "ci_tasks_created": 2,
            "transcript": (
                "Sarah Chen: Hi Brianna, this is Sarah Chen from Summit Home Loans. Is now a good time?\n"
                "Brianna: Yes! I was just going to call you.\n"
                "Sarah Chen: Great minds! I'm calling because your loan received a Conditional Approval from underwriting — congratulations!\n"
                "Brianna: Oh wow, that's amazing news!\n"
                "Sarah Chen: It really is. We just need two items to get to Clear to Close: a letter of explanation for your 2022 employment gap, and one more month of bank statements.\n"
                "Brianna: How long of a letter?\n"
                "Sarah Chen: Just a few sentences. I'll send you a template that takes about 5 minutes to fill out.\n"
                "Brianna: That's easy. And the bank statement — which account?\n"
                "Sarah Chen: Your Chase checking account ending in 4821. Just the most recent statement.\n"
                "Brianna: I can have both to you by tomorrow.\n"
                "Sarah Chen: That would be perfect! With that turnaround, you'll likely have your CTC in 3-4 days and we can target your original closing date.\n"
                "Brianna: You have no idea how relieved I am. I've been so nervous about this.\n"
                "Sarah Chen: This is completely normal — you're in great shape. I'll send that template right now and text you a reminder tomorrow morning.\n"
                "Brianna: Thank you so much, Sarah. You're the best!\n"
                "Sarah Chen: You're going to be in your new home before you know it. Talk soon!"
            ),
            "summary": (
                "Sarah Chen called Brianna Okafor to deliver Conditional Approval news. Conditions are: letter of explanation for 2022 "
                "employment gap and one month of Chase checking statements (account ending 4821). Brianna committed to providing both "
                "by tomorrow. Tasks created: send letter of explanation template to Brianna, set follow-up reminder for tomorrow morning. "
                "Closing timeline remains on track."
            ),
        },
        {
            "vapi_call_id": "demo-call-005",
            "phone_number": "+18432110107",
            "caller_name": "Nathan Prescott",
            "direction": "outbound",
            "days_ago": 10,
            "hour": 13,
            "duration": 195,
            "lead_email": "nathan.prescott@hotmail.com",
            "sentiment": "neutral",
            "intent": "follow_up",
            "ci_extractions_count": 2,
            "ci_tasks_created": 1,
            "transcript": (
                "Marcus Johnson: Hi Nathan, this is Marcus Johnson from Summit Home Loans. How are you doing?\n"
                "Nathan: Good, thanks.\n"
                "Marcus Johnson: I wanted to follow up on your pre-qualification — it's been about 3 weeks and I wanted to check in on your property search.\n"
                "Nathan: Yeah, we've seen a few condos but nothing's clicked yet. The HOA fees are killing the DTI.\n"
                "Marcus Johnson: That's a really common concern with FHA condo loans. The good news is HOA fees are actually factored into the debt-to-income calculation up front, so there are no surprises. Have you seen any that felt close?\n"
                "Nathan: There's one on Rivers Ave at $279,000. HOA is $240 a month.\n"
                "Marcus Johnson: Let me run those numbers real quick... At your income level with FHA, a $279K price and $240 HOA gets you to about 44% DTI — that's right at the FHA threshold. It's workable, especially if you can get seller concessions on closing costs.\n"
                "Nathan: Interesting. How fast could you get a pre-approval letter if we wanted to make an offer?\n"
                "Marcus Johnson: I can have a property-specific letter to you within 2 hours of you saying go. Want to schedule a quick call when you're ready to move forward?\n"
                "Nathan: Yeah, I'll call you when we decide.\n"
                "Marcus Johnson: Perfect. I'll send you a breakdown on that specific property by email today. Good talking to you, Nathan."
            ),
            "summary": (
                "Marcus Johnson followed up with Nathan Prescott who has been actively touring FHA-eligible condos. Nathan identified a "
                "specific property at $279K with $240/month HOA — Marcus calculated a 44% DTI which is at the FHA limit but workable "
                "with seller concessions. Task created: send property-specific DTI analysis email for the Rivers Ave unit. Nathan will "
                "call when ready to make an offer."
            ),
        },
        {
            "vapi_call_id": "demo-call-006",
            "phone_number": "+18432110114",
            "caller_name": "Tanya Morrison",
            "direction": "outbound",
            "days_ago": 5,
            "hour": 15,
            "duration": 221,
            "lead_email": "tanya.morrison@gmail.com",
            "sentiment": "positive",
            "intent": "follow_up",
            "ci_extractions_count": 3,
            "ci_tasks_created": 2,
            "transcript": (
                "Sarah Chen: Hi Tanya! Sarah Chen here. Got a minute?\n"
                "Tanya: Of course! I was hoping you'd call.\n"
                "Sarah Chen: I wanted to let you know that Emily has started processing your file. Everything looks really solid. The one item we're still waiting on is your 2022 tax returns.\n"
                "Tanya: I know, I know. I keep forgetting to pull them. Can I get them from the IRS directly?\n"
                "Sarah Chen: Yes, the fastest way is the IRS Get Transcript portal — it takes about 10 minutes and you can download a PDF. I'll text you the link right now.\n"
                "Tanya: Perfect. I'll do it tonight.\n"
                "Sarah Chen: Wonderful! Once we have that, Emily can complete processing and submit to underwriting. That keeps you on track for your 55-day close.\n"
                "Tanya: I'm actually getting nervous — this is my first house!\n"
                "Sarah Chen: That's so exciting! First-time buyer nerves are totally normal. I'm with you every step of the way. The hard part is behind you.\n"
                "Tanya: Thank you, Sarah. You've been so helpful.\n"
                "Sarah Chen: My job is to make this easy for you! I'll text the IRS link now. Call me if you have any questions tonight.\n"
                "Tanya: Will do. Talk soon!"
            ),
            "summary": (
                "Sarah Chen followed up with first-time buyer Tanya Morrison regarding missing 2022 tax returns blocking processing. "
                "Tanya agreed to retrieve them tonight via IRS Get Transcript portal. Sarah committed to texting the IRS portal link "
                "immediately. Tasks created: send IRS transcript link via SMS, check-in tomorrow if returns not received. File on "
                "track for 55-day close pending this single document."
            ),
        },
        # --- Voicemail drops (outbound, short) ---
        {
            "vapi_call_id": "demo-call-007",
            "phone_number": "+18432110117",
            "caller_name": "Gregory Tatum",
            "direction": "outbound",
            "days_ago": 14,
            "hour": 10,
            "duration": 28,
            "lead_email": "gregory.tatum@yahoo.com",
            "sentiment": "neutral",
            "intent": "follow_up",
            "ci_extractions_count": 0,
            "ci_tasks_created": 1,
            "transcript": (
                "[Voicemail Drop]\n"
                "Hi Gregory, this is Marcus Johnson from Summit Home Loans. I wanted to check in and see how your savings plan is going. "
                "Last time we spoke you were targeting spring for your purchase — that window is coming up fast! "
                "Give me a call at your convenience and let's see if we can get a game plan together. "
                "My number is 843-100-5003. Have a great day!"
            ),
            "summary": (
                "Voicemail drop to Gregory Tatum, a long-term nurture lead who is saving for a down payment with a spring purchase target. "
                "Call duration indicates message went to voicemail as intended. Task created: follow-up SMS in 3 days if no callback."
            ),
        },
        {
            "vapi_call_id": "demo-call-008",
            "phone_number": "+18432110118",
            "caller_name": "Courtney Langford",
            "direction": "outbound",
            "days_ago": 20,
            "hour": 11,
            "duration": 31,
            "lead_email": "courtney.langford@gmail.com",
            "sentiment": "neutral",
            "intent": "follow_up",
            "ci_extractions_count": 0,
            "ci_tasks_created": 1,
            "transcript": (
                "[Voicemail Drop]\n"
                "Hi Courtney, this is Sarah Chen from Summit Home Loans. I'm reaching out because your lease renewal is coming up and I wanted "
                "to see where you are on the credit improvement plan we discussed. If your score has crossed 640, we may be able to get you "
                "pre-qualified sooner than expected! Give me a call at 843-100-5002 and let's take a look. Looking forward to hearing from you!"
            ),
            "summary": (
                "Voicemail drop to Courtney Langford, a credit repair lead with a lease ending in approximately 9 months. Sarah prompted "
                "Courtney to check in on her credit score progress — a 640 threshold would enable pre-qualification. Short duration "
                "confirms voicemail delivery. Task created: re-attempt call in 2 weeks if no response."
            ),
        },
    ]

    inserted = 0
    skipped = 0

    for call in CALLS:
        if exists(conn, "vapi_calls", "vapi_call_id", call["vapi_call_id"]):
            skipped += 1
            continue

        lead_id = lead_ids.get(call["lead_email"])
        started_at = days_ago(call["days_ago"]).replace(
            hour=call["hour"], minute=0, second=0, microsecond=0
        )
        ended_at = started_at + timedelta(seconds=call["duration"])

        conn.execute(
            text("""
                INSERT INTO vapi_calls
                    (organization_id, vapi_call_id, phone_number, caller_name,
                     direction, status, started_at, ended_at, duration,
                     transcript, summary, sentiment, intent,
                     lead_id, ci_processed, ci_extractions_count, ci_tasks_created,
                     created_at, updated_at)
                VALUES
                    (:org_id, :vapi_call_id, :phone, :caller_name,
                     :direction, :status, :started_at, :ended_at, :duration,
                     :transcript, :summary, :sentiment, :intent,
                     :lead_id, :ci_processed, :ci_extractions, :ci_tasks,
                     :now, :now)
            """),
            {
                "org_id": org_id,
                "vapi_call_id": call["vapi_call_id"],
                "phone": call["phone_number"],
                "caller_name": call["caller_name"],
                "direction": call["direction"],
                "status": "completed",
                "started_at": started_at,
                "ended_at": ended_at,
                "duration": call["duration"],
                "transcript": call["transcript"],
                "summary": call["summary"],
                "sentiment": call["sentiment"],
                "intent": call["intent"],
                "lead_id": lead_id,
                "ci_processed": True,
                "ci_extractions": call["ci_extractions_count"],
                "ci_tasks": call["ci_tasks_created"],
                "now": NOW,
            },
        )
        inserted += 1

    conn.commit()
    print(f"✅ Seeded {inserted} call intelligence records ({skipped} already existed)")


def seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids):
    """Create activity log entries and stage history for leads and loans."""

    manager_id = user_ids.get("manager")
    lo_sarah_id = user_ids.get("lo_sarah")
    lo_marcus_id = user_ids.get("lo_marcus")
    processor_id = user_ids.get("processor")
    uw_rachel_id = user_ids.get("uw_rachel")
    uw_james_id = user_ids.get("uw_james")

    # ------------------------------------------------------------------
    # Lead activity specs
    # (email, stage, days_ago, owner_id, activities list)
    # activities: list of (type, content, offset_days_from_created, duration, sentiment)
    # ------------------------------------------------------------------
    LEAD_ACTIVITIES = [
        # --- NEW leads (1-2 activities each) ---
        {
            "email": "tyler.barnes@gmail.com",
            "stage": "New",
            "days_ago": 2,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",  "Inbound inquiry from Zillow — discussed purchase timeline and rate expectations. Left message about pre-approval process.", 0, "12 min", "neutral"),
                ("Note",  "First-time buyer previously pre-qualified with another lender. Wants rate comparison. AI score 72. Follow up with discovery call.", 0, None, "neutral"),
            ],
        },
        {
            "email": "priya.nair@outlook.com",
            "stage": "New",
            "days_ago": 5,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",  "Initial call — responded to Facebook FHA ad. Asking about minimum down payment requirements. Confirmed 3.5% FHA option.", 0, "8 min", "positive"),
                ("Email", "Sent FHA program overview PDF with down payment breakdown and credit score requirements.", 1, None, "positive"),
            ],
        },
        {
            "email": "derek.hollis@yahoo.com",
            "stage": "New",
            "days_ago": 1,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Note",  "High-priority website lead (AI score 88). Relocating for work from Atlanta. Used rate calculator — strong purchase intent. Schedule discovery call today.", 0, None, "positive"),
                ("SMS",   "Hi Derek — this is Sarah Chen at Summit Home Loans. I saw your inquiry on our website. I'd love to walk you through your options. When works for a quick call?", 0, None, "positive"),
            ],
        },
        # --- ATTEMPTED CONTACT leads (2-3 activities) ---
        {
            "email": "monique.duval@gmail.com",
            "stage": "Attempted Contact",
            "days_ago": 8,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",  "Left voicemail #1 — introduced Summit Home Loans and FHA programs. No callback.", 0, "2 min", "neutral"),
                ("Call",  "Left voicemail #2 — referenced Realtor.com listing inquiry. Offered free pre-qualification.", 2, "2 min", "neutral"),
                ("SMS",   "Hi Monique — Marcus Johnson from Summit Home Loans. Reaching out re: the home on Ashley Ave. Happy to help with financing. Reply to connect!", 3, None, "neutral"),
            ],
        },
        {
            "email": "carter.webb@icloud.com",
            "stage": "Attempted Contact",
            "days_ago": 11,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",  "Cold outreach from expired listing database — Carter showed interest in rate info but hasn't scheduled a call yet.", 0, "5 min", "neutral"),
                ("Call",  "Follow-up call — no answer. Left voicemail referencing our pre-approval process.", 3, "2 min", "neutral"),
                ("Email", "Sent calendar link for 15-min discovery call. Subject: 'Get Your Rate — 5 Minutes, No Obligation'.", 4, None, "neutral"),
            ],
        },
        # --- PROSPECT leads (3-5 activities) ---
        {
            "email": "brianna.okafor@gmail.com",
            "stage": "Prospect",
            "days_ago": 18,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Initial contact — referral from Jean Holloway at RE/MAX. Warm introduction. Discussed purchase goals and 60-day timeline.", 0, "18 min", "positive"),
                ("Email",  "Sent pre-approval checklist with income document requirements and credit score guidance.", 2, None, "positive"),
                ("Meeting","Discovery Zoom call — reviewed income ($112K), assets, and purchase target ($390K–$445K). Excellent profile for conventional 10% down.", 4, "28 min", "positive"),
                ("Note",   "Referred by realtor partner Jean Holloway. High-quality lead — ready to move. Begin pre-qual process.", 4, None, "positive"),
            ],
        },
        {
            "email": "nathan.prescott@hotmail.com",
            "stage": "Prospect",
            "days_ago": 22,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Initial Zillow lead call — browsing condos in North Charleston. Concerned about HOA impact on DTI.", 0, "14 min", "neutral"),
                ("Email",  "Sent FHA condo approval process guide and HOA add-back explanation.", 2, None, "neutral"),
                ("Call",   "Follow-up call — discussed condo HOA dues and impact on qualifying payment. Nathan still researching communities.", 5, "11 min", "neutral"),
            ],
        },
        {
            "email": "simone.arceneaux@gmail.com",
            "stage": "Prospect",
            "days_ago": 27,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Website lead — executive relocating from Atlanta. Currently has credit union pre-approval at 7.1%. Wants rate comparison.", 0, "22 min", "positive"),
                ("Email",  "Sent side-by-side rate comparison analysis vs credit union offer. Summit savings: ~$87/month at 6.500%.", 2, None, "positive"),
                ("Meeting","Rate strategy call — walked through conventional 30yr fixed at 6.500% vs ARM options. Simone prefers fixed.", 4, "35 min", "positive"),
                ("Note",   "High-value prospect — $475K loan target, relocating for senior exec role. Closing within 45 days. Rate lock ready.", 5, None, "positive"),
            ],
        },
        # --- PRE-QUALIFIED leads (3-5 activities) ---
        {
            "email": "kevin.albright@gmail.com",
            "stage": "Pre-Qualified",
            "days_ago": 38,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Referral introduction from realtor partner. Kevin searching for single-family in Park Circle area.", 0, "16 min", "positive"),
                ("Email",  "Sent income doc checklist — W-2, paystubs, bank statements requested.", 3, None, "positive"),
                ("Document","Received 2024 W-2, two recent paystubs, and 90-day bank statements. All documents complete.", 7, None, "positive"),
                ("Meeting","Pre-qualification review call — $335K pre-qual approved. DTI at 33%. Letter issued.", 10, "25 min", "positive"),
                ("Call",   "Check-in call — Kevin actively touring Park Circle. No offer yet but expects to find property in 2-3 weeks.", 20, "9 min", "positive"),
            ],
        },
        {
            "email": "jasmine.winters@yahoo.com",
            "stage": "Pre-Qualified",
            "days_ago": 45,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Zillow inquiry — Jasmine looking at townhomes in Wescott area. First-time buyer.", 0, "13 min", "positive"),
                ("Email",  "Sent pre-qual income doc checklist. Highlighted conventional loan with 10% down option.", 2, None, "positive"),
                ("Document","Received all income docs — 2024 W-2, pay stubs, 60-day bank statements.", 8, None, "positive"),
                ("Meeting","Pre-qualification call — $285K approved at 37% DTI. Pre-qual letter issued.", 12, "20 min", "positive"),
                ("Note",   "Pre-qual letter expires in 30 days. Need to follow up on property search progress. Wescott townhomes selling quickly.", 20, None, "positive"),
            ],
        },
        {
            "email": "elijah.fontaine@gmail.com",
            "stage": "Pre-Qualified",
            "days_ago": 52,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Facebook lead — Elijah looking at FHA purchase in Summerville area. DTI concern with spouse income.", 0, "17 min", "neutral"),
                ("Email",  "Sent FHA qualification requirements and request for spouse's income documentation.", 3, None, "neutral"),
                ("Call",   "Follow-up — spouse W-2 not yet available. Elijah working on gathering docs.", 10, "8 min", "neutral"),
                ("Note",   "Conditional pre-qual pending spouse income verification. W-2 and pay stubs needed. DTI at 42% — borderline.", 15, None, "neutral"),
            ],
        },
        # --- PRE-APPROVED leads (5-7 activities) ---
        {
            "email": "vanessa.hartley@gmail.com",
            "stage": "Pre-Approved",
            "days_ago": 55,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Referral from Bob Walsh at Sullivan's Realty — Vanessa needs pre-approval letter fast. Under contract.", 0, "20 min", "positive"),
                ("Email",  "Sent income doc checklist — priority request.", 1, None, "positive"),
                ("Document","Received complete doc package: W-2, paystubs, bank statements, tax returns. Quick turnaround.", 3, None, "positive"),
                ("Meeting","Pre-approval underwriting review — $450K approved, DTI 28%, credit 748. Full pre-approval issued.", 5, "30 min", "positive"),
                ("Call",   "Confirmed pre-approval and reviewed rate lock strategy. Loan amount locked at 6.750% for 45 days.", 8, "12 min", "positive"),
                ("Email",  "Pre-approval letter emailed to borrower and Bob Walsh at Sullivan's Realty. Appraisal ordered.", 10, None, "positive"),
            ],
        },
        {
            "email": "marcus.delacroix@icloud.com",
            "stage": "Pre-Approved",
            "days_ago": 68,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Website lead — Marcus actively touring homes, second offer pending on James Island property.", 0, "18 min", "positive"),
                ("Email",  "Sent pre-approval income doc checklist. Marcus has strong financials.", 2, None, "positive"),
                ("Document","Received full income package — W-2, pay stubs, bank statements, and 2023 tax returns.", 5, None, "positive"),
                ("Meeting","Pre-approval review — $380K approved at 32% DTI. Rate quoted at 6.999%.", 8, "25 min", "positive"),
                ("Call",   "Discussed rate lock timing with Marcus — waiting for offer acceptance before locking.", 12, "10 min", "positive"),
                ("Note",   "Second offer outcome unknown. Marcus will call when offer is accepted. Pre-approval letter valid 60 days.", 15, None, "positive"),
            ],
        },
        # --- APPLICATION leads (5-8 activities) ---
        {
            "email": "tanya.morrison@gmail.com",
            "stage": "Application",
            "days_ago": 65,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Realtor.com lead — Tanya found home on Wentworth St. Ready to apply. Under contract.", 0, "22 min", "positive"),
                ("Email",  "Sent full application link and income doc checklist.", 1, None, "positive"),
                ("Document","Received W-2, paystubs, bank statements. Missing 2022 tax return — follow up scheduled.", 5, None, "positive"),
                ("Meeting","Initial application review — 80% complete. 2022 tax transcripts still needed.", 8, "30 min", "positive"),
                ("Call",   "Follow-up on missing tax transcripts. Tanya ordered IRS transcript. Should arrive in 3 days.", 10, "9 min", "positive"),
                ("SMS",    "Hi Tanya — just checking in on the IRS transcript. Any update? Happy to order directly if easier!", 14, None, "positive"),
                ("Note",   "Application at 80%. Missing 2022 tax transcripts causing delay. Rate lock on SHL-2026-0001 expires soon.", 15, None, "neutral"),
            ],
        },
        {
            "email": "roberto.sandoval@hotmail.com",
            "stage": "Application",
            "days_ago": 75,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Referral lead — Roberto ready to buy townhome in North Charleston. FHA loan requested.", 0, "19 min", "positive"),
                ("Email",  "Sent FHA application link and doc checklist.", 1, None, "positive"),
                ("Document","Received most income docs. Still missing 2024 W-2 from employer.", 7, None, "positive"),
                ("Meeting","Application review meeting — full app submitted except missing W-2. FHA case number requested.", 12, "28 min", "positive"),
                ("Call",   "Followed up on missing W-2 — Roberto's employer needs 5 days to process. Appraisal scheduling initiated.", 15, "10 min", "positive"),
                ("Email",  "Title search ordered. Appraisal scheduled for next week.", 18, None, "positive"),
                ("Note",   "FHA case number requested. Appraisal scheduled. Waiting on W-2. Emily Park tracking doc status.", 20, None, "positive"),
            ],
        },
        {
            "email": "aisha.coleman@gmail.com",
            "stage": "Application",
            "days_ago": 82,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Zillow lead — Aisha under contract on new construction in Mount Pleasant. Builder close in 60 days.", 0, "24 min", "positive"),
                ("Email",  "Sent full application package. Highlighted 60-day lock option for new construction.", 2, None, "positive"),
                ("Document","Received complete doc package: W-2, tax returns, paystubs, bank statements, gift letter.", 6, None, "positive"),
                ("Meeting","Application review — excellent profile (score 91, DTI 27%). Lock rate when builder gives 45-day window.", 10, "35 min", "positive"),
                ("Call",   "Spoke with Aisha — builder confirmed 45-day close window. Initiating rate lock discussion.", 15, "12 min", "positive"),
                ("Email",  "Rate lock options sent — 45-day at 6.875% vs 60-day at 7.000%. Recommend 45-day to save.", 18, None, "positive"),
                ("Note",   "All docs received. File ready for UW submission. Builder close confirmed. Lock ASAP.", 20, None, "positive"),
            ],
        },
        # --- LONG-TERM NURTURE leads (2-3 activities) ---
        {
            "email": "gregory.tatum@yahoo.com",
            "stage": "Long-Term Nurture",
            "days_ago": 210,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Cold outreach — Gregory interested in buying but saving for down payment. Target: spring next year.", 0, "11 min", "neutral"),
                ("Email",  "Added to rate-watch drip campaign. Sent market update and savings goal worksheet.", 30, None, "neutral"),
                ("Call",   "Monthly check-in call — Gregory saving steadily. Credit score holding at 635. Not ready yet.", 90, "8 min", "neutral"),
            ],
        },
        {
            "email": "courtney.langford@gmail.com",
            "stage": "Long-Term Nurture",
            "days_ago": 260,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Website inquiry — Courtney renting, lease ends in 9 months. Credit needs work first.", 0, "13 min", "neutral"),
                ("Email",  "Sent credit improvement guide and 90-day credit review plan.", 5, None, "neutral"),
                ("Call",   "90-day credit check-in — score improved from 668 to 682. Still needs more time.", 90, "10 min", "neutral"),
            ],
        },
        {
            "email": "antoine.devereaux@gmail.com",
            "stage": "Long-Term Nurture",
            "days_ago": 340,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Referral from family member (existing client) — Antoine interested in USDA loan. Needs 12-month payment history.", 0, "14 min", "neutral"),
                ("Email",  "Sent USDA eligibility information and income limit guide for Summerville area.", 7, None, "neutral"),
                ("Call",   "Annual review call — payment history improving. USDA income limit updated — Antoine now qualifies. Follow up in 6 months.", 180, "12 min", "neutral"),
            ],
        },
        # --- CREDIT REPAIR leads (2-3 activities) ---
        {
            "email": "darnell.pace@gmail.com",
            "stage": "Credit Repair",
            "days_ago": 115,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Facebook lead — two medical collections dragging score below 580 FHA minimum. On 6-month repair plan.", 0, "16 min", "neutral"),
                ("Email",  "Sent credit repair guide and referral to credit counseling partner.", 5, None, "neutral"),
                ("Call",   "90-day check-in — one collection paid, one disputed. Score now 594. Two months from FHA eligibility.", 60, "10 min", "neutral"),
            ],
        },
        {
            "email": "shayla.dupree@yahoo.com",
            "stage": "Credit Repair",
            "days_ago": 155,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Realtor.com lead — recent late payment from job loss 8 months ago. Score improving from 595.", 0, "14 min", "positive"),
                ("Email",  "Sent credit recovery roadmap — dispute process, rapid rescore timeline, FHA threshold targets.", 7, None, "positive"),
                ("Note",   "Score trending up — check next month. If crosses 620, fast-track pre-qualification.", 60, None, "positive"),
            ],
        },
        # --- FUNDED leads (8-10 activities) ---
        {
            "email": "michelle.osei@gmail.com",
            "stage": "Funded",
            "days_ago": 102,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Referral from Bob Walsh — Michelle ready to buy in Mt Pleasant. Strong financials.", 0, "20 min", "positive"),
                ("Email",  "Sent pre-approval checklist. Priority file.", 1, None, "positive"),
                ("Document","Received complete income package — all docs in order.", 5, None, "positive"),
                ("Meeting","Pre-approval underwriting — $415K approved. DTI 30%, credit 752.", 8, "30 min", "positive"),
                ("Call",   "Discussed rate lock — 7.125% for 30 days. Lock executed.", 15, "12 min", "positive"),
                ("Document","Appraisal received — $478K, above purchase price. Clean report.", 25, None, "positive"),
                ("Call",   "UW conditions cleared — CTC issued. Closing scheduled for 5 days out.", 40, "15 min", "positive"),
                ("Meeting","Closing prep — reviewed closing disclosure, wire instructions, and what to bring.", 45, "45 min", "positive"),
                ("Call",   "Post-closing call — Michelle closed on time. 5-star satisfaction. Introduced to two neighbors for referrals.", 50, "10 min", "positive"),
                ("Note",   "Funded! Closed on time. Client satisfaction: 5 stars. Added to MUM portfolio. Referral pipeline active.", 52, None, "positive"),
            ],
        },
        {
            "email": "james.beaumont@icloud.com",
            "stage": "Funded",
            "days_ago": 160,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Website lead — James looking at single-family in Mt Pleasant. Had VA loan but switching to conventional.", 0, "18 min", "positive"),
                ("Email",  "Sent conventional loan doc checklist and program comparison vs VA.", 2, None, "positive"),
                ("Document","Full income package received.", 6, None, "positive"),
                ("Meeting","Pre-approval review — $360K approved. James prefers conventional due to appraisal flexibility.", 10, "25 min", "positive"),
                ("Call",   "Rate lock discussion — 7.250% for 30 days. Lock executed after offer accepted.", 18, "11 min", "positive"),
                ("Document","Appraisal came in strong at $418K vs $415K purchase. No value issues.", 28, None, "positive"),
                ("Call",   "All UW conditions cleared. CTC issued. Closing set for next week.", 45, "14 min", "positive"),
                ("Meeting","Closing prep meeting — all docs signed and wire instructions confirmed.", 52, "40 min", "positive"),
                ("Call",   "Post-closing congratulations call. James thrilled — VA loan conversion paid off.", 55, "9 min", "positive"),
                ("Note",   "Funded! VA loan converted to conventional at last minute — appraisal came in strong. Scheduled 6-month rate review.", 58, None, "positive"),
            ],
        },
        # --- DOES NOT QUALIFY / WITHDRAWN (1-2 activities each) ---
        {
            "email": "roderick.fulton@gmail.com",
            "stage": "Does Not Qualify",
            "days_ago": 120,
            "owner_id": lo_marcus_id,
            "activities": [
                ("Call",   "Cold outreach — DTI too high (52%), credit below FHA minimum (558), self-employed 1099. Cannot qualify at this time.", 0, "15 min", "negative"),
                ("Email",  "Sent detailed explanation of qualification gaps and 18-month action plan: credit improvement, debt paydown, stable income documentation.", 2, None, "neutral"),
            ],
        },
        {
            "email": "lydia.whitmore@outlook.com",
            "stage": "Withdrawn",
            "days_ago": 60,
            "owner_id": lo_sarah_id,
            "activities": [
                ("Call",   "Zillow lead — Lydia qualified and pre-approved but spouse changed jobs. Decided to stay in current home.", 0, "16 min", "neutral"),
                ("Note",   "Lead withdrawn — spouse job change made move impractical. Set 12-month re-engagement reminder.", 2, None, "neutral"),
            ],
        },
    ]

    act_inserted = 0
    act_skipped = 0

    for lead_spec in LEAD_ACTIVITIES:
        lead_id = lead_ids.get(lead_spec["email"])
        if not lead_id:
            continue

        created_base = days_ago(lead_spec["days_ago"])
        owner_id = lead_spec["owner_id"]

        for (act_type, content, offset_days, duration, sentiment) in lead_spec["activities"]:
            act_ts = created_base + timedelta(days=offset_days)

            # Idempotency: check by lead_id + type + truncated content prefix
            content_prefix = content[:80]
            existing = conn.execute(
                text("""
                    SELECT id FROM activities
                    WHERE lead_id = :lead_id
                      AND type = :type
                      AND LEFT(content, 80) = :prefix
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"lead_id": lead_id, "type": act_type, "prefix": content_prefix, "org_id": org_id},
            ).fetchone()
            if existing:
                act_skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO activities
                        (organization_id, type, content, lead_id, user_id,
                         duration, sentiment, created_at)
                    VALUES
                        (:org_id, :type, :content, :lead_id, :user_id,
                         :duration, :sentiment, :created_at)
                """),
                {
                    "org_id": org_id,
                    "type": act_type,
                    "content": content,
                    "lead_id": lead_id,
                    "user_id": owner_id,
                    "duration": duration,
                    "sentiment": sentiment,
                    "created_at": act_ts,
                },
            )
            act_inserted += 1

    conn.commit()

    # ------------------------------------------------------------------
    # Loan activities (2-5 per loan)
    # ------------------------------------------------------------------
    LOAN_ACTIVITY_SPECS = [
        # loan_number, days_ago, lo_id, [(type, content, offset_days)]
        ("SHL-2026-0001", 65, lo_sarah_id, [
            ("Document", "Full application package received — W-2, paystubs, bank statements. Missing 2022 tax transcripts.", 0),
            ("Call",     "Discussed loan structure and timeline with Tanya. Rate locked at 6.875% for 60 days.", 5),
            ("Note",     "Application 80% complete. Emily Park following up on 2022 tax return IRS transcript.", 12),
        ]),
        ("SHL-2026-0002", 75, lo_marcus_id, [
            ("Document", "FHA application submitted. W-2 still outstanding — employer processing delay noted.", 0),
            ("Call",     "FHA case number requested. Appraisal scheduling initiated for next week.", 8),
            ("Email",    "Title search ordered with Charleston Title Group. Confirmation #TL-4421.", 12),
            ("Note",     "Full app submitted. Awaiting W-2 and appraisal. Emily Park on processor duty.", 20),
        ]),
        ("SHL-2026-0003", 55, lo_sarah_id, [
            ("Document", "Rate locked at 6.750% — 45-day lock executed. Lock confirmation sent to borrower and agent.", 0),
            ("Document", "Appraisal ordered via AMC. Confirmation #AP-8801. ETA 7-10 business days.", 5),
            ("Call",     "Processing status update — all docs complete. File moved to UW queue.", 15),
        ]),
        ("SHL-2026-0004", 82, lo_sarah_id, [
            ("Document", "Complete income package received. Excellent file — ready for UW submission.", 0),
            ("Call",     "Rate lock strategy discussion — 45-day at 6.875%. Builder gave 45-day window.", 10),
            ("Email",    "Rate lock executed. Builder confirmed construction timeline. File submitted to UW.", 18),
            ("Note",     "Clean file. All docs in order. UW submission imminent.", 22),
        ]),
        ("SHL-2026-0005", 68, lo_marcus_id, [
            ("Document", "File submitted to underwriting. All income docs and appraisal complete.", 0),
            ("Call",     "Submission confirmation sent to Marcus Delacroix. UW turnaround expected 5-7 days.", 5),
            ("Note",     "Submitted to UW. Waiting on UW review. Marcus Delacroix second offer pending on another property.", 10),
        ]),
        ("SHL-2026-0006", 38, lo_marcus_id, [
            ("Document", "Appraisal returned — $390K vs $385K purchase price. LTV improves slightly.", 0),
            ("Call",     "Rachel Kim reviewing appraisal and income analysis. Identified one condition: HOA cert needed.", 7),
            ("Note",     "In UW review. Risk score 24. On track for CTC within 5 days pending HOA cert.", 12),
        ]),
        ("SHL-2026-0007", 45, lo_sarah_id, [
            ("Document", "Appraisal came in at $323K — tight vs $320K purchase. LTV acceptable at 88%.", 0),
            ("Call",     "James Mitchell (UW) flagged DTI concern. Requested updated pay stub for income verification.", 6),
            ("Note",     "At-risk file (risk score 38). DTI borderline at 37%. James Mitchell reviewing — CTC delayed pending VOE update.", 14),
        ]),
        ("SHL-2026-0008", 18, lo_sarah_id, [
            ("Call",     "Conditional approval issued by Rachel Kim. 3 conditions: HOI binder, title update, gift letter.", 0),
            ("Email",    "Conditions list sent to Brianna Okafor. HOI binder needed from State Farm agent.", 2),
            ("Document", "HOI binder received from State Farm. Two conditions remaining.", 4),
        ]),
        ("SHL-2026-0009", 52, lo_marcus_id, [
            ("Document", "All UW conditions cleared by James Mitchell. CTC issued.", 0),
            ("Call",     "Closing disclosure prepared and sent to Elijah Fontaine. 3-day waiting period started.", 2),
            ("Email",    "Closing scheduled with Charleston Title Group for 5 days from now. Wire instructions sent.", 3),
        ]),
        ("SHL-2026-0010", 27, lo_sarah_id, [
            ("Document", "Closing disclosure delivered — 3-day waiting period complete. Closing set for 2 days from now.", 0),
            ("Call",     "Final walkthrough confirmed with Simone Arceneaux. All docs signed and wire instructions verified.", 2),
            ("Note",     "Closing in 2 days. All conditions clear. Title confirmed. Funding imminent.", 3),
        ]),
        ("SHL-2026-0011", 102, lo_sarah_id, [
            ("Document", "Funded — wire confirmed from title. Loan disbursed to seller.", 0),
            ("Call",     "Post-close call with Michelle Osei. 5-star satisfaction. Sent referral request.", 5),
            ("Note",     "Funded on time. Michelle Osei added to MUM portfolio. 2 referrals in pipeline.", 7),
        ]),
        ("SHL-2026-0012", 160, lo_marcus_id, [
            ("Document", "Funded — conventional loan. VA conversion handled smoothly. Appraisal came in strong.", 0),
            ("Call",     "Post-close congratulations to James Beaumont. Scheduled 6-month rate review.", 8),
            ("Note",     "Funded. James Beaumont in MUM portfolio. 6-month rate check scheduled.", 10),
        ]),
        ("SHL-2026-0013", 210, lo_sarah_id, [
            ("Document", "Funded — first-time buyer success. Tyler Barnes closed conventional 10% down.", 0),
            ("Call",     "Post-close call — Tyler thrilled with his new home. Requested referral introduction email.", 5),
        ]),
        ("SHL-2026-0014", 265, lo_sarah_id, [
            ("Document", "Funded — Carter Webb conventional loan. Clean file and on-time close.", 0),
            ("Note",     "Carter Webb funded. Added to MUM portfolio. Monitoring for 1-year refi opportunity.", 5),
        ]),
        ("SHL-2026-0015", 330, lo_marcus_id, [
            ("Document", "Funded — Nathan Prescott FHA condo loan. HOA condo certification obtained.", 0),
            ("Call",     "Post-close call with Nathan. Happy with purchase. Condo community love it.", 5),
        ]),
    ]

    for (loan_number, loan_days_ago, lo_id, acts) in LOAN_ACTIVITY_SPECS:
        loan_id = loan_ids.get(loan_number)
        if not loan_id:
            continue

        base_ts = days_ago(loan_days_ago)
        for (act_type, content, offset_days) in acts:
            act_ts = base_ts + timedelta(days=offset_days)
            content_prefix = content[:80]

            existing = conn.execute(
                text("""
                    SELECT id FROM activities
                    WHERE loan_id = :loan_id
                      AND type = :type
                      AND LEFT(content, 80) = :prefix
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"loan_id": loan_id, "type": act_type, "prefix": content_prefix, "org_id": org_id},
            ).fetchone()
            if existing:
                act_skipped += 1
                continue

            conn.execute(
                text("""
                    INSERT INTO activities
                        (organization_id, type, content, loan_id, user_id,
                         duration, sentiment, created_at)
                    VALUES
                        (:org_id, :type, :content, :loan_id, :user_id,
                         :duration, :sentiment, :created_at)
                """),
                {
                    "org_id": org_id,
                    "type": act_type,
                    "content": content,
                    "loan_id": loan_id,
                    "user_id": lo_id,
                    "duration": None,
                    "sentiment": "positive",
                    "created_at": act_ts,
                },
            )
            act_inserted += 1

    conn.commit()
    print(f"✅ Seeded {act_inserted} activity records ({act_skipped} already existed)")

    # ------------------------------------------------------------------
    # Stage History
    # ------------------------------------------------------------------

    # Lead stage progression paths
    LEAD_STAGE_PATHS = {
        # email: (days_ago, owner_id, [stages in order])
        "tyler.barnes@gmail.com":      (2,   lo_sarah_id,   ["New"]),
        "priya.nair@outlook.com":      (5,   lo_marcus_id,  ["New"]),
        "derek.hollis@yahoo.com":      (1,   lo_sarah_id,   ["New"]),
        "monique.duval@gmail.com":     (8,   lo_marcus_id,  ["New", "Attempted Contact"]),
        "carter.webb@icloud.com":      (11,  lo_sarah_id,   ["New", "Attempted Contact"]),
        "brianna.okafor@gmail.com":    (18,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect"]),
        "nathan.prescott@hotmail.com": (22,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect"]),
        "simone.arceneaux@gmail.com":  (27,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect"]),
        "kevin.albright@gmail.com":    (38,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified"]),
        "jasmine.winters@yahoo.com":   (45,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified"]),
        "elijah.fontaine@gmail.com":   (52,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified"]),
        "vanessa.hartley@gmail.com":   (55,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved"]),
        "marcus.delacroix@icloud.com": (68,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved"]),
        "tanya.morrison@gmail.com":    (65,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application"]),
        "roberto.sandoval@hotmail.com":(75,  lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application"]),
        "aisha.coleman@gmail.com":     (82,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application"]),
        "gregory.tatum@yahoo.com":     (210, lo_marcus_id,  ["New", "Long-Term Nurture"]),
        "courtney.langford@gmail.com": (260, lo_sarah_id,   ["New", "Long-Term Nurture"]),
        "antoine.devereaux@gmail.com": (340, lo_marcus_id,  ["New", "Long-Term Nurture"]),
        "darnell.pace@gmail.com":      (115, lo_sarah_id,   ["New", "Credit Repair"]),
        "shayla.dupree@yahoo.com":     (155, lo_marcus_id,  ["New", "Credit Repair"]),
        "michelle.osei@gmail.com":     (102, lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application", "Funded"]),
        "james.beaumont@icloud.com":   (160, lo_marcus_id,  ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application", "Funded"]),
        "roderick.fulton@gmail.com":   (120, lo_marcus_id,  ["New", "Does Not Qualify"]),
        "lydia.whitmore@outlook.com":  (60,  lo_sarah_id,   ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Withdrawn"]),
    }

    sh_inserted = 0
    sh_skipped = 0

    for email, (total_days_ago, owner_id, stages) in LEAD_STAGE_PATHS.items():
        lead_id = lead_ids.get(email)
        if not lead_id:
            continue

        # Space stages evenly across the lead's age, 3-7 days apart
        n_transitions = len(stages)
        # Spread: allocate days across transitions
        if n_transitions == 1:
            # Only one stage: just the initial entry
            offsets = [0]
        else:
            step = max(3, total_days_ago // (n_transitions + 1))
            offsets = [total_days_ago - (i * step) for i in range(n_transitions)]
            # Clamp so last one is at least 1 day ago
            offsets = [max(1, o) for o in offsets]

        prev_stage = None
        prev_ts = None

        for idx, stage in enumerate(stages):
            changed_at = days_ago(offsets[idx])

            # Duration in previous stage (days)
            if prev_ts is not None:
                dur = int((changed_at - prev_ts).days)
            else:
                dur = None

            # Idempotency: check by lead_id + to_stage
            existing = conn.execute(
                text("""
                    SELECT id FROM stage_history
                    WHERE lead_id = :lead_id
                      AND to_stage = :to_stage
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"lead_id": lead_id, "to_stage": stage, "org_id": org_id},
            ).fetchone()
            if existing:
                sh_skipped += 1
            else:
                conn.execute(
                    text("""
                        INSERT INTO stage_history
                            (organization_id, entity_type, entity_id, lead_id,
                             from_stage, to_stage, changed_at, changed_by_id,
                             duration_in_previous_stage)
                        VALUES
                            (:org_id, 'lead', :entity_id, :lead_id,
                             :from_stage, :to_stage, :changed_at, :changed_by_id,
                             :duration)
                    """),
                    {
                        "org_id": org_id,
                        "entity_id": lead_id,
                        "lead_id": lead_id,
                        "from_stage": prev_stage,
                        "to_stage": stage,
                        "changed_at": changed_at,
                        "changed_by_id": owner_id,
                        "duration": dur,
                    },
                )
                sh_inserted += 1

            prev_stage = stage
            prev_ts = changed_at

    conn.commit()

    # Loan stage history
    LOAN_STAGE_PATHS = {
        # loan_number: (days_ago, lo_id, [stages in order])
        "SHL-2026-0001": (65,  lo_sarah_id,   ["APPLICATION"]),
        "SHL-2026-0002": (75,  lo_marcus_id,  ["APPLICATION"]),
        "SHL-2026-0003": (55,  lo_sarah_id,   ["APPLICATION", "PROCESSING"]),
        "SHL-2026-0004": (82,  lo_sarah_id,   ["APPLICATION", "PROCESSING"]),
        "SHL-2026-0005": (68,  lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED"]),
        "SHL-2026-0006": (38,  lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING"]),
        "SHL-2026-0007": (45,  lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING"]),
        "SHL-2026-0008": (18,  lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL"]),
        "SHL-2026-0009": (52,  lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE"]),
        "SHL-2026-0010": (27,  lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING"]),
        "SHL-2026-0011": (102, lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0012": (160, lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0013": (210, lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0014": (265, lo_sarah_id,   ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
        "SHL-2026-0015": (330, lo_marcus_id,  ["APPLICATION", "PROCESSING", "SUBMITTED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "CLEAR_TO_CLOSE", "CLOSING", "FUNDED"]),
    }

    for loan_number, (total_days_ago, lo_id, stages) in LOAN_STAGE_PATHS.items():
        loan_id = loan_ids.get(loan_number)
        if not loan_id:
            continue

        n = len(stages)
        step = max(4, total_days_ago // (n + 1))
        offsets = [total_days_ago - (i * step) for i in range(n)]
        offsets = [max(1, o) for o in offsets]

        prev_stage = None
        prev_ts = None

        for idx, stage in enumerate(stages):
            changed_at = days_ago(offsets[idx])
            dur = int((changed_at - prev_ts).days) if prev_ts is not None else None

            existing = conn.execute(
                text("""
                    SELECT id FROM stage_history
                    WHERE loan_id = :loan_id
                      AND to_stage = :to_stage
                      AND organization_id = :org_id
                    LIMIT 1
                """),
                {"loan_id": loan_id, "to_stage": stage, "org_id": org_id},
            ).fetchone()
            if existing:
                sh_skipped += 1
            else:
                conn.execute(
                    text("""
                        INSERT INTO stage_history
                            (organization_id, entity_type, entity_id, loan_id,
                             from_stage, to_stage, changed_at, changed_by_id,
                             duration_in_previous_stage)
                        VALUES
                            (:org_id, 'loan', :entity_id, :loan_id,
                             :from_stage, :to_stage, :changed_at, :changed_by_id,
                             :duration)
                    """),
                    {
                        "org_id": org_id,
                        "entity_id": loan_id,
                        "loan_id": loan_id,
                        "from_stage": prev_stage,
                        "to_stage": stage,
                        "changed_at": changed_at,
                        "changed_by_id": lo_id,
                        "duration": dur,
                    },
                )
                sh_inserted += 1

            prev_stage = stage
            prev_ts = changed_at

    conn.commit()
    print(f"✅ Seeded {sh_inserted} stage history records ({sh_skipped} already existed)")


