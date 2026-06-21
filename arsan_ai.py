"""
ArsanAI - Production-grade AI assistant for Sublime Text 4
Main plugin entry point with lifecycle management and command routing.
"""

import sublime
import sublime_plugin
import os
import sys

# Add current directory to path for relative imports
plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

from core.api_client import APIClient
from core.history_manager import HistoryManager
from core.mcp_coordinator import MCPCoordinator
from core.workspace_manager import WorkspaceManager
from ui.chat_view import ChatView
from ui.autocomplete import ArsanAiAutocomplete


# Global plugin instance
_plugin_instance = None


class ArsanAIPlugin:
    """
    Main ArsanAI plugin class.
    Manages all subsystems and provides command routing.
    """

    def __init__(self):
        """Initialize plugin subsystems."""
        self.cache_dir = os.path.join(
            sublime.cache_path(),
            'ArsanAI'
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.api_client: APIClient = None
        self.history_manager = HistoryManager(self.cache_dir)
        self.mcp_coordinator: MCPCoordinator = None
        self.workspace_manager: WorkspaceManager = None
        self.chat_view: ChatView = None
        self.autocomplete: ArsanAiAutocomplete = None
        self.window: sublime.Window = None
        
        self._load_settings()
        self._initialize_subsystems()

    def _load_settings(self) -> None:
        """Load plugin settings."""
        self.settings = sublime.load_settings('arsan_ai.sublime-settings')
        self.settings.clear_on_change('arsan_ai_reload')
        self.settings.add_on_change('arsan_ai_reload', self._on_settings_changed)

    def _on_settings_changed(self) -> None:
        """Callback when settings change."""
        self._initialize_subsystems()

    def _initialize_subsystems(self) -> None:
        """Initialize all plugin subsystems."""
        try:
            # Initialize API client
            api_config = self.settings.get('api', {})
            if api_config:
                self.api_client = APIClient(api_config)
            
            # Initialize MCP coordinator
            mcp_config = self.settings.get('mcp_servers', [])
            if mcp_config:
                self.mcp_coordinator = MCPCoordinator(mcp_config)
        
        except Exception as e:
            print(f"ArsanAI: Error initializing subsystems: {e}")

    def set_window(self, window: sublime.Window) -> None:
        """Set the active window."""
        self.window = window
        
        # Initialize workspace manager if workspace available
        folders = window.folders()
        if folders:
            self.workspace_manager = WorkspaceManager(folders[0])

    def open_chat_hub(self) -> None:
        """Open the chat hub interface."""
        if not self.window:
            return
        
        self.chat_view = ChatView(self.window)
        self.chat_view.open_chat_hub()

    def close_chat_hub(self) -> None:
        """Close the chat hub."""
        if self.chat_view:
            self.chat_view.close_chat_hub()
            self.chat_view = None

    def send_chat_message(self, message: str) -> None:
        """
        Send a message in the chat hub.
        
        Args:
            message: User message
        """
        if not self.api_client or not self.chat_view:
            return
        
        # Add to chat view
        self.chat_view.write_message("user", message)
        
        # Store in history
        if self.chat_view.current_session_id:
            self.history_manager.add_message(
                self.chat_view.current_session_id,
                "user",
                message
            )
        
        # Get chat context
        messages = [
            {"role": "user", "content": message}
        ]
        
        # Stream response
        full_response = ""
        
        def on_token(token: str) -> None:
            nonlocal full_response
            full_response += token
            self.chat_view.stream_token(token)
        
        def on_complete(text: str, token_count: int) -> None:
            # Store in history
            if self.chat_view.current_session_id:
                self.history_manager.add_message(
                    self.chat_view.current_session_id,
                    "assistant",
                    text,
                    token_count
                )
        
        def on_error(error: str) -> None:
            self.chat_view.write_message("error", error)
        
        self.api_client.stream_chat(
            messages,
            on_token,
            on_complete,
            on_error
        )

    def abort_generation(self) -> None:
        """Abort current generation."""
        if self.api_client:
            self.api_client.abort()

    def discover_models(self) -> list:
        """Discover available models."""
        if self.api_client:
            return self.api_client.discover_models()
        return []

    def create_blueprint(self, name: str, description: str) -> None:
        """
        Create a workspace blueprint.
        
        Args:
            name: Blueprint name
            description: Blueprint description
        """
        if not self.workspace_manager:
            sublime.message_dialog("No workspace open")
            return
        
        filepath = self.workspace_manager.create_blueprint(name, description)
        
        # Open the created blueprint
        self.window.open_file(filepath)


def plugin_loaded() -> None:
    """Sublime plugin lifecycle: plugin loaded."""
    global _plugin_instance
    
    _plugin_instance = ArsanAIPlugin()
    print("ArsanAI plugin loaded")


def plugin_unloaded() -> None:
    """Sublime plugin lifecycle: plugin unloaded."""
    global _plugin_instance
    
    if _plugin_instance:
        # Clean up resources
        if _plugin_instance.mcp_coordinator:
            _plugin_instance.mcp_coordinator.stop_all()
        
        if _plugin_instance.chat_view:
            _plugin_instance.chat_view.close_chat_hub()
    
    _plugin_instance = None
    print("ArsanAI plugin unloaded")


# Window commands

class ArsanaiOpenChatHubCommand(sublime_plugin.WindowCommand):
    """Open the ArsanAI chat hub."""

    def run(self) -> None:
        """Execute command."""
        if _plugin_instance:
            _plugin_instance.set_window(self.window)
            _plugin_instance.open_chat_hub()
            sublime.message_dialog("Chat hub opened. Press Ctrl+Enter to send messages.")


class ArsanaiCloseChatHubCommand(sublime_plugin.WindowCommand):
    """Close the ArsanAI chat hub."""

    def run(self) -> None:
        """Execute command."""
        if _plugin_instance:
            _plugin_instance.close_chat_hub()


class ArsanaiStopGenerationCommand(sublime_plugin.WindowCommand):
    """Stop current AI generation."""

    def run(self) -> None:
        """Execute command."""
        if _plugin_instance:
            _plugin_instance.abort_generation()
            sublime.status_message("Generation stopped")


class ArsanaiSelectModelCommand(sublime_plugin.WindowCommand):
    """Select active AI model."""

    def run(self) -> None:
        """Execute command."""
        if not _plugin_instance:
            return
        
        models = _plugin_instance.discover_models()
        
        if not models:
            sublime.message_dialog("No models available. Check your API configuration.")
            return
        
        model_names = [m.get('name', m.get('id', '')) for m in models]
        
        def on_select(index: int) -> None:
            if index >= 0:
                selected_model = models[index]
                _plugin_instance.settings.set('api', {
                    **_plugin_instance.settings.get('api', {}),
                    'model': selected_model.get('id')
                })
                sublime.save_settings('arsan_ai.sublime-settings')
                sublime.status_message(f"Model set to: {selected_model.get('name')}")
        
        self.window.show_quick_panel(model_names, on_select)


class ArsanaiCreateBlueprintCommand(sublime_plugin.WindowCommand):
    """Create a workspace blueprint."""

    def run(self) -> None:
        """Execute command."""
        if not _plugin_instance:
            return
        
        self.window.show_input_panel(
            "Blueprint name:",
            "Implementation",
            lambda name: self._on_name_entered(name),
            None,
            None
        )

    def _on_name_entered(self, name: str) -> None:
        """Callback after name entered."""
        self.window.show_input_panel(
            "Blueprint description:",
            "Outline the implementation plan",
            lambda desc: self._on_description_entered(name, desc),
            None,
            None
        )

    def _on_description_entered(self, name: str, description: str) -> None:
        """Callback after description entered."""
        if _plugin_instance:
            _plugin_instance.create_blueprint(name, description)


class ArsanaiOpenChatHistoryCommand(sublime_plugin.WindowCommand):
    """Open chat history session."""

    def run(self) -> None:
        """Execute command."""
        if not _plugin_instance:
            return
        
        sessions = _plugin_instance.history_manager.list_sessions()
        
        if not sessions:
            sublime.message_dialog("No chat history available")
            return
        
        session_names = [s.get('title', s.get('id', '')) for s in sessions]
        
        def on_select(index: int) -> None:
            if index >= 0:
                session_id = sessions[index]['id']
                _plugin_instance.set_window(self.window)
                _plugin_instance.open_chat_hub(session_id)
                
                # Load messages
                session = _plugin_instance.history_manager.get_session(session_id)
                if session:
                    for msg in session.get('messages', []):
                        _plugin_instance.chat_view.write_message(
                            msg['role'],
                            msg['content']
                        )
        
        self.window.show_quick_panel(session_names, on_select)


# Text commands

class ArsanaiSendChatMessageCommand(sublime_plugin.TextCommand):
    """Send message from chat view."""

    def run(self, edit: sublime.Edit) -> None:
        """Execute command."""
        if not _plugin_instance or not _plugin_instance.chat_view:
            return
        
        message = _plugin_instance.chat_view.get_user_input()
        
        if message.strip():
            _plugin_instance.send_chat_message(message)
            _plugin_instance.chat_view.clear_chat()


class ArsanaiInsertSelectedTextCommand(sublime_plugin.TextCommand):
    """Insert selected text into chat."""

    def run(self, edit: sublime.Edit) -> None:
        """Execute command."""
        if not _plugin_instance or not _plugin_instance.chat_view:
            return
        
        # Get selection from active view
        active_view = self.view
        if not active_view:
            return
        
        selected_text = ""
        for region in active_view.sel():
            if region.size() > 0:
                selected_text += active_view.substr(region) + "\n"
        
        if selected_text:
            _plugin_instance.chat_view.write_message("context", selected_text)


class ArsanaiRequestCompletionCommand(sublime_plugin.TextCommand):
    """Request AI completion for selected code."""

    def run(self, edit: sublime.Edit) -> None:
        """Execute command."""
        if not _plugin_instance or not _plugin_instance.api_client:
            return
        
        # Get selected text
        selected_text = ""
        for region in self.view.sel():
            if region.size() > 0:
                selected_text += self.view.substr(region)
        
        if not selected_text:
            sublime.message_dialog("No text selected")
            return
        
        # Request completion
        messages = [
            {
                "role": "user",
                "content": f"Complete this code:\n\n{selected_text}"
            }
        ]
        
        completion_text = ""
        
        def on_token(token: str) -> None:
            nonlocal completion_text
            completion_text += token
            sublime.status_message(f"Generating... ({len(completion_text)} chars)")
        
        def on_complete(text: str, token_count: int) -> None:
            # Insert completion
            self.view.run_command('insert', {'characters': completion_text})
        
        def on_error(error: str) -> None:
            sublime.message_dialog(f"Error: {error}")
        
        _plugin_instance.api_client.stream_chat(
            messages,
            on_token,
            on_complete,
            on_error,
            max_tokens=512
        )


class ArsanaiExportWorkspaceSummaryCommand(sublime_plugin.WindowCommand):
    """Export workspace summary."""

    def run(self) -> None:
        """Execute command."""
        if not _plugin_instance or not _plugin_instance.workspace_manager:
            sublime.message_dialog("No workspace open")
            return
        
        summary = _plugin_instance.workspace_manager.export_workspace_summary()
        
        # Create new file with summary
        view = self.window.new_file()
        view.set_name("Workspace Summary")
        view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")
        view.insert(self.window.active_view().begin_edit(), 0, summary)
