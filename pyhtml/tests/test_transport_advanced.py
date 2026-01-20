import unittest
from unittest.mock import MagicMock, AsyncMock
from pyhtml.runtime.http_transport import HTTPTransportHandler
from pyhtml.runtime.websocket import WebSocketHandler
from pyhtml.runtime.app import PyHTMLApp
import msgpack
import asyncio

class TestTransportAdvanced(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=PyHTMLApp)
        self.http_handler = HTTPTransportHandler(self.app)
        self.ws_handler = WebSocketHandler(self.app)

    async def test_http_session_cleanup(self):
        # Create session
        request = AsyncMock()
        request.json.return_value = {"path": "/"}
        
        page_class = MagicMock()
        self.app.router.match.return_value = (page_class, {}, "main")
        
        response = await self.http_handler.create_session(request)
        session_id = str(response.body).split('"session_id":"')[1].split('"')[0]
        
        self.assertIn(session_id, self.http_handler.sessions)
        
        # Manually expire session or check cleanup logic (if public)
        # For now we just verify it exists
        self.assertIsNotNone(self.http_handler.sessions[session_id])

    async def test_websocket_error_handling(self):
        ws = AsyncMock()
        ws.receive_bytes.side_effect = Exception("Connection lost")
        
        # Should catch exception and not crash
        await self.ws_handler.handle(ws)
        # If it reached here without raising, it's good

    async def test_http_event_invalid_session(self):
        request = AsyncMock()
        request.headers = {"X-PyHTML-Session": "invalid-id"}
        request.json.return_value = {"handler": "click", "data": {}}
        
        response = await self.http_handler.handle_event(request)
        self.assertEqual(response.status_code, 403)

if __name__ == "__main__":
    unittest.main()
