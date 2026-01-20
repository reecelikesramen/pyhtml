"""WebSocket handler for PyHTML."""
import asyncio
from typing import Dict, Any, Set
from starlette.websockets import WebSocket, WebSocketDisconnect
import msgpack

from pyhtml.runtime.page import BasePage
import io
import contextlib
import traceback


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
                data_bytes = await websocket.receive_bytes()
                data = msgpack.unpackb(data_bytes, raw=False)
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
        elif msg_type == 'relocate':
            await self._handle_relocate(websocket, data)
        else:
            print(f"Unknown message type: {msg_type}")

    async def _send_console_message(self, websocket: WebSocket, output: str, error: str = None):
        """Send captured stdout/stderr/exception to client console."""
        if output:
            lines = output.strip().split('\n')
            if lines:
                await websocket.send_bytes(msgpack.packb({
                    'type': 'console',
                    'level': 'info',
                    'lines': lines
                }))
        
        if error:
            lines = error.strip().split('\n')
            if lines:
                await websocket.send_bytes(msgpack.packb({
                    'type': 'console',
                    'level': 'error',
                    'lines': lines
                }))

    async def _handle_event(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle client event."""
        handler_name = data.get('handler')
        path = data.get('path', '/')
        event_data = data.get('data', {})

        # Capture output for the entire event handling lifecycle
        stdout_capture = io.StringIO()
        error_capture = None

        try:
            with contextlib.redirect_stdout(stdout_capture):
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
                    # Construct a mock request with the correct page path
                    # We copy scope to avoid mutating the actual WebSocket scope
                    scope = dict(websocket.scope)
                    scope['type'] = 'http' 
                    scope['path'] = pathname
                    scope['raw_path'] = pathname.encode('ascii')
                    scope['query_string'] = query_string.encode('ascii') if query_string else b''
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
                    if hasattr(page, 'on_load'):
                        if asyncio.iscoroutinefunction(page.on_load):
                            await page.on_load()
                        else:
                            page.on_load()
                else:
                    page = self.connection_pages[websocket]

                # Define update broadcaster
                async def broadcast_update():
                    # Re-render and send update
                    # Note: We use init=False to avoid re-running init hooks
                    up_response = await page.render(init=False)
                    up_html = up_response.body.decode('utf-8')
                    await websocket.send_bytes(msgpack.packb({
                        'type': 'update',
                        'html': up_html
                    }))

                # Inject update hook
                page._on_update = broadcast_update

                # Call handler
                print(f"DEBUG EVENT: {handler_name} payload={event_data}")
                try:
                    response = await page.handle_event(handler_name, event_data)
                    print(f"DEBUG EVENT SUCCESS: {handler_name}")
                except Exception as e:
                    print(f"DEBUG EVENT FAILED: {handler_name} with {e}")
                    raise e

                # Get updated HTML
                # Note: Response object contains bytes, we need string
                # Assuming page.render() returns a Response with .body
                html = response.body.decode('utf-8')

                # Send update
                await websocket.send_bytes(msgpack.packb({
                    'type': 'update',
                    'html': html
                }))

        except Exception:
            # Capture exception trace
            error_capture = traceback.format_exc()
            # Also print to server console for backup
            print(error_capture)

        # Send any captured output/errors to client
        await self._send_console_message(websocket, stdout_capture.getvalue(), error_capture)

    async def _handle_relocate(self, websocket: WebSocket, data: Dict[str, Any]):
        """Handle SPA navigation between sibling paths.
        
        Updates page.path, page.params, page.query, page.url without reinstantiating.
        Preserves page state across path changes.
        """
        path = data.get('path', '/')
        
        # Get existing page instance
        page = self.connection_pages.get(websocket)
        if not page:
            # No page instance yet - create one for this path
            # This happens when user navigates via SPA link before any @click
            from urllib.parse import urlparse, parse_qs
            from starlette.requests import Request
            from pyhtml.runtime.router import URLHelper
            
            parsed_url = urlparse(path)
            pathname = parsed_url.path
            query_string = parsed_url.query
            
            match = self.app.router.match(pathname)
            if not match:
                print(f"Relocate: No route found for path: {pathname}")
                return
            
            page_class, params, variant_name = match
            
            # Create request with correct path
            scope = dict(websocket.scope)
            scope['type'] = 'http'
            scope['path'] = pathname
            scope['raw_path'] = pathname.encode('ascii')
            scope['query_string'] = query_string.encode('ascii') if query_string else b''
            request = Request(scope)
            
            # Parse query
            if query_string:
                parsed = parse_qs(query_string)
                query = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            else:
                query = {}
            
            # Build path info
            path_info = {}
            if hasattr(page_class, '__routes__'):
                for name in page_class.__routes__.keys():
                    path_info[name] = (name == variant_name)
            
            # Build URL helper
            url_helper = None
            if hasattr(page_class, '__routes__'):
                url_helper = URLHelper(page_class.__routes__)
            
            # Create page instance
            page = page_class(request, params, query, path=path_info, url=url_helper)
            
            # Populate user if hook exists
            if hasattr(self.app, 'get_user'):
                page.user = self.app.get_user(websocket)
            
            self.connection_pages[websocket] = page
            
            # Run on_load lifecycle hook
            if hasattr(page, 'on_load'):
                if asyncio.iscoroutinefunction(page.on_load):
                    await page.on_load()
                else:
                    page.on_load()
            
            # Render and send initial HTML
            response = await page.render()
            html = response.body.decode('utf-8')
            await websocket.send_bytes(msgpack.packb({
                'type': 'update',
                'html': html
            }))
            return
        
        # Parse new URL
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(path)
        pathname = parsed_url.path
        query_string = parsed_url.query
        
        # Match route to get new params and variant
        match = self.app.router.match(pathname)
        if not match:
            print(f"Relocate: No route found for path: {pathname}")
            return
        
        page_class, params, variant_name = match
        
        # Always re-instantiate the page on navigation to ensure __init__ runs
        # with new params/query. This ensures state like self.id (unpacked from params)
        # is correct for the new route.
        # Note: We intentionally discard the old page instance and its state.
        
        # Verify route match (sanity check)
        if hasattr(page_class, '__routes__'):
             pass # Route logic handled by match result

        print(f"Relocate: Loading page {page_class.__name__} for {pathname}")
        
        # Create request object
        from starlette.requests import Request
        scope = dict(websocket.scope)
        scope['type'] = 'http'
        scope['path'] = pathname
        scope['raw_path'] = pathname.encode('ascii')
        scope['query_string'] = query_string.encode('ascii') if query_string else b''
        request = Request(scope)
        
        # Parse query
        if query_string:
            parsed = parse_qs(query_string)
            query = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        else:
            query = {}

        # Build path info
        path_info = {}
        if hasattr(page_class, '__routes__'):
            for name in page_class.__routes__.keys():
                path_info[name] = (name == variant_name)
        
        # Build URL helper
        from pyhtml.runtime.router import URLHelper
        url_helper = None
        if hasattr(page_class, '__routes__'):
                url_helper = URLHelper(page_class.__routes__)

        # Instantiate new page
        new_page = page_class(request, params, query, path=path_info, url=url_helper)
        
        # Migrate persistent user state if needed (e.g. auth user)
        # We don't copy component state because this is a navigation
        new_page.user = getattr(page, 'user', None)
        
        # Replace page instance
        self.connection_pages[websocket] = new_page
        
        # Set update hook
        async def broadcast_update():
                up_response = await new_page.render(init=False)
                up_html = up_response.body.decode('utf-8')
                await websocket.send_bytes(msgpack.packb({
                    'type': 'update',
                    'html': up_html
                }))
        new_page._on_update = broadcast_update

        # Run __on_load lifecycle hook
        stdout_capture = io.StringIO()
        error_capture = None
        
        try:
            with contextlib.redirect_stdout(stdout_capture):
                if hasattr(new_page, 'on_load'):
                    if asyncio.iscoroutinefunction(new_page.on_load):
                        await new_page.on_load()
                    else:
                        new_page.on_load()
                
                # Render and send HTML
                response = await new_page.render()
                html = response.body.decode('utf-8')
                
                await websocket.send_bytes(msgpack.packb({
                    'type': 'update',
                    'html': html
                }))
        except Exception:
            error_capture = traceback.format_exc()
            print(error_capture)
            
        # Send captured output
        await self._send_console_message(websocket, stdout_capture.getvalue(), error_capture)

    async def broadcast_reload(self):
        """Broadcast reload to all clients, preserving state where possible.
        
        For each connection with an existing page instance, attempts to:
        1. Create a new page instance from the updated class
        2. Migrate user state from old instance to new instance
        3. Re-render and send 'update' message
        4. Fall back to hard 'reload' if any step fails
        """
        if not self.active_connections:
            return
            
        disconnected = set()
        for connection in list(self.active_connections):
            try:
                old_page = self.connection_pages.get(connection)
                if old_page:
                    try:
                        # Get the current URL path from the old page's request
                        path = old_page.request.url.path
                        
                        # Find the NEW page class from the router (which was just updated)
                        match = self.app.router.match(path)
                        if not match:
                            raise Exception(f"No route found for {path}")
                        
                        new_page_class, params, variant_name = match
                        
                        # Create new page instance with same context
                        new_page = new_page_class(
                            old_page.request,
                            params,
                            old_page.query,
                            path=old_page.path,
                            url=old_page.url
                        )
                        
                        # Migrate user state: copy all non-framework attributes
                        # Framework attrs to skip
                        skip_attrs = {'request', 'params', 'query', 'path', 'url', 
                                      'user', 'errors', 'loading'}
                        for attr, value in old_page.__dict__.items():
                            if attr not in skip_attrs and not attr.startswith('_'):
                                try:
                                    setattr(new_page, attr, value)
                                except AttributeError:
                                    pass  # Read-only or property, skip
                        
                        # Preserve user
                        new_page.user = old_page.user
                        
                        # Update our reference
                        self.connection_pages[connection] = new_page
                        
                        # Render with new code but preserved state
                        response = await new_page.render()
                        html = response.body.decode('utf-8')
                        await connection.send_bytes(msgpack.packb({
                            'type': 'update',
                            'html': html
                        }))
                        print(f"PyHTML: Hot reload (state preserved) for {type(new_page).__name__}")
                        
                    except Exception as e:
                        # Anything failed, fall back to hard reload
                        print(f"PyHTML: Hot reload failed, falling back to hard reload: {e}")
                        import traceback
                        traceback.print_exc()
                        message_bytes = msgpack.packb({'type': 'reload'})
                        await connection.send_bytes(message_bytes)
                else:
                    # No page instance, do hard reload
                    await connection.send_bytes(msgpack.packb({'type': 'reload'}))
            except Exception:
                disconnected.add(connection)
        
        for conn in disconnected:
            self.active_connections.discard(conn)
            if conn in self.connection_pages:
                del self.connection_pages[conn]

