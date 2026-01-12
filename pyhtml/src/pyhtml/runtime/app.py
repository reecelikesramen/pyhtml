"""Main ASGI application."""
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from pyhtml.runtime.loader import PageLoader
from pyhtml.runtime.router import Router
from pyhtml.runtime.websocket import WebSocketHandler
from pyhtml.runtime.http_transport import HTTPTransportHandler


class PyHTMLApp:
    """Main ASGI application."""

    def __init__(self, pages_dir: Path, reload: bool = False):
        self.reload = reload
        self.pages_dir = Path(pages_dir)
        self.router = Router()
        self.loader = PageLoader()
        self.ws_handler = WebSocketHandler(self)
        self.http_handler = HTTPTransportHandler(self)
        
        # Initialize WebTransport handler
        from pyhtml.runtime.webtransport_handler import WebTransportHandler
        self.web_transport_handler = WebTransportHandler(self)

        # Compile and register all pages
        self._load_pages()

        # Static files
        static_dir = Path(__file__).parent.parent / 'static'
        
        # Create Starlette app with all transport routes
        self.app = Starlette(routes=[
            # Capabilities endpoint for transport negotiation
            Route('/_pyhtml/capabilities', self._handle_capabilities, methods=['GET']),
            # WebSocket transport
            WebSocketRoute('/_pyhtml/ws', self.ws_handler.handle),
            # HTTP transport endpoints
            Route('/_pyhtml/session', self.http_handler.create_session, methods=['POST']),
            Route('/_pyhtml/poll', self.http_handler.poll, methods=['GET']),
            Route('/_pyhtml/event', self.http_handler.handle_event, methods=['POST']),
            # Static files
            Mount('/_pyhtml/static', app=StaticFiles(directory=str(static_dir)), name='static'),
            # Default page handler
            Route('/{path:path}', self._handle_request, methods=['GET', 'POST'])
        ])
    
    async def _handle_capabilities(self, request: Request) -> JSONResponse:
        """Return server transport capabilities for client negotiation."""
        return JSONResponse({
            'transports': ['websocket', 'http'],
            # WebTransport requires HTTP/3 - only available when running with Hypercorn
            'webtransport': False,
            'version': '0.0.1'
        })

    def _load_pages(self):
        """Discover and compile all .pyhtml files."""
        if not self.pages_dir.exists():
            return

        for pyhtml_file in self.pages_dir.rglob('*.pyhtml'):
            try:
                # Compile .pyhtml → PageClass
                page_class = self.loader.load(pyhtml_file)

                # Register routes from !path directive
                if hasattr(page_class, '__routes__'):
                    for name, pattern in page_class.__routes__.items():
                        self.router.add_route(pattern, page_class, name)
                elif hasattr(page_class, '__route__'):
                    # Backward compatibility
                    self.router.add_route(page_class.__route__, page_class, None)
            except Exception as e:
                print(f"Error loading {pyhtml_file}: {e}")
                import traceback
                traceback.print_exc()

    def reload_page(self, path: Path):
        """Reload and recompile a specific page."""
        try:
            print(f"Reloading {path}...")
            # Recompile
            page_class = self.loader.load(path)
            
            # Update router - currently we just append, which is naive but works for MVP
            # Ideally we'd replace existing route
            # For now, let's just add it and since Router iterates list, we might need
            # to make sure new one comes first or remove old one.
            
            # Better approach: Clear routes and reload all? No, too slow.
            # Let's remove old routes for this path if possible, but route doesn't know source file.
            
            # Hack: Just add new route to BEGINNING of list so it matches first
            if hasattr(page_class, '__routes__'):
                for name, pattern in page_class.__routes__.items():
                    # Insert at 0
                    from pyhtml.runtime.router import Route
                    self.router.routes.insert(0, Route(pattern, page_class, name))
            elif hasattr(page_class, '__route__'):
                from pyhtml.runtime.router import Route
                self.router.routes.insert(0, Route(page_class.__route__, page_class, None))
                
            print(f"Reloaded {path}")
        except Exception as e:
            print(f"Error reloading {path}: {e}")
            import traceback
            traceback.print_exc()


    async def _handle_request(self, request: Request) -> Response:
        """Handle HTTP request."""
        path = request.url.path

        # Route matching
        # Route matching
        match = self.router.match(path)
        if not match:
            return Response("404 Not Found", status_code=404)

        page_class, params, variant_name = match

        # Build query params
        query = dict(request.query_params)
        
        # Build path info dict
        path_info = {}
        if hasattr(page_class, '__routes__'):
            for name in page_class.__routes__.keys():
                path_info[name] = (name == variant_name)
        elif hasattr(page_class, '__route__'):
            # Backward compatibility / simple string case
            # If string mode, __routes__ has {'main': ...}
            # But just in case
            path_info['main'] = True
            
        # Build URL helper
        from pyhtml.runtime.router import URLHelper
        url_helper = None
        if hasattr(page_class, '__routes__'):
             url_helper = URLHelper(page_class.__routes__)

        # Instantiate page
        page = page_class(request, params, query, path=path_info, url=url_helper)

        # Check if this is an event request
        if request.method == 'POST' and 'X-PyHTML-Event' in request.headers:
            # Handle event
            try:
                event_data = await request.json()
                response = await page.handle_event(
                    event_data.get('handler', ''),
                    event_data
                )
            except Exception as e:
                return JSONResponse({'error': str(e)}, status_code=500)
        else:
            # Normal render
            response = await page.render()

        # Script injection is now handled by the compiler (generator.py)
        # to ensure it's present in both dev and production.
        
        # Inject WebTransport certificate hash if available (Dev Mode)
        if hasattr(request.app.state, 'webtransport_cert_hash') and isinstance(response, Response) and response.media_type == 'text/html':
             cert_hash = list(request.app.state.webtransport_cert_hash)
             body = response.body.decode('utf-8')
             hash_script = f'<script>window.PYHTML_CERT_HASH = {cert_hash};</script>'
             
             if '</body>' in body:
                 body = body.replace('</body>', hash_script + '</body>')
             else:
                 body += hash_script
                 
             response = Response(body, media_type='text/html')
        
        return response

    async def __call__(self, scope, receive, send):
        """ASGI interface."""
        print(f"DEBUG: Scope type: {scope['type']}")
        if scope['type'] == 'webtransport':
            await self.web_transport_handler.handle(scope, receive, send)
            return
            
        await self.app(scope, receive, send)

    # --- Extensible Hooks ---

    async def on_ws_connect(self, websocket) -> bool:
        """
        Hook called before WebSocket upgrade.
        Return False to reject connection.
        """
        return True

    def get_user(self, request_or_websocket):
        """
        Hook to populate page.user from request/websocket.
        Override to return user from session/JWT.
        """
        if 'user' in request_or_websocket.scope:
            return request_or_websocket.user
        return None
