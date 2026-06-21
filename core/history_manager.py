"""
History Manager module for ArsanAI.
Manages disk-persisted local JSON chat histories and session tracking.
"""

import json
import os
from datetime import datetime
try:
    from typing import Dict, List, Any, Optional
except ImportError:
    class _TypingStub(object):
        def __getitem__(self, _item):
            return self
    _typing_stub = _TypingStub()
    Dict = List = Any = Optional = _typing_stub
import threading


class HistoryManager:
    """
    Manages persistent conversation histories.
    Stores sessions as JSON files in a local cache directory.
    """

    def __init__(self, cache_dir: str):
        """
        Initialize history manager.
        
        Args:
            cache_dir: Directory path for storing conversation histories
        """
        self.cache_dir = cache_dir
        self.sessions_index = os.path.join(cache_dir, 'sessions.json')
        self.sessions_dir = os.path.join(cache_dir, 'sessions')
        self.lock = threading.Lock()
        
        os.makedirs(self.sessions_dir, exist_ok=True)
        self._ensure_index_exists()

    def _ensure_index_exists(self) -> None:
        """Ensure the sessions index file exists."""
        if not os.path.exists(self.sessions_index):
            with open(self.sessions_index, 'w') as f:
                json.dump({'sessions': []}, f)

    def create_session(
        self,
        title: str,
        model: str,
        initial_messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Create a new conversation session.
        
        Args:
            title: Session title
            model: Model used in this session
            initial_messages: Optional initial messages
            
        Returns:
            Session ID (UUID-like string)
        """
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        
        session = {
            'id': session_id,
            'title': title,
            'model': model,
            'created_at': datetime.now().isoformat(),
            'messages': initial_messages or [],
            'token_count': 0,
        }
        
        with self.lock:
            session_file = os.path.join(self.sessions_dir, '{}.json'.format(session_id))
            with open(session_file, 'w') as f:
                json.dump(session, f, indent=2)
            
            self._add_to_index(session_id, title)
        
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str],
        token_count: int = 0,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """
        Add a message to a session.
        
        Args:
            session_id: Session ID
            role: Message role ('user', 'assistant', or 'tool')
            content: Message content
            token_count: Number of tokens in this message
            tool_calls: Optional list of tool calls for assistant message
            tool_call_id: Optional ID of the tool call this response is for
            name: Optional name of the tool this response is for
        """
        with self.lock:
            session_file = os.path.join(self.sessions_dir, '{}.json'.format(session_id))
            
            if not os.path.exists(session_file):
                return
            
            with open(session_file, 'r') as f:
                session = json.load(f)
            
            msg = {
                'role': role,
                'timestamp': datetime.now().isoformat(),
            }
            if content is not None:
                msg['content'] = content
            if tool_calls is not None:
                msg['tool_calls'] = tool_calls
            if tool_call_id is not None:
                msg['tool_call_id'] = tool_call_id
            if name is not None:
                msg['name'] = name
                
            session['messages'].append(msg)
            session['token_count'] += token_count
            
            with open(session_file, 'w') as f:
                json.dump(session, f, indent=2)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session dict or None if not found
        """
        with self.lock:
            session_file = os.path.join(self.sessions_dir, '{}.json'.format(session_id))
            
            if not os.path.exists(session_file):
                return None
            
            try:
                with open(session_file, 'r') as f:
                    return json.load(f)
            except (ValueError, IOError):
                return None

    def list_sessions(self, limit: int = 50) -> List[Dict[str, str]]:
        """
        List all sessions in reverse chronological order.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of session metadata dicts
        """
        with self.lock:
            try:
                with open(self.sessions_index, 'r') as f:
                    index = json.load(f)
                
                sessions = index.get('sessions', [])
                return sessions[-limit:][::-1]
            
            except (ValueError, IOError):
                return []

    def delete_session(self, session_id: str) -> None:
        """
        Delete a session.
        
        Args:
            session_id: Session ID
        """
        with self.lock:
            session_file = os.path.join(self.sessions_dir, '{}.json'.format(session_id))
            if os.path.exists(session_file):
                os.remove(session_file)
            
            self._remove_from_index(session_id)

    def _add_to_index(self, session_id: str, title: str) -> None:
        """Add session to index."""
        try:
            with open(self.sessions_index, 'r') as f:
                index = json.load(f)
        except (ValueError, IOError):
            index = {'sessions': []}
        
        index['sessions'].append({
            'id': session_id,
            'title': title,
            'created_at': datetime.now().isoformat(),
        })
        
        with open(self.sessions_index, 'w') as f:
            json.dump(index, f, indent=2)

    def _remove_from_index(self, session_id: str) -> None:
        """Remove session from index."""
        try:
            with open(self.sessions_index, 'r') as f:
                index = json.load(f)
        except (ValueError, IOError):
            return
        
        index['sessions'] = [
            s for s in index['sessions']
            if s['id'] != session_id
        ]
        
        with open(self.sessions_index, 'w') as f:
            json.dump(index, f, indent=2)

    def get_session_messages(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get all messages from a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of message dicts
        """
        session = self.get_session(session_id)
        return session['messages'] if session else []

    def update_session_title(self, session_id: str, new_title: str) -> None:
        """
        Update a session's title.
        
        Args:
            session_id: Session ID
            new_title: New title
        """
        with self.lock:
            session_file = os.path.join(self.sessions_dir, '{}.json'.format(session_id))
            
            if not os.path.exists(session_file):
                return
            
            with open(session_file, 'r') as f:
                session = json.load(f)
            
            session['title'] = new_title
            
            with open(session_file, 'w') as f:
                json.dump(session, f, indent=2)
            
            # Update index
            try:
                with open(self.sessions_index, 'r') as f:
                    index = json.load(f)
            except (ValueError, IOError):
                return
            
            for s in index['sessions']:
                if s['id'] == session_id:
                    s['title'] = new_title
                    break
            
            with open(self.sessions_index, 'w') as f:
                json.dump(index, f, indent=2)
