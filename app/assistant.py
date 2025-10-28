            
            async for chunk in generate_streaming_response(request.messages, request.tools, current_user, db):
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:].strip())
                        if data.get("type") == "content":
                            response_content += data.get("data", "")
                    except:
                        continue
            
            return AssistantResponse(
                response=response_content,
                success=True,
                message="Response generated successfully"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

# 
# HEALTH CHECK AND DIAGNOSTICS
# 

@router.get("/health")
async def assistant_health(current_user: User = Depends(require_admin)):
    """Health check endpoint with comprehensive diagnostics"""
    
    api_key_configured = bool(os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    diagnostics = {
        "status": "healthy" if api_key_configured else "degraded",
        "api_key_configured": api_key_configured,
        "model": model,
        "user": current_user.username,
        "available_tools": [
            "createLead",
            "getMonthlyConversionRate", 
            "searchLeads"
        ],
        "features": [
            "streaming_responses",
            "tool_calling", 
            "admin_rbac"
        ]
    }
    
    return diagnostics

@router.get("/test-tools")
async def test_tools_endpoint(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Test endpoint to verify tool execution"""
    
    # Test each tool
    results = {}
    
    # Test createLead
    try:
        lead_result = await create_lead_tool(
            {"fullName": "Test User", "email": "test@example.com"}, 
            db, 
            current_user
        )
        results["createLead"] = lead_result
    except Exception as e:
        results["createLead"] = {"error": str(e)}
    
    # Test getMonthlyConversionRate
    try:
        conversion_result = await get_conversion_rate_tool({}, db, current_user)
        results["getMonthlyConversionRate"] = conversion_result
    except Exception as e:
        results["getMonthlyConversionRate"] = {"error": str(e)}
    
    # Test searchLeads
    try:
        search_result = await search_leads_tool({"query": "test", "limit": 5}, db, current_user)
        results["searchLeads"] = search_result
    except Exception as e:
        results["searchLeads"] = {"error": str(e)}
    
    return {
        "message": "Tool execution test completed",
        "user": current_user.username,
        "results": results
    }
