"""
MCP Coordinator module for ArsanAI.
Implements Model Context Protocol (MCP) for sandboxed tool execution.
"""

import json
import subprocess
import threading
import os
from typing import Dict, Any, List, Optional, Callable
import traceback


class MCPServer:
    """Represents a single MCP server configuration."""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize MCP server.
        
        Args:
            name: Server name
            config: Server configuration dict with:
                - command: Executable path
                - args: Command arguments
                - env: Optional environment variables
        """
        self.name = name
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()

    def start(self) -> bool:
        """
        Start the MCP server process.
        
        Returns:
            True if started successfully
        """
        with self.lock:
            if self.process is not None:
                return False
            
            try:
                cmd = [self.config['command']]
                if 'args' in self.config:
                    cmd.extend(self.config['args'])
                
                env = os.environ.copy()
                if 'env' in self.config:
                    env.update(self.config['env'])
                
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                    bufsize=1,
                )
                
                return True
            
            except Exception as e:
                print(f"ArsanAI: Error starting MCP server '{self.name}': {e}")
                print(traceback.format_exc())
                return False

    def stop(self) -> None:
        """Stop the MCP server process."""
        with self.lock:
            if self.process is not None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                
                self.process = None

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Call a tool on the MCP server asynchronously.
        
        Args:
            tool_name: Name of tool to call
            arguments: Tool arguments
            on_result: Callback with result
            on_error: Callback with error message
        """
        thread = threading.Thread(
            target=self._call_tool_worker,
            args=(tool_name, arguments, on_result, on_error),
            daemon=True,
        )
        thread.start()

    def _call_tool_worker(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Worker thread for tool calls."""
        try:
            with self.lock:
                if self.process is None:
                    on_error(f"MCP server '{self.name}' is not running")
                    return
                
                request = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                    "id": 1,
                }
                
                request_json = json.dumps(request) + "\n"
                self.process.stdin.write(request_json)
                self.process.stdin.flush()
                
                response_line = self.process.stdout.readline()
                if not response_line:
                    on_error(f"No response from MCP server '{self.name}'")
                    return
                
                response = json.loads(response_line)
                
                if "error" in response:
                    on_error(response["error"].get("message", "Unknown error"))
                elif "result" in response:
                    result = response["result"]
                    if isinstance(result, dict):
                        on_result(json.dumps(result, indent=2))
                    else:
                        on_result(str(result))
                else:
                    on_error("Invalid response from MCP server")
        
        except json.JSONDecodeError as e:
            on_error(f"JSON decode error: {str(e)}")
        except Exception as e:
            on_error(f"Tool call error: {str(e)}\n{traceback.format_exc()}")


class MCPCoordinator:
    """
    Coordinates multiple MCP servers and tool execution.
    Bridges LLM tool calls to sandboxed subprocess execution.
    """

    def __init__(self, servers_config: List[Dict[str, Any]]):
        """
        Initialize MCP coordinator.
        
        Args:
            servers_config: List of MCP server configurations
        """
        self.servers: Dict[str, MCPServer] = {}
        self.lock = threading.Lock()
        
        for server_config in servers_config:
            name = server_config.get('name', 'unknown')
            self.servers[name] = MCPServer(name, server_config)

    def start_all(self) -> Dict[str, bool]:
        """
        Start all configured MCP servers.
        
        Returns:
            Dict mapping server names to start success status
        """
        results = {}
        with self.lock:
            for name, server in self.servers.items():
                results[name] = server.start()
        return results

    def stop_all(self) -> None:
        """Stop all MCP servers."""
        with self.lock:
            for server in self.servers.values():
                server.stop()

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Call a tool on a specific MCP server.
        
        Args:
            server_name: Name of MCP server
            tool_name: Name of tool
            arguments: Tool arguments
            on_result: Callback with result
            on_error: Callback with error
        """
        with self.lock:
            if server_name not in self.servers:
                on_error(f"Unknown MCP server: {server_name}")
                return
            
            server = self.servers[server_name]
        
        server.call_tool(tool_name, arguments, on_result, on_error)

    def get_available_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """
        Get available tools from a server.
        
        Args:
            server_name: Name of MCP server
            
        Returns:
            List of tool definitions
        """
        if server_name not in self.servers:
            return []
        
        server = self.servers[server_name]
        
        try:
            with server.lock:
                if server.process is None:
                    return []
                
                request = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 1,
                }
                
                request_json = json.dumps(request) + "\n"
                server.process.stdin.write(request_json)
                server.process.stdin.flush()
                
                response_line = server.process.stdout.readline()
                if not response_line:
                    return []
                
                response = json.loads(response_line)
                return response.get("result", {}).get("tools", [])
        
        except Exception:
            return []

    def process_tool_use(
        self,
        tool_use_block: Dict[str, Any],
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Process a tool use block from LLM output.
        
        Args:
            tool_use_block: Tool use block from response
            on_result: Callback with tool result
            on_error: Callback with error
        """
        server_name = tool_use_block.get('server')
        tool_name = tool_use_block.get('name')
        arguments = tool_use_block.get('input', {})
        
        if not server_name or not tool_name:
            on_error("Invalid tool use block: missing server or name")
            return
        
        self.call_tool(server_name, tool_name, arguments, on_result, on_error)
