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
try:
    from typing import Dict, Any, Callable, Optional, List
except ImportError:
    class _TypingStub(object):
        def __getitem__(self, _item):
            return self
    _typing_stub = _TypingStub()
    Dict = Any = Callable = Optional = List = _typing_stub
import traceback


class StreamParser:
    """Parses Server-Sent Events (SSE) from streaming responses."""

    def __init__(self):
        self.buffer = ""

    def parse_chunk(self, chunk: str) -> List[Dict[str, Any]]:
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
                except ValueError:
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
        self.current_process = None
        self.current_thread = None  # type: Optional[threading.Thread]
        self.lock = threading.Lock()

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_complete: Callable[[str, int, Optional[List[Dict[str, Any]]]], None],
        on_error: Callable[[str], None],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Stream a chat completion asynchronously.
        
        Args:
            messages: List of message dicts
            on_token: Callback for each token received
            on_complete: Callback on completion with (full_text, token_count, tool_calls)
            on_error: Callback for errors
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            tools: Optional list of tools schemas
        """
        with self.lock:
            if self.current_thread and self.current_thread.is_alive():
                return
            
            self.abort_signal = False
            thread = threading.Thread(
                target=self._stream_worker,
                args=(messages, on_token, on_complete, on_error, max_tokens, temperature, tools),
                daemon=True,
            )
            self.current_thread = thread
            thread.start()

    def _stream_worker(
        self,
        messages: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_complete: Callable[[str, int, Optional[List[Dict[str, Any]]]], None],
        on_error: Callable[[str], None],
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Worker thread for streaming API calls."""
        if self.config.get('api_provider') == 'cli':
            self._stream_worker_cli(messages, on_token, on_complete, on_error, max_tokens, temperature, tools)
            return
            
        try:
            payload = self._build_payload(messages, max_tokens, temperature, tools)
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
            streamed_tool_calls = {} # type: Dict[int, Dict[str, Any]]
            
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
                            self._accumulate_openai_tool_calls(event, streamed_tool_calls)
                        elif self.config['api_provider'] == 'anthropic':
                            token = self._extract_anthropic_token(event)
                        else:
                            token = self._extract_custom_token(event)
                            self._accumulate_openai_tool_calls(event, streamed_tool_calls)
                        
                        if token:
                            full_response += token
                            token_count += 1
                            on_token(token)
                
                response.close()
                
            except urllib.error.HTTPError as e:
                error_msg = "HTTP Error {}: {}".format(e.code, e.reason)
                try:
                    body = e.read().decode('utf-8', errors='ignore')
                    if body:
                        error_msg += "\n" + body
                except Exception:
                    pass
                on_error(error_msg)
                return
            
            if not self.abort_signal:
                tool_calls_list = list(streamed_tool_calls.values()) if streamed_tool_calls else None
                on_complete(full_response, token_count, tool_calls_list)
        
        except Exception as e:
            error_msg = "Error during streaming: {}\n{}".format(str(e), traceback.format_exc())
            on_error(error_msg)

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build request payload based on API provider."""
        # Clean messages
        clean_messages = []
        for msg in messages:
            clean_msg = {"role": msg["role"]}
            if "content" in msg:
                clean_msg["content"] = msg["content"]
            if "tool_calls" in msg:
                clean_msg["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                clean_msg["tool_call_id"] = msg["tool_call_id"]
            if "name" in msg:
                clean_msg["name"] = msg["name"]
            clean_messages.append(clean_msg)

        if self.config['api_provider'] == 'openai':
            payload = {
                "model": self.config['model'],
                "messages": clean_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            return payload
        elif self.config['api_provider'] == 'anthropic':
            return {
                "model": self.config['model'],
                "messages": clean_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
        else:
            payload = {
                "model": self.config['model'],
                "messages": clean_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            return payload

    def _accumulate_openai_tool_calls(self, event: Dict[str, Any], tool_calls: Dict[int, Dict[str, Any]]) -> None:
        """Accumulate streamed tool calls from OpenAI SSE event."""
        try:
            choices = event.get('choices', [])
            if not choices:
                return
            
            delta = choices[0].get('delta', {})
            delta_tool_calls = delta.get('tool_calls', [])
            
            for i, tc in enumerate(delta_tool_calls):
                idx = tc.get('index')
                if idx is None:
                    idx = i
                
                if idx not in tool_calls:
                    tool_calls[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {
                            "name": "",
                            "arguments": ""
                        }
                    }
                
                if tc.get('id'):
                    tool_calls[idx]['id'] = tc['id']
                
                func = tc.get('function', {})
                if func.get('name'):
                    tool_calls[idx]['function']['name'] = func['name']
                if func.get('arguments'):
                    tool_calls[idx]['function']['arguments'] += func['arguments']
        except Exception:
            pass

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers based on API provider."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ArsanAI/1.0",
        }
        
        api_key = self.config.get('api_key', '')
        
        if self.config['api_provider'] == 'openai':
            if api_key:
                # Using actual api_key from user config, not hardcoded
                headers["Authorization"] = "Bearer {}".format(api_key)
        elif self.config['api_provider'] == 'anthropic':
            if api_key:
                headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            # Custom endpoint
            if api_key:
                headers["Authorization"] = "Bearer {}".format(api_key)
        
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
            if self.current_process:
                try:
                    self.current_process.terminate()
                except Exception:
                    pass

    def discover_models(self) -> List[Dict[str, str]]:
        """
        Discover available models from the API endpoint or CLI.
        
        Returns:
            List of model dicts with 'id' and 'name'
        """
        if self.config.get('api_provider') == 'cli':
            models = []
            try:
                import subprocess
                import shlex
                import os
                
                cli_cmd = self.config.get('cli_command', ['arsan-cli', 'chat'])
                if isinstance(cli_cmd, str):
                    cmd_args = shlex.split(cli_cmd)
                else:
                    cmd_args = list(cli_cmd)
                
                if cmd_args and cmd_args[-1] == 'chat':
                    cmd_args[-1] = 'models'
                else:
                    cmd_args.append('models')
                    
                env = os.environ.copy()
                user_env = self.config.get('env', {})
                if isinstance(user_env, dict):
                    for k, v in user_env.items():
                        env[str(k)] = str(v)
                        
                process = subprocess.Popen(
                    cmd_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    env=env
                )
                stdout, stderr = process.communicate(timeout=5)
                
                if process.returncode == 0:
                    for line in stdout.splitlines():
                        line = line.strip()
                        if not line or line.lower().startswith(('usage', 'available', 'models:', 'id', '-', 'name')):
                            continue
                        parts = line.split()
                        if parts:
                            model_id = parts[0].strip(':-*')
                            models.append({
                                'id': model_id,
                                'name': line
                            })
            except Exception:
                pass
            return models

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
        
        except Exception:
            pass
        
        return models

    def _stream_worker_cli(
        self,
        messages: List[Dict[str, Any]],
        on_token: Callable[[str], None],
        on_complete: Callable[[str, int, Optional[List[Dict[str, Any]]]], None],
        on_error: Callable[[str], None],
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Worker thread for streaming via a local CLI process."""
        import subprocess
        import shlex
        import os
        
        try:
            payload = self._build_payload(messages, max_tokens, temperature, tools)
            # Extract last user message as prompt
            prompt_text = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    prompt_text = msg.get("content", "")
                    break
                    
            cli_cmd = self.config.get('cli_command', ['arsan-cli', 'chat'])
            if isinstance(cli_cmd, str):
                cmd_args = shlex.split(cli_cmd)
            else:
                cmd_args = list(cli_cmd)
                
            # Process CLI arguments
            cli_args = self.config.get('cli_args', [])
            processed_args = []
            for arg in cli_args:
                if arg == "{prompt}":
                    processed_args.append(prompt_text)
                else:
                    processed_args.append(arg)
            cmd_args.extend(processed_args)
            
            env = os.environ.copy()
            user_env = self.config.get('env', {})
            if isinstance(user_env, dict):
                for k, v in user_env.items():
                    env[str(k)] = str(v)
                    
            process = subprocess.Popen(
                cmd_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                env=env
            )
            
            with self.lock:
                self.current_process = process
                
            # Write payload to stdin and close it
            try:
                payload_str = json.dumps(payload)
                process.stdin.write(payload_str + "\n")
                process.stdin.close()
            except Exception as e:
                on_error("Failed to write to CLI stdin: {}".format(str(e)))
                return
                
            full_response = ""
            token_count = 0
            streamed_tool_calls = {}
            cli_format = self.config.get('cli_format', 'text')
            
            if cli_format == 'json':
                # Read line-by-line for JSON-separated stream chunks
                for line in iter(process.stdout.readline, ""):
                    if self.abort_signal:
                        break
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        chunk = json.loads(line_str)
                        if "choices" in chunk:
                            token = self._extract_openai_token(chunk)
                            if token:
                                full_response += token
                                token_count += 1
                                on_token(token)
                            self._accumulate_openai_tool_calls(chunk, streamed_tool_calls)
                        else:
                            token = chunk.get("token") or chunk.get("content") or chunk.get("text")
                            if token:
                                full_response += token
                                token_count += 1
                                on_token(token)
                            self._accumulate_cli_tool_calls(chunk, streamed_tool_calls)
                    except Exception:
                        pass
            else:
                # Read chunk-by-chunk for raw text stream
                while not self.abort_signal:
                    chunk = process.stdout.read(16)
                    if not chunk:
                        break
                    full_response += chunk
                    token_count += len(chunk) // 4 + 1
                    on_token(chunk)
                    
            # Wait for process exit and read error output
            stderr_output = process.stderr.read()
            exit_code = process.wait()
            
            with self.lock:
                self.current_process = None
                
            if exit_code != 0 and not self.abort_signal:
                on_error("CLI process exited with code {}. Stderr: {}".format(exit_code, stderr_output))
                return
                
            if not self.abort_signal:
                tool_calls_list = list(streamed_tool_calls.values()) if streamed_tool_calls else None
                on_complete(full_response, token_count, tool_calls_list)
                
        except Exception as e:
            on_error("CLI integration error: {}\n{}".format(str(e), traceback.format_exc()))
            with self.lock:
                self.current_process = None

    def _accumulate_cli_tool_calls(self, chunk: Dict[str, Any], tool_calls: Dict[str, Dict[str, Any]]) -> None:
        """Accumulate custom CLI format tool calls."""
        try:
            tc_list = chunk.get('tool_calls', [])
            if not isinstance(tc_list, list):
                return
            for tc in tc_list:
                name = tc.get('name') or tc.get('function', {}).get('name')
                if not name:
                    continue
                tc_id = tc.get('id') or name
                if tc_id not in tool_calls:
                    tool_calls[tc_id] = {
                        "id": tc.get('id') or "call_" + name,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": ""
                        }
                    }
                args = tc.get('arguments') or tc.get('function', {}).get('arguments', '')
                if isinstance(args, dict):
                    args = json.dumps(args)
                tool_calls[tc_id]['function']['arguments'] += args
        except Exception:
            pass
