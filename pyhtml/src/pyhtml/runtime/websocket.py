"""WebSocket handler for PyHTML."""
import asyncio
from typing import Dict, Any, Set
from starlette.websockets import WebSocket, WebSocketDisconnect

from pyhtml.runtime.page import BasePage


class WebSocketHandler:
    """Handles WebSocket connections for events and hot reload."""

    def __init__(self, app):
        self.app = app
        self.active_connections: Set[WebSocket] = set()
        # Map websocket to page instance
        self.connection_pages: Dict[WebSocket, BasePage] = {}

    async def handle(self, websocket: WebSocket):
        """Handle new WebSocket connection."""
        # Optional: Auth check hook
        if hasattr(self.app, 'on_ws_connect'):
            if not await self.app.on_ws_connect(websocket):
                await websocket.close()
                return

        await websocket.accept()
        self.active_connections.add(websocket)

        try:
            # Create isolated page instance for this connection
            # We need to reconstruct the page based on current URL
            # Note: This simplifies things by assuming initial state.
            # Real session support would hydrate state here.
            
            # Since we don't have the request context easily here yet without 
            # more complex routing, we wait for the first event to associate/create 
            # the page if needed, or we rely on the client to send initial context.
            # For this MVP, we'll instantiate the page when an event arrives.
            
            while True:
                data = await websocket.receive_json()
                await self._process_message(websocket, data)

        except WebSocketDisconnect:
            self.active_connections.remove(websocket)
            if websocket in self.connection_pages:
                del self.connection_pages[websocket]
        except asyncio.CancelledError:
            # Server shutdown, clean disconnect
            self.active_connections.discard(websocket)
            if websocket in self.connection_pages:
                del self.connection_pages[websocket]
            # Don't re-raise, let it exit gracefully
            return
        except Exception as e:
            print(f"WebSocket error: {e}")
            import traceback
            traceback.print_exc()

    async def _process_message(self, websocket: WebSocket, data: Dict[str, Any]):
        """Process incoming message from client."""
        msg_type = data.get('type')

        if msg_type == 'event':
            await self._handle_event(websocket, data)
        else:
            print(f"Unknown message type: {msg_type}")

    async def _handle_event(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle client event."""
        handler_name = data.get('handler')
        path = data.get('path', '/')
        event_data = data.get('data', {})

        # Get or create page instance
        if websocket not in self.connection_pages:
            # Split path into pathname and query string
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(path)
            pathname = parsed_url.path
            query_string = parsed_url.query
            
            # Find page class for path (use pathname only, not query string)
            match = self.app.router.match(pathname)
            if not match:
                print(f"No route found for path: {pathname}")
                return
            
            page_class, params, variant_name = match
            
            # Create minimal request-like object if needed, or update Page 
            # to accept None/minimal context for WS mode
            # For now, we'll pass a mock request or the websocket itself if Page supports it
            from starlette.requests import Request
            
            # Construct a mock request from the websocket scope
            # This is a simplification; ideally Page accepts WebSocket or Request
            scope = websocket.scope
            scope['type'] = 'http' # Hack to satisfy Request init if it checks
            request = Request(scope)
            
            # Extract query params from the path's query string
            if query_string:
                # parse_qs returns lists, we want single values
                parsed = parse_qs(query_string)
                query = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            else:
                query = {}
            
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
            
            page = page_class(request, params, query, path=path_info, url=url_helper)
            
            # Optional: Populate user if hook exists
            if hasattr(self.app, 'get_user'):
                page.user = self.app.get_user(websocket)
                
            self.connection_pages[websocket] = page
            
            # Run load hook
            if hasattr(page, '__on_load'):
                if asyncio.iscoroutinefunction(page.__on_load):
                    await page.__on_load()
                else:
                    page.__on_load()
        else:
            page = self.connection_pages[websocket]

        # Dispatch event
        response = await page.handle_event(handler_name, event_data)

        # Get updated HTML
        # Note: Response object contains bytes, we need string
        # Assuming page.render() returns a Response with .body
        html = response.body.decode('utf-8')

        # Send update
        await websocket.send_json({
            'type': 'update',
            'html': html
        })

    async def broadcast_reload(self):
        """Broadcast reload signal to all clients."""
        if not self.active_connections:
            return
            
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json({'type': 'reload'})
            except Exception:
                disconnected.add(connection)
        
        for conn in disconnected:
            self.active_connections.remove(conn)
            if conn in self.connection_pages:
                del self.connection_pages[conn]
