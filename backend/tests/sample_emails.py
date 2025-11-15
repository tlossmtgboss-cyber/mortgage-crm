"""
Sample test emails for all 4 profile types
Use these to test Claude parser extraction capabilities
"""

from datetime import datetime


# ==================== LEAD PROFILE EMAIL ====================
LEAD_EMAIL = {
    'id': 'msg-lead-001',
    'from_email': 'john.smith@gmail.com',
    'to_emails': ['loans@example.com'],
    'subject': 'Pre-approval inquiry',
    'sent_date': datetime.utcnow(),
    'received_at': datetime.utcnow(),
    'body_text': '''
Hi,

My name is John Smith and I'm interested in getting pre-approved for a home loan.
My wife Sarah and I are looking to buy our first home in Austin, Texas.

Here's our information:
- Email: john.smith@gmail.com
- Phone: (512) 555-1234
- Current employer: Google (Software Engineer)
- Annual income: $145,000/year
- Been at my job for 4 years
- Looking at homes around $500,000
- Have about $100,000 saved for down payment
- My credit score is around 780

We're pretty excited to get started. Can you help us figure out what we qualify for?

Thanks,
John Smith
    ''',
    'raw_text': '''
Hi,

My name is John Smith and I'm interested in getting pre-approved for a home loan.
My wife Sarah and I are looking to buy our first home in Austin, Texas.

Here's our information:
- Email: john.smith@gmail.com
- Phone: (512) 555-1234
- Current employer: Google (Software Engineer)
- Annual income: $145,000/year
- Been at my job for 4 years
- Looking at homes around $500,000
- Have about $100,000 saved for down payment
- My credit score is around 780

We're pretty excited to get started. Can you help us figure out what we qualify for?

Thanks,
John Smith
    '''
}


# ==================== ACTIVE LOAN EMAIL ====================
ACTIVE_LOAN_EMAIL = {
    'id': 'msg-loan-001',
    'from_email': 'processor@lender.com',
    'to_emails': ['loans@example.com'],
    'subject': 'Clear to Close - Loan #12345678',
    'sent_date': datetime.utcnow(),
    'received_at': datetime.utcnow(),
    'body_text': '''
Good news! Loan #12345678 has been cleared to close.

Borrower: Jennifer Martinez
Property: 456 Oak Lane, Dallas, TX 75201
Loan Amount: $425,000
Rate: 6.375% (30-year fixed)
Appraisal Value: $475,000

Timeline:
- Appraisal completed: 01/10/2025
- Title received: 01/12/2025
- Conditional approval: 01/15/2025
- Clear to Close: 01/20/2025
- Scheduled closing: 01/25/2025 at 2:00 PM

Closing Disclosure was sent to borrower on 01/18/2025 and signed on 01/19/2025.

Team:
- Loan Officer: Sarah Johnson (sjohnson@lender.com)
- Processor: Mike Chen (mchen@lender.com)
- Underwriter: David Park
- Closer: Lisa Wong (lwong@titleco.com)

Please confirm receipt and coordinate final closing details with the title company.

Best regards,
Mike Chen
Senior Loan Processor
    ''',
    'raw_text': '''
Good news! Loan #12345678 has been cleared to close.

Borrower: Jennifer Martinez
Property: 456 Oak Lane, Dallas, TX 75201
Loan Amount: $425,000
Rate: 6.375% (30-year fixed)
Appraisal Value: $475,000

Timeline:
- Appraisal completed: 01/10/2025
- Title received: 01/12/2025
- Conditional approval: 01/15/2025
- Clear to Close: 01/20/2025
- Scheduled closing: 01/25/2025 at 2:00 PM

Closing Disclosure was sent to borrower on 01/18/2025 and signed on 01/19/2025.

Team:
- Loan Officer: Sarah Johnson (sjohnson@lender.com)
- Processor: Mike Chen (mchen@lender.com)
- Underwriter: David Park
- Closer: Lisa Wong (lwong@titleco.com)

Please confirm receipt and coordinate final closing details with the title company.

Best regards,
Mike Chen
Senior Loan Processor
    '''
}


