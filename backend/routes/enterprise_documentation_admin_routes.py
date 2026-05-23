"""
Enterprise Documentation Content Management API Routes

Provides CRUD operations for managing documentation content, categories,
and metadata for the Enterprise Documentation Portal.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging
from datetime import datetime

from db import get_db
from auth.dependencies import get_current_user
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/enterprise-docs/admin")

# Pydantic models for content management
class DocumentationContent(BaseModel):
    title: str
    description: str
    content: str
    category: str
    content_type: str
    tags: List[str] = []
    is_featured: bool = False
    is_published: bool = False
    estimated_read_time: Optional[str] = None
    external_url: Optional[str] = None

class DocumentationContentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    content_type: Optional[str] = None
    tags: Optional[List[str]] = None
    is_featured: Optional[bool] = None
    is_published: Optional[bool] = None
    estimated_read_time: Optional[str] = None
    external_url: Optional[str] = None

@router.post("/content")
async def create_documentation_content(
    content_data: DocumentationContent,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new documentation content. Admin only."""
    
    # Check admin permissions
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # In a real implementation, save to database
        # For now, return mock success with generated ID
        content_id = f"doc_{int(datetime.now().timestamp())}"
        
        logger.info(f"Admin {current_user.email} created documentation content: {content_data.title}")
        
        return {
            "id": content_id,
            "title": content_data.title,
            "category": content_data.category,
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "created_by": current_user.email
        }
        
    except Exception as e:
        logger.error(f"Error creating documentation content: {e}")
        raise HTTPException(status_code=500, detail="Failed to create content")

@router.get("/content")
async def list_documentation_content(
    category: Optional[str] = Query(None, description="Filter by category"),
    published: Optional[bool] = Query(None, description="Filter by published status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all documentation content for admin management."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock content list for admin interface
        mock_content = [
            {
                "id": "doc_1",
                "title": "Loans API Reference", 
                "description": "Complete API documentation for loan management",
                "category": "api-reference",
                "content_type": "reference",
                "is_published": True,
                "is_featured": True,
                "views": 245,
                "last_updated": "2024-03-25T10:30:00Z",
                "created_by": "admin@perenniaai.com",
                "tags": ["loans", "api", "rest"]
            },
            {
                "id": "doc_2",
                "title": "Agent Tools Registry",
                "description": "Documentation of all AI agent tools",
                "category": "ai-orchestration", 
                "content_type": "reference",
                "is_published": False,
                "is_featured": False,
                "views": 89,
                "last_updated": "2024-03-26T14:15:00Z",
                "created_by": "admin@perenniaai.com",
                "tags": ["ai", "agents", "tools"]
            }
        ]
        
        # Apply filters
        if category:
            mock_content = [c for c in mock_content if c["category"] == category]
        if published is not None:
            mock_content = [c for c in mock_content if c["is_published"] == published]
        
        # Paginate
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_content = mock_content[start_idx:end_idx]
        
        return {
            "content": paginated_content,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": len(mock_content),
                "total_pages": (len(mock_content) + limit - 1) // limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error listing documentation content: {e}")
        raise HTTPException(status_code=500, detail="Failed to list content")

@router.get("/content/{content_id}")
async def get_documentation_content(
    content_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific documentation content for editing."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock content retrieval
        if content_id == "doc_1":
            return {
                "id": "doc_1",
                "title": "Loans API Reference",
                "description": "Complete API documentation for loan management endpoints",
                "content": "# Loans API Reference\n\nThis document covers all loan management endpoints...",
                "category": "api-reference",
                "content_type": "reference",
                "tags": ["loans", "api", "rest", "endpoints"],
                "is_published": True,
                "is_featured": True,
                "estimated_read_time": "15 min",
                "external_url": None,
                "views": 245,
                "created_at": "2024-03-20T09:00:00Z",
                "updated_at": "2024-03-25T10:30:00Z",
                "created_by": "admin@perenniaai.com"
            }
        else:
            raise HTTPException(status_code=404, detail="Content not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting documentation content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve content")

@router.put("/content/{content_id}")
async def update_documentation_content(
    content_id: str,
    content_update: DocumentationContentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update existing documentation content."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # In a real implementation, update database record
        # For now, return mock success
        
        logger.info(f"Admin {current_user.email} updated documentation content: {content_id}")
        
        return {
            "id": content_id,
            "status": "updated",
            "updated_at": datetime.now().isoformat(),
            "updated_by": current_user.email,
            "changes": content_update.dict(exclude_none=True)
        }
        
    except Exception as e:
        logger.error(f"Error updating documentation content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update content")

@router.delete("/content/{content_id}")
async def delete_documentation_content(
    content_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete documentation content."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # In a real implementation, soft delete or remove from database
        # For now, return mock success
        
        logger.info(f"Admin {current_user.email} deleted documentation content: {content_id}")
        
        return {
            "id": content_id,
            "status": "deleted",
            "deleted_at": datetime.now().isoformat(),
            "deleted_by": current_user.email
        }
        
    except Exception as e:
        logger.error(f"Error deleting documentation content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete content")

@router.post("/content/{content_id}/publish")
async def publish_documentation_content(
    content_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Publish documentation content to make it visible to users."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        logger.info(f"Admin {current_user.email} published documentation content: {content_id}")
        
        return {
            "id": content_id,
            "status": "published",
            "published_at": datetime.now().isoformat(),
            "published_by": current_user.email
        }
        
    except Exception as e:
        logger.error(f"Error publishing documentation content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to publish content")

@router.post("/content/{content_id}/unpublish")
async def unpublish_documentation_content(
    content_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unpublish documentation content to hide it from users."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        logger.info(f"Admin {current_user.email} unpublished documentation content: {content_id}")
        
        return {
            "id": content_id,
            "status": "unpublished",
            "unpublished_at": datetime.now().isoformat(),
            "unpublished_by": current_user.email
        }
        
    except Exception as e:
        logger.error(f"Error unpublishing documentation content {content_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to unpublish content")

@router.get("/stats")
async def get_documentation_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get documentation management statistics."""
    
    if not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Mock statistics for admin dashboard
        return {
            "total_content": 47,
            "published_content": 23,
            "draft_content": 24,
            "featured_content": 5,
            "total_views": 3456,
            "avg_views_per_content": 73.5,
            "top_categories": [
                {"category": "api-reference", "count": 15, "views": 1234},
                {"category": "ai-orchestration", "count": 12, "views": 890},
                {"category": "business-processes", "count": 8, "views": 567},
                {"category": "compliance", "count": 7, "views": 445}
            ],
            "recent_activity": [
                {"action": "created", "content": "Database Models", "user": "admin@perenniaai.com", "timestamp": "2024-03-26T14:30:00Z"},
                {"action": "published", "content": "API Authentication", "user": "admin@perenniaai.com", "timestamp": "2024-03-26T13:15:00Z"},
                {"action": "updated", "content": "Agent Tools", "user": "admin@perenniaai.com", "timestamp": "2024-03-26T12:00:00Z"}
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting documentation stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

# Helper function
def _is_admin_user(user: User) -> bool:
    """Check if user has admin privileges for content management."""
    # Check if user is admin or has content management permissions
    return (
        user.role == "admin" or 
        user.permission_role == "admin" or
        hasattr(user, 'is_admin') and user.is_admin or
        user.email in ["admin@perenniaai.com"]  # Master admin
    )

def register_content_management_routes(app, get_db, get_current_user):
    """Register content management routes with the FastAPI app.""" 
    app.include_router(router, tags=["Enterprise Documentation Admin"])
    return router