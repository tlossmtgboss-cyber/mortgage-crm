"""
Seed Carousel Themes and Templates

Run this script to populate the database with pre-built themes and templates
for the carousel builder.

Usage:
    python -m scripts.seed_carousel_themes_templates
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, engine
from models.carousel_builder import (
    CarouselTheme, CarouselTemplate,
    CarouselProjectType, CarouselPlatform, CarouselAspectRatio
)
import uuid


def generate_id():
    return str(uuid.uuid4())[:12]


# =============================================================================
# THEMES - 12 Pre-built themes
# =============================================================================

THEMES = [
    {
        "name": "Ocean Breeze",
        "description": "Fresh, calming teal and blue tones perfect for professional content",
        "colors": {
            "primary": "#217F8D",
            "secondary": "#1a5f6a",
            "accent": "#5eb5c4",
            "background": "#217F8D",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "professional",
        "tags": ["teal", "blue", "calm", "professional"],
    },
    {
        "name": "Sunset Gold",
        "description": "Warm, celebratory gold and orange tones for success stories",
        "colors": {
            "primary": "#c9a227",
            "secondary": "#a88520",
            "accent": "#f5d76e",
            "background": "#c9a227",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "celebratory",
        "tags": ["gold", "warm", "success", "celebration"],
    },
    {
        "name": "Midnight Blue",
        "description": "Deep, sophisticated navy tones for trusted authority",
        "colors": {
            "primary": "#1e3a5f",
            "secondary": "#0d1b2a",
            "accent": "#415a77",
            "background": "#1e3a5f",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "professional",
        "tags": ["navy", "dark", "trust", "authority"],
    },
    {
        "name": "Fresh Mint",
        "description": "Light, refreshing green tones for approachable content",
        "colors": {
            "primary": "#10b981",
            "secondary": "#059669",
            "accent": "#34d399",
            "background": "#10b981",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "friendly",
        "tags": ["green", "fresh", "growth", "money"],
    },
    {
        "name": "Royal Purple",
        "description": "Elegant purple gradients for premium feel",
        "colors": {
            "primary": "#7c3aed",
            "secondary": "#5b21b6",
            "accent": "#a78bfa",
            "background": "#7c3aed",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "premium",
        "tags": ["purple", "elegant", "premium", "luxury"],
    },
    {
        "name": "Coral Reef",
        "description": "Vibrant coral and pink for eye-catching posts",
        "colors": {
            "primary": "#f43f5e",
            "secondary": "#e11d48",
            "accent": "#fb7185",
            "background": "#f43f5e",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "bold",
        "tags": ["coral", "pink", "bold", "attention"],
    },
    {
        "name": "Forest Green",
        "description": "Deep, natural green for trustworthy messaging",
        "colors": {
            "primary": "#166534",
            "secondary": "#14532d",
            "accent": "#22c55e",
            "background": "#166534",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "professional",
        "tags": ["green", "nature", "trust", "stability"],
    },
    {
        "name": "Slate Modern",
        "description": "Clean, modern gray tones for minimalist design",
        "colors": {
            "primary": "#475569",
            "secondary": "#334155",
            "accent": "#94a3b8",
            "background": "#475569",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "minimal",
        "tags": ["gray", "minimal", "modern", "clean"],
    },
    {
        "name": "Sunrise Orange",
        "description": "Energetic orange for dynamic, action-oriented content",
        "colors": {
            "primary": "#ea580c",
            "secondary": "#c2410c",
            "accent": "#fb923c",
            "background": "#ea580c",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "bold",
        "tags": ["orange", "energy", "action", "dynamic"],
    },
    {
        "name": "Sky Blue",
        "description": "Bright, optimistic blue for friendly messaging",
        "colors": {
            "primary": "#0284c7",
            "secondary": "#0369a1",
            "accent": "#38bdf8",
            "background": "#0284c7",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "friendly",
        "tags": ["blue", "sky", "optimistic", "friendly"],
    },
    {
        "name": "Rose Gold",
        "description": "Soft, sophisticated pink-gold for elegant content",
        "colors": {
            "primary": "#be185d",
            "secondary": "#9d174d",
            "accent": "#f472b6",
            "background": "#be185d",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "premium",
        "tags": ["rose", "pink", "elegant", "sophisticated"],
    },
    {
        "name": "Charcoal",
        "description": "Bold, dramatic dark theme for impactful statements",
        "colors": {
            "primary": "#1f2937",
            "secondary": "#111827",
            "accent": "#6b7280",
            "background": "#1f2937",
            "text": "#ffffff",
        },
        "typography": {
            "headingFont": "Inter",
            "bodyFont": "Inter",
            "headingSize": 48,
            "bodySize": 18,
        },
        "category": "bold",
        "tags": ["dark", "charcoal", "dramatic", "bold"],
    },
]


# =============================================================================
# TEMPLATES - 20+ Pre-built templates
# =============================================================================

TEMPLATES = [
    # JUST CLOSED Templates
    {
        "name": "Just Closed - Celebration",
        "description": "Celebrate a successful closing with this 5-slide template",
        "template_type": "just_closed",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "just_closed",
        "tags": ["celebration", "closing", "success"],
        "required_data_bindings": ["borrower.first_name", "property.city"],
        "slide_templates": [
            {"title": "🎉 JUST CLOSED!", "subtitle": "Another Dream Home Funded", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#217F8D", "#1a5f6a"]}},
            {"title": "The Journey", "subtitle": "From Application to Keys", "body_text": "Every step of the way, we were there.", "background_type": "solid", "background_color": "#217F8D"},
            {"title": "Making Dreams Reality", "subtitle": "{{borrower.first_name}}'s New Home", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#c9a227", "#a88520"]}},
            {"title": "Congratulations!", "subtitle": "Welcome to {{property.city}}", "background_type": "solid", "background_color": "#217F8D"},
            {"title": "Your Turn?", "subtitle": "Let's Make It Happen", "body_text": "Contact me to start your journey.", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#217F8D", "#1a5f6a"]}},
        ],
    },
    {
        "name": "Just Closed - Minimal",
        "description": "Clean, minimal celebration template",
        "template_type": "just_closed",
        "platform": "instagram",
        "aspect_ratio": "1:1",
        "category": "just_closed",
        "tags": ["minimal", "clean", "modern"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "CLOSED", "subtitle": "Another Success Story", "background_type": "solid", "background_color": "#1f2937"},
            {"title": "From Dream to Reality", "background_type": "solid", "background_color": "#374151"},
            {"title": "Keys Handed Over", "background_type": "solid", "background_color": "#1f2937"},
            {"title": "Ready for Your Story?", "subtitle": "Let's Connect", "background_type": "solid", "background_color": "#374151"},
        ],
    },
    {
        "name": "Just Closed - Instagram Story",
        "description": "Vertical format for Instagram Stories",
        "template_type": "just_closed",
        "platform": "instagram",
        "aspect_ratio": "9:16",
        "category": "just_closed",
        "tags": ["story", "vertical", "instagram"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "🏠 JUST CLOSED", "subtitle": "Swipe to see the journey →", "background_type": "gradient", "background_gradient": {"angle": 180, "colors": ["#7c3aed", "#5b21b6"]}},
            {"title": "The Process", "body_text": "Application → Approval → Keys", "background_type": "solid", "background_color": "#5b21b6"},
            {"title": "Mission Complete!", "subtitle": "Another Happy Homeowner", "background_type": "gradient", "background_gradient": {"angle": 180, "colors": ["#5b21b6", "#7c3aed"]}},
        ],
    },

    # RATE UPDATE Templates
    {
        "name": "Rate Update - Market Alert",
        "description": "Eye-catching rate update for market movements",
        "template_type": "rate_update",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "rate_update",
        "tags": ["rates", "market", "alert"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "📊 RATE UPDATE", "subtitle": "What You Need to Know", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#0284c7", "#0369a1"]}},
            {"title": "Markets Are Moving", "body_text": "Stay informed on the latest trends", "background_type": "solid", "background_color": "#0369a1"},
            {"title": "What This Means", "subtitle": "For Buyers & Homeowners", "background_type": "solid", "background_color": "#0284c7"},
            {"title": "Get Your Quote", "subtitle": "Personalized Rates Available", "body_text": "Contact me today!", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#0284c7", "#0369a1"]}},
        ],
    },
    {
        "name": "Rate Update - Opportunity",
        "description": "Highlight refinancing opportunities",
        "template_type": "rate_update",
        "platform": "facebook",
        "aspect_ratio": "1:1",
        "category": "rate_update",
        "tags": ["refinance", "opportunity", "savings"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "💰 Rate Opportunity", "subtitle": "Could Now Be Your Time?", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#10b981", "#059669"]}},
            {"title": "Lower Your Payment", "body_text": "Current market conditions may favor refinancing", "background_type": "solid", "background_color": "#059669"},
            {"title": "Free Analysis", "subtitle": "See Your Potential Savings", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#059669", "#10b981"]}},
        ],
    },

    # EDUCATIONAL Templates
    {
        "name": "Educational - Credit Score Tips",
        "description": "Help buyers improve their credit scores",
        "template_type": "educational",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "educational",
        "tags": ["credit", "tips", "education"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "Credit Score Tips", "subtitle": "Boost Your Buying Power", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#7c3aed", "#5b21b6"]}},
            {"title": "Pay On Time", "subtitle": "Tip #1", "body_text": "Payment history is 35% of your score", "background_type": "solid", "background_color": "#5b21b6"},
            {"title": "Keep Balances Low", "subtitle": "Tip #2", "body_text": "Stay under 30% of your credit limit", "background_type": "solid", "background_color": "#7c3aed"},
            {"title": "Don't Close Old Cards", "subtitle": "Tip #3", "body_text": "Length of history matters", "background_type": "solid", "background_color": "#5b21b6"},
            {"title": "Questions?", "subtitle": "I'm Here to Help", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#7c3aed", "#5b21b6"]}},
        ],
    },
    {
        "name": "Educational - First-Time Buyer",
        "description": "Guide for first-time homebuyers",
        "template_type": "educational",
        "platform": "instagram",
        "aspect_ratio": "1:1",
        "category": "educational",
        "tags": ["first-time", "guide", "buyers"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "First-Time Buyer?", "subtitle": "Here's What to Know", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#f43f5e", "#e11d48"]}},
            {"title": "1. Get Pre-Approved", "body_text": "Know your budget before you shop", "background_type": "solid", "background_color": "#e11d48"},
            {"title": "2. Save for Down Payment", "body_text": "3-20% depending on loan type", "background_type": "solid", "background_color": "#f43f5e"},
            {"title": "3. Check Your Credit", "body_text": "Higher score = better rates", "background_type": "solid", "background_color": "#e11d48"},
            {"title": "4. Don't Go It Alone", "body_text": "Work with a trusted loan officer", "background_type": "solid", "background_color": "#f43f5e"},
            {"title": "Ready to Start?", "subtitle": "Let's Chat!", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#f43f5e", "#e11d48"]}},
        ],
    },
    {
        "name": "Educational - Loan Types",
        "description": "Explain different loan programs",
        "template_type": "educational",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "educational",
        "tags": ["loans", "FHA", "VA", "conventional"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "Loan Types Explained", "subtitle": "Find Your Fit", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#1e3a5f", "#0d1b2a"]}},
            {"title": "Conventional", "body_text": "Traditional financing with competitive rates. 3-20% down.", "background_type": "solid", "background_color": "#1e3a5f"},
            {"title": "FHA", "body_text": "Government-backed. Lower credit requirements. 3.5% down.", "background_type": "solid", "background_color": "#0d1b2a"},
            {"title": "VA", "body_text": "For veterans & service members. 0% down possible.", "background_type": "solid", "background_color": "#1e3a5f"},
            {"title": "Which Is Right?", "subtitle": "Let's Find Out Together", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#1e3a5f", "#0d1b2a"]}},
        ],
    },
    {
        "name": "Educational - Down Payment Myths",
        "description": "Bust common down payment misconceptions",
        "template_type": "educational",
        "platform": "instagram",
        "aspect_ratio": "4:5",
        "category": "educational",
        "tags": ["myths", "down payment", "misconceptions"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "Down Payment Myths", "subtitle": "BUSTED", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#ea580c", "#c2410c"]}},
            {"title": "MYTH: You Need 20%", "subtitle": "TRUTH: As low as 3% available", "background_type": "solid", "background_color": "#c2410c"},
            {"title": "MYTH: Gifts Aren't Allowed", "subtitle": "TRUTH: Gift funds are often OK", "background_type": "solid", "background_color": "#ea580c"},
            {"title": "MYTH: No Down Payment Programs", "subtitle": "TRUTH: Many assistance programs exist", "background_type": "solid", "background_color": "#c2410c"},
            {"title": "Know the Facts", "subtitle": "Ask Me Anything", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#ea580c", "#c2410c"]}},
        ],
    },

    # MARKETING Templates
    {
        "name": "Marketing - Why Work With Me",
        "description": "Showcase your value proposition",
        "template_type": "marketing",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "marketing",
        "tags": ["value", "personal brand", "trust"],
        "required_data_bindings": ["lo.name"],
        "slide_templates": [
            {"title": "Why Work With Me?", "subtitle": "Your Trusted Mortgage Partner", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#217F8D", "#1a5f6a"]}},
            {"title": "Experience", "body_text": "Hundreds of families helped achieve homeownership", "background_type": "solid", "background_color": "#1a5f6a"},
            {"title": "Communication", "body_text": "You'll never wonder where your loan stands", "background_type": "solid", "background_color": "#217F8D"},
            {"title": "Results", "body_text": "On-time closings and competitive rates", "background_type": "solid", "background_color": "#1a5f6a"},
            {"title": "Let's Connect", "subtitle": "Your Dream Home Awaits", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#217F8D", "#1a5f6a"]}},
        ],
    },
    {
        "name": "Marketing - Testimonial",
        "description": "Share client success stories",
        "template_type": "marketing",
        "platform": "facebook",
        "aspect_ratio": "1:1",
        "category": "marketing",
        "tags": ["testimonial", "review", "social proof"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "What Clients Say", "subtitle": "Real Stories, Real Results", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#c9a227", "#a88520"]}},
            {"title": "⭐⭐⭐⭐⭐", "body_text": "\"Best experience ever! Made buying our first home so easy.\"", "background_type": "solid", "background_color": "#a88520"},
            {"title": "You Could Be Next", "subtitle": "Let's Write Your Success Story", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#c9a227", "#a88520"]}},
        ],
    },
    {
        "name": "Marketing - Local Expert",
        "description": "Position yourself as a local market expert",
        "template_type": "marketing",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "marketing",
        "tags": ["local", "expert", "market"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "Your Local Expert", "subtitle": "I Know This Market", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#166534", "#14532d"]}},
            {"title": "Local Knowledge", "body_text": "Neighborhoods, schools, market trends - I know it all", "background_type": "solid", "background_color": "#14532d"},
            {"title": "Local Connections", "body_text": "Realtors, inspectors, title companies - trusted network", "background_type": "solid", "background_color": "#166534"},
            {"title": "Local Service", "body_text": "Face-to-face meetings, community commitment", "background_type": "solid", "background_color": "#14532d"},
            {"title": "Let's Meet", "subtitle": "Coffee's On Me", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#166534", "#14532d"]}},
        ],
    },

    # TikTok Vertical Templates
    {
        "name": "TikTok - Quick Tips",
        "description": "Fast-paced tips for TikTok",
        "template_type": "educational",
        "platform": "tiktok",
        "aspect_ratio": "9:16",
        "category": "educational",
        "tags": ["tiktok", "quick", "tips"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "3 Things to Know", "subtitle": "Before Buying a Home", "background_type": "gradient", "background_gradient": {"angle": 180, "colors": ["#f43f5e", "#e11d48"]}},
            {"title": "#1", "subtitle": "Get Pre-Approved FIRST", "background_type": "solid", "background_color": "#e11d48"},
            {"title": "#2", "subtitle": "Don't Open New Credit", "background_type": "solid", "background_color": "#f43f5e"},
            {"title": "#3", "subtitle": "Save for Closing Costs", "background_type": "solid", "background_color": "#e11d48"},
            {"title": "Follow for More!", "subtitle": "@yourusername", "background_type": "gradient", "background_gradient": {"angle": 180, "colors": ["#f43f5e", "#e11d48"]}},
        ],
    },
    {
        "name": "TikTok - Just Closed",
        "description": "Celebrate closings on TikTok",
        "template_type": "just_closed",
        "platform": "tiktok",
        "aspect_ratio": "9:16",
        "category": "just_closed",
        "tags": ["tiktok", "celebration", "vertical"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "🔑 KEYS HANDED", "subtitle": "Another Happy Client!", "background_type": "gradient", "background_gradient": {"angle": 180, "colors": ["#c9a227", "#a88520"]}},
            {"title": "The Feeling...", "subtitle": "When You Get The Keys", "background_type": "solid", "background_color": "#a88520"},
            {"title": "Your Turn?", "subtitle": "DM Me to Start", "background_type": "gradient", "background_gradient": {"angle": 180, "colors": ["#c9a227", "#a88520"]}},
        ],
    },

    # Additional Templates
    {
        "name": "Refinance Opportunity",
        "description": "Target existing homeowners for refinancing",
        "template_type": "marketing",
        "platform": "facebook",
        "aspect_ratio": "1:1",
        "category": "marketing",
        "tags": ["refinance", "homeowners", "savings"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "Time to Refinance?", "subtitle": "Lower Your Payment", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#10b981", "#059669"]}},
            {"title": "Benefits", "body_text": "• Lower monthly payment\n• Cash out equity\n• Shorten your term", "background_type": "solid", "background_color": "#059669"},
            {"title": "Free Quote", "subtitle": "No Obligation", "body_text": "See your potential savings today", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#10b981", "#059669"]}},
        ],
    },
    {
        "name": "Home Buying Season",
        "description": "Seasonal marketing for spring/summer",
        "template_type": "marketing",
        "platform": "instagram",
        "aspect_ratio": "1:1",
        "category": "marketing",
        "tags": ["seasonal", "spring", "summer"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "🏡 Buying Season", "subtitle": "Is Here!", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#0284c7", "#0369a1"]}},
            {"title": "Get Ahead", "body_text": "Pre-approval puts you first in line", "background_type": "solid", "background_color": "#0369a1"},
            {"title": "Act Now", "body_text": "Inventory is limited - be ready!", "background_type": "solid", "background_color": "#0284c7"},
            {"title": "Start Today", "subtitle": "Free Pre-Approval", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#0284c7", "#0369a1"]}},
        ],
    },
    {
        "name": "Closing Costs Explained",
        "description": "Break down closing costs for buyers",
        "template_type": "educational",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "educational",
        "tags": ["closing costs", "education", "buyers"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "Closing Costs", "subtitle": "What to Expect", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#475569", "#334155"]}},
            {"title": "Typical Range", "body_text": "2-5% of purchase price", "background_type": "solid", "background_color": "#334155"},
            {"title": "What's Included", "body_text": "• Loan fees\n• Title insurance\n• Escrow deposits\n• Recording fees", "background_type": "solid", "background_color": "#475569"},
            {"title": "Get Estimates", "subtitle": "No Surprises at Closing", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#475569", "#334155"]}},
        ],
    },
    {
        "name": "VA Loan Benefits",
        "description": "Highlight VA loan advantages for veterans",
        "template_type": "educational",
        "platform": "linkedin",
        "aspect_ratio": "1:1",
        "category": "educational",
        "tags": ["VA", "veterans", "military"],
        "required_data_bindings": [],
        "slide_templates": [
            {"title": "VA Loan Benefits", "subtitle": "Thank You for Your Service", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#1e3a5f", "#0d1b2a"]}},
            {"title": "No Down Payment", "body_text": "100% financing available", "background_type": "solid", "background_color": "#0d1b2a"},
            {"title": "No PMI", "body_text": "Save hundreds monthly", "background_type": "solid", "background_color": "#1e3a5f"},
            {"title": "Competitive Rates", "body_text": "Often lower than conventional", "background_type": "solid", "background_color": "#0d1b2a"},
            {"title": "You Earned It", "subtitle": "Let's Use Your Benefit", "background_type": "gradient", "background_gradient": {"angle": 135, "colors": ["#1e3a5f", "#0d1b2a"]}},
        ],
    },
]


def seed_themes(db):
    """Seed the database with themes."""
    print("Seeding themes...")

    # Check if themes already exist
    existing = db.query(CarouselTheme).filter(CarouselTheme.is_system == True).count()
    if existing > 0:
        print(f"  Found {existing} existing system themes. Skipping.")
        return

    for theme_data in THEMES:
        theme = CarouselTheme(
            id=generate_id(),
            name=theme_data["name"],
            description=theme_data["description"],
            colors=theme_data["colors"],
            typography=theme_data["typography"],
            spacing={},
            decorations={},
            category=theme_data["category"],
            tags=theme_data["tags"],
            is_system=True,
            is_active=True,
            times_used=0,
        )
        db.add(theme)

    db.commit()
    print(f"  Created {len(THEMES)} themes.")


def seed_templates(db):
    """Seed the database with templates."""
    print("Seeding templates...")

    # Check if all templates exist
    existing = db.query(CarouselTemplate).filter(CarouselTemplate.is_active == True).count()
    if existing >= len(TEMPLATES):
        print(f"  Found {existing} existing templates. Skipping.")
        return

    # Get existing template names to avoid duplicates
    existing_names = set(
        name for (name,) in db.query(CarouselTemplate.name).all()
    )

    added = 0
    for template_data in TEMPLATES:
        # Skip if template already exists
        if template_data["name"] in existing_names:
            continue

        template = CarouselTemplate(
            id=generate_id(),
            name=template_data["name"],
            description=template_data["description"],
            template_type=template_data["template_type"],
            platform=template_data["platform"],
            aspect_ratio=template_data["aspect_ratio"],
            slide_templates=template_data["slide_templates"],
            required_data_bindings=template_data.get("required_data_bindings", []),
            category=template_data["category"],
            tags=template_data["tags"],
            is_active=True,
            times_used=0,
        )
        db.add(template)
        added += 1

    if added > 0:
        db.commit()
        print(f"  Added {added} new templates (total: {existing + added}).")
    else:
        print(f"  No new templates to add. ({existing} already exist)")


def main():
    """Main function to run the seed script."""
    print("=" * 60)
    print("Seeding Carousel Themes and Templates")
    print("=" * 60)

    db = SessionLocal()

    try:
        seed_themes(db)
        seed_templates(db)
        print("=" * 60)
        print("Seeding complete!")
        print("=" * 60)
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
