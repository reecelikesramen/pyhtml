"""WebTransport handler using ASGI standard.

Handles 'webtransport' scope type from Hypercorn.
Provides the same API as WebSocketHandler for seamless transport switching.
"""
import json
import asyncio
import io
import contextlib
import traceback
from dataclasses import dataclass, field
from typing import Dict, Any, Set, Optional, Callable

from pyhtml.runtime.page import BasePage


@dataclass
class WebTransportConnection:
    """Represents an active WebTransport connection."""
    scope: dict
    send: Callable
    receive: Callable
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
        
        # Active streams buffer: stream_id -> bytes
        streams: Dict[int, bytearray] = {}
        
        # 1. Wait for connection request
        try:
            message = await receive()
            print(f"DEBUG: WebTransport received initial message: {message['type']}")
            if message['type'] != 'webtransport.connect':
                print(f"DEBUG: Unexpected message type: {message['type']}")
                return
        except Exception as e:
            print(f"DEBUG: Error receiving connect message: {e}")
            return
            
        # 2. Accept connection
        await send({'type': 'webtransport.accept'})
        print("DEBUG: WebTransport connection accepted")
        
        # Register connection
        connection_id = id(scope)
        connection = WebTransportConnection(
            scope=scope,
            send=send,
            receive=receive
        )
        self.connections[connection_id] = connection
        
        try:
            # Run two tasks concurrently:
            # 1. Process incoming messages
            # 2. Process outbound queue (for server-initiated messages)
            await asyncio.gather(
                self._process_incoming(connection, connection_id, streams),
                self._process_outbound(connection, connection_id),
                return_exceptions=True
            )
        except Exception as e:
            print(f"WebTransport handler error: {e}")
        finally:
            if connection_id in self.connections:
                del self.connections[connection_id]

    async def _process_incoming(self, connection: WebTransportConnection, connection_id: int, streams: Dict[int, bytearray]):
        """Process incoming WebTransport messages."""
        try:
            while True:
                message = await connection.receive()
                msg_type = message['type']
                
                if msg_type == 'webtransport.stream.connect':
                    # New bidirectional stream opened by client
                    stream_id = message['stream_id']
                    streams[stream_id] = bytearray()
                    
                elif msg_type == 'webtransport.stream.receive':
                    stream_id = message['stream_id']
                    data = message.get('data', b'')
                    
                    if stream_id not in streams:
                        streams[stream_id] = bytearray()
                        
                    streams[stream_id].extend(data)
                    
                    # Check if stream is finished
                    more_body = message.get('more_body', False)
                    
                    if not more_body:
                        # Full message received
                        payload = streams[stream_id]
                        del streams[stream_id]
                        
                        # Process message
                        try:
                            json_data = json.loads(payload.decode('utf-8'))
                            await self._handle_message(json_data, connection, connection_id, stream_id)
                        except Exception as e:
                            print(f"WebTransport message error: {e}")
                            traceback.print_exc()
                            
                elif msg_type == 'webtransport.disconnect':
                    break
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"WebTransport incoming error: {e}")

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

    async def _handle_message(self, data: dict, connection: WebTransportConnection, connection_id: int, stream_id: int):
        """Handle decoded JSON message."""
        msg_type = data.get('type')
        
        # Capture stdout for forwarding
        stdout_capture = io.StringIO()
        error_capture = None
        
        try:
            with contextlib.redirect_stdout(stdout_capture):
                if msg_type == 'init':
                    await self._handle_init(data, connection, connection_id, stream_id)
                elif msg_type == 'event':
                    await self._handle_event(data, connection, connection_id, stream_id)
                elif msg_type == 'relocate':
                    await self._handle_relocate(data, connection, connection_id, stream_id)
                else:
                    print(f"Unknown WebTransport message type: {msg_type}")
        except Exception:
            error_capture = traceback.format_exc()
            print(error_capture)
            
        # Send console output
        await self._send_console_message(connection, stream_id, stdout_capture.getvalue(), error_capture)

    async def _handle_init(self, data: dict, connection: WebTransportConnection, connection_id: int, stream_id: int):
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
            await self._send_response(connection, stream_id, {'type': 'error', 'error': 'Route not found'})
            return
            
        page_class, params, variant_name = match
        
        # Build request-like scope
        from starlette.requests import Request
        scope = dict(connection.scope)
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
        await self._send_response(connection, stream_id, {'type': 'update', 'html': html})

    async def _handle_event(self, data: dict, connection: WebTransportConnection, connection_id: int, stream_id: int):
        """Handle client event."""
        if connection.page is None:
            await self._send_response(connection, stream_id, {'type': 'error', 'error': 'Page not initialized'})
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
            
            await self._send_response(connection, stream_id, {'type': 'update', 'html': html})
            print(f"DEBUG EVENT SUCCESS: {handler_name}")
            
        except Exception as e:
            print(f"DEBUG EVENT FAILED: {handler_name} with {e}")
            await self._send_response(connection, stream_id, {'type': 'error', 'error': str(e)})
            raise

    async def _handle_relocate(self, data: dict, connection: WebTransportConnection, connection_id: int, stream_id: int):
        """Handle SPA navigation between sibling paths."""
        path = data.get('path', '/')
        page = connection.page
        
        if not page:
            # No page yet - create one
            await self._handle_init({'path': path}, connection, connection_id, stream_id)
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
            await self._handle_init({'path': path}, connection, connection_id, stream_id)
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
        scope = dict(connection.scope)
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
        await self._send_response(connection, stream_id, {'type': 'update', 'html': html})

    async def _send_response(self, connection: WebTransportConnection, stream_id: int, data: dict):
        """Send response back on the same stream."""
        payload = json.dumps(data).encode('utf-8')
        await connection.send({
            'type': 'webtransport.stream.send',
            'stream_id': stream_id,
            'data': payload,
            'finish': True
        })

    async def _send_server_message(self, connection: WebTransportConnection, data: dict):
        """Send a server-initiated message by creating a new stream."""
        # For server-initiated messages, we need to create a unidirectional stream
        # or use datagrams. Hypercorn's webtransport implementation may vary.
        # Fallback: Try to use the last stream or send via incoming stream response.
        # 
        # Note: The exact ASGI spec for server-initiated streams is experimental.
        # For now, we'll try sending on a pseudo stream or datagram.
        try:
            payload = json.dumps(data).encode('utf-8')
            await connection.send({
                'type': 'webtransport.datagram.send',
                'data': payload
            })
        except Exception as e:
            print(f"Failed to send server message: {e}")

    async def _send_console_message(self, connection: WebTransportConnection, stream_id: int, output: str, error: str = None):
        """Send captured stdout/stderr to client console."""
        try:
            if output:
                lines = output.strip().split('\n')
                if lines:
                    await self._send_response(connection, stream_id, {
                        'type': 'console',
                        'level': 'info',
                        'lines': lines
                    })
            
            if error:
                lines = error.strip().split('\n')
                if lines:
                    await self._send_response(connection, stream_id, {
                        'type': 'console', 
                        'level': 'error',
                        'lines': lines
                    })
        except Exception:
            # If stream is already closed (e.g. by previous response), we can't send console logs.
            pass

    async def broadcast_reload(self):
        """Broadcast reload to all active WebTransport connections."""
        for connection in list(self.connections.values()):
            try:
                await connection.outbound_queue.put({'type': 'reload'})
            except Exception as e:
                print(f"Failed to queue reload for WebTransport connection: {e}")
