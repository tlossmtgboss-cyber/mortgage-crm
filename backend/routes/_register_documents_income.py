"""
Documents & Income route registrations.

Routes: Smart docs, portal docs, income, bank statements, estimate parser,
document email import, document drop, document visibility, underwriting guidelines/engine.
"""
import logging

logger = logging.getLogger(__name__)


def register_documents_income_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register document and income management routes."""
    from database import engine

    # Include Document Email Import routes
    try:
        from routes.document_email_import_routes import router as document_email_import_router
        app.include_router(document_email_import_router, tags=["Document Email Import"])
        logger.info("Document Email Import routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Document Email Import routes: {e}")

    # Include Smart Documents routes
    try:
        from routes.smart_docs_routes import router as smart_docs_router
        app.include_router(smart_docs_router, tags=["Smart Documents"])
    except Exception as e:
        logger.warning(f"Could not load smart docs routes: {e}")

    # Include Portal Smart Documents routes
    try:
        from routes.portal_smart_docs_routes import router as portal_smart_docs_router
        app.include_router(portal_smart_docs_router, tags=["Portal Smart Documents"])
        logger.info("Portal Smart Documents routes loaded")
    except Exception as e:
        logger.warning(f"Could not load portal smart docs routes: {e}")

    # Include Document Drop routes (drag-and-drop document upload)
    try:
        from document_drop_routes import router as document_drop_router
        app.include_router(document_drop_router, tags=["Document Drop"])
    except Exception as e:
        logger.warning(f"Document Drop routes not loaded: {e}")

    # Include Income routes (AI-powered income extraction)
    try:
        from routes.income_routes import router as income_router
        app.include_router(income_router, tags=["Income Management"])

        # Auto-create income tables
        try:
            from models.income_models import (
                IncomeSource, PaystubExtraction, Employment,
                SelfEmploymentIncome, RentalIncomeProperty, IncomeCalculationHistory
            )
            for model in [IncomeSource, PaystubExtraction, Employment,
                          SelfEmploymentIncome, RentalIncomeProperty, IncomeCalculationHistory]:
                model.__table__.create(engine, checkfirst=True)
            logger.info("Income tables verified/created")
        except Exception as table_err:
            logger.warning(f"Could not auto-create income tables: {table_err}")

        logger.info("Income Management routes loaded")
    except Exception as e:
        logger.warning(f"Could not load income routes: {e}")

    # Include Bank Statement routes
    try:
        from routes.bank_statement_routes import router as bank_statement_router
        app.include_router(bank_statement_router, tags=["Bank Statement Worksheets"])
        logger.info("Bank Statement Worksheet routes loaded")
    except Exception as e:
        logger.warning(f"Could not load bank statement routes: {e}")

    # Include Income Engine routes
    try:
        from income_engine import income_router as income_engine_router
        app.include_router(income_engine_router, tags=["Income Intelligence Engine"])
        logger.info("Income Intelligence Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load income engine routes: {e}")

    # Include Application Engine routes (URLA audit + Call Intelligence)
    try:
        from routes.application_engine_routes import router as application_engine_router
        app.include_router(application_engine_router, tags=["Application Engine"])
        logger.info("Application Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load application engine routes: {e}")

    # Include Unified Income Calculator routes
    try:
        from routes.unified_income_routes import router as unified_income_router
        app.include_router(unified_income_router, tags=["Unified Income Calculator"])
        logger.info("Unified Income Calculator routes loaded")
    except Exception as e:
        logger.warning(f"Could not load unified income routes: {e}")

    # Include Underwriting Guidelines routes
    try:
        from routes.underwriting_guidelines_routes import router as underwriting_guidelines_router
        app.include_router(underwriting_guidelines_router, tags=["Underwriting Guidelines"])
        logger.info("Underwriting Guidelines routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Underwriting Guidelines routes: {e}")

    # Include AI Underwriting Engine routes
    try:
        from routes.underwriting_engine_routes import router as underwriting_engine_router
        app.include_router(underwriting_engine_router, tags=["AI Underwriting Engine"])
        logger.info("AI Underwriting Engine routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Underwriting Engine routes: {e}")

    # Include Estimate Parser routes
    try:
        from routes.estimate_parser_routes import router as estimate_parser_router
        app.include_router(estimate_parser_router, tags=["Estimate Parser"])
        logger.info("Estimate Parser routes loaded")
    except Exception as e:
        logger.warning(f"Estimate Parser routes not loaded: {e}")

    # Include Workspace Documents routes
    try:
        from routes.workspace_documents_routes import router as workspace_documents_router
        app.include_router(workspace_documents_router, tags=["Workspace Documents"])
        logger.info("Workspace Documents routes loaded")
    except Exception as e:
        logger.warning(f"Workspace Documents routes not loaded: {e}")

    # Document Visibility routes
    try:
        from routes.document_visibility_routes import router as document_visibility_router, set_dependencies as set_doc_visibility_deps
        set_doc_visibility_deps(get_db)
        app.include_router(document_visibility_router, tags=["Document Visibility"])
        logger.info("Document Visibility routes loaded")
    except Exception as e:
        logger.warning(f"Document Visibility routes not loaded: {e}")

    # Document Upload Settings routes
    try:
        from routes.document_upload_settings_routes import router as document_upload_settings_router, set_dependencies as set_document_upload_deps
        from database.models import User
        set_document_upload_deps(User, get_current_user, get_db)
        app.include_router(document_upload_settings_router, tags=["Document Upload Settings"])
        logger.info("Document Upload Settings routes loaded")
    except Exception as e:
        logger.warning(f"Document Upload Settings routes not loaded: {e}")

    logger.info("Documents & Income route group loaded")
