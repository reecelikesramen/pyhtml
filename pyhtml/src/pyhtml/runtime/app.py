"""Main ASGI application."""
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from starlette.staticfiles import StaticFiles
import traceback
import re

from pyhtml.runtime.loader import PageLoader
from pyhtml.runtime.router import Router
from pyhtml.runtime.websocket import WebSocketHandler
from pyhtml.runtime.http_transport import HTTPTransportHandler
from pyhtml.runtime.http_transport import HTTPTransportHandler
from pyhtml.runtime.error_page import ErrorPage
from pyhtml.runtime.upload_manager import upload_manager


class PyHTMLApp:
    """Main ASGI application."""

    def __init__(self, pages_dir: Path, reload: bool = False):
        self.reload = reload
        self.pages_dir = Path(pages_dir)
        self.router = Router()
        
        from pyhtml.runtime.loader import get_loader
        self.loader = get_loader()
        
        self.ws_handler = WebSocketHandler(self)
        self.http_handler = HTTPTransportHandler(self)
        
        # Initialize WebTransport handler
        from pyhtml.runtime.webtransport_handler import WebTransportHandler
        self.web_transport_handler = WebTransportHandler(self)
        
        # Valid upload tokens
        self.upload_tokens = set()

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
            # Upload endpoint
            Route('/_pyhtml/upload', self._handle_upload, methods=['POST']),
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

    async def _handle_upload(self, request: Request) -> JSONResponse:
        """Handle file uploads."""
        print(f"DEBUG: Handling upload request for {request.url}")
        try:
            # Check for upload token
            token = request.headers.get('X-Upload-Token')
            if not token or token not in self.upload_tokens:
                return JSONResponse({'error': 'Invalid or expired upload token'}, status_code=403)

            # Fail-fast: Check Content-Length header
            content_length = request.headers.get('content-length')
            if content_length:
                try:
                    length = int(content_length)
                    # Global safety limit: 10MB (allows for 5MB file + overhead)
                    # Real app might configure this or inspect specific field limits after streaming
                    if length > 10 * 1024 * 1024:
                        print(f"WARN: Upload rejected. Content-Length {length} exceeds 10MB limit.")
                        return JSONResponse({'error': 'Payload Too Large'}, status_code=413)
                except ValueError:
                    pass

            form = await request.form()
            response_data = {}
            for field_name, file in form.items():
                if hasattr(file, 'filename'): # It's an UploadFile
                    # We don't really need the ID if we are just testing upload for now?
                    # Wait, saving returns the ID!
                    upload_id = upload_manager.save(file)
                    response_data[field_name] = upload_id
            
            print(f"DEBUG: Upload successful. Returning: {response_data}")
            return JSONResponse(response_data)
        except Exception as e:
            traceback.print_exc()
            return JSONResponse({'error': str(e)}, status_code=500)

    def _load_pages(self):
        """Discover and compile all .pyhtml files."""
        # Config options (e.g. trailing slash) could be used here
        from pyhtml.config import config
        
        # Scan pages directory
        # We need to sort files to ensure deterministic order but scanning is recursive
        self._scan_directory(self.pages_dir)

    def _scan_directory(self, dir_path: Path, layout_path: Optional[str] = None, url_prefix: str = ""):
        """Recursively scan directory for pages and layouts."""
        # 1. Check for layout.pyhtml in this directory
        current_layout = layout_path
        potential_layout = dir_path / "layout.pyhtml"
        if potential_layout.exists():
            # Compile layout first (it might use the parent layout!)
            try:
                # Layouts can inherit from parent layouts too
                self.loader.load(potential_layout, implicit_layout=layout_path)
                current_layout = str(potential_layout.resolve())
            except Exception as e:
                print(f"Failed to load layout {potential_layout}: {e}")
                traceback.print_exc()

        # 2. Iterate identifiers
        # Sort to ensure index processed or consistent order
        try:
            entries = sorted(list(dir_path.iterdir()))
        except FileNotFoundError:
            return

        for entry in entries:
            if entry.name.startswith('_') or entry.name.startswith('.'):
                continue
                
            if entry.is_dir():
                # Determine new prefix
                # Check if it's a param directory [param]
                name = entry.name
                new_segment = name
                
                # Check for [param] syntax
                param_match = re.match(r'^\[(.*?)\]$', name)
                if param_match:
                     param_name = param_match.group(1)
                     # Convert to routing syntax :{name} (or whatever Router supports)
                     # Router supports :name or {name}
                     new_segment = f"{{{param_name}}}"
                
                new_prefix = (url_prefix + "/" + new_segment).replace('//', '/')
                self._scan_directory(entry, current_layout, new_prefix)
                
            elif entry.is_file() and entry.suffix == '.pyhtml':
                if entry.name == 'layout.pyhtml':
                    continue # Already handled
                
                # Determine route path
                name = entry.stem # filename without .pyhtml
                
                route_segment = name
                if name == 'index':
                    route_segment = ""
                else:
                    # Check for [param] in filename
                    param_match = re.match(r'^\[(.*?)\]$', name)
                    if param_match:
                         param_name = param_match.group(1)
                         route_segment = f"{{{param_name}}}"
                
                route_path = (url_prefix + "/" + route_segment).replace('//', '/')
                
                # Strip trailing slash for index pages (unless root)
                if route_path != "/" and route_path.endswith('/'):
                    route_path = route_path.rstrip('/')
                
                if not route_path:
                    route_path = "/"
                
                try:
                    # Load page with implicit layout
                    page_class = self.loader.load(entry, implicit_layout=current_layout)
                    
                    # Register routes
                    # 1. explicit !path overrides implicit routing?
                    # Generally yes. If !path exists, we might add those IN ADDITION or INSTEAD.
                    # Current logic in add_page inspects __routes__ (from !path).
                    # If present, use that. If not, use implicit route_path.
                    
                    if hasattr(page_class, '__routes__') and page_class.__routes__:
                         # User specified explicit paths
                         self.router.add_page(page_class)
                    elif hasattr(page_class, '__route__') and page_class.__route__:
                         # Should not happen as __route__ is derived from __routes__ usually
                         self.router.add_page(page_class)
                    else:
                         # No explicit !path, use file-based route
                         self.router.add_route(route_path, page_class)
                         
                except Exception as e:
                    print(f"Failed to load page {entry}: {e}")
                    traceback.print_exc()
                    self._register_error_page(entry, e)

    def _register_error_page(self, file_path: Path, error: Exception):
        """Register an error page for a failed file."""
        # Try to infer route from file path/content
        # 1. Start with path relative to pages_dir
        try:
            rel_path = file_path.relative_to(self.pages_dir)
            
            # Basic route inference from path
            route_path = "/" + str(rel_path.with_suffix('')).replace('index', '').strip('/')
            if not route_path:
                route_path = "/"
            
            # Also try to regex extract !path directives from file content
            # to handle custom routes properly even if compilation fails
            try:
                content = file_path.read_text()
                # Look for !path "..." or !path '...'
                # This is a simple regex, might need refinement
                path_directives = re.findall(r'!path\s+[\'"]([^\'"]+)[\'"]', content)
                
                routes_to_register = []
                if path_directives:
                    routes_to_register = path_directives
                else:
                    routes_to_register = [route_path]
                
                error_detail = "".join(traceback.format_exception(type(error), error, error.__traceback__))
                
                for route in routes_to_register:
                    # Create a closure helper to generate ErrorPage instance
                    # We can't pass the class directly because Routes expect a BasePage subclass
                    # So we define a new class dynamically that inherits from ErrorPage
                    # but has the specific error info baked in
                    
                    class BoundErrorPage(ErrorPage):
                        def __init__(self, request: Request, *args, **kwargs):
                            super().__init__(request, "Compilation Error", error_detail)

                    self.router.add_route(route, BoundErrorPage)
                    
            except Exception:
                # Fallback to basic path if regex fails
                 pass

        except Exception as e:
            print(f"Failed to register error page for {file_path}: {e}")

    def reload_page(self, path: Path):
        """Reload and recompile a specific page."""
        # Invalidate cache for this file (could be page or layout)
        self.loader.invalidate_cache(path)
        try:
            # Recompile
            new_page_class = self.loader.load(path)
            
            # Update router
            # Note: This is tricky because we need to replace the old route
            # For now, simplistic approach: add it again (router generally uses latest)
            # Better approach: remove old routes for this file first?
            # Implementation detail of router.add_page needed.
            
            # Ideally we clear routes associated with this file_path first
            self.router.remove_routes_for_file(str(path))
            self.router.add_page(new_page_class)
            
            print(f"Reloaded page: {path}")
            return True
        except Exception as e:
            print(f"Failed to reload page {path}: {e}")
            traceback.print_exc()
            
            # Register error page for this file so user sees the error on refresh
            self.router.remove_routes_for_file(str(path))
            self._register_error_page(path, e)
            
            # If we have a websocket connection on this page, we should push the error?!
            # The watcher in dev_server.py catches this exception.
            # We should probably re-raise or handle it there to broadcast 'reload' 
            # so the client reloads and sees the error page.
            
            # Re-raise so dev_server knows it failed
            raise e

    async def _handle_request(self, request: Request) -> Response:
        """Handle HTTP request."""
        # ... (simplified context)
        path = request.url.path
        match = self.router.match(path)
        if not match:
             return Response("404 Not Found", status_code=404)
        
        page_class, params, variant_name = match
        # ... (params, query, path_info, url_helper construction)
        # Build query params
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
        if isinstance(response, Response) and response.media_type == 'text/html':
             body = response.body.decode('utf-8')
             injections = []
             
             # WebTransport Hash
             if hasattr(request.app.state, 'webtransport_cert_hash'):
                 cert_hash = list(request.app.state.webtransport_cert_hash)
                 injections.append(f'<script>window.PYHTML_CERT_HASH = {cert_hash};</script>')
                 
             # Upload Token Injection
             if getattr(page, '__has_uploads__', False):
                 import secrets
                 token = secrets.token_urlsafe(32)
                 self.upload_tokens.add(token)
                 # Token meta tag
                 injections.append(f'<meta name="pyhtml-upload-token" content="{token}">')
                 
             if injections:
                 injection_str = '\n'.join(injections)
                 if '</body>' in body:
                     body = body.replace('</body>', injection_str + '</body>')
                 else:
                     body += injection_str
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
