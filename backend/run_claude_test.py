#!/usr/bin/env python
"""Wrapper to run Claude parser test with .env file loaded"""
import os
import sys
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Verify key is loaded
if not os.getenv("ANTHROPIC_API_KEY"):
    print("❌ ANTHROPIC_API_KEY not found in .env file")
    sys.exit(1)

print(f"✅ Environment loaded (AI_PROVIDER={os.getenv('AI_PROVIDER')})")
print(f"✅ ANTHROPIC_API_KEY loaded: {os.getenv('ANTHROPIC_API_KEY')[:20]}...")

# Import and run the test
import asyncio
from test_claude_parser import test_parser

if __name__ == "__main__":
    success = asyncio.run(test_parser())
    sys.exit(0 if success else 1)
