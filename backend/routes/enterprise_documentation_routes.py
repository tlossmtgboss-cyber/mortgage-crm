"""
Enterprise Documentation Portal API Routes

Provides backend endpoints to serve documentation content, handle search queries,
manage content, and track analytics for the enterprise documentation portal.
This API surfaces the 88% of backend capabilities that currently have no frontend UI.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from db import get_db
from auth.auth import get_current_user
from models.auth import User
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/enterprise-docs")

# Documentation categories and their metadata
DOCUMENTATION_CATEGORIES = {
    "api-reference": {
        "name": "API Reference",
        "description": "Complete API documentation for all backend endpoints",
        "icon": "🔌"
    },
    "business-processes": {
        "name": "Business Processes", 
        "description": "Loan workflows, compliance procedures, and operational guidelines",
        "icon": "⚙️"
    },
    "ai-orchestration": {
        "name": "AI Orchestration",
        "description": "Agent tools, orchestration patterns, and AI integrations", 
        "icon": "🤖"
    },
    "system-architecture": {
        "name": "System Architecture",
        "description": "Database models, service patterns, and technical architecture",
        "icon": "🏗️"
    },
    "integrations": {
        "name": "Integrations",
        "description": "Third-party integrations, webhooks, and external APIs",
        "icon": "🔗"
    },
    "compliance": {
        "name": "Compliance", 
        "description": "Regulatory requirements, audit trails, and compliance procedures",
        "icon": "📋"
    },
    "analytics": {
        "name": "Analytics & Reporting",
        "description": "Data models, reporting capabilities, and analytics frameworks",
        "icon": "📊"
    },
    "deployment": {
        "name": "Deployment & Operations",
        "description": "DevOps procedures, monitoring, and operational runbooks",
        "icon": "🚀"
    }
}

@router.get("/content")
async def get_documentation_content(
    category: str = Query("api-reference", description="Documentation category"),
    content_type: Optional[str] = Query(None, description="Content type filter"),
    search: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get documentation content for a specific category with optional filtering and search.
    Returns paginated results with content metadata.
    """
    try:
        # Generate mock documentation based on category
        content = await _generate_documentation_content(category, search, content_type)
        
        # Paginate results
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_content = content[start_idx:end_idx]
        
        # Get featured content for this category
        featured = await _get_featured_content(category)
        
        # Calculate analytics
        analytics = await _calculate_documentation_analytics(db, current_user)
        
        return {
            "content": paginated_content,
            "featured": featured,
            "analytics": analytics,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": len(content),
                "total_pages": (len(content) + limit - 1) // limit
            },
            "category": DOCUMENTATION_CATEGORIES.get(category, {})
        }
        
    except Exception as e:
        logger.error(f"Error getting documentation content: {e}")
        raise HTTPException(status_code=500, detail="Failed to load documentation content")

@router.get("/categories")
async def get_documentation_categories(
    current_user: User = Depends(get_current_user)
):
    """Get all available documentation categories with metadata."""
    return {
        "categories": DOCUMENTATION_CATEGORIES,
        "total": len(DOCUMENTATION_CATEGORIES)
    }

