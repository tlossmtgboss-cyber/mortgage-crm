"""
Fix for Smart AI Chat - Ensures Mission Control logging happens even if AI fails

This modifies the smart-chat endpoint to:
1. Log to Mission Control FIRST
2. Then try to get AI response
3. Log outcome (success or failure)

This way we capture all attempts, not just successful ones.
"""

# The fixed endpoint code that should replace lines 2388-2466 in main.py:

FIXED_ENDPOINT = '''
@app.post("/api/v1/ai/smart-chat")
async def smart_chat_with_memory(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    """
    Enhanced AI chat with conversation memory and context retrieval
    Uses RAG (Retrieval-Augmented Generation) for personalized responses
    """
    action_id = None

    try:
        data = await request.json()
        message = data.get("message", "")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        include_context = data.get("include_context", True)

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # ✅ FIX: Log to Mission Control FIRST (before trying AI response)
        action_id = await log_ai_action_to_mission_control(
            db=db,
            agent_name="Smart AI Chat",
            action_type="conversation",
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=current_user.id,
            context={"message": message[:100], "include_context": include_context},
            autonomy_level="assisted",
            status="pending"
        )

        # Try to get AI response (might fail)
        try:
            from ai_memory_service import context_ai

            result = await context_ai.get_intelligent_response(
                db=db,
                user_id=current_user.id,
                current_message=message,
                lead_id=lead_id,
                loan_id=loan_id,
                include_context=include_context
            )

            # ✅ Update outcome as SUCCESS
            if action_id:
                await update_ai_action_outcome(
                    db=db,
                    action_id=action_id,
                    outcome="success",
                    impact_score=0.7,
                    metadata={
                        "context_used": result.get("context_used", False),
                        "context_count": result.get("context_count", 0),
                        "has_memory": result.get("has_memory", False)
                    }
                )

            return {
                "success": True,
                "response": result.get("response"),
                "context_used": result.get("context_used", False),
                "context_count": result.get("context_count", 0),
                "has_memory": result.get("has_memory", False),
                "metadata": result.get("metadata", {})
            }

        except Exception as ai_error:
            logger.error(f"AI response failed: {ai_error}")

            # ✅ Update outcome as FAILURE (still logged!)
            if action_id:
                await update_ai_action_outcome(
                    db=db,
                    action_id=action_id,
                    outcome="failure",
                    impact_score=0.0,
                    metadata={"error": str(ai_error)}
                )

            # Return fallback response
            return {
                "success": False,
                "response": "I apologize, but I'm having trouble right now. Please try again.",
                "error": str(ai_error)
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in smart chat: {e}")

        # ✅ Try to log failure if we have action_id
        if action_id:
            try:
                await update_ai_action_outcome(
                    db=db,
                    action_id=action_id,
                    outcome="failure",
                    impact_score=0.0,
                    metadata={"error": str(e)}
                )
            except:
                pass

        return {
            "success": False,
            "response": "I apologize, but I'm having trouble right now. Please try again.",
            "error": str(e)
        }
'''

print("=" * 80)
print("SMART AI CHAT LOGGING FIX")
print("=" * 80)
print()
print("This fix ensures Mission Control logging happens BEFORE attempting AI response.")
print()
print("Key changes:")
print("  1. Log to Mission Control immediately when request received")
print("  2. Try to get AI response (might fail)")
print("  3. Log outcome (success OR failure)")
print()
print("Result: ALL Smart AI Chat attempts are logged, even if AI fails!")
print()
print("=" * 80)
print("NEXT STEP: Apply this fix to main.py")
print("=" * 80)
print()
print("Replace lines 2388-2466 in main.py with the code above.")
print()
