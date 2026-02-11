"""
Perennia AI Tool Registry Loader
Dynamically loads tool definitions from tool_registry.json
"""
import json
import os
import time
import uuid
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Path to tool registry
REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "tool_registry.json")


class ToolRegistry:
    """
    Singleton class to manage the tool registry.
    Loads tool definitions and provides lookup/validation methods.
    """
    _instance = None
    _tools: Dict[str, Dict] = {}
    _domains: Dict[str, Dict] = {}
    _loaded_at: float = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_registry()
        return cls._instance

    def _load_registry(self):
        """Load tool registry from JSON file"""
        try:
            with open(REGISTRY_PATH, 'r') as f:
                registry = json.load(f)

            self._tools = {tool['name']: tool for tool in registry.get('tools', [])}
            self._domains = registry.get('domains', {})
            self._risk_levels = registry.get('risk_levels', {})
            self._approval_required = set(registry.get('approval_required_tools', []))
            self._loaded_at = time.time()

            logger.info(f"Loaded {len(self._tools)} tools from registry")
        except FileNotFoundError:
            logger.warning(f"Tool registry not found at {REGISTRY_PATH}")
            self._tools = {}
            self._domains = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in tool registry: {e}")
            self._tools = {}
            self._domains = {}

    def reload(self):
        """Force reload of the registry"""
        self._load_registry()

    def get_tool(self, name: str) -> Optional[Dict]:
        """Get tool definition by name"""
        return self._tools.get(name)

    def get_all_tools(self) -> Dict[str, Dict]:
        """Get all tool definitions"""
        return self._tools.copy()

    def get_implemented_tools(self) -> Dict[str, Dict]:
        """Get only implemented tools"""
        return {k: v for k, v in self._tools.items() if v.get('implemented', False)}

    def get_tools_by_domain(self, domain: str) -> List[Dict]:
        """Get all tools in a specific domain"""
        return [t for t in self._tools.values() if t.get('domain') == domain]

    def get_domains(self) -> Dict[str, Dict]:
        """Get all domain definitions"""
        return self._domains.copy()

    def requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires user approval"""
        tool = self.get_tool(tool_name)
        if not tool:
            return True  # Unknown tools require approval
        return tool.get('requires_approval', False) or tool_name in self._approval_required

    def get_risk_level(self, tool_name: str) -> str:
        """Get risk level for a tool"""
        tool = self.get_tool(tool_name)
        if not tool:
            return 'critical'  # Unknown tools are critical
        return tool.get('risk_level', 'medium')

    def validate_input(self, tool_name: str, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate input data against tool schema.
        Returns (is_valid, error_message)
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"Unknown tool: {tool_name}"

        schema = tool.get('input_schema', {})
        required = schema.get('required', [])

        # Check required fields
        for field in required:
            if field not in input_data:
                return False, f"Missing required field: {field}"

        # Basic type validation
        properties = schema.get('properties', {})
        for field, value in input_data.items():
            if field in properties:
                expected_type = properties[field].get('type')
                if expected_type == 'string' and not isinstance(value, str):
                    return False, f"Field {field} must be a string"
                elif expected_type == 'integer' and not isinstance(value, int):
                    return False, f"Field {field} must be an integer"
                elif expected_type == 'number' and not isinstance(value, (int, float)):
                    return False, f"Field {field} must be a number"
                elif expected_type == 'boolean' and not isinstance(value, bool):
                    return False, f"Field {field} must be a boolean"
                elif expected_type == 'array' and not isinstance(value, list):
                    return False, f"Field {field} must be an array"

                # Check enum values
                if 'enum' in properties[field]:
                    if value not in properties[field]['enum']:
                        return False, f"Field {field} must be one of: {properties[field]['enum']}"

        return True, None

    def get_openai_tools_format(self) -> List[Dict]:
        """
        Get tools in OpenAI function calling format.
        Only returns implemented tools.
        """
        tools = []
        for name, tool in self._tools.items():
            if not tool.get('implemented', False):
                continue

            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get('description', ''),
                    "parameters": tool.get('input_schema', {"type": "object", "properties": {}})
                }
            })
        return tools

    def get_anthropic_tools_format(self) -> List[Dict]:
        """
        Get tools in Anthropic Claude format.
        Only returns implemented tools.
        """
        tools = []
        for name, tool in self._tools.items():
            if not tool.get('implemented', False):
                continue

            tools.append({
                "name": name,
                "description": tool.get('description', ''),
                "input_schema": tool.get('input_schema', {"type": "object", "properties": {}})
            })
        return tools


def standardized_response(func: Callable) -> Callable:
    """
    Decorator to wrap tool execution with standardized response format.

    Ensures all tools return:
    {
        "success": true/false,
        "data": {},
        "error": null,
        "meta": {
            "tool": "tool_name",
            "request_id": "uuid",
            "elapsed_ms": 0
        }
    }
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = str(uuid.uuid4())
        start_time = time.time()
        tool_name = func.__name__.replace('execute_', '').replace('handle_', '')

        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (time.time() - start_time) * 1000

            # If result is already in standard format, just add meta
            if isinstance(result, dict) and 'success' in result:
                result['meta'] = {
                    "tool": tool_name,
                    "request_id": request_id,
                    "elapsed_ms": round(elapsed_ms, 2)
                }
                return result

            # Wrap raw result in standard format
            return {
                "success": True,
                "data": result,
                "error": None,
                "meta": {
                    "tool": tool_name,
                    "request_id": request_id,
                    "elapsed_ms": round(elapsed_ms, 2)
                }
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Tool {tool_name} failed: {e}")
            return {
                "success": False,
                "data": None,
                "error": "Internal server error",
                "meta": {
                    "tool": tool_name,
                    "request_id": request_id,
                    "elapsed_ms": round(elapsed_ms, 2)
                }
            }

    return wrapper


# Global registry instance
registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Get the global tool registry instance"""
    return registry


def get_tool_for_ai(tool_name: str) -> Optional[Dict]:
    """Convenience function to get a tool for AI use"""
    return registry.get_tool(tool_name)


def list_available_tools() -> List[str]:
    """List all available (implemented) tool names"""
    return list(registry.get_implemented_tools().keys())


def get_tools_summary() -> Dict[str, Any]:
    """Get a summary of tool availability by domain"""
    all_tools = registry.get_all_tools()
    implemented = registry.get_implemented_tools()

    summary = {
        "total_tools": len(all_tools),
        "implemented": len(implemented),
        "not_implemented": len(all_tools) - len(implemented),
        "by_domain": {}
    }

    for domain in registry.get_domains():
        domain_tools = registry.get_tools_by_domain(domain)
        domain_implemented = [t for t in domain_tools if t.get('implemented', False)]
        summary["by_domain"][domain] = {
            "total": len(domain_tools),
            "implemented": len(domain_implemented),
            "tools": [t['name'] for t in domain_tools]
        }

    return summary
