"""
Autocomplete module for ArsanAI.
Provides context-aware AI-powered completions and inline previews.
"""

import sublime
import sublime_plugin
import threading
from typing import Optional, List, Dict, Any


class ArsanAiAutocomplete(sublime_plugin.EventListener):
    """
    Event listener for context-aware autocomplete suggestions.
    Captures code context and generates AI-powered completions.
    """

    def __init__(self):
        """Initialize autocomplete listener."""
        self.api_client: Optional[Any] = None
        self.enabled = True

    def on_query_completions(
        self,
        view: sublime.View,
        prefix: str,
        locations: List[int],
    ) -> sublime.CompletionList:
        """
        Generate completions based on context.
        
        Args:
            view: Current view
            prefix: Completion prefix typed by user
            locations: Cursor locations
            
        Returns:
            CompletionList with suggestions
        """
        if not self.enabled or not locations:
            return sublime.CompletionList()
        
        # Get code context around cursor
        context = self._get_context(view, locations[0])
        
        if not context or len(prefix) < 2:
            return sublime.CompletionList()
        
        # Trigger async completion fetch
        thread = threading.Thread(
            target=self._fetch_completions,
            args=(view, context, prefix),
            daemon=True,
        )
        thread.start()
        
        # Return empty for now, will be populated by fetch
        return sublime.CompletionList()

    def _get_context(self, view: sublime.View, point: int) -> Optional[str]:
        """
        Extract code context around cursor position.
        
        Args:
            view: Current view
            point: Cursor point
            
        Returns:
            Context string or None
        """
        try:
            # Get line range (50 lines before and after)
            line = view.line(point)
            row, col = view.rowcol(point)
            
            start_row = max(0, row - 50)
            end_row = min(view.rowcol(view.size())[0], row + 50)
            
            start_point = view.text_point(start_row, 0)
            end_point = view.text_point(end_row, 0)
            
            context = view.substr(sublime.Region(start_point, end_point))
            
            # Filter out comments and boilerplate
            context = self._filter_context(context)
            
            return context
        
        except Exception:
            return None

    def _filter_context(self, text: str) -> str:
        """
        Filter out comments, docstrings, and boilerplate.
        
        Args:
            text: Raw context text
            
        Returns:
            Filtered context
        """
        lines = text.split('\n')
        filtered = []
        
        in_docstring_double = False
        in_docstring_single = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines and single-line comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # Count triple quotes to track docstring state
            double_count = line.count('"""')
            single_count = line.count("'''")
            
            # Toggle docstring state based on count
            if double_count % 2 == 1:
                in_docstring_double = not in_docstring_double
            if single_count % 2 == 1:
                in_docstring_single = not in_docstring_single
            
            # Skip lines inside docstrings
            if in_docstring_double or in_docstring_single:
                continue
            
            # Skip import statements at start
            if stripped.startswith(('import ', 'from ')):
                continue
            
            filtered.append(line)
        
        return '\n'.join(filtered[:50])  # Limit context size

    def _fetch_completions(
        self,
        view: sublime.View,
        context: str,
        prefix: str,
    ) -> None:
        """
        Fetch completions from API in background thread.
        
        Args:
            view: Current view
            context: Code context
            prefix: User prefix
        """
        if not self.api_client:
            return
        
        try:
            # Build prompt for completion
            prompt = f"""Given the following code context:

{context}

The user has typed: {prefix}

Suggest the next 5 lines of code to complete this. Return ONLY the code, no explanation."""
            
            messages = [
                {"role": "system", "content": "You are a code completion assistant. Provide concise, accurate completions."},
                {"role": "user", "content": prompt},
            ]
            
            # Placeholder - would call API client here
            completions = self._generate_completions(prefix)
            
            # Show completions in UI thread
            sublime.set_timeout(
                lambda: self._show_completions(view, completions),
                0
            )
        
        except Exception:
            pass

    def _generate_completions(self, prefix: str) -> List[sublime.CompletionItem]:
        """
        Generate completion items.
        This is a placeholder for AI-powered completions.
        
        Args:
            prefix: User prefix
            
        Returns:
            List of completion items
        """
        # Placeholder completions
        suggestions = [
            f"{prefix}_1",
            f"{prefix}_2",
            f"{prefix}_test",
        ]
        
        items = [
            sublime.CompletionItem(
                trigger=s,
                completion=s,
                kind=(sublime.KIND_SNIPPET, "c", "Completion"),
                details=f"AI suggestion: {s}",
            )
            for s in suggestions
        ]
        
        return items

    def _show_completions(
        self,
        view: sublime.View,
        items: List[sublime.CompletionItem],
    ) -> None:
        """
        Show completions to user.
        
        Args:
            view: Current view
            items: Completion items
        """
        if items:
            view.run_command(
                'auto_complete',
                {'completions': [str(item) for item in items]}
            )


class InsertCompletionCommand(sublime_plugin.TextCommand):
    """
    TextCommand to insert and preview a completion suggestion.
    Shows inline preview before accepting.
    """

    def run(self, edit: sublime.Edit, text: str = "") -> None:
        """
        Insert completion text.
        
        Args:
            edit: Edit object
            text: Completion text
        """
        if not text:
            return
        
        # Get current selection
        for region in self.view.sel():
            self.view.replace(edit, region, text)

    def is_enabled(self) -> bool:
        """Check if command can execute."""
        return True


class ShowCompletionPreviewCommand(sublime_plugin.TextCommand):
    """
    TextCommand to show an inline preview of completion.
    Uses Sublime's Phantom system for rendering.
    """

    def run(self, edit: sublime.Edit, preview_html: str = "") -> None:
        """
        Show completion preview.
        
        Args:
            edit: Edit object
            preview_html: HTML content for preview
        """
        if not preview_html:
            return
        
        # Get cursor position
        if not self.view.sel():
            return
        
        cursor_point = self.view.sel()[0].b
        line = self.view.line(cursor_point)
        
        # Create phantom for preview
        phantom_set = sublime.PhantomSet(self.view, "arsan_completion_preview")
        
        html_content = f"""
        <style>
            .arsan-preview {{
                background-color: color(var(--foreground) alpha(0.05));
                padding: 8px;
                border-radius: 3px;
                margin-top: 4px;
            }}
        </style>
        <div class="arsan-preview">{preview_html}</div>
        """
        
        phantom = sublime.Phantom(
            line,
            html_content,
            sublime.LAYOUT_BELOW,
        )
        
        phantom_set.add([phantom])
