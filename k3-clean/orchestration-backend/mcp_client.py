"""
mcp_client.py — MCP (Model Context Protocol) Tool Connections.

Manages connections to MCP tool servers defined in mcp.json.
Provides a simple interface for listing available tools and executing them.

MCP tool servers give AI models real-world capabilities:
  - filesystem   — read/write files on disk
  - web-search   — live web search (Brave Search API)
  - github       — GitHub API (create issues, PRs, search code)
  - database     — query databases
  - any custom MCP server

Config file (mcp.json):
{
  "mcps": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home"]
    },
    "web-search": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"}
    }
  }
}

Usage in executor.py:
    tools = await mcp_client.list_tools()
    result = await mcp_client.call_tool("filesystem", "read_file", {"path": "/home/file.txt"})
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MCP_CONFIG_PATH = Path(__file__).parent / "mcp.json"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_mcp_config() -> dict:
    """Loads mcp.json. Returns empty config if file doesn't exist."""
    if not MCP_CONFIG_PATH.exists():
        logger.info("mcp.json not found — MCP tools disabled")
        return {"mcps": {}}

    try:
        with open(MCP_CONFIG_PATH) as f:
            config = json.load(f)
        logger.info("Loaded MCP config with %d servers", len(config.get("mcps", {})))
        return config
    except Exception as exc:
        logger.error("Failed to load mcp.json: %s", exc)
        return {"mcps": {}}


def _resolve_env(value: str) -> str:
    """Resolves ${ENV_VAR} patterns in config strings."""
    if value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value


def _resolve_env_dict(env: dict) -> dict:
    """Resolves all env var references in an env dict."""
    return {k: _resolve_env(v) for k, v in env.items()}


# ---------------------------------------------------------------------------
# Tool registry (in-memory, loaded at startup)
# ---------------------------------------------------------------------------

class MCPToolRegistry:
    """
    Lightweight tool registry that tracks what tools each MCP server provides.
    Uses a simple JSON-RPC stdio protocol to query tool lists at startup.
    """

    def __init__(self):
        self._tools: dict[str, list[dict]] = {}   # server_name → [tool_defs]
        self._config: dict = {}

    def load(self):
        """Loads config and attempts to discover tools from each server."""
        self._config = load_mcp_config()
        for server_name, server_config in self._config.get("mcps", {}).items():
            try:
                tools = self._probe_server_tools(server_name, server_config)
                self._tools[server_name] = tools
                logger.info(
                    "MCP server '%s': %d tools available", server_name, len(tools)
                )
            except Exception as exc:
                logger.warning(
                    "Could not probe MCP server '%s': %s — tools unavailable",
                    server_name, exc
                )
                self._tools[server_name] = []

    def _probe_server_tools(self, name: str, config: dict) -> list[dict]:
        """
        Sends a tools/list request to a stdio MCP server and returns the tool list.
        Times out after 5 seconds to avoid blocking startup.
        """
        if config.get("type") != "stdio":
            return []

        command = config["command"]
        args = config.get("args", [])
        env = {**os.environ, **_resolve_env_dict(config.get("env", {}))}

        # Build the JSON-RPC tools/list request
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }) + "\n"

        try:
            proc = subprocess.run(
                [command] + args,
                input=request,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            if proc.stdout:
                # Parse first JSON line from output
                for line in proc.stdout.strip().split("\n"):
                    try:
                        response = json.loads(line)
                        tools = response.get("result", {}).get("tools", [])
                        return tools
                    except json.JSONDecodeError:
                        continue
        except subprocess.TimeoutExpired:
            logger.warning("MCP server '%s' probe timed out", name)
        except FileNotFoundError:
            logger.warning(
                "MCP server '%s' command '%s' not found — install it with npm",
                name, command
            )
        return []

    def list_all_tools(self) -> list[dict]:
        """Returns all tools across all servers, tagged with server_name."""
        all_tools = []
        for server_name, tools in self._tools.items():
            for tool in tools:
                all_tools.append({**tool, "server": server_name})
        return all_tools

    def list_tools_for_task(self, task_type: str) -> list[dict]:
        """Returns tools relevant to a specific task type."""
        type_to_servers = {
            "research":    ["web-search", "filesystem"],
            "coding":      ["filesystem", "github"],
            "writing":     ["filesystem"],
            "reasoning":   ["web-search"],
            "translation": [],
        }
        relevant_servers = type_to_servers.get(task_type, [])
        tools = []
        for server in relevant_servers:
            tools.extend(self._tools.get(server, []))
        return tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
    ) -> Optional[str]:
        """
        Calls a tool on the specified MCP server and returns the text result.
        Returns None on failure.
        """
        server_config = self._config.get("mcps", {}).get(server_name)
        if not server_config:
            logger.error("MCP server '%s' not configured", server_name)
            return None

        if server_config.get("type") != "stdio":
            logger.warning("Only stdio MCP servers supported currently")
            return None

        command = server_config["command"]
        args = server_config.get("args", [])
        env = {**os.environ, **_resolve_env_dict(server_config.get("env", {}))}

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            }
        }) + "\n"

        start = time.monotonic()
        try:
            proc = subprocess.run(
                [command] + args,
                input=request,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            if proc.stdout:
                for line in proc.stdout.strip().split("\n"):
                    try:
                        response = json.loads(line)
                        content = response.get("result", {}).get("content", [])
                        text_parts = [
                            c.get("text", "") for c in content
                            if c.get("type") == "text"
                        ]
                        result = "\n".join(text_parts)
                        logger.info(
                            "MCP tool '%s/%s' completed in %dms",
                            server_name, tool_name, duration_ms
                        )
                        return result
                    except json.JSONDecodeError:
                        continue

        except subprocess.TimeoutExpired:
            logger.error("MCP tool '%s/%s' timed out", server_name, tool_name)
        except Exception as exc:
            logger.error("MCP tool '%s/%s' error: %s", server_name, tool_name, exc)

        return None

    def get_tools_as_openai_format(self, task_type: Optional[str] = None) -> list[dict]:
        """
        Returns tools in OpenAI function-calling format for use in provider calls.
        """
        tools = (
            self.list_tools_for_task(task_type)
            if task_type else self.list_all_tools()
        )
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": f"{tool.get('server', 'mcp')}__{tool.get('name', 'tool')}",
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            })
        return openai_tools


# Singleton — used across the application
mcp_registry = MCPToolRegistry()


def init_mcp():
    """Call at startup to load MCP config and probe servers."""
    mcp_registry.load()
    tool_count = len(mcp_registry.list_all_tools())
    logger.info("MCP initialised — %d tools available", tool_count)
