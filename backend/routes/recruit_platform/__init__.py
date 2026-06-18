"""
Recruit Platform router package.

router        — authenticated endpoints (tenants, applicants, job CRUD, landing pages, chatbot admin, KB)
public_router — no-auth endpoints (public application form, public job listings, landing pages, chatbot)
"""
from fastapi import APIRouter

from routes.recruit_platform.tenants import tenants_router
from routes.recruit_platform.applicants import applicants_router
from routes.recruit_platform.public_application import public_application_router
from routes.recruit_platform.job_postings import job_postings_router, job_postings_public_router
from routes.recruit_platform.landing_pages import router as lp_router, public_router as lp_public_router
from routes.recruit_platform.chatbot import chatbot_router, chatbot_admin_router
from routes.recruit_platform.knowledge_base import kb_router

router = APIRouter()
router.include_router(tenants_router)
router.include_router(applicants_router)
router.include_router(job_postings_router)
router.include_router(lp_router)
router.include_router(chatbot_admin_router)
router.include_router(kb_router)

public_router = APIRouter()
public_router.include_router(public_application_router)
public_router.include_router(job_postings_public_router)
public_router.include_router(lp_public_router)
public_router.include_router(chatbot_router)
