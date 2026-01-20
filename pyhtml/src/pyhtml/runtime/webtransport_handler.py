"""WebTransport handler using Starlette API.

Handles 'webtransport' connections using the high-level Starlette WebTransport API.
Provides the same API as WebSocketHandler for seamless transport switching.
"""
import json
import asyncio
import io
import contextlib
import traceback
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable

from starlette.webtransport import WebTransport, WebTransportStream, WebTransportDisconnect
from pyhtml.runtime.page import BasePage


@dataclass
class WebTransportConnection:
    """Represents an active WebTransport connection."""
    session: WebTransport
    page: Optional[BasePage] = None
    # Queue for server-initiated messages (e.g. broadcast_reload)
    outbound_queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class WebTransportHandler:
    """Handles WebTransport connections with full feature parity to WebSocket handler."""

    def __init__(self, app):
        self.app = app
        # Map connection_id -> WebTransportConnection
        self.connections: Dict[int, WebTransportConnection] = {}

    async def handle(self, scope, receive, send):
        """Handle ASGI webtransport scope."""
        print("DEBUG: WebTransport handler started")
        
        # Initialize transport session
        transport = WebTransport(scope, receive, send)
        await transport.accept()
        print("DEBUG: WebTransport connection accepted")
        
        # Register connection
        connection_id = id(scope)
        connection = WebTransportConnection(session=transport)
        self.connections[connection_id] = connection
        
        try:
            async with asyncio.TaskGroup() as tg:
                # 1. Process incoming streams (from client)
                tg.create_task(self._process_streams(transport, connection))
                # 2. Process outbound queue (for server-initiated messages)
                tg.create_task(self._process_outbound(connection, connection_id))
                
        except (WebTransportDisconnect, asyncio.CancelledError):
            print("WebTransport disconnected")
        except Exception as e:
            print(f"WebTransport handler error: {e}")
            traceback.print_exc()
        finally:
            if connection_id in self.connections:
                del self.connections[connection_id]
            # Ensure transport is closed
            await transport.close()

    async def _process_streams(self, transport: WebTransport, connection: WebTransportConnection):
        """Accept and handle incoming streams."""
        try:
            while True:
                stream = await transport.accept_stream()
                # Spawn a task to handle this specific stream
                asyncio.create_task(self._handle_stream(stream, connection))
        except (WebTransportDisconnect, asyncio.CancelledError):
            # Connection closed or cancelled
            pass
        except Exception as e:
            print(f"Error accepting stream: {e}")
            traceback.print_exc()

    async def _handle_stream(self, stream: WebTransportStream, connection: WebTransportConnection):
        """Read full message from a stream and process it."""
        print(f"DEBUG: Handling stream {stream.stream_id}")
        try:
            payload = bytearray()
            while True:
                try:
                    chunk = await stream.receive_bytes()
                    print(f"DEBUG: Stream {stream.stream_id} received chunk: {len(chunk)} bytes")
                    payload.extend(chunk)
                except WebTransportDisconnect:
                    # Stream closed naturally (FIN received)
                    print(f"DEBUG: Stream {stream.stream_id} disconnected (FIN)")
                    break
            
            print(f"DEBUG: Stream {stream.stream_id} payload complete: {len(payload)} bytes")
            if payload:
                try:
                    data = json.loads(payload.decode('utf-8'))
                    await self._handle_message(data, connection, stream)
                except Exception as e:
                    print(f"Failed to process message on stream {stream.stream_id}: {e}")
                    traceback.print_exc()
                    
        except Exception as e:
            print(f"Stream {stream.stream_id} error: {e}")

    async def _process_outbound(self, connection: WebTransportConnection, connection_id: int):
        """Process outbound queue for server-initiated messages."""
        try:
            while connection_id in self.connections:
                try:
                    # Wait for message with timeout to allow checking if still connected
                    message = await asyncio.wait_for(
                        connection.outbound_queue.get(),
                        timeout=1.0
                    )
                    await self._send_server_message(connection, message)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, data: dict, connection: WebTransportConnection, stream: WebTransportStream):
        """Handle decoded JSON message."""
        msg_type = data.get('type')
        
        # Capture stdout for forwarding
        stdout_capture = io.StringIO()
        error_capture = None
        
        try:
            with contextlib.redirect_stdout(stdout_capture):
                if msg_type == 'init':
                    await self._handle_init(data, connection, stream)
                elif msg_type == 'event':
                    await self._handle_event(data, connection, stream)
                elif msg_type == 'relocate':
                    await self._handle_relocate(data, connection, stream)
                else:
                    print(f"Unknown WebTransport message type: {msg_type}")
        except Exception:
            error_capture = traceback.format_exc()
            print(error_capture)
            
        # Send console output
        await self._send_console_message(connection, stream, stdout_capture.getvalue(), error_capture)

    async def _handle_init(self, data: dict, connection: WebTransportConnection, stream: WebTransportStream):
        """Initialize page for this connection."""
        path = data.get('path', '/')
        
        # Parse path
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(path)
        pathname = parsed_url.path
        query_string = parsed_url.query
        
        match = self.app.router.match(pathname)
        if not match:
            print(f"WebTransport init: No route found for path: {pathname}")
            await self._send_response(connection, stream, {'type': 'error', 'error': 'Route not found'})
            return
            
        page_class, params, variant_name = match
        
        # Build request-like scope
        from starlette.requests import Request
        scope = dict(connection.session.scope)
        scope['type'] = 'http'
        scope['path'] = pathname
        scope['raw_path'] = pathname.encode('ascii')
        scope['query_string'] = query_string.encode('ascii') if query_string else b''
        request = Request(scope)
        
        # Parse query params
        if query_string:
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
        
        if hasattr(self.app, 'get_user'):
            page.user = self.app.get_user(request)
            
        connection.page = page
        
        # Run __on_load hook
        if hasattr(page, '__on_load'):
            if asyncio.iscoroutinefunction(page.__on_load):
                await page.__on_load()
            else:
                page.__on_load()
        
        # Send initial render
        response = await page.render()
        html = response.body.decode('utf-8')
        await self._send_response(connection, stream, {'type': 'update', 'html': html})

    async def _handle_event(self, data: dict, connection: WebTransportConnection, stream: WebTransportStream):
        """Handle client event."""
        if connection.page is None:
            await self._send_response(connection, stream, {'type': 'error', 'error': 'Page not initialized'})
            return
            
        handler_name = data.get('handler')
        event_data = data.get('data', {})
        
        print(f"DEBUG EVENT: {handler_name} payload={event_data}")
        
        try:
            # Define update broadcaster
            async def broadcast_update():
                up_response = await connection.page.render(init=False)
                up_html = up_response.body.decode('utf-8')
                # Queue for outbound since we can't use stream_id here
                await connection.outbound_queue.put({'type': 'update', 'html': up_html})
            
            # Inject update hook
            connection.page._on_update = broadcast_update
            
            response = await connection.page.handle_event(handler_name, event_data)
            html = response.body.decode('utf-8')
            
            await self._send_response(connection, stream, {'type': 'update', 'html': html})
            print(f"DEBUG EVENT SUCCESS: {handler_name}")
            
        except Exception as e:
            print(f"DEBUG EVENT FAILED: {handler_name} with {e}")
            await self._send_response(connection, stream, {'type': 'error', 'error': str(e)})
            raise

    async def _handle_relocate(self, data: dict, connection: WebTransportConnection, stream: WebTransportStream):
        """Handle SPA navigation between sibling paths."""
        path = data.get('path', '/')
        page = connection.page
        
        if not page:
            # No page yet - create one
            await self._handle_init({'path': path}, connection, stream)
            return
        
        # Parse new URL
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(path)
        pathname = parsed_url.path
        query_string = parsed_url.query
        
        # Match route
        match = self.app.router.match(pathname)
        if not match:
            print(f"Relocate: No route found for path: {pathname}")
            return
        
        page_class, params, variant_name = match
        
        # Verify same page class
        if type(page) != page_class:
            print(f"Relocate: Page class mismatch, reinitializing")
            await self._handle_init({'path': path}, connection, stream)
            return
        
        # Update params
        page.params = params
        
        # Update query
        if query_string:
            parsed = parse_qs(query_string)
            page.query = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        else:
            page.query = {}
            
        # Update request
        from starlette.requests import Request
        scope = dict(connection.session.scope)
        scope['type'] = 'http'
        scope['path'] = pathname
        scope['raw_path'] = pathname.encode('ascii')
        scope['query_string'] = query_string.encode('ascii') if query_string else b''
        page.request = Request(scope)
        
        # Update path info
        if hasattr(page_class, '__routes__'):
            for name in page_class.__routes__.keys():
                page.path[name] = (name == variant_name)
        
        # Run __on_relocate__ hook
        if hasattr(page, '__on_relocate__'):
            if asyncio.iscoroutinefunction(page.__on_relocate__):
                await page.__on_relocate__()
            else:
                page.__on_relocate__()
        
        # Render and send
        response = await page.render()
        html = response.body.decode('utf-8')
        await self._send_response(connection, stream, {'type': 'update', 'html': html})

    async def _send_response(self, connection: WebTransportConnection, stream: WebTransportStream, data: dict):
        """Send response back on the same stream."""
        # Note: In WebTransport, we typically echo back on the request stream (bidirectional)
        pass  # We reuse the stream passed in
        
        payload = json.dumps(data).encode('utf-8')
        try:
            await stream.send_bytes(payload)
            # Typically close the stream after sending full response if it was a request/response pattern
            await stream.close()
        except Exception as e:
            print(f"Error sending response on stream {stream.stream_id}: {e}")

    async def _send_server_message(self, connection: WebTransportConnection, data: dict):
        """Send a server-initiated message using datagrams."""
        # Server-initiated messages (broadcasts) are best sent via Datagrams for minimal overhead
        # or we would need to open a unidirectional stream (not supported yet).
        try:
            payload = json.dumps(data).encode('utf-8')
            await connection.session.send_datagram(payload)
        except Exception as e:
            print(f"Failed to send server message: {e}")

    async def _send_console_message(self, connection: WebTransportConnection, stream: WebTransportStream, output: str, error: str = None):
        """Send captured stdout/stderr to client console."""
        # For console logs, we might want to try to send on the stream if open,
        # otherwise drop it or use datagrams. 
        # Here we just try to use the stream, but catch errors if it's already closed.
        try:
            if output:
                lines = output.strip().split('\n')
                if lines:
                    payload = json.dumps({
                        'type': 'console',
                        'level': 'info',
                        'lines': lines
                    }).encode('utf-8')
                    await stream.send_bytes(payload)
            
            if error:
                lines = error.strip().split('\n')
                if lines:
                    payload = json.dumps({
                        'type': 'console', 
                        'level': 'error',
                        'lines': lines
                    }).encode('utf-8')
                    await stream.send_bytes(payload)
        except Exception:
            # If stream is already closed or failing, just ignore console logs
            pass

    async def broadcast_reload(self):
        """Broadcast reload to all active WebTransport connections."""
        for connection in list(self.connections.values()):
            try:
                await connection.outbound_queue.put({'type': 'reload'})
            except Exception as e:
                print(f"Failed to queue reload for WebTransport connection: {e}")