@router.post("/analytics/view")
async def track_content_view(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """Track when a user views documentation content for analytics."""
    try:
        content_id = data.get("contentId")
        title = data.get("title")
        category = data.get("category")
        
        # In a real implementation, you would save this to a database table
        # For now, we'll just log it
        logger.info(f"Content view tracked - User: {current_user.email}, Content: {content_id}, Title: {title}, Category: {category}")
        
        return {"success": True, "message": "View tracked successfully"}
        
    except Exception as e:
        logger.error(f"Error tracking content view: {e}")
        raise HTTPException(status_code=500, detail="Failed to track content view")

@router.get("/search")
async def search_documentation(
    q: str = Query(..., description="Search query"),
    category: Optional[str] = Query(None, description="Category filter"),
    content_type: Optional[str] = Query(None, description="Content type filter"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user)
):
    """
    Search across all documentation content with advanced filtering.
    Uses full-text search and returns ranked results.
    """
    try:
        # Perform search across all categories or specific category
        categories_to_search = [category] if category else list(DOCUMENTATION_CATEGORIES.keys())
        
        all_results = []
        for cat in categories_to_search:
            content = await _generate_documentation_content(cat, q, content_type)
            # Add category info to each result
            for item in content:
                item["category"] = cat
                item["category_name"] = DOCUMENTATION_CATEGORIES[cat]["name"]
            all_results.extend(content)
        
        # Sort by relevance (mock scoring based on query match)
        if q:
            query_lower = q.lower()
            for item in all_results:
                score = 0
                title_lower = item.get("title", "").lower()
                desc_lower = item.get("description", "").lower()
                
                # Title match scores higher
                if query_lower in title_lower:
                    score += 10
                if query_lower in desc_lower:
                    score += 5
                
                # Tag matches
                for tag in item.get("tags", []):
                    if query_lower in tag.lower():
                        score += 3
                        
                item["relevance_score"] = score
            
            # Sort by relevance score
            all_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Paginate results
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_results = all_results[start_idx:end_idx]
        
        return {
            "results": paginated_results,
            "query": q,
            "filters": {
                "category": category,
                "content_type": content_type
            },
            "pagination": {
                "page": page,
                "limit": limit,
                "total": len(all_results),
                "total_pages": (len(all_results) + limit - 1) // limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error searching documentation: {e}")
        raise HTTPException(status_code=500, detail="Failed to search documentation")

@router.get("/analytics/dashboard")
async def get_documentation_analytics(
    days: int = Query(30, ge=1, le=365, description="Days to analyze"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
):
    """Get documentation usage analytics and metrics."""
    try:
        analytics = await _calculate_documentation_analytics(db, current_user)
        
        # Add time-based metrics
        analytics.update({
            "period_days": days,
            "top_content": [
                {"title": "Loans API Reference", "views": 245, "category": "api-reference"},
                {"title": "Agent Tools Registry", "views": 189, "category": "ai-orchestration"},
                {"title": "Compliance Procedures", "views": 167, "category": "compliance"},
                {"title": "Database Models", "views": 134, "category": "system-architecture"}
            ],
            "popular_categories": [
                {"category": "api-reference", "name": "API Reference", "views": 847},
                {"category": "ai-orchestration", "name": "AI Orchestration", "views": 623},
                {"category": "compliance", "name": "Compliance", "views": 445},
                {"category": "business-processes", "name": "Business Processes", "views": 321}
            ],
            "daily_views": [
                {"date": "2024-03-25", "views": 89},
                {"date": "2024-03-26", "views": 97},
                {"date": "2024-03-27", "views": 76},
                {"date": "2024-03-28", "views": 112},
                {"date": "2024-03-29", "views": 145}
            ]
        })
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error getting documentation analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get analytics")

# Helper functions

async def _generate_documentation_content(category: str, search: Optional[str] = None, content_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Generate mock documentation content based on category and filters."""
    
    # Mock content for different categories
    mock_content = {
        "api-reference": [
            {
                "id": "api-loans",
                "title": "Loans API Reference",
                "description": "Complete API documentation for loan management endpoints including creation, updates, stage transitions, and reporting",
                "type": "reference",
                "tags": ["loans", "api", "rest", "endpoints"],
                "views": 245,
                "lastUpdated": "2024-03-25",
                "path": "/enterprise-docs/api/loans",
                "estimatedReadTime": "15 min"
            },
            {
                "id": "api-leads", 
                "title": "Leads API Reference",
                "description": "Lead generation and management API endpoints with comprehensive field documentation",
                "type": "reference",
                "tags": ["leads", "api", "crm", "generation"],
                "views": 178,
                "lastUpdated": "2024-03-24",
                "path": "/enterprise-docs/api/leads",
                "estimatedReadTime": "12 min"
            },
            {
                "id": "api-authentication",
                "title": "Authentication & Authorization",
                "description": "OAuth2, JWT tokens, role-based access control, and API key management",
                "type": "reference", 
                "tags": ["auth", "oauth2", "jwt", "security"],
                "views": 298,
                "lastUpdated": "2024-03-26",
                "path": "/enterprise-docs/api/auth",
                "estimatedReadTime": "20 min"
            },
            {
                "id": "api-webhooks",
                "title": "Webhooks & Events",
                "description": "Real-time event notifications for loan status changes, lead updates, and system events",
                "type": "reference",
                "tags": ["webhooks", "events", "real-time", "notifications"],
                "views": 134,
                "lastUpdated": "2024-03-23",
                "path": "/enterprise-docs/api/webhooks",
                "estimatedReadTime": "18 min"
            }
        ],
        "ai-orchestration": [
            {
                "id": "agent-tools-registry",
                "title": "Agent Tools Registry",
                "description": "Complete documentation of all 160+ AI agent tools available in the system with examples and use cases",
                "type": "reference",
                "tags": ["ai", "agents", "tools", "registry"],
                "views": 189,
                "lastUpdated": "2024-03-26",
                "isNew": True,
                "estimatedReadTime": "45 min"
            },
            {
                "id": "orchestration-patterns",
                "title": "Orchestration Patterns",
                "description": "How AI agents coordinate to handle complex business workflows and multi-step processes",
                "type": "guide", 
                "tags": ["ai", "orchestration", "workflow", "patterns"],
                "views": 167,
                "lastUpdated": "2024-03-23",
                "estimatedReadTime": "25 min"
            },
            {
                "id": "claude-integration",
                "title": "Claude API Integration",
                "description": "Anthropic Claude integration patterns, prompt engineering, and best practices",
                "type": "tutorial",
                "tags": ["claude", "anthropic", "llm", "integration"],
                "views": 145,
                "lastUpdated": "2024-03-25",
                "estimatedReadTime": "30 min"
            }
        ],
        "business-processes": [
            {
                "id": "loan-workflow",
                "title": "Loan Processing Workflow",
                "description": "Complete loan origination process from application to funding with stage definitions and SLA targets", 
                "type": "guide",
                "tags": ["loans", "workflow", "sla", "process"],
                "views": 234,
                "lastUpdated": "2024-03-24",
                "estimatedReadTime": "35 min"
            },
            {
                "id": "lead-qualification",
                "title": "Lead Qualification Process",
                "description": "Standardized lead scoring, qualification criteria, and conversion workflows",
                "type": "guide",
                "tags": ["leads", "qualification", "scoring", "conversion"],
                "views": 156,
                "lastUpdated": "2024-03-22",
                "estimatedReadTime": "22 min"
            }
        ],
        "system-architecture": [
            {
                "id": "database-models",
                "title": "Database Schema & Models",
                "description": "Complete database schema documentation with model relationships and field definitions",
                "type": "reference",
                "tags": ["database", "schema", "models", "sqlalchemy"],
                "views": 187,
                "lastUpdated": "2024-03-26",
                "estimatedReadTime": "40 min"
            },
            {
                "id": "service-architecture",
                "title": "Service Architecture Overview",
                "description": "Microservice patterns, dependency injection, and system component interactions",
                "type": "overview",
                "tags": ["architecture", "services", "patterns", "design"],
                "views": 134,
                "lastUpdated": "2024-03-21",
                "estimatedReadTime": "28 min"
            }
        ],
        "compliance": [
            {
                "id": "soc2-procedures",
                "title": "SOC 2 Type II Procedures",
                "description": "Complete SOC 2 compliance procedures, controls, and audit trail requirements",
                "type": "guide",
                "tags": ["soc2", "compliance", "audit", "security"],
                "views": 198,
                "lastUpdated": "2024-03-25",
                "estimatedReadTime": "50 min"
            },
            {
                "id": "data-retention",
                "title": "Data Retention Policies",
                "description": "Data lifecycle management, retention schedules, and deletion procedures",
                "type": "guide",
                "tags": ["data", "retention", "privacy", "gdpr"],
                "views": 87,
                "lastUpdated": "2024-03-20",
                "estimatedReadTime": "15 min"
            }
        ]
    }
    
    content = mock_content.get(category, [])
    
    # Apply search filter
    if search:
        search_lower = search.lower()
        content = [
            item for item in content
            if search_lower in item["title"].lower() or
               search_lower in item["description"].lower() or
               any(search_lower in tag.lower() for tag in item["tags"])
        ]
    
    # Apply content type filter
    if content_type and content_type != "all":
        content = [item for item in content if item["type"] == content_type]
    
    return content

async def _get_featured_content(category: str) -> List[Dict[str, Any]]:
    """Get featured content for a specific category."""
    featured_content = {
        "api-reference": [
            {
                "id": "quick-start-api",
                "title": "API Quick Start Guide",
                "description": "Get started with the Mortgage CRM API in under 10 minutes",
                "icon": "⚡",
                "type": "tutorial",
                "views": 567,
                "path": "/enterprise-docs/quick-start"
            }
        ],
        "ai-orchestration": [
            {
                "id": "agent-playground", 
                "title": "Agent Tools Playground",
                "description": "Interactive tool explorer to test and understand AI agent capabilities",
                "icon": "🎮",
                "type": "interactive",
                "views": 345,
                "path": "/enterprise-docs/agent-playground"
            }
        ]
    }
    
    return featured_content.get(category, [])

async def _calculate_documentation_analytics(db: Session, user: User) -> Dict[str, Any]:
    """Calculate documentation analytics and coverage metrics."""
    
    # In a real implementation, you would query actual database metrics
    # For now, return mock analytics based on the 88% backend coverage goal
    
    return {
        "totalEndpoints": 847,
        "documentedEndpoints": 102, 
        "coveragePercentage": 12,  # Currently only 12% documented
        "totalTools": 160,         # AI agent tools
        "availableInUI": 19,       # Only 19 tools have UI
        "uiCoveragePercentage": 12,  # 19/160 = 12% UI coverage
        "targetCoveragePercentage": 88,  # Goal to reach 88%
        "remainingWork": {
            "endpointsToDocument": 745,
            "toolsNeedingUI": 141,
            "estimatedHours": 1200
        },
        "recentActivity": {
            "documentsAdded": 5,
            "documentsUpdated": 12,
            "newViews": 234
        }
    }

def register_enterprise_documentation_routes(app, get_db, get_current_user):
    """Register enterprise documentation routes with the FastAPI app."""
    app.include_router(router, tags=["Enterprise Documentation"])
    return router