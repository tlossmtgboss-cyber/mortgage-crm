#!/usr/bin/env python3
"""Test daily_focus_priorities query"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Get database URL
db_url = os.getenv('DATABASE_URL')
if not db_url:
    print('ERROR: DATABASE_URL not found in environment')
    exit(1)

engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
db = Session()

# Get demo user ID
result = db.execute(text('SELECT id, email, first_name, last_name FROM users WHERE email = :email'), {'email': 'demo@example.com'})
user = result.fetchone()

if not user:
    print('ERROR: Demo user not found')
    exit(1)

user_id = user[0]
print(f'Testing daily_focus_priorities for user: {user[2]} {user[3]} (ID: {user_id})')
print('=' * 80)

# Test the query
result = db.execute(text("""
    WITH priority_items AS (
        -- All pending tasks (regardless of due date)
        SELECT
            'task' as type,
            t.id,
            t.title,
            0 as value,
            t.due_date,
            CASE
                WHEN t.due_date IS NOT NULL AND t.due_date < NOW() THEN 100
                WHEN t.due_date IS NOT NULL AND t.due_date < NOW() + INTERVAL '1 day' THEN 95
                WHEN t.priority = 'high' THEN 90
                WHEN t.priority = 'normal' THEN 70
                ELSE 65
            END as priority_score,
            CASE
                WHEN t.due_date IS NOT NULL AND t.due_date < NOW() THEN 'Overdue'
                WHEN t.due_date IS NOT NULL AND t.due_date < NOW() + INTERVAL '1 day' THEN 'Due Today'
                WHEN t.priority = 'high' THEN 'High Priority'
                ELSE 'Pending'
            END as urgency_label
        FROM tasks t
        WHERE t.assigned_to = :user_id
        AND t.status != 'completed'

        UNION ALL

        -- Urgent loans
        SELECT
            'loan' as type,
            l.id,
            l.borrower_name as title,
            l.amount as value,
            l.closing_date as due_date,
            CASE
                WHEN l.closing_date < NOW() + INTERVAL '3 days' THEN 98
                WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 92
                WHEN l.risk_score > 70 THEN 85
                WHEN l.days_in_stage > 14 THEN 75
                ELSE 60
            END as priority_score,
            CASE
                WHEN l.closing_date < NOW() + INTERVAL '3 days' THEN 'Closing Imminent'
                WHEN l.closing_date < NOW() + INTERVAL '7 days' THEN 'Closing This Week'
                WHEN l.risk_score > 70 THEN 'High Risk'
                WHEN l.days_in_stage > 14 THEN 'Stalled'
                ELSE 'Active'
            END as urgency_label
        FROM loans l
        WHERE l.loan_officer_id = :user_id
        AND l.stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')
        AND (
            l.closing_date < NOW() + INTERVAL '7 days'
            OR l.risk_score > 60
            OR l.days_in_stage > 14
        )
    )
    SELECT type, id, title, value, due_date, priority_score, urgency_label
    FROM priority_items
    ORDER BY priority_score DESC, due_date ASC NULLS LAST
    LIMIT 50
"""), {'user_id': user_id})

rows = result.fetchall()
print(f'\nFound {len(rows)} priority items\n')

if len(rows) == 0:
    print('No items found. Checking what data exists...\n')

    # Check tasks
    task_result = db.execute(text("SELECT COUNT(*) FROM tasks WHERE assigned_to = :user_id AND status != 'completed'"), {'user_id': user_id})
    task_count = task_result.fetchone()[0]
    print(f'Total incomplete tasks: {task_count}')

    # Show some tasks if they exist
    if task_count > 0:
        print('\nSample tasks:')
        tasks = db.execute(text("SELECT id, title, priority, due_date, status FROM tasks WHERE assigned_to = :user_id AND status != 'completed' LIMIT 5"), {'user_id': user_id})
        for t in tasks:
            print(f'  - Task {t[0]}: {t[1]} (Priority: {t[2]}, Due: {t[3]}, Status: {t[4]})')

    # Check loans
    loan_result = db.execute(text("SELECT COUNT(*) FROM loans WHERE loan_officer_id = :user_id AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED')"), {'user_id': user_id})
    loan_count = loan_result.fetchone()[0]
    print(f'\nTotal active loans: {loan_count}')

    # Show some loans if they exist
    if loan_count > 0:
        print('\nSample loans:')
        loans = db.execute(text("SELECT id, borrower_name, stage, amount, closing_date FROM loans WHERE loan_officer_id = :user_id AND stage NOT IN ('FUNDED', 'CLOSED', 'CANCELLED') LIMIT 5"), {'user_id': user_id})
        for l in loans:
            print(f'  - Loan {l[0]}: {l[1]} (Stage: {l[2]}, Amount: ${l[3] or 0:,.0f}, Closing: {l[4]})')
else:
    print('TOP 20 PRIORITY ITEMS:\n')
    for i, row in enumerate(rows[:20], 1):
        print(f'{i}. [{row[6]}] {row[0].upper()}: {row[2]}')
        print(f'   Priority Score: {row[5]}')
        if row[4]:
            print(f'   Due Date: {row[4]}')
        if row[3] > 0:
            print(f'   Value: ${row[3]:,.0f}')
        print()

db.close()
print('\n✓ Query test completed successfully')
