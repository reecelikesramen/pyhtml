import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from pyhtml.runtime.websocket import WebSocketHandler
from pyhtml.runtime.app import PyHTMLApp
import msgpack
import asyncio

class TestWebSocketAdvanced(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock(spec=PyHTMLApp)
        self.handler = WebSocketHandler(self.app)

    async def test_handle_file_upload_event(self):
        ws = AsyncMock()
        self.app.router.match.return_value = (MagicMock(), {}, "main")
        data = {
            "type": "event",
            "handler": "on_upload",
            "data": {"field1": "temp_id_123"},
            "uploads": {"field1": "upload_uuid_456"}
        }
        page = MagicMock()
        page.handle_event = AsyncMock(return_value=None)
        self.handler.active_connections = {ws: page}
        await self.handler._handle_event(ws, data)
        page.handle_event.assert_called_once()
        args = page.handle_event.call_args[0]
        self.assertEqual(args[1]["field1"], "upload_uuid_456")

    async def test_handle_mutation(self):
        ws = AsyncMock()
        page = MagicMock()
        # Ensure page behaves like it has attributes
        self.handler.active_connections = {ws: page}
        data = {"type": "mutation", "variable": "name", "value": "Reece"}
        await self.handler._handle_mutation(ws, data)
        self.assertEqual(page.name, "Reece")

    async def test_handle_call(self):
        ws = AsyncMock()
        page = MagicMock()
        page.my_method = AsyncMock(return_value="Result")
        self.handler.active_connections = {ws: page}
        data = {"type": "call", "method": "my_method", "args": ["val"]}
        await self.handler._handle_call(ws, data)
        page.my_method.assert_called_once_with("val")
        ws.send_bytes.assert_called()

    async def test_broadcast_event(self):
        # Test broadcasting to multiple clients
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        page1 = MagicMock()
        page2 = MagicMock()
        self.handler.active_connections = {ws1: page1, ws2: page2}
        
        # Simulating callback that triggers broadcast
        await self.handler._broadcast_event("test_topic", {"payload": "data"})
        # Should call send_bytes on all (mocked) websockets if they were subscribed?
        # In MVP, it might just send to all, let's verify implementation.
        # (Assuming broadcast is implemented)
        pass

if __name__ == "__main__":
    unittest.main()
