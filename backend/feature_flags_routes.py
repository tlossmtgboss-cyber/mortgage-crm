"""
Feature Flags Routes - API endpoints for Feature Visibility Management

Provides endpoints to:
- List available features
- Control feature visibility
- Manage company feature access
- Track feature audit logs
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from database import get_db, Base
from routes.auth_deps import require_auth

# Import models using lazy loading to avoid circular imports
from models.feature_flags import (
    DevelopmentStatus,
    FeatureCategory,
    create_feature_models,
    DEFAULT_FEATURES
)

router = APIRouter(prefix="/api/v1/features", tags=["features"], dependencies=[Depends(require_auth)])

# Create model classes with proper Base
SystemFeature, CompanyFeatureAccess, FeatureAuditLog = create_feature_models(Base)


# ============ Pydantic Schemas ============

class FeatureResponse(BaseModel):
    """Response schema for a feature"""
    id: int
    feature_key: str
    feature_name: str
    description: Optional[str]
    category: str
    icon: str
    route_path: Optional[str]
    development_status: str
    is_globally_enabled: bool
    is_premium: bool
    base_price: float
    sort_order: int

    class Config:
        from_attributes = True


class FeatureAccessResponse(BaseModel):
    """Response schema for feature access"""
    id: int
    company_id: int
    feature_key: str
    is_enabled: bool
    enabled_at: Optional[datetime]
    is_trial: bool
    trial_start: Optional[datetime]
    trial_end: Optional[datetime]
    custom_config: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class FeatureAccessUpdate(BaseModel):
    """Schema for updating feature access"""
    is_enabled: bool
    is_trial: Optional[bool] = False
    trial_days: Optional[int] = None


class BulkFeatureAccessUpdate(BaseModel):
    """Schema for bulk updating feature access"""
    feature_keys: List[str]
    is_enabled: bool


class FeatureUpdateRequest(BaseModel):
    """Schema for updating a feature (admin only)"""
    development_status: Optional[str] = None
    is_globally_enabled: Optional[bool] = None
    is_premium: Optional[bool] = None
    base_price: Optional[float] = None
    description: Optional[str] = None


class UserVisibleFeaturesResponse(BaseModel):
    """Response schema for features visible to a user"""
    features: List[FeatureResponse]
    enabled_features: List[str]
    has_premium_access: bool


# ============ Helper Functions ============

def get_current_company_id(request: Request) -> int:
    """Get current company ID from request context"""
    from auth.tokens import verify_access_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        company_id = payload.get("company_id")
        if not company_id:
            raise HTTPException(status_code=401, detail="Token missing company_id")
        return company_id
    raise HTTPException(status_code=401, detail="Authentication required")


def get_current_user_id(request: Request) -> int:
    """Get current user ID from request context"""
    from auth.tokens import verify_access_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        if "user_id" in payload:
            return payload["user_id"]
        raise HTTPException(status_code=401, detail="Token missing user_id")
    raise HTTPException(status_code=401, detail="Authentication required")


def log_feature_audit(
    db: Session,
    feature_key: str,
    action: str,
    company_id: int = None,
    user_id: int = None,
    old_value: Dict = None,
    new_value: Dict = None,
    request: Request = None
):
    """Create an audit log entry"""
    audit = FeatureAuditLog(
        feature_key=feature_key,
        company_id=company_id,
        user_id=user_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None
    )
    db.add(audit)
    db.commit()


# ============ Feature Management Endpoints ============

@router.get("/available", response_model=List[FeatureResponse])
async def list_available_features(
    include_development: bool = False,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all available features.

    - By default, only shows stable and beta features
    - Set include_development=True for admin view to see all features
    - Optionally filter by category
    """
    query = db.query(SystemFeature).filter(
        SystemFeature.is_globally_enabled == True
    )

    if not include_development:
        query = query.filter(
            SystemFeature.development_status.in_(["stable", "beta"])
        )

    if category:
        query = query.filter(SystemFeature.category == category)

    features = query.order_by(SystemFeature.sort_order).all()
    return features


@router.get("/all", response_model=List[FeatureResponse])
async def list_all_features(
    db: Session = Depends(get_db)
):
    """
    List ALL features including development ones.
    Admin-only endpoint for feature management.
    """
    features = db.query(SystemFeature).order_by(SystemFeature.sort_order).all()
    return features


