"""
Agent Tools module for ArsanAI.
Defines native workspace tools (file read, file write, patch, search) for LLM agent capabilities.
"""

import os
import json
import fnmatch
from typing import Dict, List, Any, Optional

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_project_files",
            "description": "List all files in the active project workspace (excluding hidden/compiled files).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full text contents of a file in the project workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file relative to the project root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file with new content in the project workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file relative to the project root."
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete text content to write to the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": "Apply search-and-replace edits to a file in the project workspace (ideal for small edits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The path to the file relative to the project root."
                    },
                    "search_text": {
                        "type": "string",
                        "description": "The exact block of code to search for."
                    },
                    "replace_text": {
                        "type": "string",
                        "description": "The replacement block of code."
                    }
                },
                "required": ["path", "search_text", "replace_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_grep",
            "description": "Search for text patterns across all files in the project workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The text string or search query to look for."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

class AgentTools:
    """Provides local workspace file tools for the AI agent."""

    def __init__(self, workspace_root: str):
        """
        Initialize AgentTools.
        
        Args:
            workspace_root: Root directory of the project
        """
        self.workspace_root = workspace_root

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get the tools schemas list."""
        return TOOLS_SCHEMA

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute a tool by name with provided arguments.
        
        Args:
            name: Tool/function name
            arguments: Dictionary of arguments
            
        Returns:
            String response result
        """
        try:
            if name == "list_project_files":
                return self.list_project_files()
            elif name == "read_file":
                return self.read_file(arguments.get("path", ""))
            elif name == "write_file":
                return self.write_file(arguments.get("path", ""), arguments.get("content", ""))
            elif name == "patch_file":
                return self.patch_file(arguments.get("path", ""), arguments.get("search_text", ""), arguments.get("replace_text", ""))
            elif name == "search_grep":
                return self.search_grep(arguments.get("query", ""))
            else:
                return "Error: Unknown tool name '{}'".format(name)
        except Exception as e:
            return "Error executing tool '{}': {}".format(name, str(e))

    def _resolve_path(self, relative_path: str) -> str:
        """Resolve a relative path ensuring it is within the workspace root."""
        cleaned_path = os.path.normpath(relative_path).lstrip('/')
        if cleaned_path.startswith('..') or os.path.isabs(cleaned_path):
            # Fallback check
            abs_root = os.path.abspath(self.workspace_root)
            abs_target = os.path.abspath(os.path.join(self.workspace_root, cleaned_path))
            if not abs_target.startswith(abs_root):
                raise ValueError("Path must be inside the project workspace.")
            return abs_target
        return os.path.join(self.workspace_root, cleaned_path)

    def list_project_files(self) -> str:
        """List files in workspace (ignoring common build artifacts/caches)."""
        files_list = []
        exclude_patterns = ['*.sublime-workspace', '*.pyc', '.git/*', '__pycache__/*', '.arsan/*']
        
        for root, dirs, files in os.walk(self.workspace_root):
            # Prune directories in place to prevent visiting ignored folders
            dirs[:] = [
                d for d in dirs 
                if not any(fnmatch.fnmatch(os.path.relpath(os.path.join(root, d), self.workspace_root), pat.rstrip('/*')) for pat in exclude_patterns)
            ]
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.workspace_root)
                if not any(fnmatch.fnmatch(rel_path, pat) for pat in exclude_patterns):
                    files_list.append(rel_path)
                    
        return json.dumps(files_list, indent=2)

    def read_file(self, path: str) -> str:
        """Read text from a file."""
        try:
            abs_path = self._resolve_path(path)
            if not os.path.exists(abs_path):
                return "Error: File '{}' does not exist.".format(path)
            
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return content
        except Exception as e:
            return "Error reading file '{}': {}".format(path, str(e))

    def write_file(self, path: str, content: str) -> str:
        """Write content to a file."""
        try:
            abs_path = self._resolve_path(path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return "Success: File '{}' has been written successfully.".format(path)
        except Exception as e:
            return "Error writing file '{}': {}".format(path, str(e))

    def patch_file(self, path: str, search_text: str, replace_text: str) -> str:
        """Search and replace a specific text block inside a file."""
        try:
            abs_path = self._resolve_path(path)
            if not os.path.exists(abs_path):
                return "Error: File '{}' does not exist.".format(path)
            
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            if search_text not in content:
                return "Error: The search_text block was not found in the file."
                
            new_content = content.replace(search_text, replace_text, 1)
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            return "Success: File '{}' has been patched successfully.".format(path)
        except Exception as e:
            return "Error patching file '{}': {}".format(path, str(e))

    def search_grep(self, query: str) -> str:
        """Search for occurrences of a query string across the project workspace."""
        results = []
        exclude_patterns = ['*.sublime-workspace', '*.pyc', '.git/*', '__pycache__/*', '.arsan/*']
        
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [
                d for d in dirs 
                if not any(fnmatch.fnmatch(os.path.relpath(os.path.join(root, d), self.workspace_root), pat.rstrip('/*')) for pat in exclude_patterns)
            ]
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.workspace_root)
                if any(fnmatch.fnmatch(rel_path, pat) for pat in exclude_patterns):
                    continue
                
                abs_path = os.path.join(root, file)
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_no, line in enumerate(f, 1):
                            if query in line:
                                results.append({
                                    "file": rel_path,
                                    "line": line_no,
                                    "content": line.strip()
                                })
                except Exception:
                    pass
                    
        return json.dumps(results, indent=2)
