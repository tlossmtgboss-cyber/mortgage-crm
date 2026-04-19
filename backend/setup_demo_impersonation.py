#!/usr/bin/env python3
"""
Setup Demo Account with Impersonation Permissions
Enables the demo account to test the impersonation feature in production

Usage:
    python setup_demo_impersonation.py
"""

import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"🔌 Connecting to database...")
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        print("✅ Connected to database")

        # Step 1: Find demo user
        print("\n1️⃣  Finding demo user...")
        demo_user = conn.execute(text("""
            SELECT id, email, full_name FROM users
            WHERE email = 'admin@perenniaai.com'
            LIMIT 1
        """)).fetchone()

        if not demo_user:
            print("❌ Demo user not found!")
            sys.exit(1)

        demo_user_id = demo_user[0]
        print(f"   ✅ Found demo user: {demo_user[1]} (ID: {demo_user_id})")

        # Step 2: Check if employee record exists for demo user
        print("\n2️⃣  Checking employee record...")
        employee = conn.execute(text("""
            SELECT id FROM employees WHERE user_id = :user_id LIMIT 1
        """), {'user_id': demo_user_id}).fetchone()

        if not employee:
            print("   📝 Creating employee record for demo user...")
            # Create employee record
            employee_result = conn.execute(text("""
                INSERT INTO employees
                (user_id, first_name, last_name, email, employment_status, hire_date, created_at)
                VALUES
                (:user_id, 'Demo', 'User', 'admin@perenniaai.com', 'active', CURRENT_DATE, CURRENT_TIMESTAMP)
                RETURNING id
            """), {'user_id': demo_user_id})
            employee_id = employee_result.fetchone()[0]
            conn.commit()
            print(f"   ✅ Created employee ID: {employee_id}")
        else:
            employee_id = employee[0]
            print(f"   ✅ Employee record exists (ID: {employee_id})")

        # Step 3: Grant impersonation permission
        print("\n3️⃣  Granting impersonation permission...")

        # Check if permission already exists
        existing = conn.execute(text("""
            SELECT id, granted FROM employee_permissions
            WHERE employee_id = :emp_id AND permission_key = 'team.impersonate'
            LIMIT 1
        """), {'emp_id': employee_id}).fetchone()

        if existing:
            if existing[1]:
                print("   ℹ️  Permission already granted")
            else:
                # Update to granted
                conn.execute(text("""
                    UPDATE employee_permissions
                    SET granted = true, granted_at = CURRENT_TIMESTAMP, granted_by = 1
                    WHERE id = :perm_id
                """), {'perm_id': existing[0]})
                conn.commit()
                print("   ✅ Updated permission to granted")
        else:
            # Insert new permission
            conn.execute(text("""
                INSERT INTO employee_permissions
                (employee_id, permission_key, granted, granted_by, granted_at, inherited_from)
                VALUES
                (:emp_id, 'team.impersonate', true, 1, CURRENT_TIMESTAMP, 'none')
            """), {'emp_id': employee_id})
            conn.commit()
            print("   ✅ Granted team.impersonate permission")

        # Step 4: Grant additional management permissions for demo
        print("\n4️⃣  Granting additional demo permissions...")
        demo_permissions = [
            'team.view_all',
            'team.manage_permissions',
            'leads.view_all',
            'clients.view_all',
            'reports.view_all',
            'settings.view'
        ]

        for perm_key in demo_permissions:
            # Check if exists
            exists = conn.execute(text("""
                SELECT id FROM employee_permissions
                WHERE employee_id = :emp_id AND permission_key = :perm_key
                LIMIT 1
            """), {'emp_id': employee_id, 'perm_key': perm_key}).fetchone()

            if not exists:
                conn.execute(text("""
                    INSERT INTO employee_permissions
                    (employee_id, permission_key, granted, granted_by, granted_at, inherited_from)
                    VALUES
                    (:emp_id, :perm_key, true, 1, CURRENT_TIMESTAMP, 'none')
                """), {'emp_id': employee_id, 'perm_key': perm_key})

        conn.commit()
        print(f"   ✅ Granted {len(demo_permissions)} additional permissions")

        # Step 5: Create sample employees to impersonate
        print("\n5️⃣  Creating sample employees for testing...")

        sample_employees = [
            {'first': 'John', 'last': 'Sales', 'email': 'john.sales@example.com', 'role': 'Sales Rep'},
            {'first': 'Jane', 'last': 'Operations', 'email': 'jane.ops@example.com', 'role': 'Loan Processor'},
        ]

        for emp_data in sample_employees:
            # Check if employee already exists
            existing_emp = conn.execute(text("""
                SELECT id FROM employees WHERE email = :email LIMIT 1
            """), {'email': emp_data['email']}).fetchone()

            if not existing_emp:
                # Create user first
                user_result = conn.execute(text("""
                    INSERT INTO users
                    (email, hashed_password, full_name, role, is_active, created_at)
                    VALUES
                    (:email, '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5ydE8U0TzQSKy',
                     :full_name, :role, true, CURRENT_TIMESTAMP)
                    RETURNING id
                    ON CONFLICT (email) DO NOTHING
                """), {
                    'email': emp_data['email'],
                    'full_name': f"{emp_data['first']} {emp_data['last']}",
                    'role': emp_data['role']
                })

                user_row = user_result.fetchone()
                if user_row:
                    new_user_id = user_row[0]

                    # Create employee
                    conn.execute(text("""
                        INSERT INTO employees
                        (user_id, first_name, last_name, email, job_title, employment_status, hire_date, created_at)
                        VALUES
                        (:user_id, :first, :last, :email, :job_title, 'active', CURRENT_DATE, CURRENT_TIMESTAMP)
                    """), {
                        'user_id': new_user_id,
                        'first': emp_data['first'],
                        'last': emp_data['last'],
                        'email': emp_data['email'],
                        'job_title': emp_data['role']
                    })

                    conn.commit()
                    print(f"   ✅ Created {emp_data['first']} {emp_data['last']}")
                else:
                    print(f"   ℹ️  {emp_data['first']} {emp_data['last']} already exists")
            else:
                print(f"   ℹ️  {emp_data['first']} {emp_data['last']} already exists")

        # Step 6: Verify setup
        print("\n6️⃣  Verifying setup...")
        perms = conn.execute(text("""
            SELECT permission_key, granted
            FROM employee_permissions
            WHERE employee_id = :emp_id AND granted = true
            ORDER BY permission_key
        """), {'emp_id': employee_id}).fetchall()

        print(f"   ✅ Demo user has {len(perms)} active permissions:")
        for perm in perms[:10]:  # Show first 10
            print(f"      - {perm[0]}")
        if len(perms) > 10:
            print(f"      ... and {len(perms) - 10} more")

        print("\n🎉 Demo account setup complete!")
        print(f"\n📋 Login credentials:")
        print(f"   Email: admin@perenniaai.com")
        print(f"   Password: (set via DEMO_USER_PASSWORD env var)")
        print(f"\n✨ The demo account can now:")
        print(f"   - Impersonate other employees")
        print(f"   - View all teams and data")
        print(f"   - Access management features")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
