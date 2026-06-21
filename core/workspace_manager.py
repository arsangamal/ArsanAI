"""
Workspace Manager module for ArsanAI.
Handles dynamic generation of workspace staging structures and blueprints.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading


class WorkspaceManager:
    """
    Manages workspace staging structures, blueprints, and project context.
    Creates and maintains workspace files like ARSAN_BLUEPRINT.md.
    """

    def __init__(self, workspace_root: str):
        """
        Initialize workspace manager.
        
        Args:
            workspace_root: Root directory of the workspace
        """
        self.workspace_root = workspace_root
        self.staging_dir = os.path.join(workspace_root, '.arsan')
        self.lock = threading.Lock()
        
        os.makedirs(self.staging_dir, exist_ok=True)

    def create_blueprint(
        self,
        name: str,
        description: str,
        sections: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """
        Create a workspace blueprint file.
        
        Args:
            name: Blueprint name (e.g., 'REFACTOR', 'IMPLEMENTATION')
            description: Blueprint description
            sections: Dict of section names to line lists
            
        Returns:
            Path to created blueprint file
        """
        with self.lock:
            filename = f'ARSAN_{name.upper()}.md'
            filepath = os.path.join(self.staging_dir, filename)
            
            content = self._generate_blueprint_content(name, description, sections)
            
            with open(filepath, 'w') as f:
                f.write(content)
            
            return filepath

    def _generate_blueprint_content(
        self,
        name: str,
        description: str,
        sections: Optional[Dict[str, List[str]]],
    ) -> str:
        """Generate markdown content for blueprint."""
        lines = [
            f"# {name} Blueprint",
            "",
            description,
            "",
            f"**Created**: {datetime.now().isoformat()}",
            "",
            "## Overview",
            "",
            "This blueprint outlines the refactoring, implementation, or code review plan.",
            "",
        ]
        
        if sections:
            for section_name, items in sections.items():
                lines.append(f"## {section_name}")
                lines.append("")
                
                for item in items:
                    lines.append(f"- [ ] {item}")
                
                lines.append("")
        
        lines.extend([
            "## Files Affected",
            "",
            "| File | Status | Changes |",
            "|------|--------|---------|",
            "",
            "## Implementation Notes",
            "",
            "- Update this section as work progresses",
            "",
        ])
        
        return "\n".join(lines)

    def create_checklist(
        self,
        task_name: str,
        items: List[str],
    ) -> str:
        """
        Create an implementation checklist.
        
        Args:
            task_name: Name of the task
            items: List of checklist items
            
        Returns:
            Path to created checklist file
        """
        with self.lock:
            filename = f'ARSAN_CHECKLIST_{task_name.upper()}.md'
            filepath = os.path.join(self.staging_dir, filename)
            
            lines = [
                f"# {task_name} Checklist",
                "",
                f"**Created**: {datetime.now().isoformat()}",
                "",
                "## Tasks",
                "",
            ]
            
            for item in items:
                lines.append(f"- [ ] {item}")
            
            lines.extend([
                "",
                "## Progress",
                "",
                "**Completed**: 0/{len(items)}",
                "",
            ])
            
            with open(filepath, 'w') as f:
                f.write("\n".join(lines))
            
            return filepath

    def create_context_file(
        self,
        context_type: str,
        data: Dict[str, Any],
    ) -> str:
        """
        Create a context file for workspace metadata.
        
        Args:
            context_type: Type of context (e.g., 'analysis', 'review')
            data: Context data to store
            
        Returns:
            Path to created context file
        """
        with self.lock:
            filename = f'arsan_{context_type}.json'
            filepath = os.path.join(self.staging_dir, filename)
            
            context = {
                'type': context_type,
                'created_at': datetime.now().isoformat(),
                'data': data,
            }
            
            with open(filepath, 'w') as f:
                json.dump(context, f, indent=2)
            
            return filepath

    def list_blueprints(self) -> List[str]:
        """
        List all blueprint files in staging directory.
        
        Returns:
            List of blueprint filenames
        """
        with self.lock:
            try:
                files = os.listdir(self.staging_dir)
                return [f for f in files if f.startswith('ARSAN_') and f.endswith('.md')]
            except OSError:
                return []

    def read_blueprint(self, filename: str) -> Optional[str]:
        """
        Read blueprint content.
        
        Args:
            filename: Filename of blueprint
            
        Returns:
            File content or None if not found
        """
        with self.lock:
            filepath = os.path.join(self.staging_dir, filename)
            
            if not os.path.exists(filepath):
                return None
            
            try:
                with open(filepath, 'r') as f:
                    return f.read()
            except IOError:
                return None

    def update_blueprint(self, filename: str, content: str) -> bool:
        """
        Update blueprint content.
        
        Args:
            filename: Filename of blueprint
            content: New content
            
        Returns:
            True if updated successfully
        """
        with self.lock:
            filepath = os.path.join(self.staging_dir, filename)
            
            if not os.path.exists(filepath):
                return False
            
            try:
                with open(filepath, 'w') as f:
                    f.write(content)
                return True
            except IOError:
                return False

    def delete_blueprint(self, filename: str) -> bool:
        """
        Delete a blueprint file.
        
        Args:
            filename: Filename of blueprint
            
        Returns:
            True if deleted successfully
        """
        with self.lock:
            filepath = os.path.join(self.staging_dir, filename)
            
            if not os.path.exists(filepath):
                return False
            
            try:
                os.remove(filepath)
                return True
            except OSError:
                return False

    def get_project_structure(self) -> Dict[str, Any]:
        """
        Analyze project structure.
        
        Returns:
            Dict with project metadata
        """
        structure = {
            'root': self.workspace_root,
            'folders': [],
            'file_count': 0,
            'languages': set(),
        }
        
        try:
            for root, dirs, files in os.walk(self.workspace_root):
                if '.git' in dirs:
                    dirs.remove('.git')
                if '.arsan' in dirs:
                    dirs.remove('.arsan')
                if 'node_modules' in dirs:
                    dirs.remove('node_modules')
                if '__pycache__' in dirs:
                    dirs.remove('__pycache__')
                
                for file in files:
                    structure['file_count'] += 1
                    _, ext = os.path.splitext(file)
                    if ext:
                        structure['languages'].add(ext)
        
        except OSError:
            pass
        
        structure['languages'] = list(structure['languages'])
        return structure

    def export_workspace_summary(self) -> str:
        """
        Export a summary of workspace state.
        
        Returns:
            Summary markdown string
        """
        structure = self.get_project_structure()
        blueprints = self.list_blueprints()
        
        lines = [
            "# Workspace Summary",
            "",
            "## Project Structure",
            f"- **Root**: {structure['root']}",
            f"- **Total Files**: {structure['file_count']}",
            f"- **Languages**: {', '.join(structure['languages']) or 'None detected'}",
            "",
            "## Active Blueprints",
            "",
        ]
        
        if blueprints:
            for blueprint in blueprints:
                lines.append(f"- {blueprint}")
        else:
            lines.append("No active blueprints.")
        
        lines.extend([
            "",
            f"**Generated**: {datetime.now().isoformat()}",
        ])
        
        return "\n".join(lines)
