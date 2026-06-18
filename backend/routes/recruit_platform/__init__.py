"""
Recruit Platform router package.

router       — authenticated endpoints (tenants, applicants, job CRUD)
public_router — no-auth endpoints (public application form, public job listings)
"""
from fastapi import APIRouter

from routes.recruit_platform.tenants import tenants_router
from routes.recruit_platform.applicants import applicants_router
from routes.recruit_platform.public_application import public_application_router
from routes.recruit_platform.job_postings import job_postings_router, job_postings_public_router

router = APIRouter()
router.include_router(tenants_router)
router.include_router(applicants_router)
router.include_router(job_postings_router)

public_router = APIRouter()
public_router.include_router(public_application_router)
public_router.include_router(job_postings_public_router)
