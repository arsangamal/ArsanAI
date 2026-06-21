"""
API Client module for ArsanAI.
Handles asynchronous HTTP communication with OpenAI, Anthropic, and custom endpoints.
Manages streaming responses and thread-safe cancellation.
"""

import json
import threading
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Callable, Optional
import traceback


class StreamParser:
    """Parses Server-Sent Events (SSE) from streaming responses."""

    def __init__(self):
        self.buffer = ""

    def parse_chunk(self, chunk: str) -> list[Dict[str, Any]]:
        """
        Parse a chunk of SSE data and return complete events.
        
        Args:
            chunk: Raw string chunk from HTTP response
            
        Returns:
            List of parsed event dictionaries
        """
        self.buffer += chunk
        events = []
        
        while "\n\n" in self.buffer:
            event_str, self.buffer = self.buffer.split("\n\n", 1)
            event_data = self._parse_event(event_str)
            if event_data:
                events.append(event_data)
        
        return events

    def _parse_event(self, event_str: str) -> Optional[Dict[str, Any]]:
        """Parse a single SSE event."""
        lines = event_str.strip().split("\n")
        data = {}
        
        for line in lines:
            if line.startswith("data:"):
                try:
                    json_str = line[5:].strip()
                    if json_str == "[DONE]":
                        return {"type": "done"}
                    data = json.loads(json_str)
                    return data
                except json.JSONDecodeError:
                    continue
        
        return None


class APIClient:
    """
    Asynchronous HTTP client for AI model APIs.
    Supports OpenAI, Anthropic, and custom endpoints with streaming.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize API client.
        
        Args:
            config: Configuration dict with keys:
                - api_base: Base URL for API
                - api_key: API authentication key
                - model: Model identifier
                - api_provider: 'openai', 'anthropic', or 'custom'
        """
        self.config = config
        self.abort_signal = False
        self.current_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def stream_chat(
        self,
        messages: list[Dict[str, str]],
        on_token: Callable[[str], None],
        on_complete: Callable[[str, int], None],
        on_error: Callable[[str], None],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> None:
        """
        Stream a chat completion asynchronously.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            on_token: Callback for each token received
            on_complete: Callback on completion with (full_text, token_count)
            on_error: Callback for errors
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
        """
        with self.lock:
            if self.current_thread and self.current_thread.is_alive():
                return
            
            self.abort_signal = False
            thread = threading.Thread(
                target=self._stream_worker,
                args=(messages, on_token, on_complete, on_error, max_tokens, temperature),
                daemon=True,
            )
            self.current_thread = thread
            thread.start()

    def _stream_worker(
        self,
        messages: list[Dict[str, str]],
        on_token: Callable[[str], None],
        on_complete: Callable[[str, int], None],
        on_error: Callable[[str], None],
        max_tokens: int,
        temperature: float,
    ) -> None:
        """Worker thread for streaming API calls."""
        try:
            payload = self._build_payload(messages, max_tokens, temperature)
            
            headers = self._build_headers()
            
            req_body = json.dumps(payload).encode('utf-8')
            request = urllib.request.Request(
                self.config['api_base'],
                data=req_body,
                headers=headers,
                method='POST'
            )
            
            full_response = ""
            token_count = 0
            parser = StreamParser()
            
            try:
                response = urllib.request.urlopen(request)
                
                while not self.abort_signal:
                    chunk = response.read(1024)
                    if not chunk:
                        break
                    
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    events = parser.parse_chunk(chunk_str)
                    
                    for event in events:
                        if self.abort_signal:
                            break
                        
                        if event.get('type') == 'done':
                            break
                        
                        if self.config['api_provider'] == 'openai':
                            token = self._extract_openai_token(event)
                        elif self.config['api_provider'] == 'anthropic':
                            token = self._extract_anthropic_token(event)
                        else:
                            token = self._extract_custom_token(event)
                        
                        if token:
                            full_response += token
                            token_count += 1
                            on_token(token)
                
                response.close()
                
            except urllib.error.HTTPError as e:
                error_msg = f"HTTP Error {e.code}: {e.reason}"
                on_error(error_msg)
                return
            
            if not self.abort_signal:
                on_complete(full_response, token_count)
        
        except Exception as e:
            error_msg = f"Error during streaming: {str(e)}\n{traceback.format_exc()}"
            on_error(error_msg)

    def _build_payload(
        self,
        messages: list[Dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """Build request payload based on API provider."""
        if self.config['api_provider'] == 'openai':
            return {
                "model": self.config['model'],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
        elif self.config['api_provider'] == 'anthropic':
            return {
                "model": self.config['model'],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
        else:
            return {
                "model": self.config['model'],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers based on API provider."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ArsanAI/1.0",
        }
        
        if self.config['api_provider'] == 'openai':
            api_key = self.config.get('api_key', '')
            headers["Authorization"] = f"******"
        elif self.config['api_provider'] == 'anthropic':
            headers["x-api-key"] = self.config['api_key']
            headers["anthropic-version"] = "2023-06-01"
        else:
            api_key = self.config.get('api_key', '')
            headers["Authorization"] = f"******"
        
        return headers

    def _extract_openai_token(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract token from OpenAI SSE event."""
        try:
            choices = event.get('choices', [])
            if choices:
                delta = choices[0].get('delta', {})
                return delta.get('content', '')
        except (KeyError, IndexError, TypeError):
            pass
        return None

    def _extract_anthropic_token(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract token from Anthropic SSE event."""
        try:
            if event.get('type') == 'content_block_delta':
                delta = event.get('delta', {})
                if delta.get('type') == 'text_delta':
                    return delta.get('text', '')
        except (KeyError, TypeError):
            pass
        return None

    def _extract_custom_token(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract token from custom endpoint (tries common patterns)."""
        try:
            if 'choices' in event:
                choices = event.get('choices', [])
                if choices:
                    delta = choices[0].get('delta', {})
                    return delta.get('content', '')
            elif 'content' in event:
                return event.get('content', '')
            elif 'text' in event:
                return event.get('text', '')
        except (KeyError, IndexError, TypeError):
            pass
        return None

    def abort(self) -> None:
        """Signal the current streaming operation to abort."""
        with self.lock:
            self.abort_signal = True

    def discover_models(self) -> list[Dict[str, str]]:
        """
        Discover available models from the API endpoint.
        
        Returns:
            List of model dicts with 'id' and 'name'
        """
        models = []
        try:
            models_url = self.config['api_base'].replace('/chat/completions', '/models')
            headers = self._build_headers()
            
            request = urllib.request.Request(models_url, headers=headers)
            response = urllib.request.urlopen(request)
            data = json.loads(response.read().decode('utf-8'))
            
            if 'data' in data:
                models = [
                    {
                        'id': model.get('id', model.get('name', '')),
                        'name': model.get('id', model.get('name', '')),
                    }
                    for model in data['data']
                ]
            
            response.close()
        
        except Exception as e:
            pass
        
        return models
