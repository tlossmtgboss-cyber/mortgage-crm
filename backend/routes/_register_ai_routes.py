"""
AI & ML route registrations.

Routes: AI chat, orchestrator, context, metrics, workflows, knowledge base,
underwriting, file analysis, assistant, feedback, email conversations, tools registry.
"""
import logging

logger = logging.getLogger(__name__)


def register_ai_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register AI and ML routes."""
    from fastapi import Depends
    from database import engine

    # AI Orchestrator Chat routes (streaming AI chat with SSE)
    try:
        from routes.ai_chat_routes import register_ai_chat_routes
        register_ai_chat_routes(app, get_db, get_current_user_flexible, **kwargs)
        logger.info("AI orchestrator chat routes loaded (extracted)")
    except Exception as e:
        logger.warning(f"AI chat routes failed: {e}")

    # Include AI Underwriter routes
    try:
        from routes.ai_underwriter_routes import router as ai_underwriter_router, set_dependencies as set_ai_uw_deps
        set_ai_uw_deps(get_db, get_current_user)
        app.include_router(ai_underwriter_router, tags=["AI Underwriter"])
        logger.info("AI Underwriter routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Underwriter routes: {e}")

    # Include SSE Streaming Chat routes
    try:
        from routes.sse_streaming_chat_routes import router as sse_chat_router
        app.include_router(sse_chat_router, tags=["AI Streaming"])
        logger.info("SSE Streaming Chat routes loaded")
    except Exception as e:
        logger.warning(f"Could not load SSE Streaming Chat routes: {e}")

    # Include Chat and Screenshot Parsing routes
    try:
        from routes.chat_screenshot_routes import router as chat_screenshot_router
        app.include_router(chat_screenshot_router, tags=["Chat", "Screenshot Parsing"])
        logger.info("Chat and Screenshot Parsing routes loaded")
    except Exception as e:
        logger.warning(f"Could not load Chat and Screenshot Parsing routes: {e}")

    # Include AI Preferences routes
    try:
        from routes.ai_preferences_routes import router as ai_preferences_router
        app.include_router(ai_preferences_router, tags=["AI Preferences"])
        logger.info("AI Preferences routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Preferences routes: {e}")

    # Include AI Memory and Smart Chat routes
    try:
        from routes.ai_memory_chat_routes import router as ai_memory_chat_router
        app.include_router(ai_memory_chat_router, tags=["AI Memory Chat"])
        logger.info("AI Memory Chat routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Memory Chat routes: {e}")

    # Include AI Orchestrator Chat routes
    try:
        from routes.ai_orchestrator_routes import router as ai_orchestrator_router
        app.include_router(ai_orchestrator_router, tags=["AI Orchestrator"])
        logger.info("AI Orchestrator Chat routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Orchestrator Chat routes: {e}")

    # Include AI Smart File Analysis routes
    try:
        from routes.ai_file_analysis_routes import router as ai_file_analysis_router, set_dependencies as set_ai_file_deps
        set_ai_file_deps(get_db, get_current_user)
        app.include_router(ai_file_analysis_router, tags=["AI File Analysis"])
        logger.info("AI Smart File Analysis routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Smart File Analysis routes: {e}")

    # Include AI Context routes
    try:
        from routes.ai_context_routes import router as ai_context_router
        app.include_router(ai_context_router, tags=["AI Context"])
        logger.info("AI Context routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Context routes: {e}")

    # Include AI Metrics Dashboard routes
    try:
        from routes.ai_metrics_dashboard_routes import router as ai_metrics_dashboard_router
        app.include_router(ai_metrics_dashboard_router, tags=["AI Metrics Dashboard"])
        logger.info("AI Metrics Dashboard routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Metrics Dashboard routes: {e}")

    # Include AI Knowledge Base routes
    try:
        from routes.ai_knowledge_base_routes import router as ai_knowledge_base_router
        app.include_router(ai_knowledge_base_router, tags=["AI Knowledge Base"])
        logger.info("AI Knowledge Base routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Knowledge Base routes: {e}")

    # Include AI Underwriting Analysis routes
    try:
        from routes.ai_underwriting_analysis_routes import router as ai_underwriting_analysis_router
        app.include_router(ai_underwriting_analysis_router, tags=["AI Underwriting Analysis"])
        logger.info("AI Underwriting Analysis routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Underwriting Analysis routes: {e}")

    # Include AI Workflow routes
    try:
        from routes.ai_workflow_routes import router as ai_workflow_router
        app.include_router(ai_workflow_router, tags=["AI Workflows"])
        logger.info("AI Workflow routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Workflow routes: {e}")

    # Include AI Assistant routes
    try:
        from routes.ai_assistant_routes import router as ai_assistant_router
        app.include_router(ai_assistant_router, tags=["AI Assistant"])
        logger.info("AI Assistant routes loaded")
    except Exception as e:
        logger.warning(f"Could not load AI Assistant routes: {e}")

    # Include AI Feedback routes
    try:
        from routes.ai_feedback_routes import router as ai_feedback_router
        from routes import ai_feedback_routes
        ai_feedback_routes.set_dependencies(get_db, get_current_user)
        ai_feedback_routes.ensure_tables_exist(engine)
        app.include_router(ai_feedback_router, prefix="/api/v1/ai-feedback", tags=["AI Feedback"])
        logger.info("AI Feedback routes loaded")
    except Exception as e:
        logger.warning(f"AI Feedback routes not loaded: {e}")

    # Include AI Metrics routes (hallucination tracking, performance metrics)
    try:
        from routes.ai_metrics_routes import router as ai_metrics_router
        app.include_router(ai_metrics_router, prefix="/api/v1/ai-metrics", tags=["AI Metrics"])
        logger.info("AI Metrics routes loaded")
    except Exception as e:
        logger.warning(f"AI Metrics routes not loaded: {e}")

    # AI Email Conversations (Two-Way AI Communication)
    try:
        from routes.ai_email_conversation_routes import router as ai_email_conv_router
        app.include_router(ai_email_conv_router, prefix="/api/v1/ai-email", tags=["AI Email Conversations"])
        logger.info("AI Email Conversation routes loaded")
    except Exception as e:
        logger.warning(f"AI Email Conversation routes not loaded: {e}")

    # AI Email Search Routes
    try:
        from routes.ai_email_search_routes import router as ai_email_search_router
        app.include_router(ai_email_search_router, tags=["AI Email Search"])
        logger.info("AI Email Search routes loaded")
    except Exception as e:
        logger.warning(f"AI Email Search routes not loaded: {e}")

    # AI Tools Registry & Unified Tool Endpoints
    tools_router_error = None
    try:
        from tools.router import router as tools_router
        app.include_router(tools_router, tags=["AI Tools"])
        logger.info("AI Tools Registry routes loaded")
    except Exception as e:
        tools_router_error = str(e)
        import traceback
        logger.warning(f"AI Tools Registry routes not loaded: {e}")
        logger.warning(f"Full traceback: {traceback.format_exc()}")

    # AI Task Automation routes
    try:
        from ai_automation_routes import router as ai_automation_router
        app.include_router(ai_automation_router, tags=["AI Task Automation"])
    except Exception as e:
        logger.warning(f"AI Task Automation routes not loaded: {e}")

    # AI API routes
    try:
        from ai_api_endpoints import router as ai_router
        app.include_router(ai_router, tags=["AI System"])
    except Exception as e:
        logger.warning(f"AI System routes not loaded: {e}")

    # AI Insights routes for profitability
    try:
        from ai_insights_routes import router as ai_insights_router
        app.include_router(ai_insights_router, tags=["AI Profitability Insights"])
    except Exception as e:
        logger.warning(f"AI Profitability Insights routes not loaded: {e}")

    # AI Daily Blog + PDF Content Factory routes
    try:
        from blog_routes import router as blog_router
        app.include_router(blog_router, tags=["AI Daily Blog"])
    except Exception as e:
        logger.warning(f"AI Daily Blog routes not loaded: {e}")

    # AI Email Settings routes
    ai_email_settings_error = None
    try:
        from routes.ai_email_settings_routes import router as ai_email_settings_router, AIEmailSettings
        app.include_router(ai_email_settings_router, tags=["AI Email Settings"])
        AIEmailSettings.__table__.create(bind=engine, checkfirst=True)
        logger.info("AI Email Settings routes loaded")
    except Exception as e:
        ai_email_settings_error = str(e)
        import traceback
        ai_email_settings_error = traceback.format_exc()
        logger.warning(f"AI Email Settings routes not loaded: {e}")

    # AI Outreach routes
    ai_outreach_error = None
    try:
        from routes.ai_outreach_routes import router as ai_outreach_router, create_outreach_table
        app.include_router(ai_outreach_router, tags=["AI Outreach"])
        create_outreach_table(engine)
        logger.info("AI Outreach routes loaded")
    except Exception as e:
        ai_outreach_error = str(e)
        import traceback
        ai_outreach_error = traceback.format_exc()
        logger.warning(f"AI Outreach routes not loaded: {e}")

    # Automated Outreach routes (drip campaigns + triggers)
    automated_outreach_error = None
    try:
        from routes.automated_outreach_routes import router as automated_outreach_router, create_automated_outreach_tables
        app.include_router(automated_outreach_router, tags=["Automated Outreach"])
        create_automated_outreach_tables(engine)
        logger.info("Automated Outreach routes loaded")
    except Exception as e:
        automated_outreach_error = str(e)
        import traceback
        automated_outreach_error = traceback.format_exc()
        logger.warning(f"Automated Outreach routes not loaded: {e}")

    # Agent Governance routes
    try:
        from routes.agent_governance_routes import router as agent_governance_router
        app.include_router(agent_governance_router, tags=["Agent Governance"])
        logger.info("Agent Governance routes loaded")
    except Exception as e:
        logger.warning(f"Agent Governance routes not loaded: {e}")

    # Agent Governance Settings routes
    try:
        from routes.agent_governance_settings_routes import router as agent_governance_settings_router
        app.include_router(agent_governance_settings_router, tags=["Agent Governance Settings"])
        logger.info("Agent Governance Settings routes loaded")
    except Exception as e:
        logger.warning(f"Agent Governance Settings routes not loaded: {e}")

    # Agent Gym routes
    try:
        from routes.agent_gym_routes import router as agent_gym_router
        app.include_router(agent_gym_router, tags=["Agent Gym"])
        logger.info("Agent Gym routes loaded")
    except Exception as e:
        logger.warning(f"Agent Gym routes not loaded: {e}")

    # Agent Chat routes
    try:
        from routes.agent_chat_routes import router as agent_chat_router
        app.include_router(agent_chat_router, tags=["Agent Chat"])
        logger.info("Agent Chat routes loaded")
    except Exception as e:
        logger.warning(f"Agent Chat routes not loaded: {e}")

    # AI Feedback Collection routes (inline thumbs-up/down on AI responses)
    try:
        from routes.ai_feedback_collection_routes import router as ai_feedback_collection_router
        app.include_router(ai_feedback_collection_router, tags=["AI Feedback Collection"])
        logger.info("AI Feedback Collection routes loaded")
    except Exception as e:
        logger.warning(f"AI Feedback Collection routes not loaded: {e}")

    # Agent WebSocket routes
    try:
        from routes.agent_websocket import router as agent_websocket_router
        app.include_router(agent_websocket_router, tags=["Agent WebSocket"])
        logger.info("Agent WebSocket routes loaded")
    except Exception as e:
        logger.warning(f"Agent WebSocket routes not loaded: {e}")

    # Agent Orchestration routes
    try:
        from api.v1.agents import router as agent_orchestration_router
        app.include_router(agent_orchestration_router, tags=["Agent Orchestration"])
        logger.info("Agent Orchestration routes loaded")
    except Exception as e:
        logger.warning(f"Agent Orchestration routes not loaded: {e}")

    # Phase 4 AI Learning & Optimization routes
    try:
        from routes.phase4_routes import ai_learning_router, meta_agent_router
        app.include_router(ai_learning_router, tags=["AI Learning"])
        app.include_router(meta_agent_router, tags=["Continuous Learning Meta-Agent"])
        logger.info("Phase 4 AI Learning & Optimization routes loaded")
    except Exception as e:
        logger.warning(f"Phase 4 routes not loaded: {e}")

    # Phase 6 Advanced AI Orchestration & Automation routes
    try:
        from routes.phase6_routes import workflow_router, predictive_router, agent_coordination_router, healing_router
        app.include_router(workflow_router, tags=["Advanced Workflow Orchestration"])
        app.include_router(predictive_router, tags=["Predictive AI & Recommendations"])
        app.include_router(agent_coordination_router, tags=["AI Agent Coordination"])
        app.include_router(healing_router, tags=["Self-Healing System"])
        logger.info("Phase 6 Advanced AI Orchestration routes loaded")
    except Exception as e:
        logger.warning(f"Phase 6 routes not loaded: {e}")

    # Debug endpoint for tools registry loading
    @app.get("/api/v1/debug/tools-registry-status")
    async def debug_tools_registry_status(current_user=Depends(get_current_user)):
        """Debug endpoint to check tools registry loading status"""
        return {
            "tools_router_loaded": tools_router_error is None
        }

    logger.info("AI & ML route group loaded")
