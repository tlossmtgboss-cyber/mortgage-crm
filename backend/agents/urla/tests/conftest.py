"""Stub external dependencies not installed in the local dev environment."""
import sys
import types


def _ensure_stub(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


_STUBS = [
    "livekit",
    "livekit.agents",
    "livekit.agents.llm",
    "livekit.agents.stt",
    "livekit.agents.tts",
    "livekit.agents.pipeline",
    "livekit.agents.voice",
    "livekit.plugins",
    "livekit.plugins.deepgram",
    "livekit.plugins.cartesia",
    "livekit.plugins.openai",
    "livekit.plugins.anthropic",
    "livekit.plugins.silero",
    "livekit.rtc",
    "redis",
    "redis.asyncio",
    "anthropic",
    "cryptography",
    "cryptography.fernet",
]

for _name in _STUBS:
    _ensure_stub(_name)

# LiveKit agent framework expects these classes/callables
_agents = sys.modules["livekit.agents"]
_agents.Agent = type("Agent", (), {"__init__": lambda *a, **kw: None})
_agents.AgentSession = type("AgentSession", (), {})
_agents.RunContext = type("RunContext", (), {})
_agents.WorkerOptions = type("WorkerOptions", (), {"__init__": lambda *a, **kw: None})
_agents.JobContext = type("JobContext", (), {})
_agents.cli = types.ModuleType("livekit.agents.cli")
_agents.cli.run_app = lambda *a, **kw: None

_llm = sys.modules["livekit.agents.llm"]


class _FunctionToolDecorator:
    def __call__(self, f=None, **kw):
        if f is not None:
            return f
        return lambda fn: fn


_llm.function_tool = _FunctionToolDecorator()
_llm.FunctionTool = type("FunctionTool", (), {})

# Fernet stub
_fernet = sys.modules["cryptography.fernet"]
_fernet.Fernet = type(
    "Fernet",
    (),
    {
        "__init__": lambda self, key: None,
        "encrypt": lambda self, data: data,
        "decrypt": lambda self, data: data,
    },
)
