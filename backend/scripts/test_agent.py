#!/usr/bin/env python3
"""
Interactive Agent Test Harness

For quick iteration and testing during development.
Run: python scripts/test_agent.py [agent_name]

Examples:
    python scripts/test_agent.py qualification_agent
    python scripts/test_agent.py rate_analysis
    python scripts/test_agent.py pipeline
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Available agents and their descriptions
AVAILABLE_AGENTS = {
    "qualification": "Lead qualification and pre-approval",
    "rate_analysis": "Rate quotes and comparisons",
    "pipeline": "Pipeline status and metrics",
    "compliance": "Compliance checking (TRID, RESPA)",
    "documents": "Document tracking and conditions",
    "leads": "Lead management and nurturing",
    "scheduler": "Appointment scheduling",
    "general": "General assistant",
}


class MockAgent:
    """Mock agent for testing when real agent not available"""

    def __init__(self, name: str):
        self.name = name
        self.last_tool_calls = []
        self.conversation_history = []

    async def run(self, user_input: str) -> str:
        """Process user input"""
        self.conversation_history.append({"role": "user", "content": user_input})

        # Simple response logic for testing
        response = self._generate_response(user_input)

        self.conversation_history.append({"role": "assistant", "content": response})
        return response

    def _generate_response(self, user_input: str) -> str:
        """Generate mock response based on agent type"""
        input_lower = user_input.lower()

        responses = {
            "qualification": f"Based on your input, I'm checking qualification criteria. What's your credit score and target loan amount?",
            "rate_analysis": f"Current rates for conventional loans are around 6.5-7%. Would you like me to compare specific scenarios?",
            "pipeline": f"Your pipeline currently shows active loans in various stages. What specific metrics would you like to see?",
            "compliance": f"I can check TRID, RESPA, and other compliance requirements. What loan would you like me to review?",
            "documents": f"I can track missing documents and conditions. Which loan file should I check?",
            "leads": f"I can help with lead management and follow-up scheduling. What lead information do you need?",
            "scheduler": f"I can help schedule appointments. What date and time works best?",
            "general": f"I'm here to help with your mortgage questions. What would you like to know?",
        }

        return responses.get(self.name, "How can I assist you?")


def get_agent(agent_name: str):
    """Get agent instance by name"""
    try:
        # Try to import actual agent
        if agent_name == "qualification":
            from agents.qualification_agent import QualificationAgent
            return QualificationAgent()
        elif agent_name == "pipeline":
            from agents.tools.pipeline import PipelineAnalyst
            return PipelineAnalyst()
        # Add more agents as needed
    except ImportError:
        pass

    # Fallback to mock agent
    print(f"[Using mock agent for {agent_name}]")
    return MockAgent(agent_name)


async def interactive_test(agent_name: str):
    """Run interactive test session with an agent"""
    agent = get_agent(agent_name)

    print("\n" + "=" * 60)
    print(f"  Testing: {agent_name}")
    print(f"  Description: {AVAILABLE_AGENTS.get(agent_name, 'Custom agent')}")
    print("=" * 60)
    print("\nType 'quit' to exit, 'clear' to reset, 'tools' to see last tool calls\n")

    while True:
        try:
            user_input = input("\033[94mYou:\033[0m ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input.strip():
            continue

        if user_input.lower() == "quit":
            break
        elif user_input.lower() == "clear":
            if hasattr(agent, "conversation_history"):
                agent.conversation_history = []
            print("[Conversation cleared]")
            continue
        elif user_input.lower() == "tools":
            if hasattr(agent, "last_tool_calls"):
                print(f"[Last tool calls: {agent.last_tool_calls}]")
            else:
                print("[No tool call tracking available]")
            continue

        try:
            start_time = datetime.now()
            response = await agent.run(user_input)
            elapsed = (datetime.now() - start_time).total_seconds()

            print(f"\n\033[92mAgent:\033[0m {response}")
            print(f"\033[90m[{elapsed:.2f}s]\033[0m")

            if hasattr(agent, "last_tool_calls") and agent.last_tool_calls:
                print(f"\033[90mTools called: {agent.last_tool_calls}\033[0m")

            print()

        except Exception as e:
            print(f"\n\033[91mError:\033[0m {e}\n")


def list_agents():
    """List available agents"""
    print("\nAvailable agents:")
    print("-" * 40)
    for name, desc in AVAILABLE_AGENTS.items():
        print(f"  {name:15} - {desc}")
    print()


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        list_agents()
        print("Usage: python scripts/test_agent.py <agent_name>")
        print("Example: python scripts/test_agent.py qualification")
        sys.exit(1)

    agent_name = sys.argv[1].lower()

    # Handle common aliases
    aliases = {
        "qual": "qualification",
        "qualify": "qualification",
        "rates": "rate_analysis",
        "rate": "rate_analysis",
        "pipe": "pipeline",
        "comp": "compliance",
        "docs": "documents",
        "doc": "documents",
        "lead": "leads",
        "schedule": "scheduler",
        "sched": "scheduler",
    }
    agent_name = aliases.get(agent_name, agent_name)

    if agent_name not in AVAILABLE_AGENTS and agent_name not in aliases.values():
        print(f"Unknown agent: {agent_name}")
        list_agents()
        sys.exit(1)

    asyncio.run(interactive_test(agent_name))


if __name__ == "__main__":
    main()
