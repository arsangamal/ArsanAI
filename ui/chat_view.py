"""
Chat View module for ArsanAI.
Manages split-screen chat interface and streaming content rendering.
"""

import sublime
import re
from typing import Callable, Optional
import threading


class ChatView:
    """
    Manages a dedicated chat panel with streaming content support.
    Handles split-screen layouts and real-time token injection.
    """

    def __init__(self, window: sublime.Window):
        """
        Initialize chat view.
        
        Args:
            window: Sublime window
        """
        self.window = window
        self.view: Optional[sublime.View] = None
        self.lock = threading.Lock()
        self.current_session_id = ""

    def open_chat_hub(self, session_id: str = "") -> bool:
        """
        Open a chat hub in split-screen layout.
        
        Args:
            session_id: Optional session ID to load
            
        Returns:
            True if opened successfully
        """
        with self.lock:
            try:
                # Set split layout: 2 columns
                self.window.set_layout({
                    "cols": [0.0, 0.5, 1.0],
                    "rows": [0.0, 1.0],
                    "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
                })
                
                # Open new view in right column
                self.view = self.window.new_file()
                self.view.set_name("ArsanAI Chat")
                self.view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
                
                # Move to group 1 (right side)
                self.window.set_view_index(self.view, 1, 0)
                
                # Set scratch buffer
                self.view.set_scratch(True)
                
                # Write initial content
                self._write_header()
                
                self.current_session_id = session_id
                return True
            
            except Exception as e:
                return False

    def close_chat_hub(self) -> None:
        """Close the chat hub and reset layout."""
        with self.lock:
            if self.view:
                self.window.focus_view(self.view)
                self.window.run_command("close")
                self.view = None
            
            # Reset to single column
            self.window.set_layout({
                "cols": [0.0, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1]],
            })

    def write_message(self, role: str, content: str) -> None:
        """
        Write a complete message to the chat view.
        
        Args:
            role: Message role ('user' or 'assistant')
            content: Message content
        """
        with self.lock:
            if not self.view:
                return
            
            sublime.set_timeout(
                lambda: self._write_message_sync(role, content),
                0
            )

    def _write_message_sync(self, role: str, content: str) -> None:
        """Synchronous message write (must be called from UI thread)."""
        if not self.view:
            return
        
        # Format message
        if role == "user":
            formatted = f"\n**You:**\n{content}\n"
        else:
            formatted = f"\n**Assistant:**\n{content}\n"
        
        # Append to view
        self.view.run_command('append', {'characters': formatted})
        self.view.run_command('move_to', {'to': 'eof'})

    def stream_token(self, token: str) -> None:
        """
        Stream a single token to the chat view.
        Appends incrementally without blocking.
        
        Args:
            token: Token to append
        """
        with self.lock:
            if not self.view:
                return
            
            sublime.set_timeout(
                lambda: self._stream_token_sync(token),
                0
            )

    def _stream_token_sync(self, token: str) -> None:
        """Synchronous token stream (must be called from UI thread)."""
        if not self.view:
            return
        
        # On first token of response, write header
        point = self.view.size()
        if point == 0 or self.view.substr(point - 1) == '\n':
            self.view.run_command('append', {'characters': "\n**Assistant:**\n"})
        
        # Append token
        self.view.run_command('append', {'characters': token})
        self.view.run_command('move_to', {'to': 'eof'})

    def _write_header(self) -> None:
        """Write chat header."""
        header = """# ArsanAI Chat Hub

Welcome to your AI assistant. Type your message below and press Ctrl+Enter (Cmd+Enter on Mac) to send.

---

"""
        self.view.run_command('append', {'characters': header})

    def clear_chat(self) -> None:
        """Clear all content from chat view."""
        with self.lock:
            if not self.view:
                return
            
            sublime.set_timeout(
                lambda: self._clear_chat_sync(),
                0
            )

    def _clear_chat_sync(self) -> None:
        """Synchronous clear (must be called from UI thread)."""
        if not self.view:
            return
        
        self.view.run_command('select_all')
        self.view.run_command('delete')
        self._write_header()

    def get_user_input(self) -> str:
        """
        Extract unprocessed user input from chat view.
        Returns text after the last assistant message.
        
        Returns:
            User input text
        """
        with self.lock:
            if not self.view:
                return ""
            
            content = self.view.substr(sublime.Region(0, self.view.size()))
            
            # Find last assistant message marker
            last_assistant = content.rfind("\n**Assistant:**\n")
            if last_assistant == -1:
                last_assistant = content.find("---")
            
            if last_assistant != -1:
                return content[last_assistant:].strip()
            
            return content.strip()

    def format_code_block(self, code: str, language: str = "") -> str:
        """
        Format code with markdown syntax highlighting.
        
        Args:
            code: Code content
            language: Programming language identifier
            
        Returns:
            Formatted code block
        """
        return f"```{language}\n{code}\n```"

    def insert_phantom_preview(
        self,
        text: str,
        html: Optional[str] = None,
    ) -> None:
        """
        Insert an inline preview phantom.
        Useful for showing previews before accepting.
        
        Args:
            text: Text anchor
            html: HTML content for phantom
        """
        if not self.view or not html:
            return
        
        # Find position of text in view
        region = self.view.find(text, 0)
        if not region:
            return
        
        # Create phantom
        phantom_set = sublime.PhantomSet(self.view, "arsan_preview")
        phantom = sublime.Phantom(
            region,
            html,
            sublime.LAYOUT_INLINE,
        )
        phantom_set.add([phantom])

    def set_selection_to_end(self) -> None:
        """Move cursor to end of document."""
        with self.lock:
            if not self.view:
                return
            
            sublime.set_timeout(
                lambda: self.view.run_command('move_to', {'to': 'eof'}),
                0
            )

    def is_visible(self) -> bool:
        """Check if chat view is visible."""
        with self.lock:
            return self.view is not None and self.view.window() is not None
