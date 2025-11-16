#!/usr/bin/env python3
"""
Runner script for permission requests migration
"""

import sys
import os

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from migrations.add_permission_requests import upgrade

if __name__ == '__main__':
    print("Running permission_requests migration...")
    upgrade()
    print("\n✅ Migration complete!")