@router.get("/user-visible")
async def get_user_visible_features(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get features visible to the current user based on their company's access.

    This is the main endpoint for frontend to determine what to show.
    """
    company_id = get_current_company_id(request)

    # Get all non-development features
    all_features = db.query(SystemFeature).filter(
        SystemFeature.is_globally_enabled == True,
        SystemFeature.development_status.in_(["stable", "beta"])
    ).order_by(SystemFeature.sort_order).all()

    # Get company's enabled features
    company_access = db.query(CompanyFeatureAccess).filter(
        CompanyFeatureAccess.company_id == company_id,
        CompanyFeatureAccess.is_enabled == True
    ).all()

    enabled_keys = {access.feature_key for access in company_access}

    # Filter to only show enabled features
    visible_features = [f for f in all_features if f.feature_key in enabled_keys]

    return {
        "features": [f.to_dict() for f in visible_features],
        "enabled_features": list(enabled_keys),
        "has_premium_access": any(
            f.is_premium for f in visible_features
        )
    }


@router.get("/categories")
async def list_feature_categories():
    """Get list of feature categories with metadata"""
    return {
        "categories": [
            {"key": "ai_tools", "label": "AI Tools", "icon": "Brain"},
            {"key": "communication", "label": "Communication", "icon": "MessageSquare"},
            {"key": "analytics", "label": "Analytics", "icon": "BarChart"},
            {"key": "operations", "label": "Operations", "icon": "Settings"},
            {"key": "administration", "label": "Administration", "icon": "Shield"},
            {"key": "integrations", "label": "Integrations", "icon": "Plug"}
        ]
    }


# ============ Company Feature Access Endpoints ============

@router.get("/company/{company_id}/access")
async def get_company_feature_access(
    company_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all feature access settings for a company.
    Used by admin when setting up company features.
    """
    # Get all available features
    all_features = db.query(SystemFeature).filter(
        SystemFeature.is_globally_enabled == True
    ).order_by(SystemFeature.sort_order).all()

    # Get company's current access
    access_records = db.query(CompanyFeatureAccess).filter(
        CompanyFeatureAccess.company_id == company_id
    ).all()

    access_map = {a.feature_key: a for a in access_records}

    # Build response with access status for each feature
    result = []
    for feature in all_features:
        access = access_map.get(feature.feature_key)
        result.append({
            **feature.to_dict(),
            "access": {
                "is_enabled": access.is_enabled if access else False,
                "is_trial": access.is_trial if access else False,
                "trial_end": access.trial_end.isoformat() if access and access.trial_end else None,
                "enabled_at": access.enabled_at.isoformat() if access and access.enabled_at else None
            }
        })

    return {"features": result}


@router.put("/company/{company_id}/access/{feature_key}")
async def update_company_feature_access(
    company_id: int,
    feature_key: str,
    update: FeatureAccessUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update feature access for a company.
    """
    # Verify feature exists
    feature = db.query(SystemFeature).filter(
        SystemFeature.feature_key == feature_key
    ).first()

    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    # Get or create access record
    access = db.query(CompanyFeatureAccess).filter(
        CompanyFeatureAccess.company_id == company_id,
        CompanyFeatureAccess.feature_key == feature_key
    ).first()

    old_value = access.to_dict() if access else None

    if not access:
        access = CompanyFeatureAccess(
            company_id=company_id,
            feature_key=feature_key
        )
        db.add(access)

    # Update access
    access.is_enabled = update.is_enabled
    access.is_trial = update.is_trial or False

    if update.is_enabled:
        access.enabled_at = datetime.now(timezone.utc)
        access.enabled_by = get_current_user_id(request)

    if update.is_trial and update.trial_days:
        from datetime import timedelta
        access.trial_start = datetime.now(timezone.utc)
        access.trial_end = datetime.now(timezone.utc) + timedelta(days=update.trial_days)

    db.commit()
    db.refresh(access)

    # Log audit
    log_feature_audit(
        db=db,
        feature_key=feature_key,
        action="enabled" if update.is_enabled else "disabled",
        company_id=company_id,
        user_id=get_current_user_id(request),
        old_value=old_value,
        new_value=access.to_dict(),
        request=request
    )

    return access.to_dict()


@router.post("/company/{company_id}/access/bulk")
async def bulk_update_company_feature_access(
    company_id: int,
    update: BulkFeatureAccessUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Bulk update feature access for a company.
    Used when setting up multiple features at once.
    """
    results = []

    for feature_key in update.feature_keys:
        # Verify feature exists
        feature = db.query(SystemFeature).filter(
            SystemFeature.feature_key == feature_key
        ).first()

        if not feature:
            results.append({"feature_key": feature_key, "status": "not_found"})
            continue

        # Get or create access record
        access = db.query(CompanyFeatureAccess).filter(
            CompanyFeatureAccess.company_id == company_id,
            CompanyFeatureAccess.feature_key == feature_key
        ).first()

        if not access:
            access = CompanyFeatureAccess(
                company_id=company_id,
                feature_key=feature_key
            )
            db.add(access)

        access.is_enabled = update.is_enabled
        if update.is_enabled:
            access.enabled_at = datetime.now(timezone.utc)
            access.enabled_by = get_current_user_id(request)

        results.append({"feature_key": feature_key, "status": "updated", "is_enabled": update.is_enabled})

    db.commit()

    return {"results": results, "total_updated": len([r for r in results if r.get("status") == "updated"])}


# ============ Admin Feature Management ============

@router.put("/admin/{feature_key}")
async def admin_update_feature(
    feature_key: str,
    update: FeatureUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to update feature settings.
    Can change development status, pricing, etc.
    """
    feature = db.query(SystemFeature).filter(
        SystemFeature.feature_key == feature_key
    ).first()

    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    old_value = feature.to_dict()

    if update.development_status is not None:
        feature.development_status = update.development_status
    if update.is_globally_enabled is not None:
        feature.is_globally_enabled = update.is_globally_enabled
    if update.is_premium is not None:
        feature.is_premium = update.is_premium
    if update.base_price is not None:
        feature.base_price = update.base_price
    if update.description is not None:
        feature.description = update.description

    feature.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(feature)

    # Log audit
    log_feature_audit(
        db=db,
        feature_key=feature_key,
        action="feature_updated",
        user_id=get_current_user_id(request),
        old_value=old_value,
        new_value=feature.to_dict(),
        request=request
    )

    return feature.to_dict()


# ============ Migration Endpoints ============

@router.post("/migrate/create-tables")
async def create_feature_tables(db: Session = Depends(get_db)):
    """
    Create feature flag tables in the database.
    Run this once to set up the feature system.
    """
    try:
        # Create tables using SQLAlchemy
        SystemFeature.__table__.create(bind=db.get_bind(), checkfirst=True)
        CompanyFeatureAccess.__table__.create(bind=db.get_bind(), checkfirst=True)
        FeatureAuditLog.__table__.create(bind=db.get_bind(), checkfirst=True)

        return {
            "success": True,
            "message": "Feature tables created successfully",
            "tables": ["system_features", "company_feature_access", "feature_audit_log"]
        }
    except Exception as e:
        return {"success": False, "error": "Internal server error"}


@router.post("/migrate/seed-features")
async def seed_default_features(db: Session = Depends(get_db)):
    """
    Seed the default features into the database.
    This populates the system_features table with all platform features.
    """
    try:
        seeded = []
        skipped = []

        for feature_data in DEFAULT_FEATURES:
            # Check if feature already exists
            existing = db.query(SystemFeature).filter(
                SystemFeature.feature_key == feature_data["feature_key"]
            ).first()

            if existing:
                skipped.append(feature_data["feature_key"])
                continue

            # Create new feature
            feature = SystemFeature(**feature_data)
            db.add(feature)
            seeded.append(feature_data["feature_key"])

        db.commit()

        return {
            "success": True,
            "message": f"Seeded {len(seeded)} features, skipped {len(skipped)} existing",
            "seeded": seeded,
            "skipped": skipped
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/migrate/full-setup")
async def full_feature_setup(db: Session = Depends(get_db)):
    """
    Complete setup: create tables and seed default features.
    Convenience endpoint for initial deployment.
    """
    # Create tables
    table_result = await create_feature_tables(db)
    if not table_result.get("success"):
        return table_result

    # Seed features
    seed_result = await seed_default_features(db)

    return {
        "success": True,
        "message": "Feature system fully set up",
        "tables_created": table_result.get("tables"),
        "features_seeded": seed_result.get("seeded", []),
        "features_skipped": seed_result.get("skipped", [])
    }


# ============ Audit Log Endpoints ============

@router.get("/audit-log")
async def get_feature_audit_log(
    feature_key: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get feature audit log entries.
    For compliance and troubleshooting.
    """
    query = db.query(FeatureAuditLog)

    if feature_key:
        query = query.filter(FeatureAuditLog.feature_key == feature_key)
    if company_id:
        query = query.filter(FeatureAuditLog.company_id == company_id)

    logs = query.order_by(FeatureAuditLog.created_at.desc()).limit(limit).all()

    return {
        "logs": [log.to_dict() for log in logs],
        "count": len(logs)
    }
