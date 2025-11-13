#!/usr/bin/env python3
"""
Initialize AI Architecture System
Runs migration, registers agents, and sets up tools
"""

import os
import sys
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import AI components
from ai_agent_definitions import ALL_AGENTS, TOOL_DEFINITIONS
from ai_services import AgentRegistry, ToolRegistry
from ai_models import ToolContext

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


print("=" * 70)
print("🤖 AI ARCHITECTURE INITIALIZATION")
print("=" * 70)
print()


# ============================================================================
# STEP 1: RUN DATABASE MIGRATION
# ============================================================================

def run_migration():
    """Run the AI architecture database migration"""
    print("Step 1: Running database migration...")
    print("-" * 70)

    try:
        with engine.connect() as conn:
            # Read SQL file
            with open("ai_architecture_schema.sql", "r") as f:
                sql = f.read()

            # Execute migration
            conn.execute(text(sql))
            conn.commit()

            print("✅ Migration completed successfully!")
            print()

            # Verify tables
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE 'ai_%'
                ORDER BY table_name
            """))

            tables = [row[0] for row in result.fetchall()]
            print(f"Created {len(tables)} AI tables:")
            for table in tables:
                print(f"  ✅ {table}")
            print()

            return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


# ============================================================================
# STEP 2: REGISTER AGENTS
# ============================================================================

async def register_agents():
    """Register all 7 specialized agents"""
    print("Step 2: Registering agents...")
    print("-" * 70)

    db = SessionLocal()
    registry = AgentRegistry(db)

    registered = []

    try:
        for agent in ALL_AGENTS:
            try:
                agent_id = await registry.register_agent(agent)
                print(f"✅ Registered: {agent.name} ({agent.id})")
                registered.append(agent.name)
            except Exception as e:
                print(f"❌ Failed to register {agent.name}: {e}")

        print()
        print(f"Successfully registered {len(registered)}/{len(ALL_AGENTS)} agents")
        print()

        return True

    except Exception as e:
        print(f"❌ Agent registration failed: {e}")
        return False
    finally:
        db.close()


# ============================================================================
# STEP 3: REGISTER TOOLS
# ============================================================================

async def register_tools():
    """Register all tool definitions"""
    print("Step 3: Registering tools...")
    print("-" * 70)

    db = SessionLocal()
    tool_registry = ToolRegistry(db)

    registered = []

    try:
        for tool in TOOL_DEFINITIONS:
            try:
                # Create a dummy handler for now
                async def dummy_handler(input_data: dict, context: ToolContext):
                    """Placeholder handler - implement actual logic"""
                    return {
                        "success": True,
                        "message": f"Tool {tool.name} executed (placeholder)",
                        "input": input_data
                    }

                tool_id = await tool_registry.register_tool(tool, dummy_handler)
                print(f"✅ Registered: {tool.name} ({tool.category.value})")
                registered.append(tool.name)
            except Exception as e:
                print(f"❌ Failed to register {tool.name}: {e}")

        print()
        print(f"Successfully registered {len(registered)}/{len(TOOL_DEFINITIONS)} tools")
        print()

        return True

    except Exception as e:
        print(f"❌ Tool registration failed: {e}")
        return False
    finally:
        db.close()


# ============================================================================
# STEP 4: CREATE INITIAL PROMPTS
# ============================================================================

async def create_initial_prompts():
    """Create initial prompt versions for agents"""
    print("Step 4: Creating initial prompts...")
    print("-" * 70)

    db = SessionLocal()

    try:
        for agent in ALL_AGENTS:
            # Create default prompt version
            query = text("""
                INSERT INTO ai_prompt_versions (
                    agent_id, version, prompt_text, system_instructions, status
                ) VALUES (
                    :agent_id, 1, :prompt_text, :system_instructions, 'active'
                )
                ON CONFLICT DO NOTHING
            """)

            prompt_text = f"""You are {agent.name}, a specialized AI agent in a mortgage CRM system.

Your Role:
{agent.description}

Your Goals:
{chr(10).join(f"- {goal}" for goal in agent.goals)}

Available Tools:
{chr(10).join(f"- {tool}" for tool in agent.tools)}

When you receive an event, analyze the context and determine the best action to take.
Always consider the goals and use your tools appropriately.
Communicate with other agents when needed.
Escalate to humans when confidence is low or for high-risk actions.
"""

            system_instructions = f"""You are a helpful, proactive AI agent.
Always act in the best interest of the user and the organization.
Be clear, concise, and professional in all communications.
"""

            db.execute(query, {
                "agent_id": agent.id,
                "prompt_text": prompt_text,
                "system_instructions": system_instructions
            })

        db.commit()
        print(f"✅ Created initial prompts for {len(ALL_AGENTS)} agents")
        print()

        return True

    except Exception as e:
        print(f"❌ Prompt creation failed: {e}")
        return False
    finally:
        db.close()


# ============================================================================
# STEP 5: VERIFY SETUP
# ============================================================================

def verify_setup():
    """Verify the AI system is ready"""
    print("Step 5: Verifying setup...")
    print("-" * 70)

    db = SessionLocal()

    try:
        # Count agents
        result = db.execute(text("SELECT COUNT(*) FROM ai_agents WHERE status = 'active'"))
        agent_count = result.fetchone()[0]

        # Count tools
        result = db.execute(text("SELECT COUNT(*) FROM ai_tools WHERE is_active = TRUE"))
        tool_count = result.fetchone()[0]

        # Count prompts
        result = db.execute(text("SELECT COUNT(*) FROM ai_prompt_versions WHERE status = 'active'"))
        prompt_count = result.fetchone()[0]

        print(f"Active Agents: {agent_count}")
        print(f"Active Tools: {tool_count}")
        print(f"Active Prompts: {prompt_count}")
        print()

        if agent_count >= 7 and tool_count >= 10:
            print("✅ AI system is ready!")
            return True
        else:
            print("⚠️  Setup incomplete - some components missing")
            return False

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False
    finally:
        db.close()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Main initialization flow"""
    print("Initializing AI Architecture...")
    print()

    # Step 1: Run migration
    if not run_migration():
        print("❌ Migration failed. Stopping.")
        return False

    # Step 2: Register agents
    if not await register_agents():
        print("❌ Agent registration failed. Stopping.")
        return False

    # Step 3: Register tools
    if not await register_tools():
        print("⚠️  Tool registration incomplete, but continuing...")

    # Step 4: Create prompts
    if not await create_initial_prompts():
        print("⚠️  Prompt creation incomplete, but continuing...")

    # Step 5: Verify
    success = verify_setup()

    print()
    print("=" * 70)
    if success:
        print("🎉 AI ARCHITECTURE INITIALIZATION COMPLETE!")
    else:
        print("⚠️  INITIALIZATION COMPLETED WITH WARNINGS")
    print("=" * 70)
    print()

    if success:
        print("Next Steps:")
        print("1. Test event dispatch:")
        print("   python test_ai_system.py")
        print()
        print("2. View agents in database:")
        print("   SELECT * FROM ai_agents;")
        print()
        print("3. Check execution logs:")
        print("   SELECT * FROM ai_agent_executions;")
        print()
        print("4. Implement tool handlers in ai_tool_handlers.py")
        print()

    return success


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