# ==================== MUM CLIENT EMAIL ====================
MUM_CLIENT_EMAIL = {
    'id': 'msg-mum-001',
    'from_email': 'robert.williams@email.com',
    'to_emails': ['loans@example.com'],
    'subject': 'Question about refinancing',
    'sent_date': datetime.utcnow(),
    'received_at': datetime.utcnow(),
    'body_text': '''
Hi team,

I closed on my home loan with you last year (Loan #98765432) and I've been seeing rates drop.
My current rate is 7.25% and I'm wondering if it makes sense to refinance now.

Current situation:
- Original close date: March 15, 2024
- Current rate: 7.25%
- Remaining balance: approximately $380,000
- Home value has increased to about $525,000

I'm also happy to refer my coworker Tom who's looking to buy his first home.

Can you let me know if refinancing would save me money at current rates?

Thanks,
Robert Williams
(214) 555-9876
robert.williams@email.com
    ''',
    'raw_text': '''
Hi team,

I closed on my home loan with you last year (Loan #98765432) and I've been seeing rates drop.
My current rate is 7.25% and I'm wondering if it makes sense to refinance now.

Current situation:
- Original close date: March 15, 2024
- Current rate: 7.25%
- Remaining balance: approximately $380,000
- Home value has increased to about $525,000

I'm also happy to refer my coworker Tom who's looking to buy his first home.

Can you let me know if refinancing would save me money at current rates?

Thanks,
Robert Williams
(214) 555-9876
robert.williams@email.com
    '''
}


# ==================== TEAM MEMBER EMAIL ====================
TEAM_MEMBER_EMAIL = {
    'id': 'msg-team-001',
    'from_email': 'hr@example.com',
    'to_emails': ['manager@example.com'],
    'subject': 'Q4 Performance Review - Emily Rodriguez',
    'sent_date': datetime.utcnow(),
    'received_at': datetime.utcnow(),
    'body_text': '''
Q4 2024 Performance Review
Employee: Emily Rodriguez
Employee ID: EMP-2047
Department: Loan Processing
Manager: Sarah Johnson
Start Date: June 1, 2023

Performance Metrics:
- Loans Processed: 127 loans in Q4
- Average Close Time: 32 days
- Customer Satisfaction: 4.8/5.0
- Total Volume: $28.5M

DISC Profile Assessment:
- Dominance (D): 35
- Influence (I): 75
- Steadiness (S): 60
- Conscientiousness (C): 45
Primary Type: Influence (I) - Collaborative, enthusiastic, people-oriented

Goals for 2025:
Q1: Reduce average close time to under 30 days
Q2: Process 150+ loans while maintaining quality
Q3: Complete advanced underwriting certification
Q4: Mentor 2 junior processors

Development Areas:
- Technical underwriting skills
- Time management under pressure
- Delegation skills

Personal Information:
- Birthday: August 12th
- Work Anniversary: June 1st
- Emergency Contact: Maria Rodriguez (555-2468)
- Hobbies: Marathon running, photography

Overall: Emily is exceeding expectations and showing strong leadership potential.

Best regards,
HR Team
    ''',
    'raw_text': '''
Q4 2024 Performance Review
Employee: Emily Rodriguez
Employee ID: EMP-2047
Department: Loan Processing
Manager: Sarah Johnson
Start Date: June 1, 2023

Performance Metrics:
- Loans Processed: 127 loans in Q4
- Average Close Time: 32 days
- Customer Satisfaction: 4.8/5.0
- Total Volume: $28.5M

DISC Profile Assessment:
- Dominance (D): 35
- Influence (I): 75
- Steadiness (S): 60
- Conscientiousness (C): 45
Primary Type: Influence (I) - Collaborative, enthusiastic, people-oriented

Goals for 2025:
Q1: Reduce average close time to under 30 days
Q2: Process 150+ loans while maintaining quality
Q3: Complete advanced underwriting certification
Q4: Mentor 2 junior processors

Development Areas:
- Technical underwriting skills
- Time management under pressure
- Delegation skills

Personal Information:
- Birthday: August 12th
- Work Anniversary: June 1st
- Emergency Contact: Maria Rodriguez (555-2468)
- Hobbies: Marathon running, photography

Overall: Emily is exceeding expectations and showing strong leadership potential.

Best regards,
HR Team
    '''
}


# Export all samples
ALL_SAMPLE_EMAILS = {
    'lead': LEAD_EMAIL,
    'active_loan': ACTIVE_LOAN_EMAIL,
    'mum_client': MUM_CLIENT_EMAIL,
    'team_member': TEAM_MEMBER_EMAIL
}
