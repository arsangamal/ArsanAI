# ArsanAI

The long time awaited Sublime Text 4 plugin for AI.

A production-grade, deeply-integrated AI assistant for Sublime Text 4 featuring asynchronous streaming, multi-engine model support, Model Context Protocol (MCP) integration, and advanced workspace management.

## Features

- **Multi-Engine AI Support** - OpenAI, Anthropic, and custom API endpoints
- **Streaming Responses** - Real-time token streaming with instant abort capability
- **Chat Hub** - Persistent conversation history with multi-pane chat interface
- **Model Context Protocol (MCP)** - Sandboxed tool execution and system integration
- **Context-Aware Autocomplete** - Inline AI-powered completions with code context
- **Workspace Blueprinting** - Dynamic staging structures for refactoring and planning
- **Full ST4 Integration** - Native event listeners, minihtml panels, and non-blocking UI

## Installation

1. Clone this repository into your Sublime Text Packages directory:
   ```bash
   # On Linux
   cd ~/.config/sublime-text/Packages
   
   # On macOS
   cd ~/Library/Application\ Support/Sublime\ Text/Packages
   
   # On Windows
   cd %APPDATA%\Sublime Text\Packages
   
   git clone https://github.com/arsangamal/ArsanAI.git
   ```

2. Configure your API credentials in the settings file:
   - Open `Preferences → Package Settings → ArsanAI → Settings`
   - Add your API key and endpoint configuration

3. Restart Sublime Text

## Configuration

### API Setup

Edit `arsan_ai.sublime-settings` to configure your AI provider:

#### OpenAI
```json
"api": {
    "api_provider": "openai",
    "api_base": "https://api.openai.com/v1/chat/completions",
    "api_key": "sk-your-key-here",
    "model": "gpt-4-turbo-preview"
}
```

#### Anthropic
```json
"api": {
    "api_provider": "anthropic",
    "api_base": "https://api.anthropic.com/v1/messages",
    "api_key": "your-anthropic-key",
    "model": "claude-3-opus-20240229"
}
```

#### Custom Endpoint
```json
"api": {
    "api_provider": "custom",
    "api_base": "http://localhost:8000/v1/chat/completions",
    "api_key": "optional-key",
    "model": "local-model"
}
```

### Model Context Protocol (MCP)

Configure MCP servers for tool execution:

```json
"mcp_servers": [
    {
        "name": "filesystem",
        "command": "python",
        "args": ["-m", "mcp.servers.filesystem"],
        "env": {}
    }
]
```

## Usage

### Opening the Chat Hub

1. Open the Command Palette: `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS)
2. Search for "ArsanAI: Open Chat Hub"
3. The chat interface will open in a split-screen layout

### Sending Messages

- Type your message in the chat panel
- Press `Ctrl+Enter` (Windows/Linux) or `Cmd+Enter` (macOS) to send
- The AI will stream its response directly into the chat

### Stopping Generation

- Press `Ctrl+C` or use Command Palette → "ArsanAI: Stop Generation"
- The current generation will abort immediately

### Using Completions

1. Select code you want to complete
2. Use Command Palette → "ArsanAI: Request Completion"
3. The AI will suggest completions that you can accept

### Creating Blueprints

1. Use Command Palette → "ArsanAI: Create Blueprint"
2. Enter a name and description
3. A markdown blueprint file will be created in `.arsan/` directory

### Chat History

- Use Command Palette → "ArsanAI: Open Chat History"
- Select a previous conversation to continue
- All conversations are persisted locally in Sublime's cache

## Architecture

### Core Modules

- **`core/api_client.py`** - Asynchronous HTTP streaming client supporting multiple AI providers
- **`core/history_manager.py`** - Thread-safe persistent session and message storage
- **`core/mcp_coordinator.py`** - Multi-server MCP coordinator for sandboxed tool execution
- **`core/workspace_manager.py`** - Dynamic workspace blueprinting and staging

### UI Modules

- **`ui/chat_view.py`** - Split-screen chat interface with streaming support
- **`ui/autocomplete.py`** - Context-aware AI-powered code completions

### Plugin Entry Points

- **`arsan_ai.py`** - Main plugin lifecycle and command routing
- **`Default.sublime-commands`** - Command palette definitions
- **`Context.sublime-menu`** - Right-click context menu integration
- **`arsan_ai.sublime-settings`** - Configuration schema

## Technical Details

### Threading Model

All API communication runs in isolated background threads using Python's `threading` module:

```python
def stream_chat(self, messages, on_token, on_complete, on_error):
    thread = threading.Thread(target=self._stream_worker, ...)
    self.current_thread = thread
    thread.start()
```

The UI thread remains responsive by using `sublime.set_timeout()` for all view updates.

### Streaming Protocol

The plugin parses Server-Sent Events (SSE) character-by-character from streaming API responses:

```python
def parse_chunk(self, chunk):
    self.buffer += chunk
    # Extract complete events and yield them
```

### Thread-Safe Cancellation

Streaming operations can be instantly aborted via an atomic flag:

```python
def abort(self):
    with self.lock:
        self.abort_signal = True
```

The streaming loop checks this flag on every chunk and breaks immediately.

### Context Extraction

Autocomplete captures 50 lines of code context around the cursor, filters comments and boilerplate, and passes it to the AI model.

## Commands

| Command | Description |
|---------|-------------|
| `arsan_ai_open_chat_hub` | Open split-screen chat interface |
| `arsan_ai_close_chat_hub` | Close the chat interface |
| `arsan_ai_stop_generation` | Abort current generation |
| `arsan_ai_select_model` | Switch active AI model |
| `arsan_ai_create_blueprint` | Create workspace blueprint |
| `arsan_ai_open_chat_history` | Load previous conversation |
| `arsan_ai_send_chat_message` | Send message from chat view |
| `arsan_ai_insert_selected_text` | Insert selected code into chat |
| `arsan_ai_request_completion` | Request AI completion |
| `arsan_ai_export_workspace_summary` | Export workspace summary |

## Development

### Project Structure

```
ArsanAI/
├── arsan_ai.py                    # Main plugin entry point
├── Default.sublime-commands       # Command palette definitions
├── Context.sublime-menu           # Context menu definitions
├── arsan_ai.sublime-settings      # Configuration schema
├── core/
│   ├── __init__.py
│   ├── api_client.py              # Streaming API client
│   ├── history_manager.py         # Session persistence
│   ├── mcp_coordinator.py         # MCP integration
│   └── workspace_manager.py       # Workspace blueprinting
└── ui/
    ├── __init__.py
    ├── chat_view.py               # Chat interface
    └── autocomplete.py            # Code completions
```

### Design Principles

1. **Non-blocking UI** - All network and computation work runs in background threads
2. **Explicit Abort** - Streaming operations can be cancelled at any time
3. **Persistent Storage** - Chat history is saved to disk for recovery
4. **Modular Architecture** - Each component is independently testable
5. **Standard Library Only** - Uses only Python stdlib for maximum compatibility

## Troubleshooting

### API Connection Issues

- Verify API key is correctly set in settings
- Check network connectivity
- Ensure API endpoint URL is correct
- Review error messages in the Sublime console (`View → Show Console`)

### Chat Hub Not Opening

- Ensure a workspace/folder is open in Sublime
- Check that no other split layouts are active
- Try closing and reopening the window

### Performance Issues

- Review the debug log: Enable debug mode in settings
- Check number of active MCP servers
- Verify API response times using curl

## Support

For issues, questions, or feature requests, please visit the GitHub repository.

## License

ArsanAI is provided as-is for use with Sublime Text 4.

---

**Developed with ❤️ for the Sublime Text community**

