"""HTTP transport handler for PyHTML fallback."""
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from starlette.requests import Request
from starlette.responses import JSONResponse

from pyhtml.runtime.page import BasePage


@dataclass
class HTTPSession:
    """Represents an HTTP polling session."""
    session_id: str
    path: str
    page: Optional[BasePage] = None
    pending_updates: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_poll: datetime = field(default_factory=datetime.now)
    
    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """Check if session has expired."""
        return datetime.now() - self.last_poll > timedelta(seconds=timeout_seconds)


class HTTPTransportHandler:
    """Handles HTTP long-polling connections for PyHTML fallback transport."""
    
    def __init__(self, app):
        self.app = app
        self.sessions: Dict[str, HTTPSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def start_cleanup_task(self):
        """Start background task to clean up expired sessions."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Periodically clean up expired sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            expired = [
                sid for sid, session in self.sessions.items()
                if session.is_expired()
            ]
            for sid in expired:
                del self.sessions[sid]
            if expired:
                print(f"PyHTML: Cleaned up {len(expired)} expired HTTP sessions")
    
    async def create_session(self, request: Request) -> JSONResponse:
        """Create a new HTTP polling session."""
        try:
            data = await request.json()
            path = data.get('path', '/')
        except Exception:
            path = '/'
        
        session_id = str(uuid.uuid4())
        session = HTTPSession(session_id=session_id, path=path)
        
        # Try to instantiate the page for this session
        match = self.app.router.match(path)
        if match:
            page_class, params, variant_name = match
            query = dict(request.query_params)
            
            # Build path info dict
            path_info = {}
            if hasattr(page_class, '__routes__'):
                for name in page_class.__routes__.keys():
                    path_info[name] = (name == variant_name)
            elif hasattr(page_class, '__route__'):
                path_info['main'] = True
            
            # Build URL helper
            from pyhtml.runtime.router import URLHelper
            url_helper = None
            if hasattr(page_class, '__routes__'):
                 url_helper = URLHelper(page_class.__routes__)

            session.page = page_class(request, params, query, path=path_info, url=url_helper)
            
            if hasattr(self.app, 'get_user'):
                session.page.user = self.app.get_user(request)
        
        self.sessions[session_id] = session
        self.start_cleanup_task()
        
        return JSONResponse({'sessionId': session_id})
    
    async def poll(self, request: Request) -> JSONResponse:
        """Long-poll for updates."""
        session_id = request.query_params.get('session')
        
        if not session_id or session_id not in self.sessions:
            return JSONResponse({'error': 'Session not found'}, status_code=404)
        
        session = self.sessions[session_id]
        session.last_poll = datetime.now()
        
        # Wait for updates with timeout
        timeout = 30  # seconds
        start = datetime.now()
        
        while (datetime.now() - start).seconds < timeout:
            if session.pending_updates:
                updates = session.pending_updates.copy()
                session.pending_updates.clear()
                return JSONResponse(updates)
            
            await asyncio.sleep(0.5)
        
        # Return empty array on timeout (no updates)
        return JSONResponse([])
    
    async def handle_event(self, request: Request) -> JSONResponse:
        """Handle an event from an HTTP client."""
        session_id = request.headers.get('X-PyHTML-Session')
        
        if not session_id or session_id not in self.sessions:
            return JSONResponse({'error': 'Session not found'}, status_code=404)
        
        session = self.sessions[session_id]
        session.last_poll = datetime.now()
        
        try:
            data = await request.json()
            handler_name = data.get('handler')
            event_data = data.get('data', {})
            
            if session.page is None:
                # Recreate page if needed
                match = self.app.router.match(session.path)
                if not match:
                    return JSONResponse({'error': 'Page not found'}, status_code=404)
                
                page_class, params, variant_name = match
                query = dict(request.query_params)
                
                # Build path info dict
                path_info = {}
                if hasattr(page_class, '__routes__'):
                    for name in page_class.__routes__.keys():
                        path_info[name] = (name == variant_name)
                elif hasattr(page_class, '__route__'):
                    path_info['main'] = True
                
                # Build URL helper
                from pyhtml.runtime.router import URLHelper
                url_helper = None
                if hasattr(page_class, '__routes__'):
                     url_helper = URLHelper(page_class.__routes__)
                
                session.page = page_class(request, params, query, path=path_info, url=url_helper)
            
            # Dispatch event
            response = await session.page.handle_event(handler_name, event_data)
            
            # Get updated HTML
            html = response.body.decode('utf-8')
            
            return JSONResponse({
                'type': 'update',
                'html': html
            })
            
        except Exception as e:
            return JSONResponse({'type': 'error', 'error': str(e)}, status_code=500)
    
    def queue_update(self, session_id: str, update: Dict[str, Any]):
        """Queue an update to be sent to a specific session."""
        if session_id in self.sessions:
            self.sessions[session_id].pending_updates.append(update)
    
    def broadcast_reload(self):
        """Queue reload message to all sessions."""
        for session in self.sessions.values():
            session.pending_updates.append({'type': 'reload'})
