import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import msgpack
from pyhtml.runtime.websocket import WebSocketHandler
from pyhtml.runtime.page import BasePage
from starlette.requests import Request

class MockWebSocket:
    def __init__(self, scope=None):
        self.scope = scope or {
            'type': 'websocket', 
            'path': '/',
            'headers': [],
            'query_string': b'',
            'client': ['127.0.0.1', 1234]
        }
        self.sent_messages = []
        self.receive_queue = asyncio.Queue()
        self.closed = False
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive_bytes(self):
        return await self.receive_queue.get()

    async def send_bytes(self, data):
        self.sent_messages.append(msgpack.unpackb(data, raw=False))

    async def close(self, code=1000):
        self.closed = True

class TestPage(BasePage):
    def __init__(self, request, params, query, path=None, url=None):
        super().__init__(request, params, query, path, url)
        self.event_called = False
        self.last_event_data = None

    async def handle_event(self, event_name, event_data):
        self.event_called = True
        self.last_event_data = event_data
        # Return a real Response object
        from starlette.responses import Response
        return Response("<div>Test Page</div>")

    async def _render_template(self):
        return "<div>Test Page</div>"

class TestWebSocketHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = MagicMock()
        self.app.router = MagicMock()
        self.handler = WebSocketHandler(self.app)

    async def test_process_message_event(self):
        ws = MockWebSocket()
        # Mock request object with correct HTTP type
        scope = dict(ws.scope)
        scope['type'] = 'http'
        request = Request(scope=scope)
        page = TestPage(request, {}, {})
        self.handler.connection_pages[ws] = page
        
        data = {
            'type': 'event',
            'handler': 'test_handler',
            'data': {'key': 'value'}
        }
        
        await self.handler._process_message(ws, data)
        
        print(f"\nDEBUG sent_messages: {ws.sent_messages}")
        self.assertTrue(page.event_called)
        self.assertEqual(page.last_event_data, {'key': 'value'})
        
        # We might have captured console output from the print(f"DEBUG EVENT...")
        # so we check if the last message is update
        update_msg = next((m for m in ws.sent_messages if m['type'] == 'update'), None)
        self.assertIsNotNone(update_msg)
        self.assertEqual(update_msg['type'], 'update')

    async def test_handle_relocate(self):
        ws = MockWebSocket()
        
        # Setup router mock
        self.app.router.match.return_value = (TestPage, {'id': '123'}, 'main')
        
        data = {
            'type': 'relocate',
            'path': '/new-path'
        }
        
        await self.handler._handle_relocate(ws, data)
        
        self.assertIn(ws, self.handler.connection_pages)
        page = self.handler.connection_pages[ws]
        self.assertIsInstance(page, TestPage)
        self.assertEqual(page.params, {'id': '123'})
        self.assertEqual(ws.sent_messages[0]['type'], 'update')

    async def test_send_console_message(self):
        ws = MockWebSocket()
        await self.handler._send_console_message(ws, "Hello Stdout", "Hello Stderr")
        
        self.assertEqual(len(ws.sent_messages), 2)
        self.assertEqual(ws.sent_messages[0]['type'], 'console')
        self.assertEqual(ws.sent_messages[0]['level'], 'info')
        self.assertEqual(ws.sent_messages[0]['lines'], ['Hello Stdout'])
        
        self.assertEqual(ws.sent_messages[1]['level'], 'error')
        self.assertEqual(ws.sent_messages[1]['lines'], ['Hello Stderr'])

if __name__ == "__main__":
    unittest.main()
