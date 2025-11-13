#!/usr/bin/env python3
"""
Initialize AI system - Register agents and tools ONLY (skip migration).
This script assumes migration already completed successfully.
"""
import asyncio
import os
from sqlalchemy import create_engine, text
from ai_agent_definitions import ALL_AGENTS, TOOL_DEFINITIONS
from ai_tool_handlers import TOOL_HANDLERS
from ai_services import AgentRegistry, ToolRegistry

print("=" * 70)
print("🤖 AI SYSTEM INITIALIZATION (SKIP MIGRATION)")
print("=" * 70)
print()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set")
    exit(1)

engine = create_engine(DATABASE_URL)

# Initialize registries
agent_registry = AgentRegistry(engine)
tool_registry = ToolRegistry(engine)


async def main():
    """Main initialization workflow"""

    # Step 1: Verify migration completed
    print("Step 1: Verifying migration...")
    print("-" * 70)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'ai_agents'"))
        if result.scalar() == 0:
            print("❌ Migration not complete! ai_agents table doesn't exist")
            print("   Run: railway run python3 run_ai_migration.py")
            return False

    print("✅ Migration verified - ai_agents table exists")
    print()

    # Step 2: Register agents
    print("Step 2: Registering Agents")
    print("-" * 70)

    registered_count = 0
    for agent in ALL_AGENTS:
        try:
            await agent_registry.register_agent(agent)
            print(f"✅ Registered: {agent.name} ({agent.id})")
            registered_count += 1
        except Exception as e:
            print(f"⚠️  Warning - {agent.name}: {str(e)[:100]}")

    print()
    print(f"Successfully registered {registered_count}/{len(ALL_AGENTS)} agents")
    print()

    # Step 3: Register tools
    print("Step 3: Registering Tools")
    print("-" * 70)

    registered_tools = 0
    for tool in TOOL_DEFINITIONS:
        try:
            handler = TOOL_HANDLERS.get(tool.name)
            if not handler:
                print(f"⚠️  No handler for: {tool.name}")
                continue

            await tool_registry.register_tool(tool, handler)
            print(f"✅ Registered: {tool.name}")
            registered_tools += 1
        except Exception as e:
            print(f"⚠️  Warning - {tool.name}: {str(e)[:100]}")

    print()
    print(f"Successfully registered {registered_tools}/{len(TOOL_DEFINITIONS)} tools")
    print()

    # Step 4: Create initial prompt versions
    print("Step 4: Creating Initial Prompts")
    print("-" * 70)

    created_prompts = 0
    with engine.connect() as conn:
        for agent in ALL_AGENTS:
            try:
                # Create version 1 prompt for each agent
                default_prompt = f"You are {agent.name}. {agent.description}\\n\\nYour goals:\\n" + "\\n".join(f"- {goal}" for goal in agent.goals)

                conn.execute(text("""
                    INSERT INTO ai_prompt_versions (agent_id, version, prompt_text, status, activated_at)
                    VALUES (:agent_id, 1, :prompt, 'active', NOW())
                    ON CONFLICT (agent_id, version) DO NOTHING
                """), {"agent_id": agent.id, "prompt": default_prompt})
                conn.commit()

                print(f"✅ Created prompt for {agent.id}")
                created_prompts += 1
            except Exception as e:
                print(f"⚠️  Warning - {agent.id}: {str(e)[:100]}")

    print()
    print(f"Successfully created {created_prompts}/{len(ALL_AGENTS)} prompts")
    print()

    # Step 5: Verification
    print("Step 5: Verification")
    print("-" * 70)

    with engine.connect() as conn:
        # Check agents
        result = conn.execute(text("SELECT COUNT(*) FROM ai_agents"))
        agents_count = result.scalar()
        print(f"✅ Agents registered: {agents_count}")

        # Check tools
        result = conn.execute(text("SELECT COUNT(*) FROM ai_tools"))
        tools_count = result.scalar()
        print(f"✅ Tools registered: {tools_count}")

        # Check prompts
        result = conn.execute(text("SELECT COUNT(*) FROM ai_prompt_versions WHERE status = 'active'"))
        prompts_count = result.scalar()
        print(f"✅ Prompts created: {prompts_count}")

    print()
    print("=" * 70)
    print("🎉 AI SYSTEM INITIALIZATION COMPLETE!")
    print("=" * 70)
    print()
    print("✅ AI system is ready!")
    print()

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
